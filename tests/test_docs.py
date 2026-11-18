"""Documento de entrega (ENTREGA.md): todo caminho citado existe e os episódios têm o que ele promete. Python puro."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = (ROOT / "ENTREGA.md").read_text(encoding="utf-8")
EPS = ("ep01", "ep02", "ep03")


def cited_paths():
    for tok in re.findall(r"`([^`\n]+)`", DOC):
        if re.search(r"[\s<>*{}()=|]", tok) or tok.startswith(("python", "blender -b")):
            continue
        if "/" in tok:                                  # nomes soltos (ex.: narration.measured.json, opcional) são só descrição
            yield tok


class Entrega(unittest.TestCase):
    def test_every_cited_path_exists(self):
        paths = list(cited_paths())
        self.assertGreater(len(paths), 15)
        for tok in paths:
            for p in ([tok.replace("ep0X", e) for e in EPS] if "ep0X" in tok else [tok]):
                self.assertTrue((ROOT / p).exists(), f"ENTREGA.md cita {p!r}, que não existe")

    def test_the_numbers_it_promises_hold(self):
        for ep in EPS:
            tl = json.loads((ROOT / ep / "build" / f"{ep}.timeline.json").read_text(encoding="utf-8"))
            self.assertEqual((tl["duration_s"], tl["frames"], tl["fps"]), (60.0, 3600, 60), ep)
            self.assertEqual(tl["resolution"], "1080x1920", ep)
            self.assertFalse(tl.get("warnings"), ep)                                      # build --strict sem avisos
            self.assertTrue(all(s["narration_fit"]["status"] == "ok" for s in tl["scenes"]), ep)

    def test_open_decisions_are_listed_and_the_readme_links_the_hand_off(self):
        self.assertIn("Decisões em aberto", DOC)
        self.assertIn("ENTREGA.md", (ROOT / "README.md").read_text(encoding="utf-8"))
        for ep in EPS:
            self.assertTrue((ROOT / ep / "README.md").exists())


if __name__ == "__main__":
    unittest.main()
