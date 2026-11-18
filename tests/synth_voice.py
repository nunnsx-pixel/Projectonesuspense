"""Voz SINTÉTICA para testar a análise de áudio (não é fala de verdade: tom harmônico modulado em sílabas).

`perturb()` parte da linha do tempo ESTIMADA e sorteia uma "gravação" plausível (ritmo por cena, folgas entre falas,
respirações) com os tempos exatos conhecidos; `render()` converte isso em amostras; `write_wav()` grava. Assim o teste sabe o
gabarito e confere se a análise recupera início/fim/pausas.
"""
from __future__ import annotations

import math
import random
import wave
from array import array
from pathlib import Path

RATE = 8000
SPEECH_AMP = 0.30            # ~ -10 dBFS


def perturb(items, seed: int = 1, duration: float = 59.0, rate_range=(0.92, 1.12), gap_range=(0.15, 0.9),
            lead_range=(-0.2, 0.4), gap_scale=(0.5, 1.8)):
    """Devolve os itens com tempos novos (gabarito): [{id, kind, start, end, words:[(a,b)], pitch, type}]."""
    rnd = random.Random(seed)
    out, cursor, scene, k_scene, prev_end_est = [], None, None, 1.0, None
    for it in items:
        if it["scene"] != scene:
            scene, k_scene = it["scene"], rnd.uniform(*rate_range)
        gap_est = 0.0 if prev_end_est is None else max(it["start"] - prev_end_est, 0.0)
        if cursor is None:
            cursor = it["start"] + rnd.uniform(*lead_range)
        else:
            cursor += min(max(gap_est * rnd.uniform(*gap_scale), gap_range[0]), gap_range[1]) if gap_est >= 0.0 else 0.0
        dur_est = it["end"] - it["start"]
        scale = k_scene * (rnd.uniform(0.93, 1.07) if it["kind"] != "silence" else rnd.uniform(0.8, 1.2))
        s, e = cursor, cursor + dur_est * scale
        words = [(s + (w["start"] - it["start"]) * scale, s + (w["end"] - it["start"]) * scale) for w in it.get("words", [])]
        out.append({"id": it["id"], "kind": it["kind"], "start": s, "end": e, "words": words, "type": it.get("type"),
                    "speaker": it.get("speaker"), "pitch": 85.0 if it.get("speaker") == "motorista" else 120.0})
        cursor, prev_end_est = e, it["end"]
    if out[-1]["end"] > duration:                                       # comprime para caber no episódio
        f = (duration - out[0]["start"]) / (out[-1]["end"] - out[0]["start"])
        t0 = out[0]["start"]
        for o in out:
            o["start"], o["end"] = t0 + (o["start"] - t0) * f, t0 + (o["end"] - t0) * f
            o["words"] = [(t0 + (a - t0) * f, t0 + (b - t0) * f) for a, b in o["words"]]
    for o in out:
        if o["kind"] == "speech" and o["words"]:                        # o item vale do 1º ao último som
            o["start"], o["end"] = o["words"][0][0], o["words"][-1][1]
        o["pauses"] = [(a[1], b[0]) for a, b in zip(o["words"], o["words"][1:]) if b[0] - a[1] >= 0.1]
    return out


def render(truth, duration: float, rate: int = RATE, floor: float = 0.0005, breath_amp: float = 0.012, seed: int = 7):
    """Amostras (array 'h') da gravação sintética. floor=0 -> silêncio digital entre as falas (como alguns TTS)."""
    rnd = random.Random(seed)
    n = int(duration * rate)
    buf = [rnd.gauss(0.0, floor) for _ in range(n)] if floor > 0 else [0.0] * n
    two_pi = 2 * math.pi

    def tone(a, b, f0, amp):
        i0, i1 = int(a * rate), min(n, int(b * rate))
        ph = rnd.uniform(0, two_pi)
        for i in range(i0, i1):
            t = i / rate
            edge = min(1.0, (t - a) / 0.008, (b - t) / 0.008)
            syl = 0.30 + 0.70 * (0.5 + 0.5 * math.sin(two_pi * 5.0 * t + ph)) ** 0.7        # sílabas: o nível oscila, mas não zera
            w = two_pi * f0 * t
            buf[i] += amp * edge * syl * (math.sin(w) + 0.5 * math.sin(2 * w) + 0.3 * math.sin(3 * w)) / 1.8

    def noise(a, b, amp):
        i0, i1 = int(a * rate), min(n, int(b * rate))
        for i in range(i0, i1):
            t = i / rate
            env = math.sin(math.pi * (t - a) / max(b - a, 1e-6)) ** 2
            buf[i] += amp * env * rnd.gauss(0.0, 1.0)

    for it in truth:
        if it["kind"] == "speech":
            ws = it["words"]
            for k, (a, b) in enumerate(ws):
                nxt = ws[k + 1][0] if k + 1 < len(ws) else None
                end = b - 0.02 if (nxt is not None and nxt - b < 0.05) else b            # fronteira de palavra sem pausa: vale curto
                tone(a, max(end, a + 0.03), it["pitch"], SPEECH_AMP)
        elif it["kind"] == "breath":
            cycles = {"pant": 3, "hyperventilate": 5}.get(it.get("type"), 1)
            span = (it["end"] - it["start"]) / cycles
            for c in range(cycles):
                a = it["start"] + c * span
                noise(a, a + (span * 0.65 if cycles > 1 else span), breath_amp)
    peak = max(1e-9, max(abs(v) for v in buf))
    scale = 0.9 / max(peak, 0.9)
    return array("h", (int(max(-1.0, min(1.0, v * scale)) * 32767) for v in buf))


def write_wav(path: Path, samples, rate: int = RATE):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes() if sys_little() else _swapped(samples))
    return path


def sys_little() -> bool:
    import sys
    return sys.byteorder == "little"


def _swapped(samples):
    a = array("h", samples)
    a.byteswap()
    return a.tobytes()
