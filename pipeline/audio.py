"""Áudio real da voz -> narration.measured.json (início/fim de cada item e pausas internas).

Fluxo (`python -m pipeline audio ep01`):

  1. LÊ a(s) trilha(s) de voz de `ep0X/audio/` (ver `find_tracks`). WAV é lido com a biblioteca padrão; mp3/m4a/ogg/flac
     passam pelo `ffmpeg`, se existir no PATH (a ElevenLabs entrega mp3).
  2. ANALISA a amplitude: energia por quadro de 10 ms (dB) + taxa de cruzamento de zero. Isso separa FALA (tonal, forte),
     RESPIRAÇÃO (ruidosa, bem mais fraca que a fala) e SILÊNCIO, com limiares relativos ao nível da própria gravação.
  3. ALINHA com o roteiro: o roteiro estimado diz quantas falas há e quanto cada uma deveria durar; programação dinâmica
     escolhe, entre as pausas e vales de energia do áudio, os N-1 cortes que melhor separam as falas (pausas longas
     pesam a favor; durações muito diferentes do esperado pesam contra). Respirações e trechos mudos (`silence`) vão
     para o que sobra entre as falas.
  4. ESCREVE `ep0X/narration.measured.json` (início/fim por item + `pauses` internas + confiança) e um relatório.
  5. RODA o build: câmera, passos, SFX, luz e beats ancorados na voz se re-sincronizam sozinhos.

Não há reconhecimento de fala: o alinhamento é por amplitude e pelo texto/estrutura do roteiro. Por isso o relatório dá
uma confiança por item. Gravação muito ruidosa, falas coladas sem pausa ou texto diferente do roteiro pedem revisão
(`--dry-run` mostra tudo sem gravar). Só biblioteca padrão; `ffmpeg` é opcional (só para formatos que não são WAV).
"""
from __future__ import annotations

import bisect
import json
import math
import shutil
import struct
import subprocess
import sys
from array import array
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .narration import BREATH_SHAPES
from .timeline import FPS, ROOT

AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wma", ".webm", ".mp4")
HOP_S = 0.010                                     # um quadro de análise = 10 ms
TARGET_RATE = 16000


class AudioError(Exception):
    """Problema com o áudio ou com o casamento com o roteiro (mensagem em português, vai direto ao usuário)."""


# ======================================================================================================================
#  Parâmetros
# ======================================================================================================================
@dataclass
class Params:
    contrast_min_db: float = 12.0        # fala precisa passar do ruído de fundo por pelo menos isto
    voice_frac: float = 0.40             # limiar de fala = piso + 40% da distância piso->nível da fala
    edge_db: float = 6.0                 # histerese: a borda da fala desce até (limiar - 6 dB)
    breath_zcr: float = 0.20             # acima disto (e fraco) o som é ruidoso: respiração, não voz
    breath_below_db: float = 12.0        # respiração = pelo menos 12 dB abaixo do nível da fala
    breath_min_s: float = 0.12
    min_gap_s: float = 0.05              # silêncios menores que isto não separam nada
    min_pause_s: float = 0.10            # silêncio interno >= isto vira `pauses` (âncora das palavras)
    min_speech_s: float = 0.06
    # pesos da programação dinâmica
    w_dur: float = 2.0
    w_pos: float = 0.0                   # posição absoluta prevista: desligada (a deriva entre estimado e gravado é ilimitada)
    w_gap: float = 0.8
    pos_sigma_s: float = 1.2
    w_block: float = 0.35                # reservar um bloco de voz para uma respiração prevista (só quando melhora o resto)
    w_runs: float = 0.4                  # por trecho de voz a mais/a menos que os ciclos da respiração prevista (ofegar = 3, hiper = 5)
    w_pause: float = 0.5                 # silêncio interno (>= 0,15 s) além das pausas de pontuação que o roteiro prevê para a fala
    w_rate: float = 8.0                  # só entre hipóteses (respiração inicial ou não): ritmo muito diferente do previsto custa
    min_item_s: float = 0.12


# ======================================================================================================================
#  Decodificação
# ======================================================================================================================
def _parse_wav(data: bytes):
    if data[:4] not in (b"RIFF", b"RIFX") or data[8:12] != b"WAVE":
        raise AudioError("não é um WAV (RIFF/WAVE)")
    big = data[:4] == b"RIFX"
    e = ">" if big else "<"
    pos, fmt, pcm = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack(e + "I", data[pos + 4:pos + 8])[0]
        body = pos + 8
        if cid == b"fmt ":
            tag, ch, rate, _, _, bits = struct.unpack(e + "HHIIHH", data[body:body + 16])
            if tag == 0xFFFE and size >= 26:                              # WAVE_FORMAT_EXTENSIBLE: o formato real está no GUID
                tag = struct.unpack(e + "H", data[body + 24:body + 26])[0]
            fmt = (tag, ch, rate, bits)
        elif cid == b"data":
            end = body + size if body + size <= len(data) else len(data)  # arquivo gravado em fluxo: tamanho inválido
            pcm = data[body:end]
            break
        pos = body + size + (size & 1)
    if fmt is None or pcm is None:
        raise AudioError("WAV sem bloco 'fmt ' ou 'data'")
    return fmt, pcm, big


def _wav_to_mono(path: Path):
    (tag, ch, rate, bits), pcm, big = _parse_wav(path.read_bytes())
    if ch < 1:
        raise AudioError(f"{path.name}: WAV sem canais")
    if tag == 1 and bits == 8:
        samples = array("f", ((b - 128) / 128.0 for b in pcm))
    elif tag == 1 and bits == 16:
        a = array("h", pcm[: len(pcm) // 2 * 2])
        if big:
            a.byteswap()
        samples = array("f", (v / 32768.0 for v in a))
    elif tag == 1 and bits == 24:
        n = len(pcm) // 3
        order = "big" if big else "little"
        samples = array("f", (int.from_bytes(pcm[3 * i:3 * i + 3], order, signed=True) / 8388608.0 for i in range(n)))
    elif tag == 1 and bits == 32:
        a = array("i", pcm[: len(pcm) // 4 * 4])
        if big:
            a.byteswap()
        samples = array("f", (v / 2147483648.0 for v in a))
    elif tag == 3 and bits == 32:
        samples = array("f", pcm[: len(pcm) // 4 * 4])
        if big:
            samples.byteswap()
    elif tag == 3 and bits == 64:
        a = array("d", pcm[: len(pcm) // 8 * 8])
        if big:
            a.byteswap()
        samples = array("f", a)
    else:
        raise AudioError(f"{path.name}: WAV com formato não suportado (tag {tag}, {bits} bits); use PCM 8/16/24/32 ou float")
    if ch > 1:
        n = len(samples) // ch
        samples = array("f", (sum(samples[i * ch:(i + 1) * ch]) / ch for i in range(n)))
    return samples, rate


def _ffmpeg_to_mono(path: Path):
    exe = shutil.which("ffmpeg")
    if not exe:
        raise AudioError(f"{path.name}: só WAV é lido sem o ffmpeg. Instale o ffmpeg (ele decodifica mp3/m4a/ogg/flac) "
                         f"ou converta o arquivo para WAV.")
    r = subprocess.run([exe, "-v", "error", "-nostdin", "-i", str(path), "-ac", "1", "-ar", str(TARGET_RATE), "-f", "s16le", "-"],
                       capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise AudioError(f"{path.name}: o ffmpeg não conseguiu decodificar ({r.stderr.decode(errors='replace').strip()[:200]})")
    a = array("h", r.stdout[: len(r.stdout) // 2 * 2])
    if sys.byteorder == "big":
        a.byteswap()
    return array("f", (v / 32768.0 for v in a)), TARGET_RATE


def read_audio(path: Path):
    """Devolve (amostras mono em [-1, 1] como array('f'), taxa em Hz), com a taxa reduzida a ~16 kHz (basta para a análise)."""
    path = Path(path)
    if not path.exists():
        raise AudioError(f"áudio não encontrado: {path}")
    if path.suffix.lower() == ".wav":
        try:
            samples, rate = _wav_to_mono(path)
        except AudioError as exc:
            if "não é um WAV" in str(exc) and shutil.which("ffmpeg"):
                samples, rate = _ffmpeg_to_mono(path)
            else:
                raise
    else:
        samples, rate = _ffmpeg_to_mono(path)
    if rate > TARGET_RATE * 3 // 2:
        f = rate // TARGET_RATE
        samples, rate = samples[::f], rate // f
    if len(samples) < rate // 2:
        raise AudioError(f"{path.name}: áudio curto demais ({len(samples) / rate:.2f} s)")
    return samples, rate


# ======================================================================================================================
#  Análise de quadros
# ======================================================================================================================
@dataclass
class Frames:
    db: list                               # nível suavizado (dB, ~30 ms) por quadro de 10 ms
    zcr: list                              # taxa de cruzamento de zero por quadro
    floor: float = 0.0
    ref: float = 0.0
    hop: float = HOP_S
    duration: float = 0.0


def analyse(samples, rate: int) -> Frames:
    hop = max(2, int(round(rate * HOP_S)))
    n = len(samples) // hop
    energy, zcr = [], []
    for b in range(n):
        blk = samples[b * hop:(b + 1) * hop]
        energy.append(sum(v * v for v in blk) / hop)
        z, prev = 0, blk[0] < 0
        for v in blk[1:]:
            cur = v < 0
            if cur != prev:
                z += 1
            prev = cur
        zcr.append(z / (hop - 1) if energy[-1] > 0 else 0.0)
    sm = []                                # média móvel de 3 quadros na energia (não em dB)
    for i in range(n):
        lo, hi = max(0, i - 1), min(n, i + 2)
        sm.append(sum(energy[lo:hi]) / (hi - lo))
    db = [10 * math.log10(e + 1e-12) for e in sm]
    live = sorted(v for v in db if v > -110)
    if len(live) < 20:
        raise AudioError("o áudio parece vazio (silêncio digital)")
    floor = live[int(0.05 * len(live))]
    ref = live[int(0.92 * len(live))]
    if (len(db) - len(live)) / len(db) >= 0.05 and floor > ref - 45:
        # muito silêncio DIGITAL (TTS que zera entre as falas): o piso medido só enxerga os vales da própria fala e
        # ficaria alto demais; vale um piso bem abaixo da fala
        floor = ref - 70
    return Frames(db=db, zcr=zcr, floor=floor, ref=ref, hop=hop / rate, duration=n * hop / rate)


@dataclass
class Segments:
    voiced: list = field(default_factory=list)       # [(início, fim)] em s
    breaths: list = field(default_factory=list)
    cuts: list = field(default_factory=list)         # candidatos a fronteira entre falas: (início, fim, força)
    gaps: list = field(default_factory=list)         # silêncios reais entre trechos de voz: (início, fim)
    floor: float = 0.0
    ref: float = 0.0
    contrast_db: float = 0.0


def _runs(mask, hop, min_len=0.0):
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            if (j - i) * hop >= min_len:
                out.append((i, j))
            i = j
        else:
            i += 1
    return out


def segment(fr: Frames, p: Params | None = None) -> Segments:
    p = p or Params()
    db, zcr, hop = fr.db, fr.zcr, fr.hop
    n = len(db)
    span = fr.ref - fr.floor
    t_voice = fr.floor + max(p.contrast_min_db, p.voice_frac * span)
    t_edge = t_voice - p.edge_db
    t_low = fr.floor + max(6.0, 0.10 * span)
    quiet_noise = [zcr[i] > p.breath_zcr and db[i] < fr.ref - p.breath_below_db for i in range(n)]
    core = [db[i] >= t_voice and not quiet_noise[i] for i in range(n)]
    ext = [db[i] >= t_edge and not quiet_noise[i] for i in range(n)]
    voiced = [False] * n
    for a, b in _runs(ext, hop):                                    # histerese: só vale o trecho com núcleo forte
        if any(core[a:b]):
            for i in range(a, b):
                voiced[i] = True
    breathy = [(quiet_noise[i] and db[i] >= t_low) and not voiced[i] for i in range(n)]
    # respiração curtinha colada à voz (fricativas fracas: f, s, x) é voz; solta é descartada
    for a, b in _runs(breathy, hop):
        if (b - a) * hop < p.breath_min_s:
            touch = (a > 0 and voiced[a - 1]) or (b < n and voiced[b])
            for i in range(a, b):
                breathy[i] = False
                voiced[i] = voiced[i] or touch
    raw = _runs(voiced, hop)
    # silêncios pequenos demais para separar algo: funde; trechos minúsculos isolados: descarta
    merged: list[list[int]] = []
    for a, b in raw:
        if merged and (a - merged[-1][1]) * hop < p.min_gap_s:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    merged = [(a, b) for a, b in merged if (b - a) * hop >= p.min_speech_s]
    seg = Segments(floor=fr.floor, ref=fr.ref, contrast_db=span)
    seg.voiced = [(a * hop, b * hop) for a, b in merged]
    seg.breaths = [(a * hop, b * hop) for a, b in _runs(breathy, hop, p.breath_min_s)]
    for (_, b0), (a1, _) in zip(merged, merged[1:]):
        seg.gaps.append((b0 * hop, a1 * hop))
        seg.cuts.append((b0 * hop, a1 * hop, max(0.15, min(1.5, (a1 - b0) * hop / 0.40))))
    # vales de energia dentro da voz (fala sem pausa): candidatos fracos, só para quando faltarem pausas de verdade
    for a, b in merged:
        for v in range(a + 3, b - 3):
            if db[v] > min(db[v - 1], db[v + 1]) or db[v] > min(db[v - 3:v + 4]) + 0.01:
                continue
            left, right = max(db[max(a, v - 30):v]), max(db[v + 1:min(b, v + 31)] or [db[v]])
            prom = min(left, right) - db[v]
            if prom >= 7.0 and not any(abs(v * hop - (c0 + c1) / 2) < 0.12 for c0, c1, _ in seg.cuts):
                seg.cuts.append((v * hop - 0.01, v * hop + 0.01, 0.05 + prom / 80.0))
    seg.cuts.sort()
    return seg


# ======================================================================================================================
#  Alinhamento com o roteiro
# ======================================================================================================================
@dataclass
class Placed:
    start: float
    end: float
    conf: float
    note: str = ""
    pauses: list = field(default_factory=list)


def align_speech(durs, est_pos, seg: Segments, p: Params | None = None, want_cost: bool = False, internal=None,
                 breaths=None, with_blocks: bool = False, bursts=None):
    """Escolhe, entre os cortes candidatos, as fronteiras que melhor separam as N falas do roteiro.

    durs    duração esperada de cada fala (incluindo as pausas internas), do roteiro estimado
    est_pos instante estimado do FIM de cada fala (mesmo referencial da estimativa)
    internal quantas pausas de pontuação (>= 0,1 s) o roteiro prevê DENTRO de cada fala; silêncio de verdade a mais do que isso
            dentro de uma fala custa (separa suspiro/gasp da fala e evita fundir duas falas).
    breaths  duração prevista da(s) respiração(ões) entre a fala k e a k+1 (0 = nenhuma). Onde há uma, o alinhamento pode
            reservar um BLOCO de trechos de voz entre as duas falas para ela (bocejo, ofegar, suspiro soados, que têm tom e o
            detector toma por fala); sem ela, fala e respiração se fundiriam.
    Devolve [(início, fim, confiança)] por fala, no tempo do ARQUIVO de áudio; com `want_cost`, (spans, custo); com
    `with_blocks`, (spans, blocos, custo), onde blocos[k] = (início, fim) da respiração soada entre a fala k e a k+1 (ou None).
    bursts   quantos trechos de voz a respiração entre a fala k e a k+1 deve ter (ofegar "huh-huh-huh" = 3, hiperventilar = 5;
            padrão 1 e sem custo). Impede que um bloco de ofegos engula a primeira sílaba da fala seguinte.
    """
    p = p or Params()
    n = len(durs)
    if not seg.voiced:
        raise AudioError("nenhuma fala detectada no áudio")
    t_on, t_off = seg.voiced[0][0], seg.voiced[-1][1]
    if n == 1:
        one = [(t_on, t_off, 1.0)]
        return (one, [], 0.0) if with_blocks else ((one, 0.0) if want_cost else one)
    est_first = est_pos[0] - durs[0]
    est_span = max(est_pos[-1] - est_first, 1e-6)
    cuts = [c for c in seg.cuts if c[0] > t_on + p.min_item_s and c[1] < t_off - p.min_item_s]
    if len(cuts) < n - 1:
        raise AudioError(f"o roteiro tem {n} falas mas o áudio só mostra {len(cuts) + 1} trechos separáveis "
                         f"(pausas/vales de energia); há falas coladas sem pausa ou texto diferente do roteiro")
    G = len(cuts)
    INF = float("inf")
    breaths = list(breaths) if breaths is not None else [0.0] * (n - 1)
    big = sorted((a, b) for a, b in seg.gaps if b - a >= 0.15)
    g_start, g_end = [a for a, _ in big], [b for _, b in big]
    v_start, v_end = [a for a, _ in seg.voiced], [b for _, b in seg.voiced]
    bursts = list(bursts) if bursts is not None else [1] * (n - 1)

    def runs_in(a, b):                                                  # trechos de voz que cobrem (a, b) por mais de 50 ms
        return bisect.bisect_left(v_start, b - 0.05) - bisect.bisect_right(v_end, a + 0.05)

    def run_dp(r):
        pred = [t_on + (e - est_first) * r for e in est_pos]

        def item_cost(k, start, end):                                   # k = índice da fala (0..n-1)
            d = end - start
            if d < p.min_item_s:
                return INF
            c = p.w_dur * math.log(d / max(durs[k] * r, 1e-3)) ** 2
            if internal is not None and big:
                inside = bisect.bisect_right(g_end, end + 1e-6) - bisect.bisect_left(g_start, start - 1e-6)
                c += p.w_pause * max(0, inside - internal[k])
            if k < n - 1 and p.w_pos:
                c += p.w_pos * ((end - pred[k]) / p.pos_sigma_s) ** 2
            return c

        # E[k][c]: custo mínimo das falas 0..k com a fala k terminando no corte c
        # S[k][c2]: custo mínimo antes da fala k, que COMEÇA no corte c2 (depois de um bloco de respiração, se houver)
        E = [[INF] * G for _ in range(n - 1)]
        bE = [[-1] * G for _ in range(n - 1)]
        S = [[INF] * G for _ in range(n)]
        bS = [[-1] * G for _ in range(n)]
        for c in range(G):
            E[0][c] = item_cost(0, t_on, cuts[c][0]) - p.w_gap * cuts[c][2]
        for k in range(1, n):
            pl = breaths[k - 1]
            for c2 in range(G):
                S[k][c2], bS[k][c2] = E[k - 1][c2], c2                  # sem bloco: a fala k começa no mesmo corte
                if pl > 0:
                    for c in range(c2):
                        if E[k - 1][c] == INF:
                            continue
                        dur = cuts[c2][0] - cuts[c][1]
                        if dur < 0.12 or dur > max(2.5 * pl, pl + 3.0):
                            continue
                        cost = E[k - 1][c] + p.w_block + 0.3 * math.log(dur / pl) ** 2 - p.w_gap * cuts[c2][2]
                        if bursts[k - 1] > 1:
                            cost += p.w_runs * abs(runs_in(cuts[c][1], cuts[c2][0]) - bursts[k - 1])
                        if cost < S[k][c2]:
                            S[k][c2], bS[k][c2] = cost, c
            if k == n - 1:
                break
            for c3 in range(G):
                a3 = cuts[c3][0]
                for c2 in range(c3):
                    if S[k][c2] == INF or cuts[c2][1] >= a3:
                        continue
                    cst = S[k][c2] + item_cost(k, cuts[c2][1], a3) - p.w_gap * cuts[c3][2]
                    if cst < E[k][c3]:
                        E[k][c3], bE[k][c3] = cst, c2
        tail, c2l = INF, -1
        for c2 in range(G):
            if S[n - 1][c2] < INF:
                cst = S[n - 1][c2] + item_cost(n - 1, cuts[c2][1], t_off)
                if cst < tail:
                    tail, c2l = cst, c2
        if c2l < 0:
            raise AudioError("não foi possível casar as falas do roteiro com as pausas do áudio")
        starts, ends = [None] * n, [None] * n                              # cortes: onde cada fala começa/termina
        starts[n - 1] = c2l
        for k in range(n - 1, 0, -1):
            ends[k - 1] = bS[k][starts[k]]
            if k - 1 >= 1:
                starts[k - 1] = bE[k - 1][ends[k - 1]]
        return tail, starts, ends

    def blocks_of(starts, ends):
        out = []
        for k in range(1, n):
            c, c2 = ends[k - 1], starts[k]
            out.append(None if c2 == c else (cuts[c][1], cuts[c2][0]))
        return out

    def rate_of(blocks):                                                 # ritmo da FALA (sem os blocos de respiração) / estimado
        used = [(b, breaths[k]) for k, b in enumerate(blocks) if b is not None]
        speech_time = (t_off - t_on) - sum(b[1] - b[0] for b, _ in used)
        return speech_time / max(est_span - sum(pl for _, pl in used), 1e-6)

    def total_cost(starts, ends, r):                                     # custo de um alinhamento já escolhido, no ritmo r
        pred = [t_on + (e - est_first) * r for e in est_pos]

        def item_cost(k, start, end):
            d = end - start
            if d < p.min_item_s:
                return INF
            c = p.w_dur * math.log(d / max(durs[k] * r, 1e-3)) ** 2
            if internal is not None and big:
                inside = bisect.bisect_right(g_end, end + 1e-6) - bisect.bisect_left(g_start, start - 1e-6)
                c += p.w_pause * max(0, inside - internal[k])
            if k < n - 1 and p.w_pos:
                c += p.w_pos * ((end - pred[k]) / p.pos_sigma_s) ** 2
            return c

        tot = item_cost(0, t_on, cuts[ends[0]][0]) - p.w_gap * cuts[ends[0]][2] if n > 1 else 0.0
        for k in range(1, n):
            c, c2 = ends[k - 1], starts[k]
            if c2 != c:
                dur = cuts[c2][0] - cuts[c][1]
                tot += p.w_block + 0.3 * math.log(dur / breaths[k - 1]) ** 2 - p.w_gap * cuts[c2][2]
                if bursts[k - 1] > 1:
                    tot += p.w_runs * abs(runs_in(cuts[c][1], cuts[c2][0]) - bursts[k - 1])
            if k < n - 1:
                tot += item_cost(k, cuts[c2][1], cuts[ends[k]][0]) - p.w_gap * cuts[ends[k]][2]
            else:
                tot += item_cost(k, cuts[c2][1], t_off)
        return tot

    # O ritmo real depende de quais trechos são respiração, e quais são respiração depende do ritmo: parte-se de duas hipóteses
    # (tudo é fala; as respirações ocupam o que o roteiro previu), refina cada uma e fica com o alinhamento de menor custo
    # medido no PRÓPRIO ritmo (assim um ponto fixo ruim não vence um bom).
    planned_total = sum(breaths)
    seeds = [(t_off - t_on) / est_span]
    if planned_total > 0:
        seeds.append(((t_off - t_on) - planned_total) / max(est_span - planned_total, 1e-6))
    best = None
    seen = set()
    for r in seeds:
        for _ in range(3):
            try:
                _, starts, ends = run_dp(r)
            except AudioError:
                break
            key = (tuple(starts[1:]), tuple(ends[:-1]))
            r_a = rate_of(blocks_of(starts, ends))
            if key not in seen:
                seen.add(key)
                tot = total_cost(starts, ends, r_a) + p.w_rate * math.log(max(r_a, 1e-3)) ** 2
                if best is None or tot < best[0]:
                    best = (tot, starts, ends, r_a)
            if abs(r_a - r) <= 0.02 * r:
                break
            r = r_a
    if best is None:
        raise AudioError("não foi possível casar as falas do roteiro com as pausas do áudio")
    cost, starts, ends, r = best
    blocks = blocks_of(starts, ends)
    out = []
    for k in range(n):
        s_ = t_on if k == 0 else cuts[starts[k]][1]
        e_ = t_off if k == n - 1 else cuts[ends[k]][0]
        ls = 1.0 if k == 0 else min(1.0, cuts[starts[k]][2])
        rs = 1.0 if k == n - 1 else min(1.0, cuts[ends[k]][2])
        ratio = math.exp(-abs(math.log(max(e_ - s_, 1e-3) / max(durs[k] * r, 1e-3))))
        out.append((s_, e_, round(max(0.05, min(1.0, (0.5 * ls + 0.5 * rs) * (0.35 + 0.65 * ratio))), 2)))
    if with_blocks:
        return out, blocks, cost
    return (out, cost) if want_cost else out


def _drop_leading_runs(seg: Segments, k: int) -> Segments:
    """Segmentos sem as k primeiras trechos de voz, que passam a contar como RESPIRAÇÃO (suspiro, gasp, hiperventilação
    soados que o detector tomou por voz porque têm tom)."""
    first_on = seg.voiced[k][0]
    return Segments(voiced=seg.voiced[k:], breaths=sorted(seg.breaths + seg.voiced[:k]),
                    cuts=[c for c in seg.cuts if c[0] >= first_on], gaps=[g for g in seg.gaps if g[0] >= first_on],
                    floor=seg.floor, ref=seg.ref, contrast_db=seg.contrast_db)


def leading_breath_runs(seg: Segments, durs, est_pos, planned: float, p: Params, internal=None, breaths=None) -> int:
    """Quantos dos primeiros trechos de voz são, na verdade, a respiração que o roteiro põe antes da 1ª fala.

    O roteiro diz quantos trechos de voz esperar: cada fala dá 1 trecho + 1 por pausa de pontuação que ela prevê. Se o áudio
    traz MAIS trechos do que isso, os que sobram são respiração soada (suspiro, gasp, hiperventilação têm tom e o detector os
    toma por voz). Com uma respiração prevista antes da 1ª fala, os que sobram são os PRIMEIROS (desde que caibam no que o
    roteiro previu para ela). Só vale se o alinhamento ficar plausível (custo não muito pior que sem a hipótese)."""
    if planned <= 0 or len(durs) < 2 or internal is None:
        return 0
    expected = sum(x + 1 for x in internal)
    surplus = len(seg.voiced) - expected
    if surplus < 1:
        return 0
    limit = max(2.3 * planned, planned + 2.5)                      # a respiração gravada pode durar bem mais que a prevista
    run_max = max(0.5, 1.3 * planned)                              # mas cada trecho dela é curto (fala solta tem mais que isso)
    try:
        _, cost0 = align_speech(durs, est_pos, seg, p, want_cost=True, internal=internal, breaths=breaths)
    except AudioError:
        cost0 = float("inf")
    for k in range(min(surplus, 6), 0, -1):
        if seg.voiced[k - 1][1] - seg.voiced[0][0] > limit or len(seg.voiced) - k < len(durs):
            continue
        if any(b - a > run_max for a, b in seg.voiced[:k]):        # um trecho longo é fala ("CARALHO!"), não respiração
            continue
        try:
            _, cost = align_speech(durs, est_pos, _drop_leading_runs(seg, k), p, want_cost=True, internal=internal, breaths=breaths)
        except AudioError:
            continue
        if cost <= cost0 + 0.6:
            return k
    return 0


def _union_breath(runs, dur):
    """Escolhe o conjunto contíguo de respirações cujo vão total mais se aproxima da duração esperada."""
    best, score = None, float("inf")
    runs = sorted(runs)
    for i in range(len(runs)):
        for j in range(i, len(runs)):
            span = runs[j][1] - runs[i][0]
            sc = abs(math.log(max(span, 1e-3) / max(dur, 1e-3)))
            if sc < score:
                best, score = (runs[i][0], runs[j][1]), sc
    return best, score


# ======================================================================================================================
#  Trilhas e itens
# ======================================================================================================================
def find_tracks(audio_dir: Path, scene_ids, speakers=("protagonista",)) -> list[dict]:
    """Descobre as trilhas em `ep0X/audio/` (nome do arquivo = tipo da trilha; qualquer extensão de áudio).

    narration.<ext>            UMA trilha do episódio inteiro, com t=0 no início do vídeo (offset 0).
    s1.<ext>, s2.<ext> ...     um bloco por cena, com todas as vozes da cena.
    s2.motorista.<ext> ...     um bloco por cena E por falante (cada voz gerada à parte; ver `speakers` no narration.json).
    audio/offsets.json         {"s2": 18.3, "narration": 0.0}: onde o t=0 de um arquivo cai NA LINHA DO TEMPO (segundos).

    Sem offset explícito, o bloco é POSICIONADO pelo roteiro: a 1ª fala do bloco cai no instante previsto dela e, havendo
    vários blocos na mesma cena (falantes diferentes), cada um começa depois do anterior, com a folga prevista entre eles.
    """
    if not audio_dir.is_dir():
        raise AudioError(f"pasta de áudio não encontrada: {audio_dir}. Coloque lá narration.wav (episódio inteiro) "
                         f"ou um arquivo por bloco ({', '.join(f'{s}.wav' for s in scene_ids)}; "
                         f"com vozes separadas: s2.motorista.wav, s2.protagonista.wav).")
    files = {}
    for f in sorted(audio_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in AUDIO_EXTS:
            if f.stem in files:
                raise AudioError(f"há dois arquivos de áudio para '{f.stem}': {files[f.stem].name} e {f.name}")
            files[f.stem] = f
    offs_file = audio_dir / "offsets.json"
    offsets = json.loads(offs_file.read_text(encoding="utf-8")) if offs_file.exists() else {}
    speakers = set(speakers)
    tracks, bad = [], []
    for stem, path in files.items():
        scene, _, who = stem.partition(".")
        if stem == "narration":
            tracks.append({"stem": stem, "path": path, "scenes": list(scene_ids), "speaker": None})
        elif scene in scene_ids and (not who or who in speakers):
            tracks.append({"stem": stem, "path": path, "scenes": [scene], "speaker": who or None})
        else:
            bad.append(path.name)
    if bad:
        raise AudioError(f"arquivo(s) de áudio que não reconheço: {', '.join(bad)}. Os nomes aceitos são narration, "
                         f"{', '.join(scene_ids)} ou <cena>.<falante> (falantes: {', '.join(sorted(speakers))}).")
    if not tracks:
        raise AudioError(f"nenhum áudio de narração em {audio_dir}: esperava narration.<ext>, {', '.join(scene_ids)} "
                         f"ou <cena>.<falante> (.wav/.mp3/...)")
    if any(t["stem"] == "narration" for t in tracks) and len(tracks) > 1:
        extra = [t["stem"] for t in tracks if t["stem"] != "narration"]
        raise AudioError(f"há narration e também {', '.join(extra)}: escolha UMA forma (episódio inteiro OU por bloco)")
    for sc in scene_ids:
        mine = [t for t in tracks if t["scenes"] == [sc]]
        if any(t["speaker"] is None for t in mine) and len(mine) > 1:
            raise AudioError(f"a cena {sc} tem {sc} (todas as vozes) e também {', '.join(t['stem'] for t in mine if t['speaker'])}: "
                             f"escolha UMA forma")
    unknown = sorted(set(offsets) - {t["stem"] for t in tracks} - set(scene_ids) - {"narration"})
    if unknown:
        raise AudioError(f"offsets.json cita blocos inexistentes: {unknown}")
    for t in tracks:
        t["offset"] = offsets.get(t["stem"], 0.0 if t["stem"] == "narration" else None)
        t["default_offset"] = t["offset"] is None
    order = {s: k for k, s in enumerate(scene_ids)}
    tracks.sort(key=lambda t: (order[t["scenes"][0]], t["speaker"] or ""))
    return tracks


def estimated_items(ep_id: str, root: Path = ROOT):
    """(itens de narração, linha do tempo) ESTIMADOS: ignora o measured.json atual, então reexecutar é estável."""
    from .build import build_episode
    tl = build_episode(ep_id, root=root, write=False, use_measured=False)
    return tl["narration"], tl


def _track_ids(tr, order, by_id):
    """Itens (fala e respiração) cuja voz está neste arquivo. A respiração vai com o falante da fala SEGUINTE da cena
    (ou da anterior, no fim): quem respira antes de falar é quem fala."""
    scene_items = [i for i in order if by_id[i]["scene"] in tr["scenes"] and by_id[i]["kind"] in ("speech", "breath")]
    if tr["speaker"] is None:
        return scene_items
    who = lambda i: by_id[i].get("speaker") or "protagonista"                       # noqa: E731
    out = []
    for k, i in enumerate(scene_items):
        if by_id[i]["kind"] == "speech":
            owner = who(i)
        else:
            nxt = next((j for j in scene_items[k + 1:] if by_id[j]["kind"] == "speech"), None)
            prv = next((j for j in reversed(scene_items[:k]) if by_id[j]["kind"] == "speech"), None)
            owner = who(nxt) if nxt else (who(prv) if prv else None)
        if owner == tr["speaker"]:
            out.append(i)
    return out


def analyse_episode(ep_id: str, root: Path = ROOT, audio_dir: Path | None = None, params: Params | None = None) -> dict:
    """Mede todas as trilhas e devolve {"items": {id: {...}}, "report": {...}} (nada é gravado)."""
    p = params or Params()
    est, tl = estimated_items(ep_id, root)
    ep_dir = root / ep_id
    audio_dir = audio_dir or ep_dir / "audio"
    scene_ids = [s["id"] for s in tl["scenes"]]
    by_id = {i["id"]: i for i in est}
    order = [i["id"] for i in est]
    speakers = {i.get("speaker") or "protagonista" for i in est if i["kind"] == "speech"}
    tracks = find_tracks(audio_dir, scene_ids, speakers)
    placed: dict[str, Placed] = {}
    report = {"episode": ep_id, "audio": {}, "warnings": []}
    last_clip: dict[str, str] = {}                                                # cena -> última fala do bloco anterior
    scene_rank = {s: k for k, s in enumerate(scene_ids)}
    for tr in tracks:
        tr["ids"] = _track_ids(tr, order, by_id)
        sp = [i for i in tr["ids"] if by_id[i]["kind"] == "speech"]
        tr["first_start"] = by_id[sp[0]]["start"] if sp else float("inf")
    # blocos da mesma cena na ORDEM DO ROTEIRO (quem fala primeiro vem primeiro), não por nome de arquivo
    tracks.sort(key=lambda t: (scene_rank[t["scenes"][0]], t["first_start"]))
    for tr in tracks:
        ids = tr["ids"]
        speech = [i for i in ids if by_id[i]["kind"] == "speech"]
        if not speech:
            report["warnings"].append(f"{tr['path'].name}: nenhuma fala do roteiro corresponde a este arquivo")
            continue
        samples, rate = read_audio(tr["path"])
        fr = analyse(samples, rate)
        seg = segment(fr, p)
        durs = [by_id[i]["end"] - by_id[i]["start"] for i in speech]
        ends_est = [by_id[i]["end"] for i in speech]
        internal = [sum(1 for a, b in zip(by_id[i].get("words", []), by_id[i].get("words", [])[1:]) if b["start"] - a["end"] >= 0.1)
                    for i in speech]                                              # pausas de pontuação previstas dentro de cada fala
        pos_ = {i: n_ for n_, i in enumerate(ids)}                                # respirações previstas entre cada par de falas
        slot_pl = [sum(by_id[i]["end"] - by_id[i]["start"] for i in ids[pos_[a_] + 1:pos_[b_]] if by_id[i]["kind"] == "breath")
                   for a_, b_ in zip(speech, speech[1:])]
        slot_bursts = [max([BREATH_SHAPES[by_id[i]["type"]].get("cycles", 1) for i in ids[pos_[a_] + 1:pos_[b_]]
                            if by_id[i]["kind"] == "breath"] or [1]) for a_, b_ in zip(speech, speech[1:])]
        lead = [i for i in ids[:ids.index(speech[0])] if by_id[i]["kind"] == "breath"]
        k_lead = leading_breath_runs(seg, durs, ends_est, sum(by_id[i]["end"] - by_id[i]["start"] for i in lead), p, internal, slot_pl)
        if k_lead:
            seg = _drop_leading_runs(seg, k_lead)                                  # o suspiro/gasp soado é respiração, não fala
        spans, blocks, _cost = align_speech(durs, ends_est, seg, p, internal=internal, breaths=slot_pl, with_blocks=True,
                                            bursts=slot_bursts)
        breath_runs = sorted(seg.breaths + [b_ for b_ in blocks if b_])           # blocos de voz reservados para respirações soadas
        clip_on = spans[0][0]
        pushed = 0.0
        if tr["offset"] is not None:                                              # offset explícito (ou trilha do episódio)
            offset = tr["offset"]
        else:                                                                     # posicionado pelo roteiro
            sc = tr["scenes"][0]
            prev = last_clip.get(sc)
            if prev is None:
                anchor = by_id[speech[0]]["start"]                                # 1ª fala no instante previsto
                tail = max((pl.end for pl in placed.values()), default=0.0)       # sem invadir o que já foi medido
                if anchor < tail + 0.2:
                    pushed, anchor = tail + 0.2 - anchor, tail + 0.2
            else:                                                                 # depois do bloco anterior, com a folga prevista
                anchor = placed[prev].end + max(by_id[speech[0]]["start"] - by_id[prev]["end"], 0.15)
            offset = anchor - clip_on
        info = {"offset": round(offset, 3), "duration": round(fr.duration, 3), "floor_db": round(fr.floor, 1),
                "speech_db": round(fr.ref, 1), "contrast_db": round(fr.ref - fr.floor, 1), "voiced_runs": len(seg.voiced),
                "breath_runs": len(seg.breaths), "cut_candidates": len(seg.cuts), "offset_default": bool(tr["default_offset"]),
                "scene": tr["scenes"][0] if len(tr["scenes"]) == 1 else None, "speaker": tr["speaker"]}
        report["audio"][tr["path"].name] = info
        if pushed > 0.05:
            report["warnings"].append(f"{tr['path'].name}: a voz anterior termina depois do previsto e empurra esta {pushed:.2f} s")
        if fr.ref - fr.floor < 20:
            report["warnings"].append(f"{tr['path'].name}: contraste baixo entre fala e ruído de fundo "
                                      f"({fr.ref - fr.floor:.0f} dB); confira o resultado")
        for sid, (s, e, conf) in zip(speech, spans):
            pauses = [[round(a + offset, 3), round(b + offset, 3)] for a, b in seg.gaps
                      if a >= s - 1e-6 and b <= e + 1e-6 and b - a >= p.min_pause_s]
            placed[sid] = Placed(round(s + offset, 3), round(e + offset, 3), conf, pauses=pauses)
        _place_breaths(ids, by_id, placed, breath_runs, offset, fr.duration, p)
        if tr["offset"] is None:                                                  # nada pode começar antes da janela da cena
            w0 = next(s for s in tl["scenes"] if s["id"] == tr["scenes"][0])["narration_fit"]["window"][0]
            early = min(placed[i].start for i in ids if i in placed)
            if early < w0 - 1 / FPS:
                d = round(w0 - early, 3)
                for i in ids:
                    if i in placed:
                        pl = placed[i]
                        pl.start, pl.end = round(pl.start + d, 3), round(pl.end + d, 3)
                        pl.pauses = [[round(a + d, 3), round(b + d, 3)] for a, b in pl.pauses]
                report["warnings"].append(f"{tr['path'].name}: a respiração/fala inicial começaria {d:.2f} s antes da janela da "
                                          f"cena; o bloco foi empurrado {d:.2f} s")
        last_clip[tr["scenes"][0]] = speech[-1]

    # ---- itens sem áudio: posição estimada, deslocada junto com a cena (nunca por cima do que foi medido) ----
    delta, prev_end, missing = {}, 0.0, []
    for iid in order:
        it = by_id[iid]
        if iid in placed:
            delta[it["scene"]] = placed[iid].end - it["end"]
            prev_end = max(prev_end, placed[iid].end)
        elif it["kind"] != "silence":
            s0 = max(it["start"] + delta.get(it["scene"], 0.0), prev_end)
            placed[iid] = Placed(round(s0, 3), round(s0 + it["end"] - it["start"], 3), 0.0,
                                 note="sem áudio: posição estimada (deslocada junto com a cena)")
            prev_end = placed[iid].end
            missing.append(iid)
    if missing:
        report["warnings"].append(f"sem áudio (posição estimada): {', '.join(missing)}")
    # ---- trechos mudos: ocupam a folga entre os vizinhos; depois, ordem e sobreposição ----
    _fill_silences_and_fix_order(order, by_id, placed, report,
                                 {s["id"]: tuple(s["narration_fit"]["window"]) for s in tl["scenes"] if s.get("narration_fit")})
    for iid, pl in placed.items():
        sc = next(s for s in tl["scenes"] if s["id"] == by_id[iid]["scene"])
        if pl.conf > 0 and (pl.start < sc["start"] - 1.0 or pl.end > sc["end"] + 1.0):
            report["warnings"].append(f"{iid}: {pl.start:.2f}-{pl.end:.2f}s cai fora da cena {sc['id']} "
                                      f"({sc['start']:.0f}-{sc['end']:.0f}s) por mais de 1 s")
        if pl.end > tl["duration_s"]:
            report["warnings"].append(f"{iid}: termina em {pl.end:.2f}s, depois do fim do episódio ({tl['duration_s']:.0f}s)")
    report["scenes"] = scene_fit(tl, by_id, order, placed)
    shrunk = [(i, by_id[i]["end"] - by_id[i]["start"], placed[i].end - placed[i].start) for i in order
              if i in placed and by_id[i]["kind"] == "breath" and 0 < placed[i].conf < 0.5
              and (by_id[i]["end"] - by_id[i]["start"]) - (placed[i].end - placed[i].start) > 0.3]
    if shrunk:
        report["warnings"].append("respiração planejada que não está no áudio e ficou mais curta: " + "; ".join(
            f"{i} ({want:.1f} s -> {got:.1f} s)" for i, want, got in shrunk)
            + " (a fala seguinte entra mais cedo; gere a respiração no ElevenLabs ou insira o trecho na edição)")
    for f in report["scenes"]:
        if f["over_window_s"] > 0.3:
            report["warnings"].append(f"cena {f['scene']}: a voz termina {f['over_window_s']:.1f} s depois do fim da cena "
                                      f"({f['window'][1]:.0f} s)")
    items = {}
    for iid in order:
        if iid in placed:
            pl = placed[iid]
            d = {"start": pl.start, "end": pl.end}
            if pl.pauses:
                d["pauses"] = pl.pauses
            d["conf"] = pl.conf
            if pl.note:
                d["note"] = pl.note
            items[iid] = d
    low = [i for i, d in items.items() if 0 < d["conf"] < 0.5]
    if low:
        report["warnings"].append(f"confiança baixa (<0,5) em: {', '.join(low)} — revise com --dry-run e confira no áudio")
    report["estimated"] = {i["id"]: [round(i["start"], 3), round(i["end"], 3)] for i in est}
    report["kinds"] = {i["id"]: i["kind"] for i in est}
    return {"items": items, "report": report, "params": asdict(p), "tracks": [t["path"].name for t in tracks]}


def scene_fit(tl, by_id, order, placed) -> list[dict]:
    """Por cena: quanto o roteiro previu para a voz (1ª fala -> última, com as folgas e trechos mudos planejados) e quanto
    a gravação ocupa de fato; e quanto a voz passa do fim da cena."""
    out = []
    for s in tl["scenes"]:
        sp = [i for i in order if by_id[i]["scene"] == s["id"] and by_id[i]["kind"] == "speech"]
        if not sp or not any(placed[i].conf > 0 for i in sp):
            continue
        budget = by_id[sp[-1]]["end"] - by_id[sp[0]]["start"]
        a, b = placed[sp[0]].start, placed[sp[-1]].end
        syl = sum(w["syl"] for i in sp for w in by_id[i].get("words", []))
        out.append({"scene": s["id"], "window": [s["start"], s["end"]], "voice": [round(a, 2), round(b, 2)],
                    "planned_s": round(budget, 2), "measured_s": round(b - a, 2), "diff_s": round(b - a - budget, 2),
                    "over_window_s": round(max(0.0, b - s["end"]), 2), "syllables": syl,
                    "complete": all(placed[i].conf > 0 for i in sp)})
    return out


def format_fit(result: dict) -> str:
    rows = result["report"].get("scenes", [])
    if not rows:
        return ""
    lines = ["cena  janela      voz medida        previsto  medido   dif.   passa da cena"]
    for f in rows:
        lines.append(f"{f['scene']:<6}{f['window'][0]:>3.0f}–{f['window'][1]:<4.0f}s {f['voice'][0]:>7.2f}–{f['voice'][1]:<7.2f}"
                     f"{f['planned_s']:>9.1f}s{f['measured_s']:>7.1f}s{f['diff_s']:>+7.1f}s"
                     f"{('  +%.1f s' % f['over_window_s']) if f['over_window_s'] > 0.05 else '       -':>14}"
                     + ("" if f["complete"] else "   (incompleta: falta áudio)"))
    return "\n".join(lines)


def _place_breaths(ids, by_id, placed, breath_runs, offset, track_dur, p):
    """Casa os itens `breath` de uma trilha com as respirações detectadas, na folga entre as falas vizinhas."""
    speech_idx = [k for k, i in enumerate(ids) if by_id[i]["kind"] == "speech"]
    bounds = [-1] + speech_idx + [len(ids)]
    for lo_k, hi_k in zip(bounds, bounds[1:]):                                  # folga entre a fala lo_k e a hi_k
        slot = [i for i in ids[lo_k + 1:hi_k] if by_id[i]["kind"] == "breath"]
        if not slot:
            continue
        t0 = (placed[ids[lo_k]].end - offset) if lo_k >= 0 else 0.0
        t1 = (placed[ids[hi_k]].start - offset) if hi_k < len(ids) else track_dur
        runs = [(a, b) for a, b in breath_runs if a >= t0 - 0.05 and b <= t1 + 0.05]
        groups: list = []
        if runs and len(slot) == 1:
            want = by_id[slot[0]]["end"] - by_id[slot[0]]["start"]
            full = (min(a for a, _ in runs), max(b for _, b in runs))
            if full[1] - full[0] <= max(2.2 * want, want + 2.5):               # a respiração inteira, como foi gravada
                span = full
            else:
                span, _ = _union_breath(runs, want)
            groups = [span]
        elif runs:
            runs = sorted(runs)
            if len(runs) >= len(slot):                                          # divide nas (len(slot)-1) maiores folgas
                gaps = sorted(range(len(runs) - 1), key=lambda g: runs[g + 1][0] - runs[g][1], reverse=True)[:len(slot) - 1]
                cuts = sorted(gaps)
                lo = 0
                for c in cuts + [len(runs) - 1]:
                    groups.append((runs[lo][0], runs[c][1]))
                    lo = c + 1
            else:
                groups = [(a, b) for a, b in runs] + [None] * (len(slot) - len(runs))
        else:
            groups = [None] * len(slot)
        cursor = t0
        for iid, g in zip(slot, groups):
            d = by_id[iid]["end"] - by_id[iid]["start"]
            if g is not None:
                placed[iid] = Placed(round(g[0] + offset, 3), round(g[1] + offset, 3), 0.75)
                cursor = g[1]
            else:                                                               # não achou: posição estimada, no meio da folga
                free = max(t1 - cursor, 0.0)
                dur = min(d, max(free - 0.06, 1 / FPS))
                s = cursor + (free - dur) / 2
                placed[iid] = Placed(round(s + offset, 3), round(s + dur + offset, 3), 0.2,
                                     note="respiração não detectada no áudio: posição estimada")
                cursor = s + dur


def _fill_silences_and_fix_order(order, by_id, placed, report, windows=None):
    # trechos mudos (`silence`): duração PREVISTA, encostados no item seguinte (um passageiro que vem pelo corredor dura o que
    # o roteiro diz, não o que sobrou); se a folga for menor, ocupam só ela. Nunca antes da janela da cena.
    windows = windows or {}
    for k, iid in enumerate(order):
        if by_id[iid]["kind"] != "silence" or iid in placed:
            continue
        run = [iid]                                                             # trechos mudos CONSECUTIVOS dividem a mesma folga
        for j in order[k + 1:]:
            if by_id[j]["kind"] != "silence" or j in placed:
                break
            run.append(j)
        prev = next((placed[j].end for j in reversed(order[:k]) if j in placed), by_id[iid]["start"])
        nxt = next((placed[j].start for j in order[k + len(run):] if j in placed), by_id[run[-1]]["end"])
        gap = max(nxt - prev, 0.0)
        planned = sum(by_id[j]["end"] - by_id[j]["start"] for j in run)
        if gap <= planned:                                                      # folga menor que o previsto: ocupa só a folga
            t0, scale = prev, (gap / planned if planned > 0 else 0.0)
        else:                                                                   # folga maior: duração prevista, junto do item seguinte
            t0, scale = nxt - planned, 1.0
            w0 = windows.get(by_id[iid]["scene"], (None, None))[0]
            if w0 is not None and t0 < w0:
                t0 = min(w0, nxt - planned) if nxt - planned < w0 else w0
        cur = t0
        for j in run:
            d = (by_id[j]["end"] - by_id[j]["start"]) * scale
            placed[j] = Placed(round(cur, 3), round(cur + d, 3), 0.5,
                               note="trecho sem voz: duração prevista, junto do item seguinte" if scale == 1.0
                               else "trecho sem voz: ocupa a folga entre as falas vizinhas")
            cur += d
    # ordem crescente e sem sobreposição (o build recusa itens sobrepostos)
    cursor = 0.0
    for iid in order:
        pl = placed.get(iid)
        if pl is None:
            continue
        if pl.start < cursor:
            pl.start = round(cursor, 3)
            pl.note = (pl.note + "; " if pl.note else "") + "início ajustado para não sobrepor o item anterior"
        if pl.end <= pl.start:
            pl.end = round(pl.start + 1 / FPS, 3)
        cursor = pl.end


# ======================================================================================================================
#  Gravação, relatório e comando
# ======================================================================================================================
def write_measured(ep_id: str, result: dict, root: Path = ROOT, force: bool = False) -> Path:
    path = root / ep_id / "narration.measured.json"
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        if not old.get("generated_by") and not force:
            raise AudioError(f"{path.name} já existe e foi escrito à mão; use --force para sobrescrever (salvo uma cópia .bak)")
        shutil.copyfile(path, path.with_suffix(".json.bak"))
    doc = {"generated_by": "python -m pipeline audio", "audio": result["report"]["audio"], "tracks": result["tracks"],
           "params": result["params"], "items": result["items"]}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def format_table(result: dict) -> str:
    rep, items = result["report"], result["items"]
    lines = [f"{'item':<7}{'tipo':<8}{'estimado':>17}{'medido':>17}{'Δini':>8}{'Δfim':>8}{'pausas':>7}{'conf':>6}"]
    for iid, d in items.items():
        es, ee = rep["estimated"][iid]
        lines.append(f"{iid:<7}{rep['kinds'][iid]:<8}{es:>8.2f}–{ee:<7.2f}{d['start']:>8.2f}–{d['end']:<7.2f}"
                     f"{d['start'] - es:>+8.2f}{d['end'] - ee:>+8.2f}{len(d.get('pauses', [])):>7}{d['conf']:>6.2f}")
    return "\n".join(lines)


def resync_summary(before: dict, after: dict, threshold: float = 0.05) -> dict:
    """Compara a linha do tempo estimada com a medida: o que se moveu (beats, cues, passos)."""
    def starts(tl):
        d = {}
        for s in tl["scenes"]:
            for b in s["beats"]:
                d[f"beat {b['id']}"] = b["start"]
        for c in tl["sfx"]["cues"]:
            d[f"cue {c['id']}"] = c["start"]
        return d
    a, b = starts(before), starts(after)
    moved = {k: round(b[k] - a[k], 3) for k in a if k in b and abs(b[k] - a[k]) > threshold}
    steps_b = [s["start"] for s in before["sfx"]["footsteps"]]
    steps_a = [s["start"] for s in after["sfx"]["footsteps"]]
    return {"anchors": len(a), "moved": moved, "max_shift": max((abs(v) for v in moved.values()), default=0.0),
            "steps": len(steps_a), "steps_moved": sum(1 for x, y in zip(steps_b, steps_a) if abs(x - y) > threshold)}


def measured_scene_summary(tl: dict) -> list[dict]:
    """Por cena, com os tempos MEDIDOS: onde a voz começa/termina, ritmo real (sílabas/s) e quanto passa da cena.
    (O `narration_fit` do build é da ESTIMATIVA e não vale mais depois da medição.)"""
    out = []
    for s in tl["scenes"]:
        sp = [i for i in tl["narration"] if i["scene"] == s["id"] and i["kind"] == "speech"]
        words = [w for i in sp for w in i.get("words", [])]
        if not words:
            continue
        syl, talk = sum(w["syl"] for w in words), sum(w["end"] - w["start"] for w in words)
        a, b = sp[0]["start"], sp[-1]["end"]
        out.append({"scene": s["id"], "voice": [round(a, 2), round(b, 2)], "window": [s["start"], s["end"]],
                    "articulation": round(syl / talk, 2) if talk else 0.0, "overall": round(syl / (b - a), 2),
                    "overrun": round(max(0.0, b - s["end"]), 2), "early": round(max(0.0, s["start"] - a), 2)})
    return out


def run(args, root: Path = ROOT) -> int:
    from .build import build_episode
    ep = args.episode
    p = Params()
    if args.min_pause_ms is not None:
        p.min_pause_s = args.min_pause_ms / 1000.0
    try:
        result = analyse_episode(ep, root=root, audio_dir=Path(args.audio_dir) if args.audio_dir else None, params=p)
    except AudioError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    for name, info in result["report"]["audio"].items():
        print(f"{ep}: {name} — {info['duration']} s · fala {info['speech_db']} dB · fundo {info['floor_db']} dB "
              f"· {info['voiced_runs']} trechos de voz, {info['breath_runs']} respirações · início em {info['offset']} s"
              + (" (padrão: 1º item previsto da cena)" if info["offset_default"] else ""))
    print(format_table(result))
    fit = format_fit(result)
    if fit:
        print("\nencaixe por cena (o que o roteiro previu × o que a gravação ocupa):\n" + fit + "\n")
    for w in result["report"]["warnings"]:
        print(f"  AVISO: {w}")
    if args.dry_run:
        print("(--dry-run: nada foi gravado)")
        return 0
    mpath = root / ep / "narration.measured.json"
    previous = mpath.read_text(encoding="utf-8") if mpath.exists() else None
    try:
        path = write_measured(ep, result, root=root, force=args.force)
    except AudioError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    print(f"gravado: {path.relative_to(root)}")
    if args.no_build:
        return 0
    before = build_episode(ep, root=root, write=False, use_measured=False)
    try:
        tl = build_episode(ep, root=root)
    except ValueError as exc:
        print(f"ERRO no build: {exc}", file=sys.stderr)
        if getattr(args, "keep_on_error", False):
            print("(o narration.measured.json foi mantido: --keep-on-error)", file=sys.stderr)
        else:
            if previous is None:
                mpath.unlink(missing_ok=True)
            else:
                mpath.write_text(previous, encoding="utf-8")
            mpath.with_suffix(".json.bak").unlink(missing_ok=True) if previous is None else None
            print("o narration.measured.json NÃO foi mantido (o build falharia com ele): a voz não cabe no episódio "
                  "como está. Veja o resumo por cena acima e use --keep-on-error para guardá-lo assim mesmo.", file=sys.stderr)
        return 1
    rs = resync_summary(before, tl)
    print(f"\n{tl['episode']}: {tl['frames']} frames @{tl['fps']}fps -> {ep}/build/ (voz MEDIDA)")
    for m in measured_scene_summary(tl):
        extra = (f" · PASSA do fim da cena em {m['overrun']} s" if m["overrun"] > 0.3 else "") + \
                (f" · começa {m['early']} s antes da cena" if m["early"] > 0.3 else "")
        print(f"  {m['scene']}  voz {m['voice'][0]:.2f}–{m['voice'][1]:.2f} s (cena {m['window'][0]:.0f}–{m['window'][1]:.0f} s) "
              f"· {m['articulation']} sil/s falando, {m['overall']} sil/s no total{extra}")
    print(f"re-sincronizado: {len(rs['moved'])} de {rs['anchors']} âncoras (beats e cues) se moveram "
          f"(maior deslocamento {rs['max_shift']:.2f} s); {rs['steps_moved']} de {rs['steps']} passos")
    for k, v in sorted(rs["moved"].items(), key=lambda kv: -abs(kv[1]))[:8]:
        print(f"    {k:<28}{v:+.2f} s")
    for w in tl["warnings"]:
        print(f"  AVISO: {w}")
    return 1 if (args.strict and (tl["warnings"] or result["report"]["warnings"])) else 0
