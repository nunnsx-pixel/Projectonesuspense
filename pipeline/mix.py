"""Mixagem final de um episódio: voz medida + SFX sintetizados, tudo preso à linha do tempo.

  python -m pipeline mix ep01          # grava ep01/build/ep01.mix.wav (estéreo, 48 kHz, 60,000 s)

O QUE ENTRA
  * a voz de `ep0X/audio/` na posição em que o `narration.measured.json` a mediu (`audio.<arquivo>.offset`), com o ganho
    nivelado pela medição (`speech_db`) e as automações do roteiro (`sfx.mix.narration_gain_db`);
  * as camas e os sons pontuais de `timeline.json > sfx.cues` (ganho, fade e loop do cue sheet);
  * passos, batidas da estrada, falhas de luz e batimentos, cada um no seu instante e com o seu ganho;
  * a automação de ambiência do episódio (`sfx.mix.ambience_gain_db`) e o corte seco do Ep. 3 (silêncio absoluto).

OS SONS SÃO SINTETIZADOS (ruído filtrado, senos, envelopes) — servem de MARCADOR FINAL de timbre e de nível, não de
foley gravado: troque qualquer um por um arquivo de biblioteca sem mexer na sincronia (veja `RECIPES`). A mixagem é
determinística (semente por cue). Precisa de numpy e, para ler mp3, do ffmpeg.
"""
from __future__ import annotations

import csv
import json
import math
import subprocess
import wave
import zlib
from pathlib import Path

try:
    import numpy as np
except ImportError:                                            # pragma: no cover
    np = None

from .timeline import FPS, ROOT

SR = 48000
VOICE_REF_DB = -14.0          # nível (10 ms) dos trechos mais fortes da voz após o nivelamento
BED_RMS_DB = -18.0            # RMS de cada cama com ganho 0 dB (o `gain_db` do cue sheet vale a partir daqui)
ONESHOT_PEAK_DB = -3.0        # pico de cada som pontual com ganho 0 dB


class MixError(Exception):
    pass


# ---- ferramentas -----------------------------------------------------------------------------------------------------
def _need_numpy():
    if np is None:
        raise MixError("a mixagem precisa do numpy (pip install numpy)")


def _rng(key: str):
    return np.random.default_rng(zlib.crc32(key.encode()))


def _db(x: float) -> float:
    return 10 ** (x / 20.0)


def _n(sec: float) -> int:
    return max(int(round(sec * SR)), 1)


def _shape(x, lo=None, hi=None, order=2):
    """Passa-faixa por FFT (lo = corta graves, hi = corta agudos)."""
    f = np.fft.rfftfreq(len(x), 1.0 / SR)
    g = np.ones_like(f)
    if hi:
        g = g / np.sqrt(1.0 + (f / hi) ** (2 * order))
    if lo:
        g = g / np.sqrt(1.0 + (lo / np.maximum(f, 1e-3)) ** (2 * order))
    return np.fft.irfft(np.fft.rfft(x) * g, len(x)).astype(np.float32)


def _noise(r, n, lo=None, hi=None):
    return _shape(r.standard_normal(n).astype(np.float32), lo, hi)


def _rms_norm(x, db):
    r = float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) or 1.0
    return (x * (_db(db) / r)).astype(np.float32)


def _peak_norm(x, db):
    p = float(np.max(np.abs(x))) or 1.0
    return (x * (_db(db) / p)).astype(np.float32)


def _exp(n, tau, attack=0.002):
    t = np.arange(n, dtype=np.float32) / SR
    return (np.exp(-t / tau) * np.minimum(1.0, t / max(attack, 1e-4))).astype(np.float32)


def _sine(n, f0, f1=None, phase=0.0):
    t = np.arange(n, dtype=np.float64) / SR
    f = f0 if f1 is None else f0 + (f1 - f0) * t / max(t[-1], 1e-9)
    return np.sin(2 * np.pi * np.cumsum(np.broadcast_to(f, t.shape)) / SR + phase).astype(np.float32)


def _slow(r, n, rate_hz, lo=0.0, hi=1.0):
    """Curva lenta aleatória em [lo, hi] (interpolação de pontos sorteados)."""
    k = max(int(n / SR * rate_hz) + 2, 2)
    pts = r.uniform(lo, hi, k).astype(np.float32)
    return np.interp(np.linspace(0, k - 1, n), np.arange(k), pts).astype(np.float32)


def _curve(points, t):
    """Automação por pontos [[t, valor]...] avaliada em `t` (array)."""
    xs, ys = zip(*points)
    return np.interp(t, xs, ys).astype(np.float32)


def _sum(*parts):
    """Soma sinais de durações diferentes (o mais curto é completado com zeros)."""
    n = max(len(p) for p in parts)
    out = np.zeros(n, np.float32)
    for p in parts:
        out[:len(p)] += p
    return out


# ---- sons pontuais (mono, pico normalizado depois) -------------------------------------------------------------------
def thump(r, f0=70.0, f1=38.0, tau=0.12, dur=0.5, click=0.25, click_hi=2500.0):
    n = _n(dur)
    body = _sine(n, f0, f1) * _exp(n, tau)
    tk = _noise(r, n, hi=click_hi) * _exp(n, 0.012, 0.0005) * click
    return body + tk


def step_hard(r, k=1.0):
    n = _n(0.45)
    x = thump(r, 95, 60, 0.05, 0.45, 0.9, 6000)
    tail = _noise(r, n, lo=300, hi=3500) * _exp(n, 0.16) * 0.10                 # saguão grande: um resto de reverb
    return x + tail


def step_metal(r, k=1.0):
    n = _n(0.5)
    x = thump(r, 110, 70, 0.04, 0.5, 0.7, 5000)
    ring = sum(_sine(n, f) * a for f, a in ((640, 0.5), (1180, 0.35), (1960, 0.25), (3100, 0.12))) * _exp(n, 0.14, 0.001)
    return x + ring * 0.5


def step_rubber(r, k=1.0):
    return thump(r, 80, 50, 0.06, 0.35, 0.35, 900)


def step_wet(r, k=1.0):
    n = _n(0.4)
    return thump(r, 70, 45, 0.08, 0.4, 0.5, 1400) + _noise(r, n, lo=200, hi=1200) * _exp(n, 0.07) * 0.6


def step_heavy(r, k=1.0):
    return thump(r, 62, 38, 0.1, 0.5, 0.45, 1200)


def beep(r, k=1.0):
    n = _n(0.16)
    return (_sine(n, 2400) + 0.3 * _sine(n, 4800)) * np.minimum(1, np.arange(n) / (0.004 * SR)) * np.minimum(1, (n - np.arange(n)) / (0.01 * SR))


def ratchet(r, k=1.0):
    n = _n(0.7)
    x = np.zeros(n, np.float32)
    for i in range(7):
        a = int(i * 0.075 * SR)
        c = thump(r, 520, 300, 0.012, 0.06, 0.8, 4000)
        x[a:a + len(c)] += c[:n - a] * (1.0 - 0.05 * i)
    return x + _noise(r, n, lo=200, hi=1800) * np.hanning(n) * 0.18


def seat_thud(r, k=1.0):
    n = _n(0.7)
    return _sum(thump(r, 62, 40, 0.1, 0.7, 0.2, 900), _noise(r, n, lo=150, hi=2500) * _exp(n, 0.2, 0.01) * 0.5, 0.15 * creak(r, 0.5))


def creak(r, dur=0.6, f=520.0):
    n = _n(dur)
    fm = f * (1.0 + 0.35 * _slow(r, n, 9, -1, 1))
    ph = 2 * np.pi * np.cumsum(fm.astype(np.float64)) / SR
    x = (np.sin(ph) + 0.5 * np.sin(2.01 * ph) + 0.3 * np.sin(3.02 * ph)).astype(np.float32)
    return x * np.hanning(n) * (0.5 + 0.5 * _slow(r, n, 22, 0, 1))


def jingle(r, k=1.0):
    n = _n(0.9)
    x = thump(r, 80, 50, 0.05, 0.9, 0.2, 1200) * 0.6
    for i in range(9):
        a = int(r.uniform(0.0, 0.7) * SR)
        c = sum(_sine(_n(0.25), f) for f in r.uniform(2500, 6500, 2)) * _exp(_n(0.25), 0.05, 0.0005)
        x[a:a + len(c)] += c[:n - a] * r.uniform(0.2, 0.5)
    return x


def crack(r, k=1.0):
    n = _n(0.5)
    x = thump(r, 140, 80, 0.03, 0.5, 0.1, 800) * 0.4
    for a in (0.0, 0.05, 0.11, 0.16):
        c = _noise(r, _n(0.03), lo=800, hi=5000) * _exp(_n(0.03), 0.006, 0.0003)
        i = int(a * SR)
        x[i:i + len(c)] += c * r.uniform(0.7, 1.0)
    return x


def wet_slap(r, k=1.0):
    n = _n(0.6)
    x = thump(r, 90, 55, 0.07, 0.6, 0.3, 1500) + _noise(r, n, lo=250, hi=1500) * _exp(n, 0.1) * 0.7
    for a in (0.04, 0.09):
        i = int(a * SR)
        c = _noise(r, _n(0.02), lo=1500, hi=4500) * _exp(_n(0.02), 0.004, 0.0003)
        x[i:i + len(c)] += c * 0.5
    return x


def click(r, k=1.0):
    n = _n(0.18)
    x = np.zeros(n, np.float32)
    for a in (0.0, 0.07):
        c = _noise(r, _n(0.02), lo=1500, hi=7000) * _exp(_n(0.02), 0.004, 0.0003) + 0.4 * _sine(_n(0.02), 2200) * _exp(_n(0.02), 0.006)
        i = int(a * SR)
        x[i:i + len(c)] += c
    return x


def hiss(r, dur=1.6):
    n = _n(dur)
    return _noise(r, n, lo=1800, hi=9000) * (_exp(n, dur * 0.45, 0.01) + 0.15 * np.hanning(n))


def screech(r, dur=0.6):
    n = _n(dur)
    sweep = _sine(n, 2800, 1300) + 0.5 * _sine(n, 5600, 2600) + 0.5 * _sine(n, 900, 400)
    bite = _noise(r, n, lo=800, hi=8000) * 0.6
    body = thump(r, 60, 35, 0.2, dur, 0.3, 1500)
    return (sweep * 0.7 + bite) * np.maximum(_exp(n, dur * 0.8, 0.003), 0.15) + body


def bum(r, dur=2.2):
    n = _n(dur)
    x = thump(r, 58, 28, 0.35, dur, 0.5, 1800) * 1.0
    x += _noise(r, n, lo=60, hi=500) * _exp(n, 0.5, 0.001) * 0.9                     # suspensão batendo
    x += creak(r, dur, 380) * _exp(n, 1.0, 0.02) * 0.25
    return x


def glitch_pop(r, k=1.0):
    n = _n(0.12)
    return _noise(r, n, lo=900, hi=8000) * _exp(n, 0.02, 0.0005)


def heart(r, k=1.0):
    n = _n(0.5)
    x = thump(r, 58, 40, 0.07, 0.5, 0.0)
    d = thump(r, 52, 36, 0.06, 0.5, 0.0) * 0.7
    i = int(0.19 * SR)
    x[i:] += d[:n - i]
    return x


SHOT = {   # id/tag -> gerador (a duração e o timbre ficam aqui; ganho e instante vêm do cue sheet)
    "bip-catraca": beep, "catraca-giro": ratchet, "sentar-banco": seat_thud, "mochila-banco": jingle,
    "estalo-pescoco": crack, "costas-divisoria": lambda r, k=1: _sum(thump(r, 95, 55, 0.09, 0.6, 0.6, 3000), 0.4 * creak(r, 0.5, 700)),
    "mao-balaustre": lambda r, k=1: creak(r, 0.45, 780) * 0.6 + _noise(r, _n(0.45), lo=300, hi=2500) * np.hanning(_n(0.45)) * 0.2,
    "mao-ombro": wet_slap, "botao-vermelho": click, "freada-metal": screech, "bum-buraco": bum,
    "porta-pneumatica": hiss, "metal-rangendo-bum": lambda r, k=1: creak(r, 2.9, 430) * 0.8 + creak(r, 2.9, 910) * 0.4,
}
STEP = {"passos-corrida-saguao": step_hard, "passos-degrau-metal": step_metal, "passos-onibus-borracha": step_rubber,
        "passos-pesados-borracha": step_heavy}


def _shot_for(cue_id: str):
    for key, fn in SHOT.items():
        if cue_id == key or cue_id.startswith(key + "-") or cue_id.rstrip("0123456789-") == key:
            return fn
    return None


# ---- camas (estéreo, com a duração do cue) ---------------------------------------------------------------------------
def bed_hum(r, n, ch, base=60.0, noise_hi=2500):
    t = np.arange(n) / SR
    wob = 1 + 0.02 * _slow(r, n, 0.7, -1, 1)
    hum = sum(np.sin(2 * np.pi * base * h * t * wob + h) / h for h in (1, 2, 3, 5))
    return (0.6 * hum + _noise(r, n, lo=80, hi=noise_hi)).astype(np.float32)


def bed_wind(r, n, ch, lo=300, hi=1800):
    x = _noise(r, n, lo=lo, hi=hi)
    howl = _sine(n, 520 + 60 * ch, 640)
    return x * (0.5 + 0.5 * _slow(r, n, 0.4, 0, 1)) + 0.25 * howl * _slow(r, n, 0.6, 0, 1)


def bed_gravel(r, n, ch):
    x = _noise(r, n, lo=900, hi=6000)
    pops = (r.random(n) > 0.9992).astype(np.float32)
    pops = _shape(pops * r.standard_normal(n).astype(np.float32) * 6, lo=1500, hi=7000)
    return x * 0.35 * (0.6 + 0.4 * _slow(r, n, 6, 0, 1)) + pops


def bed_static(r, n, ch, lo=1500, hi=9000):
    return _noise(r, n, lo=lo, hi=hi) * (0.5 + 0.5 * _slow(r, n, 7, 0, 1))


def bed_radio(r, n, ch):
    x = _noise(r, n, lo=300, hi=3200) * (0.5 + 0.5 * _slow(r, n, 5, 0, 1))
    crackle = _shape((r.random(n) > 0.9995).astype(np.float32) * 5 * r.standard_normal(n).astype(np.float32), lo=500, hi=5000)
    return x + crackle + 0.05 * _sine(n, 1000)


def bed_murmur(r, n, ch):
    x = np.zeros(n, np.float32)
    for f in (180, 320, 540, 780):
        band = _noise(r, n, lo=f * 0.8, hi=f * 1.3)
        x += band * np.maximum(_slow(r, n, 3.5 + r.random() * 2, -0.3, 1.0), 0)
    return x


def bed_creak(r, n, ch):
    out = np.zeros(n, np.float32)
    k = max(int(n / SR * 0.9), 1)
    for _ in range(k):
        c = creak(r, r.uniform(0.25, 0.9), r.uniform(280, 900))
        a = int(r.uniform(0, max(n - len(c), 1)))
        out[a:a + len(c)] += c[:n - a] * r.uniform(0.2, 0.8)
    return out + _noise(r, n, lo=40, hi=400) * (0.3 + 0.7 * _slow(r, n, 2, 0, 1))


BED = {
    "amb-rodoviaria": lambda r, n, ch: bed_hum(r, n, ch, 120.0, 1800),
    "zumbido-eletrico": lambda r, n, ch: bed_hum(r, n, ch, 60.0, 4000),
    "vento-frestas": bed_wind, "vento-forte": lambda r, n, ch: bed_wind(r, n, ch, 200, 3000),
    "cascalho-pneus": bed_gravel, "chiado-celular": bed_static, "radio-am": bed_radio, "murmurios-neblina": bed_murmur,
    "chassi-rangendo": bed_creak, "chassi-balancando": bed_creak,
}


def engine(r, n, speed_kmh, muffle):
    """Motor diesel: fundamental e harmônicos seguem a velocidade; `muffle` (0..1) fecha o filtro."""
    t = np.arange(n) / SR
    f0 = 22.0 + 0.55 * np.interp(t, np.arange(len(speed_kmh)) / FPS, speed_kmh)
    ph = 2 * np.pi * np.cumsum(f0.astype(np.float64)) / SR
    x = sum(np.sin(h * ph + h) / (h ** 0.9) for h in range(1, 10)).astype(np.float32)
    x *= 0.65 + 0.35 * np.sin(ph * 0.5)                                             # irregularidade das explosões
    rumble = _noise(r, n, lo=20, hi=220) * 1.6
    full = x + rumble + 0.18 * _noise(r, n, lo=700, hi=3500)
    dull = _shape(full, hi=170)
    return (full * (1.0 - muffle) + dull * muffle).astype(np.float32)


def _decode(path: Path):
    """Mono float32 a 48 kHz (ffmpeg lê mp3/wav/etc)."""
    try:
        out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                             capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        raise MixError(f"não consegui decodificar {path.name} (precisa do ffmpeg): {e}")
    return np.frombuffer(out, dtype="<f4").copy()


# ---- a mixagem -------------------------------------------------------------------------------------------------------
def _add(buf, x, t0, gain=1.0):
    """Soma `x` (n) ou (2, n) em `buf` (2, N) a partir de t0 segundos (recorta o que passa das bordas)."""
    i0 = int(round(t0 * SR))
    if x.ndim == 1:
        x = np.stack([x, x])
    a, b = max(i0, 0), min(i0 + x.shape[1], buf.shape[1])
    if b > a:
        buf[:, a:b] += x[:, a - i0:b - i0] * gain


def _fade(x, t_in, t_out):
    n = x.shape[-1]
    env = np.ones(n, np.float32)
    if t_in and t_in > 0:
        k = min(_n(t_in), n)
        env[:k] = np.linspace(0, 1, k, dtype=np.float32)
    if t_out and t_out > 0:
        k = min(_n(t_out), n)
        env[n - k:] *= np.linspace(1, 0, k, dtype=np.float32)
    return x * env


def _camera_columns(root: Path, ep: str, cols):
    path = root / ep / "build" / f"{ep}.camera.csv"
    if not path.exists():
        raise MixError(f"{path} não existe: rode `python -m pipeline build {ep}` antes")
    out = {c: [] for c in cols}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for c in cols:
                out[c].append(float(row[c]))
    return {c: np.array(v, np.float32) for c, v in out.items()}


def mix_episode(ep: str, root: Path = ROOT, audio_dir: Path | None = None, with_voice: bool = True) -> dict:
    """Devolve {"audio": (2, N) float32, "report": {...}}; nada é gravado."""
    _need_numpy()
    tl = json.loads((root / ep / "build" / f"{ep}.timeline.json").read_text(encoding="utf-8"))
    dur = float(tl["duration_s"])
    N = _n(dur)
    sfx = tl["sfx"]
    cam = _camera_columns(root, ep, ("speed_kmh", "black"))
    speed = cam["speed_kmh"]
    voice, beds, shots, hum = (np.zeros((2, N), np.float32) for _ in range(4))
    report = {"episode": ep, "voice": {}, "unknown_cues": [], "missing_voice": []}
    t_axis = np.arange(N) / SR

    # -- voz
    measured_p = root / ep / "narration.measured.json"
    audio_dir = audio_dir or root / ep / "audio"
    if with_voice and measured_p.exists():
        meas = json.loads(measured_p.read_text(encoding="utf-8")).get("audio", {})
        for name, info in sorted(meas.items()):
            f = audio_dir / name
            if not f.is_file():
                report["missing_voice"].append(name)
                continue
            x = _decode(f) * _db(VOICE_REF_DB - info["speech_db"])
            _add(voice, x, info["offset"])
            report["voice"][name] = {"offset": info["offset"], "gain_db": round(VOICE_REF_DB - info["speech_db"], 1)}
    elif with_voice:
        report["missing_voice"].append("(sem narration.measured.json)")
    gcurve = sfx.get("mix", {}).get("narration_gain_db")
    if gcurve:
        voice *= _db_curve(gcurve, t_axis)

    # -- camas e sons pontuais do cue sheet
    for c in sfx["cues"]:
        r = _rng(f"{ep}/{c['id']}")
        g = _db(c["gain_db"])
        t0, t1 = float(c["start"]), float(c["end"])
        shot = _shot_for(c["id"])
        bed = BED.get(c["id"])
        if c["id"] == "motor-onibus":
            n = _n(t1 - t0)
            tt = t0 + np.arange(n) / SR
            if ep == "ep01":
                muffle = _curve([[t0, 0.0], [36.0, 0.15], [59.5, 1.0]], tt)               # abafa enquanto o sono chega
            elif ep == "ep02":
                black = np.interp(tt, np.arange(len(cam["black"])) / FPS, cam["black"])
                muffle = np.clip(1.0 - _smooth_open(black, 0.4), 0, 1)                       # abafado na tela preta, abre no BUM
            else:
                muffle = np.zeros(n, np.float32)
            x = np.stack([engine(r, n, speed[int(t0 * FPS):] if int(t0 * FPS) < len(speed) else speed, muffle) for _ in (0, 1)])
            x = _rms_norm(x, BED_RMS_DB) * g
            _add(beds, _fade(x, c.get("fade_in"), c.get("fade_out")), t0)
        elif bed is not None:
            n = _n(t1 - t0)
            x = np.stack([bed(r, n, 0), bed(r, n, 1)])
            x = _rms_norm(x, BED_RMS_DB) * g
            if c["id"] == "radio-am":                                                      # cresce com os estalos do pescoço
                tt = t0 + np.arange(n) / SR
                x = x * _curve([[t0, 0.5], [20.8, 0.6], [22.8, 1.6], [t1, 1.0]], tt)
            _add(hum if c["id"] == "zumbido-eletrico" else beds, _fade(x, c.get("fade_in"), c.get("fade_out")), t0)
        elif shot is not None:
            x = _peak_norm(shot(r), ONESHOT_PEAK_DB) * g
            if c["id"] in ("porta-pneumatica", "metal-rangendo-bum", "freada-metal"):
                x = _fade(x, 0, c.get("fade_out"))
            _add(shots, x, t0)
        elif c["id"] == "passos-passageiro":                                                # passos rápidos do passageiro
            k = max(int((t1 - t0) / 0.23), 1)
            for i in range(k):
                _add(shots, _peak_norm(step_wet(r), ONESHOT_PEAK_DB) * g * (0.35 + 0.65 * (i + 1) / k), t0 + i * (t1 - t0) / k)
        else:
            report["unknown_cues"].append(c["id"])

    # -- eventos gerados (passos, batidas, falhas de luz, batimentos)
    for s in sfx.get("footsteps", []):
        fn = STEP.get(s.get("tag"), step_rubber)
        r = _rng(f"{ep}/{s['id']}")
        _add(shots, _peak_norm(fn(r), ONESHOT_PEAK_DB) * _db(s["gain_db"]), s["start"])
    for b in sfx.get("bumps", []):
        r = _rng(f"{ep}/{b['id']}")
        x = _sum(thump(r, 66, 34, 0.14, 0.7, 0.35, 1200), 0.5 * creak(r, 0.5, 340) * _exp(_n(0.5), 0.2))
        _add(shots, _peak_norm(x, ONESHOT_PEAK_DB) * _db(b["gain_db"]), b["start"])
    for h in sfx.get("heartbeat", []):
        r = _rng(f"{ep}/{h['id']}")
        _add(shots, _peak_norm(heart(r), ONESHOT_PEAK_DB) * _db(h["gain_db"]), h["start"])
    for fl in sfx.get("flicker", []):                                                     # a lâmpada cai: corta o zumbido e estala
        r = _rng(f"{ep}/{fl['id']}")
        a, b = int(fl["start"] * SR), int(max(fl["end"], fl["start"] + 0.05) * SR)
        hum[:, a:b] *= 1.0 - 0.9 * float(fl.get("depth", 1.0))
        for edge in (fl["start"], max(fl["end"], fl["start"] + 0.05)):
            _add(shots, _peak_norm(glitch_pop(r), ONESHOT_PEAK_DB) * _db(fl["gain_db"]), edge)

    beds += hum
    amb = sfx.get("mix", {}).get("ambience_gain_db")
    if amb:
        beds *= _db_curve(amb, t_axis)

    # -- soma, corte seco (Ep. 3) e limitador
    out = voice + beds + shots
    cut = _cut_time(tl)
    if cut is not None:
        i = int(cut * SR)
        keep = _peak_after_cut(shots, ep, sfx, cut)
        fade = _n(0.004)
        out[:, i - fade:i] *= np.linspace(1, 0, fade, dtype=np.float32)
        out[:, i:] = 0.0
        out += keep
    peak_raw = float(np.max(np.abs(out)))
    out = np.tanh(out * 0.9) / np.tanh(0.9)                                                # limitador suave
    pk = float(np.max(np.abs(out)))
    if pk > _db(-1.0):
        out *= _db(-1.0) / pk
    report["peak_raw_dbfs"] = round(20 * math.log10(max(peak_raw, 1e-9)), 1)
    report["peak_dbfs"] = round(20 * math.log10(max(float(np.max(np.abs(out))), 1e-9)), 1)
    report["rms_dbfs"] = round(20 * math.log10(max(float(np.sqrt(np.mean(out.astype(np.float64) ** 2))), 1e-9)), 1)
    report["seconds"] = round(out.shape[1] / SR, 3)
    return {"audio": out.astype(np.float32), "report": report}


def _db_curve(points, t):
    xs, ys = zip(*points)
    return (10 ** (np.interp(t, xs, ys) / 20.0)).astype(np.float32)


def _smooth_open(black, tau):
    """1 = aberto: a tela preta fecha o abafamento, ao abrir sobe suave."""
    open_ = 1.0 - black.astype(np.float32)
    k = max(int(tau * SR), 1)
    c = np.concatenate([[0.0], np.cumsum(open_, dtype=np.float64)])
    idx = np.arange(len(open_))
    lo, hi = np.clip(idx - k // 2, 0, len(open_)), np.clip(idx + k // 2, 0, len(open_))
    return ((c[hi] - c[lo]) / np.maximum(hi - lo, 1)).astype(np.float32)


def _cut_time(tl):
    for c in tl["sfx"]["cues"]:
        if c["id"] == "freada-metal":
            return float(c["start"])
    return None


def _peak_after_cut(shots, ep, sfx, cut):
    """O som do corte seco (freada) sobrevive ao corte: só ele existe a partir de `cut`."""
    keep = np.zeros_like(shots)
    r = _rng(f"{ep}/freada-metal")
    for c in sfx["cues"]:
        if c["id"] == "freada-metal":
            x = _fade(_peak_norm(screech(r), ONESHOT_PEAK_DB) * _db(c["gain_db"]), 0, c.get("fade_out"))
            _add(keep, x, c["start"])
    return keep


def write_wav(path: Path, audio) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1.0, 1.0).T * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path


def run(args, root: Path = ROOT) -> int:
    """`python -m pipeline mix epXX [--no-voice]` -> epXX/build/epXX.mix.wav"""
    try:
        res = mix_episode(args.episode, root, with_voice=not args.no_voice)
    except MixError as e:
        print(f"mix: {e}")
        return 1
    rep = res["report"]
    out = write_wav(root / args.episode / "build" / f"{args.episode}.mix.wav", res["audio"])
    print(f"{args.episode}: {out.relative_to(root)} · {rep['seconds']} s · pico {rep['peak_dbfs']} dBFS · RMS {rep['rms_dbfs']} dBFS")
    for name, v in rep["voice"].items():
        print(f"  voz {name:24s} entra em {v['offset']:7.3f} s (ganho {v['gain_db']:+.1f} dB)")
    for name in rep["missing_voice"]:
        print(f"  AVISO: sem áudio de voz: {name} (a mixagem sai só com SFX)")
    for cid in rep["unknown_cues"]:
        print(f"  AVISO: cue sem receita de som (ficou mudo): {cid}")
    return 0
