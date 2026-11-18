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

import json
import math
import shutil
import struct
import subprocess
import sys
from array import array
from dataclasses import asdict, dataclass, field
from pathlib import Path

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


def align_speech(durs, est_pos, seg: Segments, p: Params | None = None):
    """Escolhe, entre os cortes candidatos, as N-1 fronteiras que melhor separam as N falas.

    durs    duração esperada de cada fala (incluindo as pausas internas), do roteiro estimado
    est_pos instante estimado do FIM de cada fala (mesmo referencial da estimativa)
    Devolve [(início, fim, confiança)] por fala, no tempo do ARQUIVO de áudio.
    """
    p = p or Params()
    n = len(durs)
    if not seg.voiced:
        raise AudioError("nenhuma fala detectada no áudio")
    t_on, t_off = seg.voiced[0][0], seg.voiced[-1][1]
    if n == 1:
        return [(t_on, t_off, 1.0)]
    est_first = est_pos[0] - durs[0]
    r = (t_off - t_on) / max(est_pos[-1] - est_first, 1e-6)             # ritmo real / estimado
    cuts = [c for c in seg.cuts if c[0] > t_on + p.min_item_s and c[1] < t_off - p.min_item_s]
    if len(cuts) < n - 1:
        raise AudioError(f"o roteiro tem {n} falas mas o áudio só mostra {len(cuts) + 1} trechos separáveis "
                         f"(pausas/vales de energia); há falas coladas sem pausa ou texto diferente do roteiro")
    pred = [t_on + (e - est_first) * r for e in est_pos]               # fim previsto de cada fala
    G = len(cuts)
    INF = float("inf")

    def item_cost(k, start, end):                                       # k = índice da fala (0..n-1)
        d = end - start
        if d < p.min_item_s:
            return INF
        c = p.w_dur * math.log(d / max(durs[k] * r, 1e-3)) ** 2
        if k < n - 1:
            c += p.w_pos * ((end - pred[k]) / p.pos_sigma_s) ** 2
        return c

    # best[k][j]: custo mínimo das falas 0..k, com a fronteira k no corte j
    best = [[INF] * G for _ in range(n - 1)]
    back = [[-1] * G for _ in range(n - 1)]
    for j in range(G):
        best[0][j] = item_cost(0, t_on, cuts[j][0]) - p.w_gap * cuts[j][2]
    for k in range(1, n - 1):
        for j in range(G):
            aj = cuts[j][0]
            for i in range(j):
                if best[k - 1][i] == INF or cuts[i][1] >= aj:
                    continue
                c = best[k - 1][i] + item_cost(k, cuts[i][1], aj) - p.w_gap * cuts[j][2]
                if c < best[k][j]:
                    best[k][j], back[k][j] = c, i
    tail, jl = INF, -1
    for j in range(G):
        if best[n - 2][j] < INF:
            c = best[n - 2][j] + item_cost(n - 1, cuts[j][1], t_off)
            if c < tail:
                tail, jl = c, j
    if jl < 0:
        raise AudioError("não foi possível casar as falas do roteiro com as pausas do áudio")
    chosen = [jl]
    for k in range(n - 2, 0, -1):
        chosen.append(back[k][chosen[-1]])
    chosen.reverse()
    out = []
    for k in range(n):
        s = t_on if k == 0 else cuts[chosen[k - 1]][1]
        e = t_off if k == n - 1 else cuts[chosen[k]][0]
        ls = 1.0 if k == 0 else min(1.0, cuts[chosen[k - 1]][2])
        rs = 1.0 if k == n - 1 else min(1.0, cuts[chosen[k]][2])
        ratio = math.exp(-abs(math.log(max(e - s, 1e-3) / max(durs[k] * r, 1e-3))))
        out.append((s, e, round(max(0.05, min(1.0, (0.5 * ls + 0.5 * rs) * (0.35 + 0.65 * ratio))), 2)))
    return out


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
def find_tracks(audio_dir: Path, scene_ids) -> list[dict]:
    """Descobre as trilhas em `ep0X/audio/`.

    narration.<ext>    UMA trilha do episódio inteiro, com t=0 no início do vídeo (offset 0).
    s1.<ext>, s2.<ext> uma trilha por cena; por padrão o t=0 do arquivo cai no início previsto do 1º item da cena.
    audio/offsets.json {"s2": 18.3, "narration": 0.0}: onde cada arquivo começa NA LINHA DO TEMPO (segundos).
    """
    if not audio_dir.is_dir():
        raise AudioError(f"pasta de áudio não encontrada: {audio_dir}. Coloque lá narration.wav (episódio inteiro) "
                         f"ou um arquivo por cena ({', '.join(f'{s}.wav' for s in scene_ids)}).")
    files = {}
    for f in sorted(audio_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in AUDIO_EXTS:
            if f.stem in files:
                raise AudioError(f"há dois arquivos de áudio para '{f.stem}': {files[f.stem].name} e {f.name}")
            files[f.stem] = f
    offs_file = audio_dir / "offsets.json"
    offsets = json.loads(offs_file.read_text(encoding="utf-8")) if offs_file.exists() else {}
    if "narration" in files:
        extra = [s for s in scene_ids if s in files]
        if extra:
            raise AudioError(f"há narration e também {', '.join(extra)}: escolha UMA forma (episódio inteiro OU por cena)")
        return [{"stem": "narration", "path": files["narration"], "scenes": list(scene_ids), "offset": offsets.get("narration", 0.0),
                 "default_offset": False}]
    found = [s for s in scene_ids if s in files]
    if not found:
        raise AudioError(f"nenhum áudio de narração em {audio_dir}: esperava narration.<ext> ou {', '.join(scene_ids)} (.wav/.mp3/...)")
    unknown = sorted(set(offsets) - set(scene_ids) - {"narration"})
    if unknown:
        raise AudioError(f"offsets.json cita cenas inexistentes: {unknown}")
    return [{"stem": s, "path": files[s], "scenes": [s], "offset": offsets.get(s), "default_offset": s not in offsets} for s in found]


def estimated_items(ep_id: str, root: Path = ROOT):
    """(itens de narração, linha do tempo) ESTIMADOS: ignora o measured.json atual, então reexecutar é estável."""
    from .build import build_episode
    tl = build_episode(ep_id, root=root, write=False, use_measured=False)
    return tl["narration"], tl


def analyse_episode(ep_id: str, root: Path = ROOT, audio_dir: Path | None = None, params: Params | None = None) -> dict:
    """Mede todas as trilhas e devolve {"items": {id: {...}}, "report": {...}} (nada é gravado)."""
    p = params or Params()
    est, tl = estimated_items(ep_id, root)
    ep_dir = root / ep_id
    audio_dir = audio_dir or ep_dir / "audio"
    scene_ids = [s["id"] for s in tl["scenes"]]
    tracks = find_tracks(audio_dir, scene_ids)
    by_id = {i["id"]: i for i in est}
    order = [i["id"] for i in est]
    placed: dict[str, Placed] = {}
    report = {"episode": ep_id, "audio": {}, "warnings": []}

    for tr in tracks:
        ids = [i for i in order if by_id[i]["scene"] in tr["scenes"]]
        speech = [i for i in ids if by_id[i]["kind"] == "speech"]
        if not speech:
            continue
        offset = tr["offset"]
        if offset is None:                                                       # por cena: t=0 do arquivo = 1º item previsto
            offset = by_id[ids[0]]["start"]
        samples, rate = read_audio(tr["path"])
        fr = analyse(samples, rate)
        seg = segment(fr, p)
        info = {"offset": round(offset, 3), "duration": round(fr.duration, 3), "floor_db": round(fr.floor, 1),
                "speech_db": round(fr.ref, 1), "contrast_db": round(fr.ref - fr.floor, 1), "voiced_runs": len(seg.voiced),
                "breath_runs": len(seg.breaths), "cut_candidates": len(seg.cuts), "offset_default": bool(tr["default_offset"])}
        report["audio"][tr["path"].name] = info
        if fr.ref - fr.floor < 20:
            report["warnings"].append(f"{tr['path'].name}: contraste baixo entre fala e ruído de fundo "
                                      f"({fr.ref - fr.floor:.0f} dB); confira o resultado")
        # offset do arquivo -> linha do tempo; o roteiro estimado vive na linha do tempo, então traz-se ele ao arquivo
        durs = [by_id[i]["end"] - by_id[i]["start"] for i in speech]
        ends_est = [by_id[i]["end"] - offset for i in speech]
        spans = align_speech(durs, ends_est, seg, p)
        for sid, (s, e, conf) in zip(speech, spans):
            pauses = [[round(a + offset, 3), round(b + offset, 3)] for a, b in seg.gaps
                      if a >= s - 1e-6 and b <= e + 1e-6 and b - a >= p.min_pause_s]
            placed[sid] = Placed(round(s + offset, 3), round(e + offset, 3), conf, pauses=pauses)
        # ---- respirações: ficam nas folgas entre as falas (script order) ----
        _place_breaths(ids, by_id, placed, seg.breaths, offset, fr.duration, p)

    # ---- trechos mudos e o que sobrou: preenchem as folgas entre vizinhos; depois, ordem e sobreposição ----
    _fill_silences_and_fix_order(order, by_id, placed, report)
    for iid in order:
        if iid not in placed:
            report["warnings"].append(f"{iid}: sem áudio correspondente; mantido na posição estimada (pode sobrepor vizinhos)")
    for iid, pl in placed.items():
        sc = next(s for s in tl["scenes"] if s["id"] == by_id[iid]["scene"])
        if pl.start < sc["start"] - 1.0 or pl.end > sc["end"] + 1.0:
            report["warnings"].append(f"{iid}: {pl.start:.2f}-{pl.end:.2f}s cai fora da cena {sc['id']} "
                                      f"({sc['start']:.0f}-{sc['end']:.0f}s) por mais de 1 s")
        if pl.end > tl["duration_s"]:
            report["warnings"].append(f"{iid}: termina em {pl.end:.2f}s, depois do fim do episódio ({tl['duration_s']:.0f}s)")
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
    low = [i for i, d in items.items() if d["conf"] < 0.5]
    if low:
        report["warnings"].append(f"confiança baixa (<0,5) em: {', '.join(low)} — revise com --dry-run e confira no áudio")
    report["estimated"] = {i["id"]: [round(i["start"], 3), round(i["end"], 3)] for i in est}
    report["kinds"] = {i["id"]: i["kind"] for i in est}
    return {"items": items, "report": report, "params": asdict(p), "tracks": [t["path"].name for t in tracks]}


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
            span, _ = _union_breath(runs, by_id[slot[0]]["end"] - by_id[slot[0]]["start"])
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


def _fill_silences_and_fix_order(order, by_id, placed, report):
    # trechos mudos (`silence`): ocupam a folga entre o vizinho anterior e o seguinte já medidos
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
        share = max(nxt - prev, 0.0) / len(run)
        for q, j in enumerate(run):
            placed[j] = Placed(round(prev + q * share, 3), round(prev + (q + 1) * share, 3), 0.5,
                               note="trecho sem voz: ocupa a folga entre as falas vizinhas")
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
    for w in result["report"]["warnings"]:
        print(f"  AVISO: {w}")
    if args.dry_run:
        print("(--dry-run: nada foi gravado)")
        return 0
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
