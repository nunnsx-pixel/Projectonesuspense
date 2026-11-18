"""Testes do pipeline do ep03.   Rodar:  python -m unittest discover -s tests -v"""
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


class Ep03(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tl = build_episode("ep03", write=False)
        cls.cam = cls.tl.pop("_cam")
        cls.rows = cls.cam["rows"]
        cls.cues = {c["id"]: c for c in cls.tl["sfx"]["cues"]}
        cls.beats = {b["id"]: b for s in cls.tl["scenes"] for b in s["beats"]}
        cls.items = {i["id"]: i for i in cls.tl["narration"]}
        cls.kicks = {k["id"]: k for k in cls.tl["camera"]["kicks"]}

    # ---- estrutura ------------------------------------------------------------------
    def test_all_scenes_fit_and_no_warnings(self):
        self.assertEqual(self.tl["warnings"], [])
        for sc in self.tl["scenes"]:
            self.assertEqual(sc["narration_fit"]["status"], "ok", sc["id"])

    def test_scene2_is_the_tight_one_and_driver_speaks_slower_than_the_student(self):
        fit = {s["id"]: s["narration_fit"]["fit_ratio"] for s in self.tl["scenes"]}
        self.assertLess(fit["s2"], fit["s1"])
        self.assertLess(fit["s2"], fit["s3"])

        def rate(item):                                    # sílabas/s só da articulação
            ws = self.items[item]["words"]
            return sum(w["syl"] for w in ws) / sum(w["end"] - w["start"] for w in ws)
        self.assertLess(rate("s2-02"), 5.5)                # motorista: grave e lento
        self.assertLess(rate("s3-07"), 3.5)                # ainda mais lento: voz calma e macabra
        self.assertGreater(rate("s2-06"), 6.0)             # protagonista: terror, fala atropelada

    def test_speakers_and_voice_notes(self):
        who = {i["id"]: i.get("speaker", "protagonista") for i in self.tl["narration"] if i["kind"] == "speech"}
        self.assertEqual({k for k, v in who.items() if v == "motorista"}, {"s2-02", "s2-03", "s3-07"})
        self.assertIn("fx_suggestion", self.tl["speakers"]["motorista"])
        self.assertIn("rádio", self.tl["speakers"]["motorista"]["voice"])

    def test_script_numbers_are_spoken_the_agreed_way(self):
        words = [w for i in self.tl["narration"] for w in i.get("words", [])]
        spoken = {w["w"]: w["spoken"] for w in words if w["w"] in ("348", "2019")}
        self.assertEqual(spoken, {"348": "três quatro oito", "2019": "dois mil e dezenove"})
        self.assertEqual(sum(w["w"] == "348" for w in words), 2)
        self.assertTrue(all("meia" not in w["spoken"] for w in words))

    def test_markdown_script_matches_active_narration(self):
        """O .md (roteiro humano) tem que dizer o mesmo que narration.json: quem fala, texto e respirações."""
        md = (ROOT / "ep03-fim-da-linha.md").read_text(encoding="utf-8")
        norm = lambda t: re.sub(r"\s+", " ", t).strip().lower()                          # noqa: E731

        def parse(speaker, line):
            labels = re.findall(r"\*\(([^)]*)\)\*", line)
            text = re.sub(r"\*\([^)]*\)\*", "", line).replace("*", "").replace('"', "")
            return speaker, norm(text), [l.lower() for l in labels]

        md_blocks = [parse("protagonista", m) for m in re.findall(r"\*\*Fala[^\n]*\n\s*>\s*(.+)", md)]
        md_blocks += [parse(sp.lower(), q) for sp, q in re.findall(r"\*\*(Motorista|Protagonista)[^\n]*\n\s*>\s*(.+)", md)]
        self.assertEqual(len(md_blocks), 5)                # s1 + (s2: motorista, protag.) + (s3: protag., motorista)

        expected = []
        for sid in ("s1", "s2", "s3"):
            groups = []
            for i in (x for x in self.tl["narration"] if x["scene"] == sid and x["kind"] != "silence"):
                spk = i.get("speaker", "protagonista")
                if not groups or groups[-1][0] != spk:
                    groups.append([spk, [], []])
                if i["kind"] == "speech":
                    groups[-1][1].append(i["text"])
                else:
                    groups[-1][2].append(i["label"].lower())
            expected += [(g[0], norm(" ".join(g[1])), g[2]) for g in groups]
        self.assertEqual(md_blocks, expected)

    # ---- o final: corte, silêncio ---------------------------------------------------
    def test_black_and_absolute_silence_after_the_cut(self):
        black = [r["frame"] for r in self.rows if r["black"]]
        self.assertEqual(black, list(range(59 * FPS, 3600)))                              # 1 s de preto a partir de 59,0
        self.assertEqual(self.cues["freada-metal"]["start_frame"], 59 * FPS)
        self.assertEqual(self.beats["b3-corte"]["start_frame"], 59 * FPS)
        for c in self.tl["sfx"]["cues"]:
            if c["id"] != "freada-metal":
                self.assertLessEqual(c["end"], 59.0 + 1e-6, c["id"])                       # todo o resto corta em 59,0
        sound_end = self.cues["freada-metal"]["end"]
        self.assertAlmostEqual(sound_end, 59.6, places=2)                                  # e depois, silêncio absoluto
        generated = (self.tl["sfx"]["footsteps"] + self.tl["sfx"].get("bumps", []) + self.tl["sfx"]["heartbeat"]
                     + self.tl["sfx"].get("flicker", []))
        self.assertTrue(all(g["start"] < 59.0 for g in generated))
        self.assertTrue(all(it["end"] <= 57.1 for it in self.tl["narration"]))             # fala acaba antes da ação final

    def test_final_fall_is_a_tumble_into_red(self):
        last = next(r for r in reversed(self.rows) if not r["black"])
        self.assertLess(last["look_pitch"], -60)
        self.assertGreater(last["look_roll"], 35)
        self.assertEqual(last["red_fog"], 1.0)
        self.assertGreater(last["fov_pct"], 10)

    # ---- batimentos: som = tremor da câmera ----------------------------------------------
    def test_heartbeat_sfx_land_on_the_camera_pulse(self):
        beats = self.tl["sfx"]["heartbeat"]
        self.assertGreater(len(beats), 150)
        heart = [r["heart"] for r in self.rows]
        for b in beats:
            f = b["start_frame"]
            self.assertGreaterEqual(heart[f], 0.88, f"batida em {b['start']}s")          # o frame do SFX é o PICO do pulso
        gains = [b["gain_db"] for b in beats]
        self.assertGreater(gains[-1] - gains[0], 25)                                       # crescendo
        self.assertTrue(all(b2 >= a - 1e-6 for a, b2 in zip(gains, gains[1:])))
        bpm = [b["bpm"] for b in beats]
        self.assertGreater(bpm[-1], bpm[0] + 30)                                            # e acelerando
        self.assertTrue(all(b["origin"] == "roteiro" for b in beats))

    def test_ambience_is_ducked_as_the_heart_grows(self):
        duck = dict(map(tuple, self.tl["sfx"]["mix"]["ambience_gain_db"]))
        self.assertLess(duck[58.9], duck[20.0])

    # ---- cena 1: cambaleio e balaústres ---------------------------------------------------
    def test_handrail_grabs_are_one_event_in_audio_and_camera(self):
        for n in range(1, 5):
            cue, kick = self.cues[f"mao-balaustre-{n}"], self.kicks[f"k-grab-{n}"]
            self.assertEqual(round(kick["t"] * FPS), cue["start_frame"])
            self.assertTrue(0.35 < cue["start"] < 6.3)                                      # durante o cambaleio
        steps = [s for s in self.tl["sfx"]["footsteps"] if s["segment"] == "cambaleio-corredor"]
        self.assertEqual({r["frame"] for r in self.rows if r["step"]} & {s["start_frame"] for s in steps},
                         {s["start_frame"] for s in steps})
        self.assertGreaterEqual(len(steps), 10)
        self.assertTrue(all(s["origin"] == "roteiro" for s in steps))                       # "passos pesados no piso metálico"

    def test_stumble_is_much_rougher_than_calm_walking_would_be(self):
        roll = max(abs(r["shake_roll"]) for r in self.rows[21:360])
        self.assertGreater(roll, 3.0)

    def test_looks_at_the_door_on_the_right(self):
        look = {r["frame"]: r["look_yaw"] for r in self.rows}
        b = self.beats["b1-porta"]
        self.assertGreater(look[round((b["start"] + 0.9) * FPS)], 40)

    # ---- cena 2: o pescoço, o rádio, o recuo --------------------------------------------------
    def test_neck_cracks_follow_the_turn_and_radio_tracks_the_driver(self):
        turn = self.beats["b2-pescoco"]
        cracks = [self.cues[f"estalo-pescoco-{n}"] for n in (1, 2, 3)]
        self.assertEqual([round(c["start"] - turn["start"], 2) for c in cracks], [0.5, 1.4, 2.4])
        self.assertTrue(all(c["origin"] == "roteiro" for c in cracks))
        self.assertLess(cracks[0]["start"], self.items["s2-02"]["start"])                   # estala antes de ele falar
        for n, c in enumerate(cracks, 1):
            pulse = next(p for p in self.tl["camera"]["pulses"] if p["id"] == f"p-estalo-{n}")
            self.assertEqual(round(pulse["t"] * FPS), c["start_frame"])
        gain = dict(map(tuple, self.cues["radio-am"]["automation"]["gain_db"]))
        self.assertGreater(max(g for t, g in gain.items() if 22 <= t <= 33), gain[20.3] + 8)  # sobe com a voz dele
        self.assertLess(gain[self.items["s2-05"]["start"]], -24)                             # recua quando o protagonista grita

    def test_driver_face_reveal_drops_the_light(self):
        rosto = self.beats["b2-rosto"]["start"]
        ev = [e for e in self.tl["camera"]["flicker"] if e["origin"] == "marcado" and abs(e["t"] - (rosto - 0.2)) < 0.02]
        self.assertEqual(len(ev), 1)
        f0 = round(ev[0]["t"] * FPS)
        self.assertTrue(all(self.rows[f]["light"] == 0.0 for f in range(f0, f0 + ev[0]["frames"])))

    def test_two_steps_back_then_the_turnstile_hit(self):
        back = [s for s in self.tl["sfx"]["footsteps"] if s["segment"] == "recua-catraca"]
        self.assertEqual(len(back), 2)                                                      # "recuando dois passos"
        hit = self.cues["costas-catraca"]
        self.assertGreater(hit["start"], back[-1]["start"])                                  # ...e então bate as costas
        self.assertEqual(round(self.kicks["k-costas"]["t"] * FPS), hit["start_frame"])
        gasp = self.items["s2-05"]
        self.assertLess(gasp["start"], back[0]["start"])
        self.assertLess(hit["start"], gasp["start"] + 1.2)

    # ---- cena 3: revelação e porta --------------------------------------------------------------
    def test_each_blink_during_the_approach_is_closer_and_the_last_is_the_reveal(self):
        marked = [e for e in self.tl["camera"]["flicker"] if e["origin"] == "marcado" and e["t"] > 42]
        reveal = self.beats["b3-revela"]["start"]
        approach = [e for e in marked if e["t"] < reveal]
        self.assertEqual(len(approach), 3)                                                   # 3 piscadas, cada uma mais perto
        self.assertTrue(all(b["t"] > a["t"] for a, b in zip(approach, approach[1:])))
        self.assertLess(reveal - approach[-1]["t"], 0.15)                                    # a última É a revelação
        self.assertGreaterEqual(approach[-1]["frames"], approach[0]["frames"])
        for e in approach:
            self.assertEqual(self.rows[round(e["t"] * FPS)]["light"], 1 - e["depth"] if e["depth"] < 1 else 0.0)
        self.assertGreater(self.items["s3-02"]["start"], reveal)                              # o grito vem depois de ver
        self.assertEqual(round(self.kicks["k-revela"]["t"] * FPS), self.beats["b3-revela"]["start_frame"])
        look = {r["frame"]: r["look_yaw"] for r in self.rows}
        self.assertGreater(look[round(45.0 * FPS)], 165)                                      # olhando para o fundo do corredor

    def test_door_hiss_button_fog_and_driver_line_are_in_order(self):
        porta = self.beats["b3-porta"]
        self.assertEqual(self.cues["porta-pneumatica"]["start_frame"], porta["start_frame"])
        self.assertEqual(self.cues["vento-forte"]["start_frame"], porta["start_frame"])
        self.assertEqual(round(self.kicks["k-porta"]["t"] * FPS), porta["start_frame"])
        self.assertAlmostEqual(porta["start"] - self.cues["botao-vermelho"]["start"], 0.35, places=1)   # clique, depois o chiado
        self.assertGreater(self.items["s3-07"]["start"], porta["start"])                     # a fala cai com a porta aberta
        self.assertLess(self.items["s3-07"]["end"], self.beats["b3-ombro"]["start"] + 1e-6)
        f0 = porta["start_frame"]
        self.assertEqual(self.rows[f0]["red_fog"], 0.0)
        self.assertEqual(self.rows[f0 + 54]["red_fog"], 1.0)                                  # neblina vermelha em 0,9 s
        self.assertTrue(all(self.rows[f]["red_fog"] == 0.0 for f in range(0, f0)))
        marked = [e for e in self.tl["camera"]["flicker"] if abs(e["t"] - porta["start"]) < 0.02]
        self.assertTrue(marked and marked[0]["depth"] < 1.0)                                  # a luz cai ao abrir

    def test_shoulder_grab_and_push_are_synced_with_audio_and_camera(self):
        ombro = self.beats["b3-ombro"]
        self.assertEqual(self.cues["mao-ombro"]["start_frame"], ombro["start_frame"])
        self.assertEqual(round(self.kicks["k-ombro"]["t"] * FPS), ombro["start_frame"])
        self.assertAlmostEqual(ombro["start"], self.items["s3-07"]["end"], places=2)        # "Ação Final [00:57]"
        self.assertAlmostEqual(self.beats["b3-empurra"]["start"], ombro["start"] + 0.4, places=2)
        pushed = [s for s in self.tl["sfx"]["footsteps"] if s["segment"] == "empurrado"]
        self.assertEqual(len(pushed), 3)
        self.assertTrue(all(s["origin"] == "inferido" for s in pushed))

    def test_turning_to_the_front_after_the_last_scream(self):
        look = {r["frame"]: r["look_yaw"] for r in self.rows}
        self.assertGreater(look[round(51.0 * FPS)], 165)
        self.assertLess(abs(look[round(51.7 * FPS)]), 15)
        self.assertGreaterEqual(self.beats["b3-vira-frente"]["start"], self.items["s3-05"]["end"])
        self.assertLess(self.beats["b3-vira-frente"]["start"], self.cues["botao-vermelho"]["start"])

    # ---- geral -------------------------------------------------------------------------------------
    def test_light_and_road_are_generated_from_one_event_list(self):
        events, lamp = self.tl["camera"]["flicker"], self.tl["sfx"]["flicker"]
        self.assertEqual([e["t"] for e in events], [f["start"] for f in lamp])
        for e in events:
            self.assertLessEqual(self.rows[round(e["t"] * FPS)]["light"], 1 - e["depth"] + 1e-3)
        cam_t = [b["t"] for b in self.tl["camera"]["bumps"]]
        self.assertEqual(cam_t, [b["start"] for b in self.tl["sfx"]["bumps"]])
        self.assertEqual({r["frame"] for r in self.rows if r["bump"]}, {round(t * FPS) for t in cam_t})
        self.assertGreater(len(cam_t), 100)                                                   # o ônibus nunca reduz: estrada o tempo todo

    def test_extra_columns_for_ep3(self):
        self.assertEqual(self.tl["camera"]["columns"][-4:], ["light", "motion_blur", "bump", "red_fog"])
        self.assertEqual(len(self.rows), 3600)

    def test_deterministic(self):
        again = build_episode("ep03", write=False)
        again.pop("_cam")
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(self.tl, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
