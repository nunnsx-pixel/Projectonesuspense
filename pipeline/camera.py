"""Câmera POV em primeira pessoa: balanço realista sincronizado.

Gera, frame a frame (@60fps), uma camada ADITIVA de movimento sobre o caminho
base da câmera + a "intenção de olhar" (para onde a cabeça aponta) + canais de
tela (vinheta, blur de borda, pálpebra).

Camadas do balanço (todas determinísticas, semente em camera.json):
  passada   passos viram a oscilação da cabeça (sobe/desce, balanço lateral, giro)
            e cada pisada gera um evento de passo que o SFX usa -> câmera e som
            de passos são a MESMA lista de tempos.
  respiração  peito sobe/desce seguindo os respiros da NARRAÇÃO (inspirações do
            roteiro + um respiro antes de cada frase); fora da fala segue a
            frequência respiratória da curva `breath_rate`.
  coração   pulso lub-dub a partir de `hr_bpm`.
  mão       ruído suave de câmera na mão, escalado por `noise`.
  ônibus    vibração do motor, balanço de pista e inclinação por aceleração
            (derivada de `speed_kmh`).
  impactos  `kicks` (mola amortecida: sentar, catraca, jogar mochila...) e
            `pulses` (sobe e desce suave: fungada, cabeçada de sono...).
  estrada   `road`: buracos/terreno irregular em momentos aleatórios (semente fixa); cada
            batida é um impacto de câmera E um evento que o SFX do chassi usa (mesmo frame).
  luz       `flicker`: falhas elétricas da lâmpada (marcadas + rajadas aleatórias); o canal
            `light` (0..1) e os SFX de falha elétrica usam a mesma lista de eventos.

Convenções: +X direita, +Y cima, +Z frente; yaw + = olhar p/ direita,
pitch + = olhar p/ cima, roll + = inclinar p/ a direita; ordem YXZ.
Posição em centímetros, rotação em graus.
"""
from __future__ import annotations

import bisect
import math
import random

from .timeline import FPS, Curve, Resolver, curve_from_spec, lerp, smoothstep, snap

TAU = math.tau
POS = ("x_cm", "y_cm", "z_cm")
ROT = ("yaw", "pitch", "roll")
FLOOR = 0.15           # nível do peito ao fim da expiração (fração da amplitude)


class Noise:
    """Soma de senoides incomensuráveis: suave, determinística, pico típico ~1."""

    def __init__(self, seed: int, lo: float, hi: float, n: int = 8):
        rnd = random.Random(seed)
        self.parts = []
        for k in range(n):
            f = lo * (hi / lo) ** ((k + rnd.random()) / n)
            self.parts.append((f, f ** -0.6, rnd.random() * TAU))
        rms = math.sqrt(sum(a * a for _, a, _ in self.parts) / 2)
        self.scale = 1.0 / (2.0 * rms)

    def __call__(self, t: float) -> float:
        return self.scale * sum(a * math.sin(TAU * f * t + p) for f, a, p in self.parts)


# ----------------------------------------------------------------------------
# Passos
# ----------------------------------------------------------------------------
def _table_lookup(table: list[dict], cadence: float) -> dict:
    rows = sorted(table, key=lambda r: r["cadence"])
    if cadence <= rows[0]["cadence"]:
        return {k: v for k, v in rows[0].items() if k != "cadence"}
    if cadence >= rows[-1]["cadence"]:
        return {k: v for k, v in rows[-1].items() if k != "cadence"}
    for a, b in zip(rows, rows[1:]):
        if a["cadence"] <= cadence <= b["cadence"]:
            u = (cadence - a["cadence"]) / (b["cadence"] - a["cadence"])
            return {k: lerp(a[k], b[k], u) for k in a if k != "cadence"}
    raise AssertionError


def make_steps(cfg: dict, res: Resolver) -> list[dict]:
    """Gera os passos (tempo de cada pisada) a partir dos segmentos de locomoção."""
    steps = []
    for seg in cfg.get("locomotion", []):
        t = res.time(seg["from"])
        t_end = res.time(seg["to"]) if "to" in seg else math.inf
        n_max = seg.get("steps")
        cad = seg["cadence"]
        cadence = curve_from_spec({"mode": "linear", "keys": cad["keys"]}, res) if isinstance(cad, dict) \
            else (lambda _t, c=float(cad): c)
        k = 0
        while (n_max is None or k < n_max) and t <= t_end + 1e-9:
            c = cadence(t)
            steps.append({"t": snap(t), "seg": seg["id"], "cadence": c, "period": 1.0 / c,
                          "scale": seg.get("scale", {}), "surface": seg.get("surface", ""),
                          "sfx": seg.get("sfx", {})})
            t += 1.0 / c
            k += 1
    steps.sort(key=lambda s: s["t"])
    max_gap = cfg.get("gait_connect_gap_s", 1.1)
    run_idx = 0
    for i, s in enumerate(steps):
        run_idx = run_idx + 1 if i and s["t"] - steps[i - 1]["t"] <= max_gap else 0
        s["idx"] = run_idx
        amp = _table_lookup(cfg["gait_table"], s["cadence"])
        for key, mult in s["scale"].items():
            amp[key] = amp[key] * mult
        s["amp"] = amp
        s["connected_next"] = i + 1 < len(steps) and steps[i + 1]["t"] - s["t"] <= max_gap
    return steps


class Gait:
    ZERO = {c: 0.0 for c in ("x_cm", "y_cm", "yaw", "pitch", "roll")}

    def __init__(self, steps: list[dict], impact_f: float = 7.5, impact_tau: float = 0.09):
        self.steps = steps
        self.times = [s["t"] for s in steps]
        self.f, self.tau = impact_f, impact_tau

    def _phase(self, t: float):
        n, ts, st = len(self.steps), self.times, self.steps
        i = bisect.bisect_right(ts, t) - 1
        if i >= 0 and i + 1 < n and st[i]["connected_next"]:
            a, b = st[i], st[i + 1]
            u = (t - a["t"]) / (b["t"] - a["t"])
            w = smoothstep(u)
            amp = {k: lerp(a["amp"][k], b["amp"][k], w) for k in a["amp"]}
            return a["idx"] + u, amp, 1.0
        if i >= 0 and (t - st[i]["t"]) < 0.5 * st[i]["period"]:
            a = st[i]
            u = (t - a["t"]) / a["period"]
            return a["idx"] + u, a["amp"], 1.0 - smoothstep(u / 0.5)
        if i + 1 < n and (st[i + 1]["t"] - t) < 0.5 * st[i + 1]["period"]:
            b = st[i + 1]
            u = (t - b["t"]) / b["period"]
            return b["idx"] + u, b["amp"], smoothstep((u + 0.5) / 0.5)
        return None

    def at(self, t: float) -> dict:
        out = dict(self.ZERO)
        got = self._phase(t)
        if got is None:
            return out
        phase, a, fade = got
        c2, s1, c1 = math.cos(TAU * phase), math.sin(math.pi * phase), math.cos(math.pi * phase)
        out["y_cm"] = -a["bob_y_cm"] * c2 * fade           # mais baixo na pisada
        out["pitch"] = -a["pitch_deg"] * c2 * fade
        out["x_cm"] = -a["sway_x_cm"] * s1 * fade          # desloca p/ o lado do apoio
        out["roll"] = -a["roll_deg"] * s1 * fade
        out["yaw"] = -a["yaw_deg"] * c1 * fade
        return out

    def impact(self, t: float) -> dict:
        """Resposta de mola às pisadas recentes (estalo do impacto)."""
        y = p = 0.0
        j = bisect.bisect_right(self.times, t) - 1
        while j >= 0 and t - self.times[j] < 0.5:
            s = t - self.times[j]
            k = math.exp(-s / self.tau) * math.sin(TAU * self.f * s)
            a = self.steps[j]["amp"]
            y -= a["impact_y_cm"] * k
            p -= a["impact_pitch_deg"] * k
            j -= 1
        return {"y_cm": y, "pitch": p}


# ----------------------------------------------------------------------------
# Respiração e coração
# ----------------------------------------------------------------------------
def fill_breath_cycles(events: list[dict], occupied: list[tuple[float, float]], rate: Curve,
                       duration: float) -> list[dict]:
    """Completa com ciclos de respiração basal os trechos sem fala/respiro marcado."""
    occ = sorted(occupied)
    merged: list[list[float]] = []
    for a, b in occ:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    gaps, cur = [], 0.0
    for a, b in merged:
        if a > cur:
            gaps.append((cur, a))
        cur = max(cur, b)
    if cur < duration:
        gaps.append((cur, duration))
    out = list(events)
    for a, b in gaps:
        t = a
        while True:
            period = 60.0 / rate(t)
            if t + 0.8 * period > b:
                break
            out.append({"t": t, "inhale": 0.38 * period, "hold": 0.0, "exhale": 0.62 * period,
                        "amp": 1.0, "type": "basal", "ref": None, "explicit": False})
            t += period
    return sorted(out, key=lambda e: e["t"])


class BreathLevel:
    """Nível do peito (0..amp) a partir de uma lista ordenada de inspirações."""

    def __init__(self, events: list[dict]):
        self.ev = events
        self.ts = [e["t"] for e in events]
        self.start_level = []
        prev_level = FLOOR
        for i, e in enumerate(events):
            self.start_level.append(prev_level)
            prev_level = self._eval(i, events[i + 1]["t"]) if i + 1 < len(events) else prev_level

    def _eval(self, i: int, t: float) -> float:
        e, l0 = self.ev[i], self.start_level[i]
        s = t - e["t"]
        if s < e["inhale"]:
            return lerp(l0, e["amp"], smoothstep(s / e["inhale"]))
        s -= e["inhale"]
        if s < e["hold"]:
            return e["amp"]
        s -= e["hold"]
        if s < e["exhale"]:
            return lerp(e["amp"], FLOOR * e["amp"], smoothstep(s / e["exhale"]))
        return FLOOR * e["amp"]

    def __call__(self, t: float) -> float:
        i = bisect.bisect_right(self.ts, t) - 1
        return FLOOR if i < 0 else self._eval(i, t)


def heartbeats(hr: Curve, duration: float) -> list[tuple[float, float]]:
    """(tempo, período) de cada batida integrando a frequência cardíaca."""
    beats, phase, t, dt = [], 0.0, 0.0, 0.001
    while t < duration + 1.0:
        new = phase + hr(t) / 60.0 * dt
        if int(new) > int(phase):
            beats.append((t, 60.0 / hr(t)))
        phase, t = new, t + dt
    return beats


def heart_pulse(beats, t: float, sigma: float = 0.03) -> float:
    j = bisect.bisect_right([b[0] for b in beats], t + 0.05) - 1
    v = 0.0
    while j >= 0 and t - beats[j][0] < 0.5:
        tb, period = beats[j]
        lag = min(0.30, 0.36 * period)
        v += math.exp(-(((t - tb) / sigma) ** 2)) + 0.6 * math.exp(-(((t - tb - lag) / sigma) ** 2))
        j -= 1
    return v


# ----------------------------------------------------------------------------
# Eventos pontuais
# ----------------------------------------------------------------------------
def kick_response(ev: dict, t: float) -> dict[str, float]:
    s = t - ev["t"]
    if s < 0 or s > 6 * ev["tau_s"]:
        return {}
    f, tau = ev["f_hz"], ev["tau_s"]
    s_pk = math.atan(TAU * f * tau) / (TAU * f)
    norm = 1.0 / (math.exp(-s_pk / tau) * math.sin(TAU * f * s_pk))
    k = norm * math.exp(-s / tau) * math.sin(TAU * f * s)
    return {c: ev[c] * k for c in POS + ROT if c in ev}


def pulse_response(ev: dict, t: float) -> dict[str, float]:
    s = t - ev["t"]
    if s < 0 or s > ev["attack"] + ev["decay"]:
        return {}
    w = smoothstep(s / ev["attack"]) if s < ev["attack"] else 1.0 - smoothstep((s - ev["attack"]) / ev["decay"])
    return {c: ev[c] * w for c in POS + ROT + ("fov_pct",) if c in ev}


def make_bumps(cfg: dict, res: Resolver, seed: int) -> list[dict]:
    """Batidas da estrada: instantes aleatórios (Poisson, semente fixa) por trecho `road`."""
    out = []
    for si, seg in enumerate(cfg.get("road", [])):
        t0, t1 = res.time(seg["from"]), res.time(seg["to"])
        rate = curve_from_spec({"mode": "linear", "keys": seg["rate_hz"]}, res)
        amp = curve_from_spec(seg["amp"], res) if "amp" in seg else (lambda _t: 1.0)
        rnd = random.Random(seed * 7919 + si)
        t = t0
        while True:
            t += max(seg.get("min_gap_s", 0.12), rnd.expovariate(max(rate(t), 1e-3)))
            if t >= t1:
                break
            size = (0.3 + 0.7 * rnd.random() ** 1.5) * amp(t)          # maioria pequena, poucas grandes
            out.append({"t": snap(t), "size": size, "seg": seg["id"], "sx": rnd.choice((-1, 1)),
                        "sr": rnd.choice((-1, 1)), "sp": rnd.choice((-1, 1)), "sfx": seg.get("sfx", {})})
    return sorted(out, key=lambda b: b["t"])


def bump_kick(b: dict, resp: dict) -> dict:
    """Resposta de mola de uma batida (mesma matemática dos `kicks`)."""
    return {"t": b["t"], "f_hz": resp["f_hz"], "tau_s": resp["tau_s"], "y_cm": resp["y_cm"] * b["size"],
            "pitch": resp["pitch"] * b["size"] * b["sp"], "roll": resp["roll"] * b["size"] * b["sr"],
            "x_cm": resp["x_cm"] * b["size"] * b["sx"]}


def make_flicker(cfg: dict, res: Resolver, duration: float, seed: int):
    """Falhas elétricas da lâmpada: eventos (marcados + rajadas) e o canal `light` por frame."""
    n = int(round(duration * FPS))
    fl = cfg.get("flicker")
    if not fl:
        return [], [1.0] * n
    events = [{"t": snap(res.time(e["at"])), "frames": int(e["frames"]), "depth": float(e["depth"]),
               "origin": "marcado", "note": e.get("note", "")} for e in fl.get("events", [])]
    rate = curve_from_spec({"mode": "linear", "keys": fl["rate_hz"]}, res)
    rnd = random.Random(seed * 104729 + 17)
    t, t_end = res.time(fl.get("from", 0.0)), min(res.time(fl.get("to", duration)), duration - 0.1)
    while True:
        t += rnd.expovariate(max(rate(t), 1e-3))
        if t >= t_end:
            break
        for _ in range(rnd.randint(*fl["burst_count"])):
            frames = rnd.randint(*fl["burst_frames"])
            events.append({"t": snap(t), "frames": frames, "depth": round(rnd.uniform(*fl["depth"]), 3),
                           "origin": "rajada", "note": ""})
            t += (frames + rnd.randint(*fl["burst_gap_frames"])) / FPS
    base = curve_from_spec(fl["base"], res) if "base" in fl else (lambda _t: 1.0)
    dip = [0.0] * n
    for e in events:
        f0 = int(round(e["t"] * FPS))
        for f in range(max(f0, 0), min(f0 + e["frames"], n)):
            dip[f] = max(dip[f], e["depth"])
    light = [max(0.0, min(1.0, base(f / FPS) * (1.0 - dip[f]))) for f in range(n)]
    return sorted(events, key=lambda e: e["t"]), light


# ----------------------------------------------------------------------------
# Montagem
# ----------------------------------------------------------------------------
def build(cfg: dict, res: Resolver, breath_events: list[dict], speech_spans: list[tuple[float, float]],
          scene_windows: list[tuple[str, float, float]], duration: float) -> dict:
    n_frames = int(round(duration * FPS))
    seed = cfg.get("seed", 348)
    master = cfg.get("intensity", 1.0)

    curves = {name: curve_from_spec(spec, res) for name, spec in cfg["curves"].items()
              if not name.startswith("_")}
    c = lambda name, t: curves[name](t) if name in curves else 0.0  # noqa: E731

    steps = make_steps(cfg, res)
    gait = Gait(steps, cfg.get("impact_f_hz", 7.5), cfg.get("impact_tau_s", 0.09))

    look_keys = sorted(({**k, "t": res.time(k["at"])} for k in cfg["look"]), key=lambda k: k["t"])
    look = {ch: Curve([(k["t"], k.get(ch, 0.0)) for k in look_keys]) for ch in ROT}

    kicks = [{**k, "t": res.time(k["at"])} for k in cfg.get("kicks", [])]
    pulses = [{**p, "t": res.time(p["at"])} for p in cfg.get("pulses", [])]

    occupied = list(speech_spans) + [(e["t"], e["t"] + e["inhale"] + e["hold"] + 0.4)
                                     for e in breath_events if e["explicit"]]
    cycles = fill_breath_cycles(breath_events, occupied, curves["breath_rate"], duration)
    level = BreathLevel(cycles)
    beats = heartbeats(curves["hr_bpm"], duration)

    A = cfg["amplitudes"]
    noises = {ch: Noise(seed * 100 + i, *A["noise"]["band_hz"]) for i, ch in enumerate(POS + ROT + ("fov_pct",))}
    sway_n = {ch: Noise(seed * 100 + 20 + i, 0.15, 0.6, 5) for i, ch in enumerate(("x_cm", "roll", "yaw"))}
    vib_f = A["bus_vibration"]["freq_hz"]

    fx = cfg["fx"]
    if "black_ranges" in fx:
        black_ranges = [(res.time(a), res.time(b)) for a, b in fx["black_ranges"]]
    else:                                                    # compat: corte seco até o fim
        black_ranges = [(res.time(fx["cut_to_black_at"]), duration)]
    step_frames = {int(round(s["t"] * FPS)) for s in steps}

    bumps = make_bumps(cfg, res, seed)
    bump_resp = cfg.get("bump_response", {})
    bump_evs = [bump_kick(b, bump_resp) for b in bumps]
    bump_ts = [b["t"] for b in bumps]
    bump_frames = {int(round(b["t"] * FPS)) for b in bumps}
    flickers, light = make_flicker(cfg, res, duration, seed)

    rows = []
    for fr in range(n_frames):
        t = fr / FPS
        acc = {ch: 0.0 for ch in POS + ROT}
        fov = 0.0

        g = gait.at(t)
        imp = gait.impact(t)
        for ch, v in g.items():
            acc[ch] += v
        for ch, v in imp.items():
            acc[ch] += v

        lv = level(t) - 0.35
        bg = c("breath", t)
        acc["pitch"] += A["breath"]["pitch_deg"] * lv * bg
        acc["y_cm"] += A["breath"]["y_cm"] * lv * bg
        acc["z_cm"] += A["breath"]["z_cm"] * lv * bg

        hp = heart_pulse(beats, t)
        hg = c("heart", t)
        acc["pitch"] += A["heart"]["pitch_deg"] * hp * hg
        acc["y_cm"] += A["heart"]["y_cm"] * hp * hg
        fov += A["heart"]["fov_pct"] * hp * hg

        ng = c("noise", t)
        for ch in POS + ROT:
            acc[ch] += A["noise"][ch] * noises[ch](t) * ng
        fov += A["noise"]["fov_pct"] * noises["fov_pct"](t) * ng

        vg = c("bus_vib", t)
        vib = math.sin(TAU * vib_f[0] * t) + 0.6 * math.sin(TAU * vib_f[1] * t + 1.3)
        for ch, v in A["bus_vibration"].items():
            if ch != "freq_hz":
                acc[ch] += v * vib * vg
        sg = c("bus_sway", t)
        for ch, key in (("x_cm", "x_cm"), ("roll", "roll"), ("yaw", "yaw")):
            acc[ch] += A["bus_sway"][key] * sway_n[ch](t) * sg

        accel = (curves["speed_kmh"](t + 0.1) - curves["speed_kmh"](t - 0.1)) / 3.6 / 0.2   # m/s²
        acc["pitch"] += A["bus_lean"]["pitch_deg_per_ms2"] * accel
        acc["z_cm"] += A["bus_lean"]["z_cm_per_ms2"] * accel

        acc["pitch"] -= c("droop_deg", t)

        for k in kicks:
            for ch, v in kick_response(k, t).items():
                acc[ch] += v
        for p in pulses:
            for ch, v in pulse_response(p, t).items():
                if ch == "fov_pct":
                    fov += v
                else:
                    acc[ch] += v

        j = bisect.bisect_right(bump_ts, t) - 1
        while j >= 0 and t - bump_ts[j] < 6 * bump_resp.get("tau_s", 0.16):
            for ch, v in kick_response(bump_evs[j], t).items():
                acc[ch] += v
            j -= 1

        scene = next((sid for sid, a, b in scene_windows if a <= t < b), scene_windows[-1][0])
        black = 1 if any(a - 1e-9 <= t < b - 1e-9 for a, b in black_ranges) else 0
        row = {"frame": fr, "t": round(t, 5), "scene": scene,
               "shake_x_cm": acc["x_cm"] * master, "shake_y_cm": acc["y_cm"] * master,
               "shake_z_cm": acc["z_cm"] * master,
               "shake_yaw": acc["yaw"] * master, "shake_pitch": acc["pitch"] * master,
               "shake_roll": acc["roll"] * master,
               "look_yaw": look["yaw"](t), "look_pitch": look["pitch"](t), "look_roll": look["roll"](t),
               "fov_pct": fov * master + c("fov_pct", t),
               "vignette": c("vignette", t), "edge_blur": c("edge_blur", t),
               "eyelid": c("eyelid", t), "black": black,
               "breath": level(t), "heart": hp, "speed_kmh": c("speed_kmh", t),
               "step": 1 if fr in step_frames else 0,
               "light": light[fr], "motion_blur": c("motion_blur", t), "bump": 1 if fr in bump_frames else 0}
        if black:
            row["eyelid"] = 1.0
        rows.append(row)

    return {"rows": rows, "steps": [s for s in steps if s["t"] >= 0.0], "all_steps": steps, "gait": gait,
            "breath_cycles": cycles, "heartbeats": beats, "look_keys": look_keys, "kicks": kicks,
            "pulses": pulses, "curves": curves, "black_ranges": black_ranges,
            "bumps": bumps, "flickers": flickers}
