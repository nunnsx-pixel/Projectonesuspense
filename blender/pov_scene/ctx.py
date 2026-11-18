"""Contexto de um episódio: lê build/epXX.timeline.json e o CSV da câmera (sem bpy)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class Ctx:
    def __init__(self, ep: str, root: Path | str | None = None):
        self.ep = ep
        self.root = Path(root) if root else ROOT
        build = self.root / ep / "build"
        self.tl = json.loads((build / f"{ep}.timeline.json").read_text(encoding="utf-8"))
        self.csv_path = build / f"{ep}.camera.csv"
        self.fps = self.tl["fps"]
        self.duration = self.tl["duration_s"]
        self.beats = {b["id"]: b for s in self.tl["scenes"] for b in s["beats"]}
        self.items = {i["id"]: i for i in self.tl["narration"]}
        self.cues = {c["id"]: c for c in self.tl["sfx"]["cues"]}
        self.kicks = {k["id"]: k for k in self.tl["camera"]["kicks"]}
        self._steps: dict[str, list[float]] = {}
        for s in self.tl["camera"]["steps"]:
            self._steps.setdefault(s["segment"], []).append(s["t"])
        self._rows = None

    # ---- consultas por id -------------------------------------------------------------
    def beat(self, id_: str) -> tuple[float, float]:
        b = self.beats[id_]
        return b["start"], b["end"]

    def cue(self, id_: str) -> tuple[float, float]:
        c = self.cues[id_]
        return c["start"], c["end"]

    def item(self, id_: str) -> tuple[float, float]:
        i = self.items[id_]
        return i["start"], i["end"]

    def word(self, item_id: str, word: str, nth: int = 0) -> tuple[float, float]:
        hits = [w for w in self.items[item_id]["words"] if w["w"].lower().strip(",.!?…") == word.lower()]
        return hits[nth]["start"], hits[nth]["end"]

    def steps(self, segment: str) -> list[float]:
        """Instantes de contato do pé de um segmento de locomoção (mesmos do SFX e do CSV)."""
        return list(self._steps[segment])

    def frame(self, t: float, start_frame: int = 1) -> int:
        return start_frame + int(round(t * self.fps))

    # ---- CSV ----------------------------------------------------------------------------
    def rows(self) -> list[dict]:
        if self._rows is None:
            with open(self.csv_path, newline="", encoding="utf-8") as f:
                self._rows = [{k: (v if k == "scene" else float(v)) for k, v in r.items()} for r in csv.DictReader(f)]
        return self._rows

    def bus_distance(self) -> list[float]:
        """Distância (m) percorrida pelo ônibus a cada frame: integral de speed_kmh do CSV."""
        out, d = [], 0.0
        for r in self.rows():
            out.append(d)
            d += r["speed_kmh"] / 3.6 / self.fps
        return out
