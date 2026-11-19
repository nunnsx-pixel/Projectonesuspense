"""Testes do pipeline do ep02.   Rodar:  python -m unittest discover -s tests -v"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.build import build_episode      # noqa: E402
from pipeline.timeline import FPS             # noqa: E402


class Ep02(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tl = build_episode("ep02", write=False)
        cls.cam = cls.tl.pop("_cam")
        cls.rows = cls.cam["rows"]
        cls.cues = {c["id"]: c for c in cls.tl["sfx"]["cues"]}
        cls.beats = {b["id"]: b for s in cls.tl["scenes"] for b in s["beats"]}
        cls.items = {i["id"]: i for i in cls.tl["narration"]}

    # ---- estrutura -------------------------------------------------------------
    def test_all_scenes_fit_and_no_warnings(self):
        self.assertEqual(self.tl["warnings"], [])
        for sc in self.tl["scenes"]:
            self.assertEqual(sc["narration_fit"]["status"], "ok", sc["id"])

    def test_black_only_at_the_start_and_video_ends_on_the_nape(self):
        self.assertEqual(len(self.rows), 3600)
        black = [r["frame"] for r in self.rows if r["black"]]
        self.assertEqual(black, list(range(30)))                       # tela preta de 0,5 s, nada além disso
        self.assertTrue(all(r["eyelid"] == 1.0 for r in self.rows[:30]))
        last = self.rows[-1]                                           # "corte seco" = o vídeo acaba na nuca
        self.assertEqual(last["black"], 0)
        self.assertLess(last["fov_pct"], -14)                          # zoom lento sobre a nuca do motorista
        self.assertGreater(last["look_pitch"], 4)
        self.assertLess(abs(last["look_yaw"]), 5)

    def test_no_speech_in_the_black(self):
        for it in self.tl["narration"]:
            self.assertGreaterEqual(it["start"], 0.5, it["id"])

    # ---- O BUM: tudo no mesmo frame ----------------------------------------------
    def test_bum_is_one_event_across_audio_camera_light_and_blur(self):
        self.assertEqual(self.cues["bum-buraco"]["start_frame"], 30)
        self.assertEqual(self.beats["b1-bum"]["start_frame"], 30)
        kicks = {k["id"]: k for k in self.tl["camera"]["kicks"]}
        self.assertEqual(round(kicks["k-bum-vertical"]["t"] * FPS), 30)
        first = self.tl["camera"]["flicker"][0]
        self.assertEqual((round(first["t"] * FPS), first["depth"]), (30, 1.0))          # lâmpadas morrem
        self.assertTrue(all(self.rows[f]["light"] == 0.0 for f in range(30, 42)))       # 12 frames apagada
        self.assertLess(self.rows[29]["motion_blur"], 0.01)
        self.assertGreater(self.rows[32]["motion_blur"], 0.9)                           # blur explode no impacto
        # a câmera de fato sacode forte logo após o BUM e acalma
        # (calma = nível típico, RMS de 2 s adiante: uma batida da estrada que caia justo na janela não conta como "agitada")
        peak = max(abs(self.rows[f]["shake_pitch"]) for f in range(30, 60))
        calm = (sum(self.rows[f]["shake_pitch"] ** 2 for f in range(300, 420)) / 120) ** 0.5
        self.assertGreater(peak, 5 * calm)

    def test_eyelids_snap_open_right_after_the_hit_and_before_the_gasp_ends(self):
        self.assertEqual(self.rows[30]["eyelid"], 1.0)
        self.assertLess(self.rows[49]["eyelid"], 0.01)                                   # aberto aos 0,8 s
        gasp = self.items["s1-01"]
        self.assertGreater(gasp["start"], 0.5)
        self.assertLess(gasp["start"], 0.8)

    # ---- batidas da estrada ---------------------------------------------------------
    def test_road_bumps_are_the_same_events_in_camera_csv_and_sfx(self):
        cam_t = [b["t"] for b in self.tl["camera"]["bumps"]]
        sfx_t = [b["start"] for b in self.tl["sfx"]["bumps"]]
        self.assertEqual(cam_t, sfx_t)
        self.assertEqual({r["frame"] for r in self.rows if r["bump"]}, {round(t * FPS) for t in cam_t})
        self.assertGreater(len(cam_t), 60)
        self.assertGreaterEqual(min(cam_t), 1.4)
        self.assertLessEqual(max(cam_t), 59.8)
        for t in cam_t:
            self.assertLess(abs(t * FPS - round(t * FPS)), 0.01)                          # na grade de frames

    def test_gravel_takes_over_in_scene_3(self):
        tags = {b["segment"]: b["tag"] for b in self.tl["sfx"]["bumps"]}
        self.assertEqual(tags["estrada-terra"], "cascalho-batida")
        self.assertIn(tags["estrada-deterioracao"], ("rangido-chassi", "batida-suspensao"))

    # ---- luz com falha elétrica --------------------------------------------------------
    def test_light_drops_match_flicker_events_and_electrical_sfx(self):
        events = self.tl["camera"]["flicker"]
        lamp = self.tl["sfx"]["flicker"]
        self.assertEqual([e["t"] for e in events], [f["start"] for f in lamp])
        self.assertGreater(len(events), 40)
        for e in events:
            f0 = round(e["t"] * FPS)
            self.assertLessEqual(self.rows[f0]["light"], 1 - e["depth"] + 1e-3, f"frame {f0}")
        self.assertTrue(all(0.0 <= r["light"] <= 1.0 for r in self.rows))
        self.assertGreater(sum(r["light"] == 1.0 for r in self.rows), 2500)               # pisca, não é strobe

    def test_flicker_tag_is_marked_inferred_so_it_can_be_dropped(self):
        self.assertTrue(all(f["origin"] == "inferido" for f in self.tl["sfx"]["flicker"]))
        self.assertIn("zumbido-eletrico", self.cues)                                      # o zumbido em si é do roteiro
        self.assertEqual(self.cues["zumbido-eletrico"]["origin"], "roteiro")

    # ---- fala, respirações e anotações ----------------------------------------------
    def test_script_numbers_are_spoken_the_agreed_way(self):
        words = [w for i in self.tl["narration"] for w in i.get("words", [])]
        spoken = {w["w"]: w["spoken"] for w in words if w["w"] in ("348", "GPS", "4G")}
        self.assertEqual(spoken, {"348": "três quatro oito", "GPS": "gê pê ésse", "4G": "quatro gê"})
        self.assertEqual(sum(w["w"] == "348" for w in words), 2)
        self.assertTrue(all("meia" not in w["spoken"] for w in words))

    def test_scared_breathing_shapes(self):
        gasp = [b for b in self.tl["breaths"] if b["ref"] == "s1-01"]
        pant = [b for b in self.tl["breaths"] if b["ref"] == "s1-07"]
        self.assertEqual(len(gasp), 1)
        self.assertEqual(len(pant), 3)                                                   # huh-huh-huh
        self.assertGreater(gasp[0]["amp"], 1.5)
        self.assertLess(pant[1]["t"] - pant[0]["t"], 0.5)
        lvl = {r["frame"]: r["breath"] for r in self.rows}
        for b in gasp + pant:
            f0, f1 = round(b["t"] * FPS), round((b["t"] + b["inhale"]) * FPS)
            self.assertGreater(lvl[f1], lvl[max(f0 - 1, 0)] + 0.25, b["ref"])

    def test_panicked_scenes_breathe_between_short_pauses(self):
        implicit = [b for b in self.tl["breaths"] if not b["explicit"]]
        self.assertGreaterEqual(len(implicit), 15)

    def test_markdown_script_matches_active_narration(self):
        """O .md (roteiro humano) tem que dizer o mesmo que narration.json: texto, respirações e direções."""
        md = (ROOT / "ep02-despertar-escuro.md").read_text(encoding="utf-8")
        lines = re.findall(r"\*\*Fala[^\n]*\n\s*>\s*(.+)", md)
        self.assertEqual(len(lines), 3)
        norm = lambda t: re.sub(r"\s+", " ", t).strip().lower()                          # noqa: E731
        for sid, line in zip(("s1", "s2", "s3"), lines):
            items = [i for i in self.tl["narration"] if i["scene"] == sid]
            notes = []
            for i in items:                                           # anotações na ordem em que aparecem
                if i["kind"] == "breath":
                    notes.append(i["label"])
                elif i.get("direction"):
                    notes.append(i["direction"])
            labels = re.findall(r"\*\(([^)]*)\)\*", line)
            text = re.sub(r"\*\([^)]*\)\*", "", line).replace("*", "").replace('"', "")
            self.assertEqual(norm(text), norm(" ".join(i["text"] for i in items if i["kind"] == "speech")), sid)
            self.assertEqual([l.lower() for l in labels], [n.lower() for n in notes], sid)

    # ---- âncoras do roteiro -------------------------------------------------------------
    def test_sign_phone_and_silhouette_follow_the_words(self):
        placa = next(w for w in self.items["s3-03"]["words"] if w["w"] == "placa")
        self.assertAlmostEqual(self.beats["b3-placa"]["start"], placa["start"] - 0.3, places=2)
        gps = next(w for w in self.items["s3-01"]["words"] if w["w"] == "GPS")
        self.assertLess(self.beats["b3-celular"]["start"], gps["start"])                 # o celular já está subindo
        self.assertGreater(self.beats["b3-celular"]["end"], self.items["s3-02"]["end"])  # e fica até "4G sumiu"
        chiado = self.cues["chiado-celular"]
        self.assertEqual((chiado["start"], chiado["end"]), (self.beats["b3-celular"]["start"], self.beats["b3-celular"]["end"]))
        maluco = next(w for w in self.items["s2-08"]["words"] if w["w"] == "maluco")
        self.assertLess(self.beats["b2-silhueta"]["start"], maluco["start"])
        # na hora em que fala do maluco no fundo, a câmera olha para trás
        look = {r["frame"]: r["look_yaw"] for r in self.rows}
        self.assertGreater(look[round((maluco["start"] + 0.3) * FPS)], 120)

    def test_window_is_left_and_backpack_seat_is_right_like_ep1(self):
        look = {r["frame"]: (r["look_yaw"], r["look_pitch"]) for r in self.rows}
        banco = self.beats["b2-banco"]["start"]
        yaw, pitch = look[round((banco + 0.9) * FPS)]
        self.assertGreater(yaw, 15)                                       # banco do corredor: direita
        self.assertLess(pitch, -30)                                       # olhando para baixo
        self.assertLess(look[round(40.4 * FPS)][0], -60)                  # janela (logo após o giro): esquerda

    def test_phone_is_in_the_left_hand_like_ep1(self):
        self.assertIn("ESQUERDA", self.tl["scenes"][2]["set"]["props"][1]["state"])

    def test_deterministic(self):
        again = build_episode("ep02", write=False)
        again.pop("_cam")
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(self.tl, sort_keys=True))


class ExtraColumns(unittest.TestCase):
    def test_csv_has_the_extra_columns_only_when_requested(self):
        ep02 = build_episode("ep02", write=False)
        ep02.pop("_cam")
        self.assertEqual(ep02["camera"]["columns"][-3:], ["light", "motion_blur", "bump"])
        ep01 = build_episode("ep01", write=False)
        ep01.pop("_cam")
        self.assertNotIn("light", ep01["camera"]["columns"])                # Ep. 1 segue com o CSV de sempre


if __name__ == "__main__":
    unittest.main()
