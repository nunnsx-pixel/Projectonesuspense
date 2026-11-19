"""Render/montagem (pipeline/render.py): lotes, comando do Blender e o mp4 final (ffmpeg). Python puro."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import struct
import subprocess
import tempfile
import zlib
import unittest
from argparse import Namespace
from pathlib import Path

from pipeline import render

ROOT = Path(__file__).resolve().parent.parent


def args(**kw):
    base = dict(episode="ep01", out="renders", width=1080, height=None, samples=96, device="auto", threads=0, first=0, last=None,
                step=1, chunks=None, chunk=0, bench=0, overwrite=False, textures_dir=None, blender=None, python=None, dry_run=True,
                backend="auto", perfil="", batch=0, stage=None, retries=6, status=False)
    base.update(kw)
    return Namespace(**base)


class Lots(unittest.TestCase):
    def test_chunks_cover_every_frame_exactly_once(self):
        for n, k in ((3600, 8), (3600, 7), (10, 3)):
            seen = []
            for c in range(k):
                a, b = render.frame_range(args(chunks=k, chunk=c), n)
                seen += list(range(a, b + 1)) if b >= a else []
            self.assertEqual(seen, list(range(n)), (n, k))

    def test_chunk_out_of_range_is_refused(self):
        with self.assertRaises(SystemExit):
            render.frame_range(args(chunks=4, chunk=4), 3600)

    def test_range_is_clamped_to_the_episode(self):
        self.assertEqual(render.frame_range(args(first=10, last=99999), 3600), (10, 3599))

    def test_command_uses_the_given_python_with_every_option(self):
        cmd = render.blender_command(args(python="/x/py"), ROOT)
        self.assertEqual(cmd[0], "/x/py")
        self.assertTrue(cmd[1].endswith("render_episode.py"))

    def test_gpu_backend_is_forwarded_only_when_chosen(self):
        import contextlib
        import io
        for backend, expect in (("auto", False), ("cuda", True)):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                render.run_render(args(python="/x/py", backend=backend), ROOT)
            line = buf.getvalue()
            self.assertEqual("--backend cuda" in line, expect, backend)

    def test_blender_executable_is_run_in_background_mode(self):
        cmd = render.blender_command(args(blender="/opt/blender"), ROOT)
        self.assertEqual(cmd[:3], ["/opt/blender", "-b", "-P"])
        self.assertEqual(cmd[-1], "--")


@unittest.skipIf(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, "ffmpeg ausente")
class Assemble(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "ep01" / "build").mkdir(parents=True)
        (self.root / "ep01" / "build" / "ep01.timeline.json").write_text(json.dumps({"frames": 60, "fps": 60}), encoding="utf-8")
        self.rend = self.root / "renders" / "ep01"
        self.rend.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def frames(self, keys):
        for k in keys:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x{k * 4 % 256:02x}4060:s=64x112", "-frames:v", "1",
                            str(self.rend / f"f{k + 1:05d}.png")], check=True)

    def ns(self, **kw):
        base = dict(episode="ep01", renders=str(self.root / "renders"), out=str(self.root / "out"), audio=None, allow_partial=False,
                    upscale=False, suffix="", preset="ultrafast", crf=30, stage=None, step=1, maxrate=None, audio_bitrate="192k")
        base.update(kw)
        return Namespace(**base)

    def test_complete_sequence_becomes_a_one_second_60fps_mp4(self):
        self.frames(range(60))
        self.assertEqual(render.run_assemble(self.ns(), self.root), 0)
        out = self.root / "out" / "ep01.mp4"
        self.assertTrue(out.exists())
        self.assertIn("64x112 · 60/1 · 60 quadros", render.probe(out))

    def test_missing_frames_are_refused_unless_partial(self):
        self.frames(range(0, 60, 12))
        with self.assertRaisesRegex(SystemExit, "faltam 55 de 60"):
            render.run_assemble(self.ns(), self.root)

    def test_partial_preview_holds_each_frame_and_keeps_the_exact_duration(self):
        self.frames(range(0, 60, 12))
        self.assertEqual(render.run_assemble(self.ns(allow_partial=True, suffix=".previa"), self.root), 0)
        self.assertIn("60 quadros", render.probe(self.root / "out" / "ep01.previa.mp4"))


    def test_half_rate_render_becomes_a_true_30fps_mp4_with_the_same_duration(self):
        self.frames(range(0, 60, 2))
        self.assertEqual(render.run_assemble(self.ns(step=2), self.root), 0)
        info = render.probe(self.root / "out" / "ep01.mp4")
        self.assertIn("30/1 · 30 quadros", info)
        self.assertIn("1.000 s", info)

    def test_half_rate_with_a_missing_frame_is_still_refused(self):
        self.frames([k for k in range(0, 60, 2) if k != 10])
        with self.assertRaisesRegex(SystemExit, "faltam 1 de 30"):
            render.run_assemble(self.ns(step=2), self.root)

    def test_assemble_is_atomic_and_can_encode_on_a_local_stage(self):
        self.frames(range(60))
        stage = self.root / "stage"
        self.assertEqual(render.run_assemble(self.ns(stage=str(stage)), self.root), 0)
        out = self.root / "out"
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["ep01.mp4"])              # nenhum .part sobra
        self.assertEqual(list(stage.iterdir()), [])
        self.assertIn("60 quadros", render.probe(out / "ep01.mp4"))


def make_png(w=4, h=4) -> bytes:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x80" * (w * 3) for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


class Batches(unittest.TestCase):
    """Render em lotes curtos com checkpoint: o que falta é recalculado da pasta final, então uma queda não perde nada."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "ep01" / "build").mkdir(parents=True)
        (self.root / "ep01" / "build" / "ep01.timeline.json").write_text(json.dumps({"frames": 40, "fps": 60}), encoding="utf-8")
        self.out, self.stage = self.root / "drive", self.root / "stage"
        self.calls, self.written = [], []
        self.fail_on = set()                                     # números de chamada que "caem" depois de gravar metade
        self._orig, self._orig_cmd = render._spawn, render.blender_command
        render._spawn = self.fake
        render.blender_command = lambda a, r=None: ["fake-blender"]

    def tearDown(self):
        render._spawn, render.blender_command = self._orig, self._orig_cmd
        self.tmp.cleanup()

    def fake(self, cmd, cwd):
        i = cmd.index("--frames")
        frames = [int(x) for x in cmd[i + 1].split(",")]
        folder = Path(cmd[cmd.index("--out") + 1]) / "ep01"
        folder.mkdir(parents=True, exist_ok=True)
        self.calls.append(frames)
        n = len(self.calls)
        for j, k in enumerate(frames):
            if n in self.fail_on and j >= len(frames) // 2:
                (folder / "_w1.png").write_bytes(make_png()[:20])                # morreu no meio de um quadro
                return -9
            (folder / f"f{k + 1:05d}.png").write_bytes(make_png())
            self.written.append(k)
        return 0

    def run_it(self, **kw):
        a = args(dry_run=False, batch=8, out=str(self.out), stage=str(self.stage), **kw)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = render.run_render(a, self.root)
        return rc, buf.getvalue()

    def on_disk(self):
        return sorted(render._frames_on_disk(self.out / "ep01"))

    def test_png_check_rejects_a_file_cut_in_the_middle(self):
        good = self.root / "ok.png"
        good.write_bytes(make_png())
        bad = self.root / "bad.png"
        bad.write_bytes(make_png()[:-9])
        self.assertTrue(render.png_ok(good))
        self.assertFalse(render.png_ok(bad))
        self.assertFalse(render.png_ok(self.root / "nao-existe.png"))

    def test_every_frame_ends_up_in_the_final_folder_in_short_batches(self):
        rc, _ = self.run_it()
        self.assertEqual(rc, 0)
        self.assertEqual(self.on_disk(), list(range(40)))
        self.assertTrue(all(len(c) <= 8 for c in self.calls))
        self.assertEqual(len(self.calls), 5)
        self.assertEqual(list(self.stage.joinpath("ep01").iterdir()), [])                  # a pasta local fica vazia
        self.assertFalse(list((self.out / "ep01").glob("*.part")))
        log = (self.out / "ep01.log").read_text(encoding="utf-8")
        self.assertEqual(len(log.strip().splitlines()), 5)
        self.assertIn("s/quadro", log)

    def test_a_crash_loses_nothing_and_the_batch_is_retried_smaller(self):
        self.fail_on = {2}
        rc, text = self.run_it()
        self.assertEqual(rc, 0)
        self.assertEqual(self.on_disk(), list(range(40)))
        self.assertIn("o lote falhou", text)
        self.assertEqual(len(self.calls[1]), 8)
        self.assertEqual(len(self.calls[2]), 4)                                              # o lote seguinte à queda tem metade
        self.assertEqual(sorted(self.written), list(range(40)))                              # cada quadro foi renderizado uma vez só
        self.assertEqual(list(self.stage.joinpath("ep01").glob("_w*.png")), [])               # resto do quadro cortado foi descartado

    def test_second_run_resumes_from_the_first_missing_frame_and_never_redoes_done_ones(self):
        self.run_it()
        for k in (10, 11, 30):                                                               # "o Drive perdeu" estes
            (self.out / "ep01" / f"f{k + 1:05d}.png").unlink()
        self.calls.clear()
        rc, _ = self.run_it()
        self.assertEqual(rc, 0)
        self.assertEqual(sorted(k for c in self.calls for k in c), [10, 11, 30])
        self.calls.clear()
        rc, text = self.run_it()
        self.assertEqual((rc, self.calls), (0, []))                                          # tudo pronto: não abre o Blender
        self.assertIn("todos os 40 quadros prontos", text)

    def test_it_gives_up_after_the_retries_and_says_how_to_resume(self):
        render._spawn = lambda cmd, cwd: (self.calls.append(cmd) or 1)
        rc, text = self.run_it(retries=3)
        self.assertEqual(rc, 1)
        self.assertEqual(len(self.calls), 3)
        self.assertIn("rode o mesmo comando", text)

    def test_leftovers_in_the_local_stage_are_recovered_before_the_first_batch(self):
        d = self.stage / "ep01"
        d.mkdir(parents=True)
        (d / "f00001.png").write_bytes(make_png())
        (d / "f00002.png").write_bytes(make_png()[:30])                                      # quadro cortado: descartado
        self.run_it()
        asked = [k for c in self.calls for k in c]
        self.assertNotIn(0, asked)                                                           # o quadro 0 estava inteiro: foi aproveitado
        self.assertIn(1, asked)                                                              # o 1 estava cortado: foi refeito

    def test_status_reports_progress_and_the_last_log_line(self):
        self.fail_on = {2}
        self.run_it(retries=1)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            render.run_render(args(status=True, out=str(self.out)), self.root)
        self.assertRegex(buf.getvalue(), r"ep01: \d+/40 quadros")
        self.assertIn("último registro", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
