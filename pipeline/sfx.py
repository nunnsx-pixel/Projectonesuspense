"""SFX: cues do sfx.json resolvidos + passos gerados a partir da câmera.

Os passos NÃO são digitados: vêm da lista de pisadas da câmera (camera.make_steps),
então o som de cada passo cai no mesmo frame em que a cabeça toca o chão.
"""
from __future__ import annotations

import random

from .timeline import Resolver, curve_from_spec


def build(cfg: dict, res: Resolver, steps: list[dict], seed: int,
          scene_windows: list[tuple[str, float, float]], gait_table: list[dict]) -> dict:
    def scene_of(t: float) -> str:
        return next((sid for sid, a, b in scene_windows if a <= t < b), scene_windows[-1][0])

    cues = []
    for c in cfg["cues"]:
        start, end = res.span("cue", c["id"])
        cue = {k: v for k, v in c.items() if k not in ("at", "dur", "until", "automation")}
        cue.update(start=start, end=end, scene=scene_of(start))
        if "automation" in c:
            cue["automation"] = {p: _keys(spec, res) for p, spec in c["automation"].items()}
        cues.append(cue)

    rnd = random.Random(seed + 7)
    peak = max(r["bob_y_cm"] for r in gait_table)
    foot = []
    for n, s in enumerate(steps, 1):
        sfx = s["sfx"]
        foot.append({
            "id": f"passo-{n:03d}", "layer": "foley", "kind": "footstep",
            "origin": sfx.get("origin", "roteiro"), "tag": sfx.get("tag", "passo"),
            "surface": s["surface"], "start": s["t"], "end": s["t"],
            "gain_db": round(sfx.get("gain_db", -8.0) + rnd.uniform(-1.0, 1.0), 2),
            "intensity": round(min(1.0, 0.35 + 0.65 * s["amp"]["bob_y_cm"] / peak), 2),
            "foot": "L" if s["idx"] % 2 == 0 else "R", "segment": s["seg"],
            "scene": scene_of(s["t"]), "generated": "camera.step"})

    mix = {p: _keys(spec, res) for p, spec in cfg.get("mix", {}).items()}
    return {"cues": sorted(cues, key=lambda c: c["start"]), "footsteps": foot, "mix": mix}


def _keys(spec, res: Resolver) -> list[list[float]]:
    return [[round(t, 4), v] for t, v in curve_from_spec(spec, res).pts]
