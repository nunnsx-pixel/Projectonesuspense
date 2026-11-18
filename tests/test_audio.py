"""Análise de áudio da voz (pipeline/audio.py): decodificação, segmentação, alinhamento e o fluxo até o build.

Não há gravação real no repositório: os testes usam voz SINTÉTICA (tests/synth_voice.py) com gabarito conhecido, derivada da
linha do tempo estimada de cada episódio. Python puro (o ffmpeg só é usado no teste de formato comprimido, se existir).
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import synth_voice as sv  # noqa: E402
from pipeline import audio  # noqa: E402
from pipeline.build import _retime, build_episode, match_pauses  # noqa: E402
from pipeline.timeline import FPS  # noqa: E402

EPS = ("ep01", "ep02", "ep03")
FRAME = 1.0 / FPS


# ---- utilidades -------------------------------------------------------------------------------------------------
def make_root(tmp: Path) -> Path:
    """Cópia só das fontes do projeto (sem build/ nem measured), para o teste gravar à vontade."""
    root = tmp / "proj"
    root.mkdir()
    shutil.copy(ROOT / "scenes-config.json", root / "scenes-config.json")
    for ep in EPS:
        shutil.copytree(ROOT / ep, root / ep, ignore=shutil.ignore_patterns("build", "narration.measured.json*", "audio", "__pycache__"))
    return root


def wav_bytes(samples, rate=8000, bits=16, channels=1, tag=1, extensible=False, stream_header=False, big=False):
    """Monta um WAV na mão (para testar o leitor com formatos que o módulo `wave` não cobre)."""
    if tag == 3 and bits == 32:
        body = array("f", samples)
        if big:
            body.byteswap()
        pcm = body.tobytes()
    elif bits == 8:
        pcm = bytes(int(max(0, min(255, v * 127 + 128))) for v in samples)
    elif bits == 16:
        a = array("h", (int(max(-1, min(1, v)) * 32767) for v in samples))
        if big:
            a.byteswap()
        pcm = a.tobytes()
    elif bits == 24:
        pcm = b"".join(int(max(-1, min(1, v)) * 8388607).to_bytes(3, "big" if big else "little", signed=True) for v in samples)
    elif bits == 32:
        a = array("i", (int(max(-1, min(1, v)) * 2147483647) for v in samples))
        if big:
            a.byteswap()
        pcm = a.tobytes()
    else:
        raise ValueError(bits)
    e = ">" if big else "<"
    block = channels * bits // 8
    if extensible:
        fmt = struct.pack(e + "HHIIHH", 0xFFFE, channels, rate, rate * block, block, bits) + struct.pack(e + "HHI", 22, bits, 0) \
            + struct.pack(e + "H", tag) + b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71"
    else:
        fmt = struct.pack(e + "HHIIHH", tag, channels, rate, rate * block, block, bits)
    size = 0xFFFFFFFF if stream_header else len(pcm)
    magic = b"RIFX" if big else b"RIFF"
    return magic + struct.pack(e + "I", 36 + len(pcm)) + b"WAVE" + b"fmt " + struct.pack(e + "I", len(fmt)) + fmt \
        + b"data" + struct.pack(e + "I", size) + pcm


def tone(seconds, rate=8000, f=200.0, amp=0.5):
    return [amp * math.sin(2 * math.pi * f * i / rate) for i in range(int(seconds * rate))]


def estimated(root, ep):
    return build_episode(ep, root=root, write=False, use_measured=False)["narration"]


def recover(root, ep, seed, tmp, **kw):
    """Sintetiza uma gravação (gabarito conhecido) do episódio e roda a análise. Devolve (gabarito, resultado)."""
    est = estimated(root, ep)
    truth = sv.perturb(est, seed=seed)
    adir = tmp / f"{ep}_{seed}"
    sv.write_wav(adir / "narration.wav", sv.render(truth, 60.0, seed=seed, **kw))
    return truth, audio.analyse_episode(ep, root=root, audio_dir=adir)


def iou(a0, a1, b0, b1):
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    return inter / (max(a1, b1) - min(a0, b0))


class WithProject(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls.tmpdir.name)
        cls.root = make_root(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()


# ---- decodificação ------------------------------------------------------------------------------------------------
class Decoding(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.sig = tone(1.0, amp=0.4)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, data, name="a.wav"):
        p = self.dir / name
        p.write_bytes(data)
        return audio.read_audio(p)

    def assert_signal(self, samples, rate, tol=0.01):
        self.assertEqual(rate, 8000)
        self.assertEqual(len(samples), len(self.sig))
        self.assertLess(max(abs(a - b) for a, b in zip(samples, self.sig)), tol)

    def test_pcm_formats(self):
        for bits in (8, 16, 24, 32):
            with self.subTest(bits=bits):
                s, r = self.read(wav_bytes(self.sig, bits=bits))
                self.assert_signal(s, r, tol=0.02 if bits == 8 else 0.002)

    def test_float_formats_and_extensible_header(self):
        s, r = self.read(wav_bytes(self.sig, bits=32, tag=3))
        self.assert_signal(s, r, 1e-6)
        s, r = self.read(wav_bytes(self.sig, bits=16, extensible=True))
        self.assert_signal(s, r, 0.002)

    def test_big_endian_and_streamed_header(self):
        s, r = self.read(wav_bytes(self.sig, bits=16, big=True))
        self.assert_signal(s, r, 0.002)
        s, r = self.read(wav_bytes(self.sig, bits=16, stream_header=True))          # tamanho do bloco de dados inválido
        self.assert_signal(s, r, 0.002)

    def test_stereo_is_mixed_down_to_mono(self):
        left, right = self.sig, [0.0] * len(self.sig)
        inter = [v for pair in zip(left, right) for v in pair]
        s, r = self.read(wav_bytes(inter, channels=2))
        self.assertEqual(len(s), len(self.sig))
        self.assertLess(max(abs(a - b / 2) for a, b in zip(s, self.sig)), 0.002)

    def test_high_sample_rates_are_decimated(self):
        s, r = self.read(wav_bytes(tone(1.0, rate=48000), rate=48000))
        self.assertEqual(r, 16000)
        self.assertEqual(len(s), 16000)

    def test_clear_errors(self):
        with self.assertRaisesRegex(audio.AudioError, "não encontrado"):
            audio.read_audio(self.dir / "nao-existe.wav")
        with self.assertRaisesRegex(audio.AudioError, "WAV com formato não suportado"):
            self.read(wav_bytes(self.sig, bits=16, tag=2))
        with self.assertRaisesRegex(audio.AudioError, "curto demais"):
            self.read(wav_bytes(tone(0.1)))

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg não instalado")
    def test_compressed_formats_go_through_ffmpeg(self):
        wav = self.dir / "a.wav"
        wav.write_bytes(wav_bytes(self.sig))
        out = self.dir / "a.flac"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), str(out)], check=True)
        s, r = audio.read_audio(out)
        self.assertEqual(r, 16000)
        self.assertAlmostEqual(len(s) / r, 1.0, delta=0.02)
        self.assertGreater(max(s), 0.3)

    def test_non_wav_without_ffmpeg_explains_what_to_do(self):
        p = self.dir / "a.mp3"
        p.write_bytes(b"ID3")
        old = shutil.which
        audio.shutil.which = lambda *_: None
        try:
            with self.assertRaisesRegex(audio.AudioError, "ffmpeg"):
                audio.read_audio(p)
        finally:
            audio.shutil.which = old


# ---- segmentação --------------------------------------------------------------------------------------------------
class Segmentation(unittest.TestCase):
    def make(self, parts, rate=8000, floor=0.0004):
        """parts = [(kind, segundos)]: 'v' fala, 'b' respiração (ruído fraco), 's' silêncio."""
        import random
        rnd = random.Random(2)
        out = []
        for kind, dur in parts:
            n = int(dur * rate)
            if kind == "v":
                out += [0.3 * math.sin(2 * math.pi * 130 * i / rate) * (0.6 + 0.4 * math.sin(2 * math.pi * 5 * i / rate)) for i in range(n)]
            elif kind == "b":
                out += [0.012 * rnd.gauss(0, 1) * math.sin(math.pi * i / n) ** 2 for i in range(n)]
            else:
                out += [0.0] * n
        return array("f", (v + rnd.gauss(0, floor) for v in out)), rate

    def test_speech_breath_and_silence_are_told_apart(self):
        s, rate = self.make([("s", 0.5), ("v", 1.0), ("s", 0.4), ("b", 0.8), ("s", 0.3), ("v", 0.7), ("s", 0.5)])
        seg = audio.segment(audio.analyse(s, rate))
        self.assertEqual(len(seg.voiced), 2)
        for (a, b), (ea, eb) in zip(seg.voiced, [(0.5, 1.5), (3.0, 3.7)]):
            self.assertAlmostEqual(a, ea, delta=0.04)
            self.assertAlmostEqual(b, eb, delta=0.04)
        self.assertEqual(len(seg.breaths), 1)
        self.assertAlmostEqual(seg.breaths[0][0], 1.9, delta=0.15)
        self.assertAlmostEqual(seg.breaths[0][1], 2.7, delta=0.15)
        self.assertEqual(len(seg.gaps), 1)                                           # a pausa entre as duas falas

    def test_tiny_dips_inside_a_word_do_not_split_it(self):
        s, rate = self.make([("s", 0.3), ("v", 0.5), ("s", 0.03), ("v", 0.5), ("s", 0.3)])
        seg = audio.segment(audio.analyse(s, rate))
        self.assertEqual(len(seg.voiced), 1)

    def test_digital_silence_between_lines_is_fine(self):
        s, rate = self.make([("s", 0.5), ("v", 1.0), ("s", 0.6), ("v", 1.0), ("s", 0.5)], floor=0.0)
        seg = audio.segment(audio.analyse(s, rate))
        self.assertEqual(len(seg.voiced), 2)

    def test_empty_audio_is_reported(self):
        with self.assertRaisesRegex(audio.AudioError, "vazio"):
            audio.analyse(array("f", [0.0] * 8000), 8000)


class Alignment(unittest.TestCase):
    def test_longest_pauses_win_when_durations_agree(self):
        seg = audio.Segments(voiced=[(0.0, 2.0), (2.5, 4.5), (5.2, 7.0)], gaps=[(2.0, 2.5), (4.5, 5.2)],
                             cuts=[(2.0, 2.5, 1.25), (4.5, 5.2, 1.5)])
        spans = audio.align_speech([2.0, 2.0, 1.8], [2.0, 4.5, 7.0], seg)
        self.assertEqual([(round(a, 2), round(b, 2)) for a, b, _ in spans], [(0.0, 2.0), (2.5, 4.5), (5.2, 7.0)])

    def test_internal_pause_is_not_mistaken_for_a_boundary(self):
        # 2 falas esperadas (2,0 s e 3,0 s); há 3 pausas: uma interna da 2ª fala (0,5 s) e a verdadeira (0,3 s) em 2,0
        seg = audio.Segments(voiced=[(0.0, 2.0), (2.3, 3.5), (4.0, 5.3)], gaps=[(2.0, 2.3), (3.5, 4.0)],
                             cuts=[(2.0, 2.3, 0.75), (3.5, 4.0, 1.25)])
        spans = audio.align_speech([2.0, 3.0], [2.0, 5.0], seg)
        self.assertAlmostEqual(spans[0][1], 2.0, places=2)

    def test_too_few_separable_chunks_is_an_explicit_error(self):
        seg = audio.Segments(voiced=[(0.0, 5.0)], gaps=[], cuts=[])
        with self.assertRaisesRegex(audio.AudioError, "falas coladas"):
            audio.align_speech([2.0, 3.0], [2.0, 5.0], seg)

    def test_weak_energy_valleys_split_lines_that_have_no_pause(self):
        seg = audio.Segments(voiced=[(0.0, 5.0)], gaps=[], cuts=[(2.0, 2.02, 0.2), (3.3, 3.32, 0.2)])
        spans = audio.align_speech([2.0, 3.0], [2.0, 5.0], seg)
        self.assertAlmostEqual(spans[0][1], 2.0, places=2)


# ---- recuperação do gabarito (3 episódios) ----------------------------------------------------------------------------
class Recovery(WithProject):
    def check(self, ep, seed, tol=0.04, breath_iou=0.6, **kw):
        truth, res = recover(self.root, ep, seed, self.tmp, **kw)
        items = res["items"]
        self.assertEqual(set(items), {t["id"] for t in truth})                         # todos os itens ganham tempo
        for t in truth:
            m = items[t["id"]]
            if t["kind"] == "speech":
                self.assertAlmostEqual(m["start"], t["start"], delta=tol, msg=f"{ep} {t['id']} início")
                self.assertAlmostEqual(m["end"], t["end"], delta=tol, msg=f"{ep} {t['id']} fim")
                got = m.get("pauses", [])
                for ta, tb in t["pauses"]:                                              # as pausas claras (>= 0,16 s) têm que aparecer
                    if tb - ta >= 0.16:
                        self.assertTrue(any(abs(a - ta) < 0.05 and abs(b - tb) < 0.05 for a, b in got), f"{ep} {t['id']} pausa {ta:.2f}")
                for a, b in got:                                                         # e nada aparece onde não houve pausa
                    self.assertTrue(any(abs(a - ta) < 0.06 and abs(b - tb) < 0.06 for ta, tb in t["pauses"]), f"{ep} {t['id']} pausa falsa {a:.2f}")
                self.assertGreater(m["conf"], 0.3, f"{ep} {t['id']} confiança")
            elif t["kind"] == "breath":
                self.assertGreater(iou(m["start"], m["end"], t["start"], t["end"]), breath_iou, f"{ep} {t['id']} respiração")
                self.assertNotIn("não detectada", m.get("note", ""))
        return truth, res

    def test_ep01(self):
        for seed in (1, 2):
            self.check("ep01", seed)

    def test_ep02(self):
        for seed in (1, 2):
            self.check("ep02", seed)

    def test_ep03_two_speakers_and_silent_stretches(self):
        for seed in (1, 2):
            truth, res = self.check("ep03", seed)
            sil = [t for t in truth if t["kind"] == "silence"]
            self.assertEqual(len(sil), 4)                                              # pescoço, "processa o que ouviu", passageiro vindo, porta
            for t in sil:                                                              # o mudo ocupa a folga entre as falas vizinhas
                m = res["items"][t["id"]]
                self.assertGreater(m["end"] - m["start"], 0.3)
                self.assertIn("sem voz", m["note"])

    def test_digital_silence_and_noisy_background_and_no_breaths(self):
        self.check("ep01", 3, tol=0.1, floor=0.0)                                      # TTS com silêncio digital entre as falas
        self.check("ep02", 3, tol=0.04, breath_iou=0.45, floor=0.003)                  # fundo ruidoso (-50 dB): a borda da respiração é incerta
        truth, res = recover(self.root, "ep02", 4, self.tmp, breath_amp=0.0)           # voz sem nenhuma respiração gravada
        for t in truth:
            if t["kind"] == "breath":
                m = res["items"][t["id"]]
                self.assertIn("não detectada", m["note"])                              # posição estimada, sinalizada
                self.assertLess(m["conf"], 0.5)
        self.assertTrue(any("confiança baixa" in w for w in res["report"]["warnings"]))

    def test_items_never_overlap_and_stay_in_order(self):
        for ep in EPS:
            _, res = recover(self.root, ep, 5, self.tmp)
            prev = 0.0
            for iid, m in res["items"].items():
                self.assertGreaterEqual(m["start"], prev - 1e-6, f"{ep} {iid}")
                self.assertGreater(m["end"], m["start"])
                prev = m["end"]

    def test_rerunning_is_stable_and_ignores_the_previous_measurement(self):
        truth, res1 = recover(self.root, "ep01", 1, self.tmp)
        audio.write_measured("ep01", res1, root=self.root)
        res2 = audio.analyse_episode("ep01", root=self.root, audio_dir=self.tmp / "ep01_1")
        self.assertEqual(res1["items"], res2["items"])
        (self.root / "ep01" / "narration.measured.json").unlink()
        (self.root / "ep01" / "narration.measured.json.bak").unlink(missing_ok=True)


# ---- trilhas por cena ---------------------------------------------------------------------------------------------------
class PerScene(WithProject):
    def split(self, ep, seed, with_offsets):
        est = estimated(self.root, ep)
        truth = sv.perturb(est, seed=seed)
        samples = sv.render(truth, 60.0, seed=seed)
        adir = self.tmp / f"{ep}_scenes_{with_offsets}"
        scenes = list(dict.fromkeys(i["scene"] for i in est))
        first_truth = {sid: next(t for t, e in zip(truth, est) if e["scene"] == sid)["start"] for sid in scenes}
        offsets = {}
        for k, sid in enumerate(scenes):
            t0 = max(0.0, first_truth[sid] - 0.37)                                       # o arquivo da cena começa um pouco antes da 1ª fala
            t1 = first_truth[scenes[k + 1]] - 0.1 if k + 1 < len(scenes) else 60.0
            a, b = int(t0 * sv.RATE), int(t1 * sv.RATE)
            sv.write_wav(adir / f"{sid}.wav", array("h", samples[a:b]))
            offsets[sid] = a / sv.RATE
        (adir / "offsets.json").write_text(json.dumps(offsets), encoding="utf-8")
        return truth, adir

    def test_one_file_per_scene_with_offsets_json(self):
        truth, adir = self.split("ep01", 1, True)
        res = audio.analyse_episode("ep01", root=self.root, audio_dir=adir)
        for t in truth:
            if t["kind"] == "speech":
                m = res["items"][t["id"]]
                self.assertAlmostEqual(m["start"], t["start"], delta=0.04, msg=t["id"])
                self.assertAlmostEqual(m["end"], t["end"], delta=0.04, msg=t["id"])
        self.assertTrue(all(not i["offset_default"] for i in res["report"]["audio"].values()))

    def test_blocks_are_placed_by_the_script_first_speech_lands_on_its_planned_start(self):
        """Sem offsets.json o bloco é posicionado pelo roteiro: a 1ª fala cai no instante previsto e o resto vem com a
        estrutura medida (durações e pausas da gravação)."""
        est = estimated(self.root, "ep02")
        scenes = list(dict.fromkeys(i["scene"] for i in est))
        truth = sv.perturb(est, seed=2)
        samples = sv.render(truth, 60.0, seed=2)
        adir = self.tmp / "ep02_blocks"
        for k, sid in enumerate(scenes):
            first = next(t for t, e in zip(truth, est) if e["scene"] == sid)["start"]
            end = next((t for t, e in zip(truth, est) if e["scene"] == scenes[k + 1]), None) if k + 1 < len(scenes) else None
            stop = (end["start"] - 0.1) if end else 60.0
            sv.write_wav(adir / f"{sid}.wav", array("h", samples[int(max(0.0, first - 0.3) * sv.RATE):int(stop * sv.RATE)]))
        res = audio.analyse_episode("ep02", root=self.root, audio_dir=adir)
        self.assertTrue(all(i["offset_default"] for i in res["report"]["audio"].values()))
        for sid in scenes:
            mine = [(t, e) for t, e in zip(truth, est) if e["scene"] == sid and e["kind"] == "speech"]
            shift = mine[0][1]["start"] - mine[0][0]["start"]                          # 1ª fala no instante previsto
            for t, e in mine:
                m = res["items"][t["id"]]
                self.assertAlmostEqual(m["start"], t["start"] + shift, delta=0.05, msg=t["id"])
                self.assertAlmostEqual(m["end"], t["end"] + shift, delta=0.05, msg=t["id"])

    def test_track_discovery_errors(self):
        d = self.tmp / "vazia"
        with self.assertRaisesRegex(audio.AudioError, "pasta de áudio não encontrada"):
            audio.find_tracks(d, ["s1", "s2", "s3"])
        d.mkdir()
        with self.assertRaisesRegex(audio.AudioError, "nenhum áudio"):
            audio.find_tracks(d, ["s1", "s2", "s3"])
        for name in ("narration.wav", "s1.wav"):
            (d / name).write_bytes(b"x")
        with self.assertRaisesRegex(audio.AudioError, "UMA forma"):
            audio.find_tracks(d, ["s1", "s2", "s3"])
        (d / "s1.wav").unlink()
        (d / "narration.mp3").write_bytes(b"x")
        with self.assertRaisesRegex(audio.AudioError, "dois arquivos"):
            audio.find_tracks(d, ["s1", "s2", "s3"])


# ---- blocos por falante (Ep. 3), cenas sem áudio, estouro ------------------------------------------------------------------
class SpeakerBlocks(WithProject):
    def clips(self, ep, seed, scenes, **perturb):
        """Escreve um arquivo por (cena, falante) para as cenas pedidas. Devolve (gabarito, estimado, pasta)."""
        est = estimated(self.root, ep)
        truth = sv.perturb(est, seed=seed, **perturb)
        adir = self.tmp / f"{ep}_spk_{seed}_{'_'.join(scenes)}"
        for sid in scenes:
            for who in ("protagonista", "motorista"):
                mine = [t for t, e in zip(truth, est) if e["scene"] == sid and e["kind"] in ("speech", "breath")
                        and ((e.get("speaker") or "protagonista") == who if e["kind"] == "speech" else True)]
                # respiração: vai com o falante da fala seguinte da cena (a de cena 2 do Ep. 3 é do protagonista)
                sp_ids = [t["id"] for t in mine if t["kind"] == "speech"]
                if not sp_ids:
                    continue
                mine = [t for t in mine if t["kind"] == "speech" or self.owner(t, est, truth, sid) == who]
                a = max(0.0, min(t["start"] for t in mine) - 0.3)
                b = max(t["end"] for t in mine) + 0.3
                samples = sv.render(mine, 60.0, seed=seed)
                stem = f"{sid}.{who}" if who == "motorista" or any((e.get("speaker") for e in est if e["scene"] == sid)) else sid
                sv.write_wav(adir / f"{stem}.wav", array("h", samples[int(a * sv.RATE):int(b * sv.RATE)]))
        return truth, est, adir

    @staticmethod
    def owner(t, est, truth, sid):
        later = [(x, e) for x, e in zip(truth, est) if e["scene"] == sid and e["kind"] == "speech" and x["start"] >= t["end"] - 1e-6]
        return ((later[0][1].get("speaker") or "protagonista") if later else "protagonista")

    def test_two_voices_in_one_scene_are_chained_with_the_planned_gap(self):
        truth, est, adir = self.clips("ep03", 2, ["s2"])
        self.assertTrue((adir / "s2.motorista.wav").exists() and (adir / "s2.protagonista.wav").exists())
        res = audio.analyse_episode("ep03", root=self.root, audio_dir=adir)
        it = res["items"]
        by_est = {e["id"]: e for e in est}
        by_truth = {t["id"]: t for t in truth}
        # 1º bloco (motorista): a 1ª fala dele cai no instante previsto; as durações medidas são as da gravação
        self.assertAlmostEqual(it["s2-02"]["start"], by_est["s2-02"]["start"], delta=0.03)
        for iid in ("s2-02", "s2-03", "s2-06", "s2-07", "s2-08", "s2-09", "s2-10"):
            t = by_truth[iid]
            self.assertAlmostEqual(it[iid]["end"] - it[iid]["start"], t["end"] - t["start"], delta=0.06, msg=iid)
        # 2º bloco (protagonista): começa depois do motorista, com a folga prevista entre as duas falas
        gap_est = by_est["s2-06"]["start"] - by_est["s2-03"]["end"]
        self.assertAlmostEqual(it["s2-06"]["start"] - it["s2-03"]["end"], gap_est, delta=0.06)
        self.assertTrue(res["report"]["audio"]["s2.motorista.wav"]["speaker"] == "motorista")
        # o gasp de terror (s2-05) é do protagonista: está no arquivo dele, antes da 1ª fala
        self.assertLessEqual(it["s2-05"]["end"], it["s2-06"]["start"] + 1e-6)
        self.assertNotIn("sem áudio", it["s2-05"].get("note", ""))

    def test_scenes_without_audio_keep_the_plan_shifted_with_the_scene_and_never_overlap(self):
        truth, est, adir = self.clips("ep03", 2, ["s2"])
        res = audio.analyse_episode("ep03", root=self.root, audio_dir=adir)
        it, by_est = res["items"], {e["id"]: e for e in est}
        for iid in ("s1-02", "s1-05", "s3-02", "s3-07"):                               # cenas 1 e 3: sem áudio
            self.assertEqual(it[iid]["conf"], 0.0, iid)
            self.assertIn("sem áudio", it[iid]["note"])
        self.assertAlmostEqual(it["s1-02"]["start"], by_est["s1-02"]["start"], places=2)          # cena 1 não se mexe
        self.assertTrue(any(w.startswith("sem áudio") for w in res["report"]["warnings"]))
        prev = 0.0
        for iid, m in it.items():                                                       # ordem e sem sobreposição (o build exige)
            self.assertGreaterEqual(m["start"], prev - 1e-6, iid)
            prev = m["end"]
        self.assertEqual([f["scene"] for f in res["report"]["scenes"]], ["s2"])        # o quadro por cena só tem a cena medida
        self.assertTrue(res["report"]["scenes"][0]["complete"])

    def test_voice_that_runs_over_the_scene_is_reported_and_pushes_the_next_one(self):
        est = estimated(self.root, "ep01")
        truth = sv.perturb(est, seed=3, rate_range=(1.40, 1.45), duration=200.0)        # voz bem mais lenta que o previsto
        samples = sv.render(truth, 100.0, seed=3)
        adir = self.tmp / "ep01_slow"
        scenes = list(dict.fromkeys(i["scene"] for i in est))
        for k, sid in enumerate(scenes):
            a = max(0.0, next(t for t, e in zip(truth, est) if e["scene"] == sid)["start"] - 0.3)
            nxt = next((t for t, e in zip(truth, est) if e["scene"] == scenes[k + 1]), None) if k + 1 < len(scenes) else None
            sv.write_wav(adir / f"{sid}.wav", array("h", samples[int(a * sv.RATE):int(((nxt["start"] - 0.1) if nxt else 100.0) * sv.RATE)]))
        res = audio.analyse_episode("ep01", root=self.root, audio_dir=adir)
        fit = {f["scene"]: f for f in res["report"]["scenes"]}
        self.assertGreater(fit["s1"]["over_window_s"], 0.3)                             # a cena 1 passa do fim (15 s)
        self.assertGreater(fit["s1"]["diff_s"], 3.0)                                    # e ocupa bem mais que o previsto
        self.assertTrue(any("depois do fim da cena" in w for w in res["report"]["warnings"]))
        self.assertTrue(any("empurra" in w for w in res["report"]["warnings"]))         # a cena 2 foi empurrada, não sobreposta
        prev = 0.0
        for iid, m in res["items"].items():
            self.assertGreaterEqual(m["start"], prev - 1e-6, iid)
            prev = m["end"]

    def test_file_names_with_speakers_and_typos_are_checked(self):
        d = self.tmp / "nomes"
        d.mkdir()
        (d / "s2.motorista.wav").write_bytes(b"x")
        tracks = audio.find_tracks(d, ["s1", "s2", "s3"], {"protagonista", "motorista"})
        self.assertEqual([(t["stem"], t["speaker"]) for t in tracks], [("s2.motorista", "motorista")])
        with self.assertRaisesRegex(audio.AudioError, "não reconheço"):                 # falante que o episódio não tem
            audio.find_tracks(d, ["s1", "s2", "s3"], {"protagonista"})
        (d / "s2.wav").write_bytes(b"x")
        with self.assertRaisesRegex(audio.AudioError, "UMA forma"):                     # bloco da cena E por falante
            audio.find_tracks(d, ["s1", "s2", "s3"], {"protagonista", "motorista"})
        (d / "s2.wav").unlink()
        (d / "cena2.mp3").write_bytes(b"x")
        with self.assertRaisesRegex(audio.AudioError, "cena2.mp3"):                     # nome que não reconheço
            audio.find_tracks(d, ["s1", "s2", "s3"], {"protagonista", "motorista"})


class BuildFailure(WithProject):
    def args(self, ep, adir, **kw):
        d = dict(episode=ep, audio_dir=str(adir), dry_run=False, no_build=False, force=False, min_pause_ms=None, strict=False,
                 keep_on_error=False)
        d.update(kw)
        return argparse.Namespace(**d)

    def test_a_voice_that_does_not_fit_the_episode_is_not_kept_unless_asked(self):
        est = estimated(self.root, "ep02")
        truth = sv.perturb(est, seed=4, rate_range=(1.45, 1.5), duration=70.0)           # tão lenta que passa dos 60 s
        samples = sv.render(truth, 75.0, seed=4)
        adir = self.tmp / "ep02_long"
        scenes = list(dict.fromkeys(i["scene"] for i in est))
        for k, sid in enumerate(scenes):
            a = max(0.0, next(t for t, e in zip(truth, est) if e["scene"] == sid)["start"] - 0.3)
            nxt = next((t for t, e in zip(truth, est) if e["scene"] == scenes[k + 1]), None) if k + 1 < len(scenes) else None
            stop = (nxt["start"] - 0.1) if nxt else max(t["end"] for t in truth) + 0.3
            sv.write_wav(adir / f"{sid}.wav", array("h", samples[int(a * sv.RATE):int(stop * sv.RATE)]))
        path = self.root / "ep02" / "narration.measured.json"
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = audio.run(self.args("ep02", adir), root=self.root)
        self.assertEqual(code, 1)
        self.assertIn("ERRO no build", err.getvalue())
        self.assertIn("NÃO foi mantido", err.getvalue())
        self.assertFalse(path.exists())                                                  # nada quebrado fica no projeto
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = audio.run(self.args("ep02", adir, keep_on_error=True), root=self.root)
        self.assertEqual(code, 1)
        self.assertTrue(path.exists())                                                   # a pedido, fica (para depurar)
        path.unlink()
        path.with_suffix(".json.bak").unlink(missing_ok=True)


# ---- pausas internas no build ---------------------------------------------------------------------------------------
class PausesInBuild(unittest.TestCase):
    def item(self):
        words, t = [], 10.0
        for w, d, punct, gap in (("Mano", 0.3, "", 0.0), ("tá", 0.2, ",", 0.15), ("por", 0.2, "", 0.0), ("que", 0.2, "...", 0.55),
                                 ("não", 0.3, "", 0.0), ("fecha", 0.4, "", 0.0)):
            words.append({"w": w, "spoken": w, "punct": punct, "start": t, "end": t + d})
            t += d + gap
        return {"id": "x", "start": 10.0, "end": t, "words": words}

    def test_words_land_after_the_measured_pause(self):
        it = self.item()
        old = [(w["start"], w["end"]) for w in it["words"]]
        s, e = 20.0, 24.0
        _retime(it, s, e, pauses=[[21.6, 22.3]])                       # só a pausa longa ("...") foi medida: 0,7 s
        w = it["words"]
        self.assertAlmostEqual(w[3]["end"], 21.6, places=3)           # "que" termina onde a pausa medida começa
        self.assertAlmostEqual(w[4]["start"], 22.3, places=3)         # "não" começa onde ela termina
        self.assertAlmostEqual(w[0]["start"], s, places=3)
        self.assertAlmostEqual(w[-1]["end"], e, places=3)
        plain = self.item()
        _retime(plain, s, e)
        self.assertNotAlmostEqual(plain["words"][4]["start"], 22.3, delta=0.05)    # sem pausas: só proporcional
        for a, b in zip(it["words"], it["words"][1:]):
            self.assertLessEqual(a["end"], b["start"] + 1e-9)
        self.assertEqual(len(old), len(w))

    def test_pauses_that_do_not_match_anything_are_ignored(self):
        it, plain = self.item(), self.item()
        _retime(it, 20.0, 24.0, pauses=[[20.0, 20.01], [23.99, 24.0]])           # na borda e minúsculas
        _retime(plain, 20.0, 24.0)
        for a, b in zip(it["words"], plain["words"]):
            self.assertAlmostEqual(a["start"], b["start"], places=6)

    def test_matching_is_monotonic_and_picks_the_right_pause(self):
        it = self.item()
        knots = match_pauses(it, 20.0, 24.0, [[20.9, 21.1], [22.5, 23.2]])
        self.assertEqual(knots, sorted(knots))
        self.assertTrue(all(b > a for a, b in zip(knots, knots[1:])))


# ---- do áudio ao build -----------------------------------------------------------------------------------------------------
class EndToEnd(WithProject):
    def args(self, ep, adir, **kw):
        d = dict(episode=ep, audio_dir=str(adir), dry_run=False, no_build=False, force=False, min_pause_ms=None, strict=False)
        d.update(kw)
        return argparse.Namespace(**d)

    def run_cli(self, *a, **kw):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = audio.run(self.args(*a, **kw), root=self.root)
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_writes_nothing(self):
        truth, _ = recover(self.root, "ep01", 1, self.tmp)
        code, out, _ = self.run_cli("ep01", self.tmp / "ep01_1", dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("nada foi gravado", out)
        self.assertFalse((self.root / "ep01" / "narration.measured.json").exists())

    def test_full_flow_ep01_resyncs_beats_steps_and_sfx_to_the_real_voice(self):
        ep, root = "ep01", self.root
        truth, _ = recover(root, ep, 2, self.tmp)
        before = build_episode(ep, root=root, write=False, use_measured=False)
        code, out, err = self.run_cli(ep, self.tmp / f"{ep}_2", strict=False)
        self.assertEqual(code, 0, err + out)
        self.assertIn("voz MEDIDA", out)
        self.assertIn("re-sincronizado", out)
        doc = json.loads((root / ep / "narration.measured.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["generated_by"], "python -m pipeline audio")
        tl = json.loads((root / ep / "build" / f"{ep}.timeline.json").read_text(encoding="utf-8"))
        items = {i["id"]: i for i in tl["narration"]}
        for t in truth:                                                                 # a linha do tempo agora É a gravação
            self.assertEqual(items[t["id"]]["timing"], "medido")
            self.assertAlmostEqual(items[t["id"]]["start"], doc["items"][t["id"]]["start"], delta=FRAME)
            if t["kind"] == "speech":
                self.assertAlmostEqual(items[t["id"]]["start"], t["start"], delta=0.05)
        # âncoras por palavra seguem a voz: mochila (beat), bip da catraca (4º: 0,2 s depois do fim de "né")
        beats = {b["id"]: b for s in tl["scenes"] for b in s["beats"]}
        mochila = next(w for w in items["s3-01"]["words"] if w["w"] == "mochila")
        self.assertAlmostEqual(beats["b3-mochila"]["start"], mochila["start"] - 0.1, delta=2 * FRAME)
        ne = next(w for w in items["s2-04"]["words"] if w["w"].strip(",.?!") == "né")
        bip = next(c for c in tl["sfx"]["cues"] if c["id"] == "bip-catraca")
        self.assertAlmostEqual(bip["start"], ne["end"] + 0.2, delta=2 * FRAME)
        # a partida do ônibus acompanha o fim da 1ª frase da cena 3
        self.assertAlmostEqual(beats["b3-partida"]["start"], items["s3-01"]["end"], delta=2 * FRAME)
        # câmera == SFX: cada passo continua sendo o MESMO instante nos dois (re-sincronizados juntos)
        with open(root / ep / "build" / f"{ep}.camera.csv", encoding="utf-8") as f:
            csv_steps = {int(r["frame"]) for r in __import__("csv").DictReader(f) if r["step"] not in ("", "0")}
        self.assertEqual({s["start_frame"] for s in tl["sfx"]["footsteps"]}, csv_steps)
        # algo de fato se moveu em relação à estimativa
        old = {b["id"]: b["start"] for s in before["scenes"] for b in s["beats"]}
        moved = [k for k, b in beats.items() if abs(b["start"] - old[k]) > 0.1]
        self.assertGreater(len(moved), 3)
        self.assertEqual(tl["warnings"], [])

    def test_full_flow_other_episodes_build_clean(self):
        for ep, seed in (("ep02", 3), ("ep03", 3)):
            recover(self.root, ep, seed, self.tmp)
            code, out, err = self.run_cli(ep, self.tmp / f"{ep}_{seed}")
            self.assertEqual(code, 0, f"{ep}: {err}{out}")
            tl = json.loads((self.root / ep / "build" / f"{ep}.timeline.json").read_text(encoding="utf-8"))
            self.assertTrue(all(i["timing"] == "medido" for i in tl["narration"]), ep)
            self.assertEqual((tl["frames"], tl["fps"]), (3600, 60), ep)

    def test_hand_written_measured_file_is_protected(self):
        ep = "ep03"
        recover(self.root, ep, 4, self.tmp)
        path = self.root / ep / "narration.measured.json"
        path.write_text(json.dumps({"items": {}}), encoding="utf-8")
        code, _, err = self.run_cli(ep, self.tmp / f"{ep}_4")
        self.assertEqual(code, 2)
        self.assertIn("--force", err)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"items": {}})
        code, _, err = self.run_cli(ep, self.tmp / f"{ep}_4", force=True)
        self.assertEqual(code, 0, err)
        self.assertTrue(path.with_suffix(".json.bak").exists())

    def test_missing_audio_is_a_clear_error_not_a_traceback(self):
        code, _, err = self.run_cli("ep01", self.tmp / "nao-existe")
        self.assertEqual(code, 2)
        self.assertIn("pasta de áudio não encontrada", err)

    def test_resync_summary_reports_what_moved(self):
        ep = "ep02"
        recover(self.root, ep, 5, self.tmp)
        self.run_cli(ep, self.tmp / f"{ep}_5")
        before = build_episode(ep, root=self.root, write=False, use_measured=False)
        after = build_episode(ep, root=self.root, write=False)
        rs = audio.resync_summary(before, after)
        self.assertGreater(rs["anchors"], 20)
        self.assertGreater(len(rs["moved"]), 0)
        self.assertGreaterEqual(rs["max_shift"], max(abs(v) for v in rs["moved"].values()) - 1e-9)


if __name__ == "__main__":
    unittest.main()
