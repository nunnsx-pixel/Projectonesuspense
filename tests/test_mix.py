"""Mixagem final (pipeline/mix.py): SFX sintetizados + voz medida, presos à linha do tempo. Precisa de numpy (e do ffmpeg para a voz)."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import wave
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

from pipeline import mix

ROOT = Path(__file__).resolve().parent.parent
SR = mix.SR


def rms_db(x, a, b):
    seg = x[:, int(a * SR):int(b * SR)].astype(np.float64)
    return 20 * np.log10(float(np.sqrt(np.mean(seg ** 2))) + 1e-12)


@unittest.skipIf(np is None, "numpy ausente")
class Sfx(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mixes = {ep: mix.mix_episode(ep, with_voice=False) for ep in ("ep01", "ep02", "ep03")}
        cls.tl = {ep: json.loads((ROOT / ep / "build" / f"{ep}.timeline.json").read_text(encoding="utf-8")) for ep in cls.mixes}

    def test_exactly_sixty_seconds_stereo_without_clipping(self):
        for ep, m in self.mixes.items():
            a = m["audio"]
            self.assertEqual(a.shape, (2, 60 * SR), ep)
            self.assertLessEqual(float(np.abs(a).max()), 1.0, ep)
            self.assertLess(m["report"]["peak_dbfs"], -0.5, ep)
            self.assertEqual(m["report"]["unknown_cues"], [], ep)               # todo cue do cue sheet tem receita de som

    def test_it_is_deterministic(self):
        again = mix.mix_episode("ep02", with_voice=False)["audio"]
        self.assertTrue(np.array_equal(again, self.mixes["ep02"]["audio"]))

    def test_ep03_hard_cut_is_absolute_silence_after_the_brake(self):
        a = self.mixes["ep03"]["audio"]
        brake = next(c for c in self.tl["ep03"]["sfx"]["cues"] if c["id"] == "freada-metal")
        self.assertEqual(float(np.abs(a[:, int((brake["end"] + 0.05) * SR):]).max()), 0.0)     # silêncio ABSOLUTO até 60 s
        self.assertGreater(rms_db(a, brake["start"] + 0.02, brake["start"] + 0.3), -30)         # e a freada existe
        self.assertLess(rms_db(a, brake["start"] - 1.0, brake["start"] - 0.01), rms_db(a, brake["start"] + 0.02, brake["start"] + 0.3))

    def test_footsteps_land_on_the_camera_contact_frames(self):
        a = self.mixes["ep01"]["audio"]
        steps = self.tl["ep01"]["sfx"]["footsteps"]
        loud = [s for s in steps if s["gain_db"] > -12][:8]
        self.assertTrue(loud)
        for s in loud:
            self.assertGreater(rms_db(a, s["start"], s["start"] + 0.05) - rms_db(a, s["start"] - 0.12, s["start"] - 0.02), 3.0, s["id"])

    def test_bum_is_the_loudest_moment_of_ep02_s1(self):
        a = self.mixes["ep02"]["audio"]
        bum = next(c for c in self.tl["ep02"]["sfx"]["cues"] if c["id"] == "bum-buraco")
        self.assertGreater(rms_db(a, bum["start"], bum["start"] + 0.3), rms_db(a, 5.0, 15.0) + 10)

    def test_ep01_engine_muffles_as_sleep_arrives(self):
        a = self.mixes["ep01"]["audio"]

        def hf(t):                                           # energia acima de 1 kHz, 1 s de janela
            seg = a[0, int(t * SR):int((t + 1) * SR)].astype(np.float64)
            sp = np.abs(np.fft.rfft(seg)) ** 2
            f = np.fft.rfftfreq(len(seg), 1 / SR)
            return float(sp[f > 1000].sum() / sp.sum())
        self.assertLess(hf(57.0), 0.5 * hf(26.0))


@unittest.skipIf(np is None or shutil.which("ffmpeg") is None, "numpy/ffmpeg ausentes")
class Voice(unittest.TestCase):
    def test_voice_enters_where_the_measurement_says_with_its_level_normalised(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for f in ("timeline.json", "camera.csv"):
                (root / "ep01" / "build").mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / "ep01" / "build" / f"ep01.{f}", root / "ep01" / "build" / f"ep01.{f}")
            n = int(2.0 * SR)
            t = np.arange(n) / SR
            tone = (0.05 * 32767 * np.sin(2 * np.pi * 220 * t)).astype("<i2")                # voz "baixinha": o nivelamento a sobe
            (root / "ep01" / "audio").mkdir()
            with wave.open(str(root / "ep01" / "audio" / "s1.wav"), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes(tone.tobytes())
            (root / "ep01" / "narration.measured.json").write_text(
                json.dumps({"audio": {"s1.wav": {"offset": 3.0, "speech_db": -34.0}}, "items": {}}), encoding="utf-8")
            with_v = mix.mix_episode("ep01", root)
            without = mix.mix_episode("ep01", root, with_voice=False)
            a, b = with_v["audio"], without["audio"]
            self.assertTrue(np.allclose(a[:, :int(2.9 * SR)], b[:, :int(2.9 * SR)], atol=1e-3))                     # antes: igual
            self.assertGreater(rms_db(a, 3.2, 4.8), rms_db(b, 3.2, 4.8) + 3)                                         # entra em 3,0 s
            self.assertEqual(list(with_v["report"]["voice"]), ["s1.wav"])
            self.assertAlmostEqual(with_v["report"]["voice"]["s1.wav"]["gain_db"], mix.VOICE_REF_DB + 34.0, places=1)


if __name__ == "__main__":
    unittest.main()
