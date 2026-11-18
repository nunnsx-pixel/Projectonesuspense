"""Testes do pipeline do ep01.   Rodar:  python -m unittest discover -s tests -v"""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.build import build_episode                                  # noqa: E402
from pipeline.narration import count_syllables, fit_status               # noqa: E402
from pipeline.timeline import FPS, Resolver                              # noqa: E402


def copy_project(dst: Path) -> Path:
    shutil.copy(ROOT / "scenes-config.json", dst / "scenes-config.json")
    shutil.copytree(ROOT / "ep01", dst / "ep01", ignore=shutil.ignore_patterns("build"))
    return dst


def edit_json(path: Path, fn) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class Ep01(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tl = build_episode("ep01", write=False)
        cls.cam = cls.tl.pop("_cam")
        cls.rows = cls.cam["rows"]

    # ---- estrutura -------------------------------------------------------------
    def test_frames_and_final_cut(self):
        self.assertEqual(len(self.rows), 3600)
        self.assertEqual([r["frame"] for r in self.rows], list(range(3600)))
        first_black = next(r["frame"] for r in self.rows if r["black"])
        self.assertEqual(first_black, round(59.5 * FPS))
        self.assertTrue(all(r["black"] for r in self.rows[first_black:]))
        closed = next(r["t"] for r in self.rows if r["eyelid"] >= 0.999)
        self.assertLess(closed, 59.5)            # pálpebra fecha ANTES do corte seco

    def test_scenes_cover_episode(self):
        sc = self.tl["scenes"]
        self.assertEqual(sc[0]["start"], 0)
        self.assertEqual(sc[-1]["end"], 60)
        for a, b in zip(sc, sc[1:]):
            self.assertEqual(a["end"], b["start"])

    def test_narration_ordered_inside_windows(self):
        items = self.tl["narration"]
        for a, b in zip(items, items[1:]):
            self.assertLessEqual(a["end"], b["start"] + 1e-6, f"{a['id']} / {b['id']}")
        for it in items:
            sc = next(s for s in self.tl["scenes"] if s["id"] == it["scene"])
            w0, w1 = sc["narration_fit"]["window"]
            self.assertGreaterEqual(it["start"], w0 - 1 / FPS)
            self.assertLessEqual(it["end"], w1 + 1 / FPS)
            for w in it.get("words", []):
                self.assertGreater(w["end"], w["start"])
            for w1_, w2_ in zip(it.get("words", []), it.get("words", [])[1:]):
                self.assertLessEqual(w1_["end"], w2_["start"] + 1e-6)

    def test_all_cues_have_origin_and_fit_episode(self):
        for c in self.tl["sfx"]["cues"]:
            self.assertIn(c["origin"], ("roteiro", "inferido"), c["id"])
            self.assertGreaterEqual(c["start"], 0)
            self.assertLessEqual(c["end"], 60)

    # ---- SINCRONIA ---------------------------------------------------------------
    def test_steps_sfx_and_csv_are_the_same_events(self):
        steps = [s["t"] for s in self.tl["camera"]["steps"]]
        sfx_steps = [f["start"] for f in self.tl["sfx"]["footsteps"]]
        self.assertEqual(steps, sfx_steps)
        for t in steps:                                           # na grade de frames (JSON arredonda a 4 casas)
            self.assertLess(abs(t * FPS - round(t * FPS)), 0.01)
        csv_frames = {r["frame"] for r in self.rows if r["step"]}
        self.assertEqual(csv_frames, {round(t * FPS) for t in steps})
        self.assertGreater(len(steps), 50)

    def test_head_is_lowest_at_footfall(self):
        gait, d = self.cam["gait"], 3 / FPS
        checked = 0
        for i, s in enumerate(gait.steps):
            nxt = gait.steps[i + 1] if i + 1 < len(gait.steps) else None
            prv = gait.steps[i - 1] if i else None
            if not (nxt and prv and s["connected_next"] and prv["connected_next"]) or s["t"] < 0.2:
                continue
            y = gait.at(s["t"])["y_cm"]
            self.assertLess(y, gait.at(s["t"] - d)["y_cm"], f"passo {s['t']:.3f}s")
            self.assertLess(y, gait.at(s["t"] + d)["y_cm"], f"passo {s['t']:.3f}s")
            checked += 1
        self.assertGreater(checked, 40)

    def test_chest_rises_on_scripted_breaths(self):
        lvl = {r["frame"]: r["breath"] for r in self.rows}
        explicit = [b for b in self.tl["breaths"] if b["explicit"] and b["inhale"] >= 0.2]
        self.assertGreaterEqual(len(explicit), 4)            # sigh, fungada(0.19 não conta), bocejo, profunda, inspiração
        for b in explicit:
            f0 = round(b["t"] * FPS)
            f1 = round((b["t"] + b["inhale"]) * FPS)
            self.assertGreater(lvl[f1], lvl[max(f0 - 1, 0)] + 0.25, b["ref"])

    def test_phone_beat_is_anchored_to_the_words(self):
        beat = next(b for s in self.tl["scenes"] for b in s["beats"] if b["id"] == "b1-celular")
        item = next(i for i in self.tl["narration"] if i["id"] == "s1-04")
        quase = next(w for w in item["words"] if w["w"] == "quase")
        meia = next(w for w in item["words"] if w["w"] == "meia-noite")
        self.assertLessEqual(beat["start"], quase["start"])               # celular já está subindo
        self.assertGreater(beat["start"], quase["start"] - 0.6)
        self.assertGreater(beat["end"], meia["end"])                      # e fica até depois da frase

    def test_ticket_beep_after_ne_and_sit_before_toss(self):
        cues = {c["id"]: c for c in self.tl["sfx"]["cues"]}
        beats = {b["id"]: b for s in self.tl["scenes"] for b in s["beats"]}
        ne = next(w for i in self.tl["narration"] if i["id"] == "s2-04" for w in i["words"] if w["w"] == "né")
        self.assertAlmostEqual(cues["bip-catraca"]["start"], ne["end"] + 0.2, places=2)
        self.assertGreater(cues["catraca-giro"]["start"], cues["bip-catraca"]["start"])
        self.assertLess(beats["b3-senta"]["start"], beats["b3-mochila"]["start"])

    def test_vignette_blur_and_engine_follow_the_script(self):
        v = {r["frame"]: r for r in self.rows}
        self.assertLess(v[round(40 * FPS)]["vignette"], v[round(55 * FPS)]["vignette"])
        self.assertEqual(self.rows[0]["speed_kmh"], 0)
        self.assertGreater(self.rows[-1]["speed_kmh"], 50)
        eng = next(c for c in self.tl["sfx"]["cues"] if c["id"] == "motor-onibus")
        self.assertIn("pitch_semitones", eng["automation"])
        self.assertIn("lowpass_hz", eng["automation"])

    def test_every_scene_fits_its_window(self):
        self.assertEqual(self.tl["warnings"], [])
        for sc in self.tl["scenes"]:
            self.assertEqual(sc["narration_fit"]["status"], "ok", sc["id"])

    def test_scene3_is_the_approved_script(self):
        s3 = [i for i in self.tl["narration"] if i["scene"] == "s3"]
        spoken = " ".join(i["text"] for i in s3 if i["kind"] == "speech")
        self.assertEqual(spoken, "Pronto, mochila no banco do lado pra ninguém sentar junto. "
                                 "Meu ponto é exato o 348, na marginal. Se eu passar do ponto 348, eu tô frito. "
                                 "Ai, fechar o olho só cinco minutinhos...")
        self.assertNotIn("s3-03", [i["id"] for i in s3])                    # "Meu olho tá pesando" cortado
        self.assertEqual([i["id"] for i in s3 if i["kind"] == "breath"], ["s3-02", "s3-06"])  # bocejo e respiração

    def test_348_is_spoken_tres_quatro_oito(self):
        w = next(w for i in self.tl["narration"] if i["id"] == "s3-04" for w in i["words"] if w["w"] == "348")
        self.assertEqual(w["spoken"], "três quatro oito")
        self.assertEqual(w["syl"], 5)
        self.assertNotIn("meia", w["spoken"])             # "meia" = 6: "três-meia-oito" seria 368

    def test_markdown_script_matches_active_narration(self):
        """O .md (roteiro humano) tem que dizer o mesmo que narration.json: texto e respirações."""
        md = (ROOT / "ep01-embarque-campinas.md").read_text(encoding="utf-8")
        lines = re.findall(r"\*\*Fala[^\n]*\n\s*>\s*(.+)", md)
        self.assertEqual(len(lines), 3)
        for sid, line in zip(("s1", "s2", "s3"), lines):
            items = [i for i in self.tl["narration"] if i["scene"] == sid]
            labels = re.findall(r"\*\(([^)]*)\)\*", line)
            text = re.sub(r"\*\([^)]*\)\*", "", line).replace("*", "").replace('"', "")
            norm = lambda t: re.sub(r"\s+", " ", t).strip().lower()          # noqa: E731
            self.assertEqual(norm(text), norm(" ".join(i["text"] for i in items if i["kind"] == "speech")), sid)
            self.assertEqual([l.lower() for l in labels],
                             [i["label"].lower() for i in items if i["kind"] == "breath"], sid)

    def test_bus_leaves_before_the_yawn_and_reaches_full_roar(self):
        beats = {b["id"]: b for s in self.tl["scenes"] for b in s["beats"]}
        s3_01 = next(i for i in self.tl["narration"] if i["id"] == "s3-01")
        yawn = next(i for i in self.tl["narration"] if i["id"] == "s3-02")
        self.assertAlmostEqual(beats["b3-partida"]["start"], s3_01["end"], places=2)    # parte ao fim da 1ª frase ("...sentar junto.")
        self.assertLess(beats["b3-partida"]["start"], yawn["start"])
        self.assertGreater(beats["b3-janela"]["start"], yawn["start"])                  # vira p/ a janela já no bocejo
        speed = {round(r["t"], 3): r["speed_kmh"] for r in self.rows}
        self.assertGreater(speed[58.0], 58)                                              # velocidade cheia no fim
        eng = next(c for c in self.tl["sfx"]["cues"] if c["id"] == "motor-onibus")
        self.assertGreater(dict(map(tuple, eng["automation"]["pitch_semitones"]))[58.0], 8.5)

    def test_deterministic(self):
        again = build_episode("ep01", write=False)
        again.pop("_cam")
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(self.tl, sort_keys=True))


class Units(unittest.TestCase):
    def test_syllables_ptbr(self):
        expect = {"Jundiaí": 3, "rodoviária": 5, "ninguém": 2, "quero": 2, "saindo": 3, "sério": 2, "Boa": 2,
                  "cenário": 3, "meio": 2, "minutinhos": 4, "acadêmico": 5, "Deus": 1, "mochila": 3, "aqui": 2,
                  "trezentos": 3, "quarenta": 3, "oito": 2}
        for word, n in expect.items():
            self.assertEqual(count_syllables(word), n, word)

    def test_fit_status(self):
        self.assertEqual(fit_status(1.0), "ok")
        self.assertEqual(fit_status(0.8), "apertado")
        self.assertEqual(fit_status(0.5), "ESTOURA")
        self.assertEqual(fit_status(2.0), "folgado")

    def test_resolver_follows_retimed_words(self):
        def make(shift):
            r = Resolver()
            r.items["a"] = {"start": 1 + shift, "end": 4 + shift,
                            "words": [{"w": "oi,", "start": 1 + shift, "end": 2 + shift},
                                      {"w": "tchau", "start": 2 + shift, "end": 4 + shift}]}
            r.register("cue", [{"id": "c1", "at": {"ref": "a", "word": "tchau", "edge": "end", "offset": 0.5}},
                               {"id": "c2", "at": {"cue": "c1", "offset": 0.25}}])
            return r
        self.assertAlmostEqual(make(0).span("cue", "c2")[0], 4.75)
        self.assertAlmostEqual(make(3).span("cue", "c2")[0], 7.75)      # tudo acompanha a fala

    def test_resolver_rejects_cycles(self):
        r = Resolver()
        r.register("cue", [{"id": "a", "at": {"cue": "b"}}, {"id": "b", "at": {"cue": "a"}}])
        with self.assertRaises(ValueError):
            r.span("cue", "a")


class Validation(unittest.TestCase):
    def test_text_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = copy_project(Path(d))
            edit_json(root / "ep01" / "narration.json",
                      lambda n: n["scenes"][0]["items"][1].update(text="Mano, sério, eu AMO fazer trabalho em grupo!"))
            with self.assertRaisesRegex(ValueError, "difere do dialogue"):
                build_episode("ep01", root=root, write=False)

    def test_impossible_window_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            root = copy_project(Path(d))
            edit_json(root / "ep01" / "narration.json", lambda n: n["scenes"][0].update(window=[0.15, 9.0]))
            tl = build_episode("ep01", root=root, write=False)
            self.assertEqual(tl["scenes"][0]["narration_fit"]["status"], "ESTOURA")
            self.assertTrue(any(w.startswith("s1:") for w in tl["warnings"]))

    def test_skipped_line_leaves_the_active_script(self):
        """`skip` tira a fala do roteiro ativo: o dialogue de scenes-config.json precisa acompanhar."""
        last = " Ai, fechar o olho só cinco minutinhos..."
        with tempfile.TemporaryDirectory() as d:
            root = copy_project(Path(d))
            edit_json(root / "ep01" / "narration.json", lambda n: [
                it.update(skip=True) for it in n["scenes"][2]["items"] if it["id"] == "s3-07"])
            with self.assertRaisesRegex(ValueError, "difere do dialogue"):        # dialogue ainda tem a fala
                build_episode("ep01", root=root, write=False)

            def drop(c):
                sc = c["episodes"][0]["scenes"][2]
                sc["dialogue"] = sc["dialogue"].replace(last, "")
            edit_json(root / "scenes-config.json", drop)
            tl = build_episode("ep01", root=root, write=False)
        self.assertNotIn("s3-07", [i["id"] for i in tl["narration"]])

    def test_measured_timing_overrides_and_cues_follow(self):
        with tempfile.TemporaryDirectory() as d:
            root = copy_project(Path(d))
            (root / "ep01" / "narration.measured.json").write_text(json.dumps(
                {"items": {"s2-04": {"start": 22.0, "end": 23.6}}}), encoding="utf-8")
            tl = build_episode("ep01", root=root, write=False)
        item = next(i for i in tl["narration"] if i["id"] == "s2-04")
        self.assertEqual(item["timing"], "medido")
        self.assertAlmostEqual(item["start"], 22.0, places=1)
        bip = next(c for c in tl["sfx"]["cues"] if c["id"] == "bip-catraca")
        self.assertAlmostEqual(bip["start"], 23.6 + 0.2, places=1)       # o bip acompanhou "né?"

    def test_measured_overlap_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = copy_project(Path(d))
            (root / "ep01" / "narration.measured.json").write_text(json.dumps(
                {"items": {"s2-04": {"start": 22.5, "end": 24.5}}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sobrepostos"):
                build_episode("ep01", root=root, write=False)


if __name__ == "__main__":
    unittest.main()
