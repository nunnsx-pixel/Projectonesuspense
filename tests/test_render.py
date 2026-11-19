"""Render/montagem (pipeline/render.py): lotes, comando do Blender e o mp4 final (ffmpeg). Python puro."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from pipeline import render

ROOT = Path(__file__).resolve().parent.parent


def args(**kw):
    base = dict(episode="ep01", out="renders", width=1080, height=None, samples=96, device="auto", threads=0, first=0, last=None,
                step=1, chunks=None, chunk=0, bench=0, overwrite=False, textures_dir=None, blender=None, python=None, dry_run=True,
                backend="auto")
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
                    upscale=False, suffix="", preset="ultrafast", crf=30)
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


if __name__ == "__main__":
    unittest.main()
