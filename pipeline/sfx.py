"""SFX: cues do sfx.json resolvidos + passos gerados a partir da câmera.

Nada que a câmera/luz faz é digitado aqui: passos, batidas do chassi e falhas elétricas vêm das
listas de eventos da câmera (camera.make_steps / make_bumps / make_flicker), então cada som cai
no mesmo frame do movimento (cabeça no chão, solavanco, lâmpada que apaga).
"""
from __future__ import annotations

import random

from .timeline import Resolver, curve_from_spec


def build(cfg: dict, res: Resolver, steps: list[dict], seed: int,
          scene_windows: list[tuple[str, float, float]], gait_table: list[dict] | None = None,
          bumps: list[dict] = (), flickers: list[dict] = (), flicker_sfx: dict | None = None) -> dict:
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
    peak = max((r["bob_y_cm"] for r in gait_table or []), default=1.0)
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

    road = []
    for n, b in enumerate(bumps, 1):
        sfx = b["sfx"]
        road.append({
            "id": f"batida-{n:03d}", "layer": "veiculo", "kind": "bump", "origin": sfx.get("origin", "roteiro"),
            "tag": sfx.get("tag_big") if b["size"] >= sfx.get("big_from", 0.75) and sfx.get("tag_big") else sfx.get("tag", "batida-chassi"),
            "start": b["t"], "end": b["t"], "gain_db": round(sfx.get("gain_db", -14.0) + rnd.uniform(-1.0, 1.0)
                                                               + 6.0 * (b["size"] - 0.5), 2),
            "intensity": round(min(1.0, b["size"]), 2), "segment": b["seg"], "scene": scene_of(b["t"]),
            "generated": "camera.bump"})
    fl_cfg = flicker_sfx or {}
    lamp = []
    for n, e in enumerate(flickers, 1):
        lamp.append({
            "id": f"falha-luz-{n:03d}", "layer": "eletrico", "kind": "flicker", "origin": fl_cfg.get("origin", "inferido"),
            "tag": fl_cfg.get("tag", "falha-eletrica"), "start": e["t"], "end": e["t"] + e["frames"] / 60.0,
            "gain_db": round(fl_cfg.get("gain_db", -16.0) + 8.0 * (e["depth"] - 0.5) + rnd.uniform(-0.8, 0.8), 2),
            "depth": e["depth"], "origin_event": e["origin"], "scene": scene_of(e["t"]),
            "generated": "camera.flicker"})

    mix = {p: _keys(spec, res) for p, spec in cfg.get("mix", {}).items()}
    return {"cues": sorted(cues, key=lambda c: c["start"]), "footsteps": foot, "bumps": road, "flicker": lamp,
            "mix": mix}


def _keys(spec, res: Resolver) -> list[list[float]]:
    return [[round(t, 4), v] for t, v in curve_from_spec(spec, res).pts]
