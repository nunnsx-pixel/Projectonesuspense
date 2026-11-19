"""Manifesto de materiais (blender/materials.json) e diretrizes (blender/TEXTURAS.md). Python puro."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLENDER = ROOT / "blender"
MAN = json.loads((BLENDER / "materials.json").read_text(encoding="utf-8"))
KNOWN_MAPS = {"albedo", "roughness", "metallic", "ao", "height", "normal"}


class Manifest(unittest.TestCase):
    def test_every_material_is_well_formed(self):
        for mid, m in MAN["materials"].items():
            self.assertIn(m["space"], ("bus", "world"), mid)
            self.assertTrue(m["desc"].strip() and m["episodes"], mid)
            self.assertTrue(set(m["episodes"]) <= {"ep01", "ep02", "ep03"}, mid)
            self.assertTrue(m.get("variants"), f"{mid}: sem variantes")
            if m.get("kind") != "volume":
                self.assertGreater(m["tile_m"], 0, mid)
                self.assertTrue(m["maps"] and set(m["maps"]) <= KNOWN_MAPS, mid)
            for v, over in m["variants"].items():          # variante só sobrescreve parâmetros que existem (sem erro de digitação)
                self.assertTrue(set(over) <= set(m["procedural"]), f"{mid}/{v}: {set(over) - set(m['procedural'])}")

    def test_scripts_only_use_materials_and_variants_that_exist(self):
        used = set()
        for f in (BLENDER / "pov_scene").glob("*.py"):
            for mid, var in re.findall(r'materials\.get\(\s*"([\w-]+)"(?:\s*,\s*"([\w-]+)")?', f.read_text(encoding="utf-8")):
                self.assertIn(mid, MAN["materials"], f"{f.name}: material {mid!r} fora do manifesto")
                if var:
                    self.assertIn(var, MAN["materials"][mid]["variants"], f"{f.name}: {mid}/{var}")
                used.add(mid)
            used |= set(re.findall(r'materials\.ground_fog', f.read_text(encoding="utf-8"))) and {"neblina-rasteira"}
        bus = (BLENDER / "pov_scene" / "bus.py").read_text(encoding="utf-8")
        self.assertIn('"estofado", "mofado" if decayed else "limpo"', bus)           # ep01 limpo, ep02/03 mofado
        self.assertEqual(used | {"estofado"}, set(MAN["materials"]), "material do manifesto que nenhum script usa")

    def test_the_four_scenarios_requested_are_covered(self):
        by = MAN["materials"]
        self.assertEqual(by["piso-encerado"]["episodes"], ["ep01"])                        # Rodoviária de Campinas
        self.assertTrue({"ep02", "ep03"} <= set(by["estofado"]["episodes"]))               # estofado mofado
        self.assertTrue({"mofado", "podre"} <= set(by["estofado"]["variants"]))
        self.assertTrue({"ep02", "ep03"} <= set(by["metal-enferrujado"]["episodes"]))      # metal enferrujado
        self.assertTrue({"ep02", "ep03"} <= set(by["terra-vermelha"]["episodes"]))         # terra vermelha
        self.assertEqual(by["neblina-rasteira"]["kind"], "volume")                         # neblina volumétrica
        self.assertEqual(by["neblina-rasteira"]["episodes"], ["ep03"])

    def test_space_choice_prevents_texture_swimming(self):
        for mid in ("estofado", "metal-enferrujado", "piso-emborrachado", "camisa-social"):
            self.assertEqual(MAN["materials"][mid]["space"], "bus", mid)                    # anda com o ônibus
        for mid in ("piso-encerado", "terra-vermelha", "neblina-rasteira"):
            self.assertEqual(MAN["materials"][mid]["space"], "world", mid)                  # cenário fixo

    def test_briefing_bus_interior_materials(self):
        """Briefing consolidado: poltronas de tecido ESTAMPADO azul/cinza, balaústres de INOX, piso EMBORRACHADO escuro,
        motorista de camisa social AZUL AMARROTADA."""
        by = MAN["materials"]
        fabric = by["estofado"]["procedural"]
        self.assertGreater(fabric["print_amount"], 0.2)
        r, g, b = fabric["print_color"]
        self.assertTrue(abs(r - g) < 0.08 and b >= r)                                       # cinza azulado
        self.assertGreater(fabric["color"][2], fabric["color"][0] * 2)                       # base azul
        inox = by["metal-enferrujado"]["variants"]["inox"]
        self.assertLess(inox["rust"], 0.06)                                                  # inox quase sem ferrugem
        self.assertLess(by["metal-enferrujado"]["variants"]["inox"]["rust"], by["metal-enferrujado"]["variants"]["enferrujado"]["rust"])
        rubber = by["piso-emborrachado"]
        self.assertEqual(rubber["episodes"], ["ep01", "ep02", "ep03"])
        self.assertTrue(all(c < 0.06 for c in rubber["procedural"]["color"]))               # escuro
        self.assertGreater(rubber["procedural"]["stud_bump"], 0.3)                          # antiderrapante: pastilhas em relevo
        self.assertTrue({"limpo", "sujo"} <= set(rubber["variants"]))
        shirt = by["camisa-social"]["procedural"]
        self.assertTrue(shirt["color"][2] > 2 * shirt["color"][0] and shirt["color"][2] > shirt["color"][1])   # azul
        self.assertGreater(shirt["wrinkle_bump"], 0.3)                                       # amarrotada
        self.assertTrue({"azul", "encardida"} <= set(by["camisa-social"]["variants"]))

    def test_footsteps_inside_the_bus_sound_like_the_rubber_floor(self):
        """O som segue o material real: no ônibus o piso é borracha (abafado); metal só nos degraus."""
        rubber_gain = {}
        for ep in ("ep01", "ep02", "ep03"):
            tl = json.loads((ROOT / ep / "build" / f"{ep}.timeline.json").read_text(encoding="utf-8"))
            for s in tl["sfx"]["footsteps"]:
                if s["segment"] in ("corrida-saguao", "degraus"):                          # saguão encerado / degraus metálicos
                    continue
                self.assertIn("emborrachado", s["surface"], f"{ep}/{s['segment']}")
                self.assertIn("borracha", s["tag"], f"{ep}/{s['segment']}")
                self.assertNotIn("metal", s["tag"], f"{ep}/{s['segment']}")
                rubber_gain.setdefault(ep, []).append(s["gain_db"])
        self.assertEqual(set(rubber_gain), {"ep01", "ep03"})                                 # o Ep. 2 não tem passos
        steps = json.loads((ROOT / "ep01" / "build" / "ep01.timeline.json").read_text(encoding="utf-8"))["sfx"]["footsteps"]
        stairs = [s for s in steps if s["segment"] == "degraus"]
        self.assertTrue(stairs and all("metal" in s["tag"] for s in stairs))                  # degraus continuam metálicos
        self.assertLess(max(rubber_gain["ep01"]), min(s["gain_db"] for s in stairs))          # borracha mais baixa que o degrau

    def test_guidelines_document_every_material_and_every_map(self):
        doc = (BLENDER / "TEXTURAS.md").read_text(encoding="utf-8")
        for mid in MAN["materials"]:
            self.assertIn(f"`{mid}`", doc, f"TEXTURAS.md não cita {mid}")
        for m in KNOWN_MAPS:
            self.assertIn(m, doc)
        for term in ("tile_m", "Non-Color", "sRGB", "textures/", "OpenGL", "ONIBUS"):
            self.assertIn(term, doc)


if __name__ == "__main__":
    unittest.main()
