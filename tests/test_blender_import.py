"""Testes do importador do Blender.

A matemática (eixos, sinais, Euler) roda em qualquer Python. Os testes de cena rodam o importador
no Blender de verdade e só executam onde o módulo `bpy` existe (ex.: `pip install bpy`).
"""
from __future__ import annotations

import csv
import importlib.util
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "ep01" / "build" / "ep01.camera.csv"
CSV2 = ROOT / "ep02" / "build" / "ep02.camera.csv"

spec = importlib.util.spec_from_file_location("import_camera_csv", ROOT / "blender" / "import_camera_csv.py")
imp = importlib.util.module_from_spec(spec)
sys.modules["import_camera_csv"] = imp
spec.loader.exec_module(imp)
bpy = imp.bpy


def apply(m, v):
    return [sum(m[i][j] * v[j] for j in range(3)) for i in range(3)]


class MathConventions(unittest.TestCase):
    """CSV (+X dir, +Y cima, +Z frente; yaw+ dir, pitch+ cima, roll+ à direita) -> eixos do Blender."""

    def look(self, yaw=0, pitch=0, roll=0):
        m = imp.camera_rotation_matrix(yaw, pitch, roll)
        return apply(m, [0, 0, -1]), apply(m, [1, 0, 0]), apply(m, [0, 1, 0])   # frente, direita, cima

    def test_neutral_camera_looks_forward_and_up_is_up(self):
        fwd, right, up = self.look()
        for got, want in zip(fwd + right + up, [0, 1, 0, 1, 0, 0, 0, 0, 1]):      # Y frente, X direita, Z cima
            self.assertAlmostEqual(got, want, places=9)

    def test_yaw_positive_turns_right(self):
        fwd, _, _ = self.look(yaw=30)
        self.assertAlmostEqual(fwd[0], math.sin(math.radians(30)), places=9)
        self.assertAlmostEqual(fwd[1], math.cos(math.radians(30)), places=9)
        self.assertAlmostEqual(fwd[2], 0, places=9)

    def test_pitch_positive_looks_up(self):
        fwd, _, _ = self.look(pitch=20)
        self.assertAlmostEqual(fwd[2], math.sin(math.radians(20)), places=9)
        self.assertGreater(fwd[1], 0)

    def test_roll_positive_tilts_right(self):
        fwd, right, up = self.look(roll=10)
        self.assertAlmostEqual(fwd[1], 1.0, places=9)                  # roll não muda para onde olha
        self.assertLess(right[2], 0)                                   # lado direito desce
        self.assertGreater(up[0], 0)                                   # topo vai para a direita
        self.assertAlmostEqual(right[2], -math.sin(math.radians(10)), places=9)

    def test_euler_round_trip(self):
        for a, b, g in [(1.5, 0.1, -1.3), (1.2, -0.2, 0.4), (2.0, 0.3, 1.0)]:
            m = imp._mul(imp._mul(imp._rz(g), imp._ry(b)), imp._rx(a))
            got = imp.euler_xyz(m)
            for x, y in zip(got, (a, b, g)):
                self.assertAlmostEqual(x, y, places=9)

    def test_euler_is_continuous_across_pi(self):
        prev = None
        for deg in range(-170, 171, 5):                                # gira o olhar quase 340°
            m = imp.camera_rotation_matrix(deg, 0, 0)
            prev = imp.euler_xyz(m, prev)
        self.assertAlmostEqual(prev[2], -math.radians(170), places=6)  # sem pulo de 2π

    def test_euler_has_no_flips_over_whole_episodes(self):
        for path in (CSV, CSV2):                           # Ep. 2 chega a yaw +150° (olhar para trás)
            prev, worst = None, 0.0
            for r in imp.read_rows(path):
                _, e = imp.camera_pose(r, 0.01, prev)
                if prev is not None:
                    worst = max(worst, max(abs(a - b) for a, b in zip(e, prev)))
                prev = e
            self.assertLess(math.degrees(worst), 12.0, path.name)   # maior passo por frame (BUM do Ep. 2 é o mais brusco)

    def test_position_mapping_and_unit_scale(self):
        row = {"shake_x_cm": 10, "shake_y_cm": 20, "shake_z_cm": 30, "shake_yaw": 0, "shake_pitch": 0,
               "shake_roll": 0, "look_yaw": 0, "look_pitch": 0, "look_roll": 0}
        loc, _ = imp.camera_pose(row, 0.01)
        self.assertEqual(loc, (0.10, 0.30, 0.20))                      # (X dir, Y frente, Z cima)
        loc, _ = imp.camera_pose(row, 0.01 / 0.01)                     # cena com unit scale 0.01 (cm)
        self.assertEqual(loc, (10.0, 30.0, 20.0))

    def test_reads_real_csv(self):
        rows = imp.read_rows(CSV)
        self.assertEqual(len(rows), 3600)
        self.assertEqual(rows[0]["scene"], "s1")

    def test_rejects_stale_csv(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "x.csv"
            bad.write_text("frame,t\n0,0\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "faltam colunas"):
                imp.read_rows(bad)
            gap = Path(d) / "y.csv"
            lines = CSV.read_text(encoding="utf-8").splitlines()
            gap.write_text("\n".join(lines[:3] + lines[4:]) + "\n", encoding="utf-8")     # some o frame 2
            with self.assertRaisesRegex(ValueError, "contíguos"):
                imp.read_rows(gap)


@unittest.skipUnless(bpy is not None, "módulo bpy não instalado")
class BlenderScene(unittest.TestCase):
    CAM_AT = (2.0, 3.0, 1.6)

    @classmethod
    def setUpClass(cls):
        cls.rows = imp.read_rows(CSV)
        cls.csv_rows = {int(r["frame"]): r for r in cls.rows}

    def fresh_scene(self, with_camera=True, parent=None):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene
        if with_camera:
            cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
            scene.collection.objects.link(cam)
            cam.location = self.CAM_AT
            if parent:
                cam.parent = parent
            scene.camera = cam
        return scene

    def at(self, scene, csv_frame, start=1):
        scene.frame_set(start + csv_frame)
        bpy.context.view_layer.update()

    def test_import_poses_match_csv_independently(self):
        scene = self.fresh_scene()
        info = imp.import_csv(CSV, step_markers=True)
        cam = scene.camera
        self.assertEqual((scene.render.fps, scene.render.fps_base), (60, 1.0))
        self.assertEqual((scene.render.resolution_x, scene.render.resolution_y), (1080, 1920))
        self.assertEqual((scene.frame_start, scene.frame_end), (1, 3600))
        self.assertTrue(info["head_created"])
        self.assertEqual(cam.parent.name, "POV_Head")

        for f in (0, 1, 100, 206, 483, 960, 1800, 2400, 2700, 3200, 3569, 3599):
            r = self.csv_rows[f]
            self.at(scene, f)
            yaw = math.radians(r["look_yaw"] + r["shake_yaw"])
            pitch = math.radians(r["look_pitch"] + r["shake_pitch"])
            roll = math.radians(r["look_roll"] + r["shake_roll"])
            # direção para onde olha: fórmula escrita à mão (X dir, Y frente, Z cima)
            want_fwd = (math.sin(yaw) * math.cos(pitch), math.cos(yaw) * math.cos(pitch), math.sin(pitch))
            m = cam.matrix_world
            got_fwd = -m.col[2].xyz
            for g, w in zip(got_fwd, want_fwd):
                self.assertAlmostEqual(g, w, places=4, msg=f"frame {f}")
            # o lado direito da câmera cai/sobe com o roll (z_direita = -sin(roll)·cos(pitch) p/ pitch pequeno)
            self.assertAlmostEqual(m.col[0].z, -math.sin(roll) * math.cos(pitch), places=3, msg=f"frame {f}")
            # posição: cabeça (onde a câmera estava) + balanço, em metros
            want_pos = (self.CAM_AT[0] + r["shake_x_cm"] / 100, self.CAM_AT[1] + r["shake_z_cm"] / 100,
                        self.CAM_AT[2] + r["shake_y_cm"] / 100)
            for g, w in zip(m.translation, want_pos):
                self.assertAlmostEqual(g, w, places=4, msg=f"frame {f}")

    def assert_pose(self, scene, cam, r, f, start=1):
        """Direção/roll/posição da câmera num frame, com fórmulas escritas à mão (independentes do importador)."""
        self.at(scene, f, start)
        yaw = math.radians(r["look_yaw"] + r["shake_yaw"])
        pitch = math.radians(r["look_pitch"] + r["shake_pitch"])
        roll = math.radians(r["look_roll"] + r["shake_roll"])
        want_fwd = (math.sin(yaw) * math.cos(pitch), math.cos(yaw) * math.cos(pitch), math.sin(pitch))
        m = cam.matrix_world
        for g, w in zip(-m.col[2].xyz, want_fwd):
            self.assertAlmostEqual(g, w, places=4, msg=f"frame {f}")
        self.assertAlmostEqual(m.col[0].z, -math.sin(roll) * math.cos(pitch), places=3, msg=f"frame {f}")
        want_pos = (self.CAM_AT[0] + r["shake_x_cm"] / 100, self.CAM_AT[1] + r["shake_z_cm"] / 100,
                    self.CAM_AT[2] + r["shake_y_cm"] / 100)
        for g, w in zip(m.translation, want_pos):
            self.assertAlmostEqual(g, w, places=4, msg=f"frame {f}")

    def test_ep02_poses_extra_channels_and_black_marker(self):
        scene = self.fresh_scene()
        imp.import_csv(CSV2)
        cam = scene.camera
        rows = {int(r["frame"]): r for r in imp.read_rows(CSV2)}
        for f in (0, 31, 36, 60, 1907, 1950, 2407, 2700, 3000, 3597):         # inclui BUM, olhar p/ trás (+148°), janela, nuca
            self.assert_pose(scene, cam, rows[f], f)
        for f in (0, 29, 30, 33, 41, 42, 1000, 3300):                          # canais extras exatos (degraus)
            self.at(scene, f)
            for p in ("light", "bump", "black", "motion_blur"):
                self.assertAlmostEqual(cam[p], rows[f][p], places=3, msg=f"{p} frame {f}")
        marks = [(m.name, m.frame) for m in scene.timeline_markers]
        self.assertIn(("POV:preto", 1), marks)                                 # tela preta já no 1º frame
        self.assertEqual([m for m in marks if m[0] == "POV:preto"], [("POV:preto", 1)])   # e só essa
        self.assertIn(("POV:s2", 1 + 1080), marks)

    def test_ep01_has_no_extra_channels(self):
        scene = self.fresh_scene()
        imp.import_csv(CSV)
        self.assertNotIn("light", scene.camera.keys())

    def test_sync_channels_fov_and_flags(self):
        scene = self.fresh_scene()
        cam = scene.camera
        cam.data.angle = math.radians(80)
        imp.import_csv(CSV)
        for f in (0, 483, 3000, 3569, 3570, 3599):
            r = self.csv_rows[f]
            self.at(scene, f)
            for p in imp.SMOOTH_PROPS + imp.CONSTANT_PROPS:
                self.assertAlmostEqual(cam[p], r[p], places=3, msg=f"{p} frame {f}")
            self.assertAlmostEqual(cam.data.angle, math.radians(80) * (1 + r["fov_pct"] / 100), places=4)
        # flag em degrau: o corte para preto não "rampa" entre frames
        self.at(scene, 3569)
        self.assertEqual(cam["black"], 0.0)
        self.at(scene, 3570)
        self.assertEqual(cam["black"], 1.0)

    def test_markers(self):
        scene = self.fresh_scene()
        imp.import_csv(CSV, start_frame=11, step_markers=True)
        marks = {}
        for m in scene.timeline_markers:
            marks.setdefault(m.name, []).append(m.frame)
        self.assertEqual(marks["POV:s1"], [11])
        self.assertEqual(marks["POV:s2"], [11 + 900])
        self.assertEqual(marks["POV:s3"], [11 + 2100])
        self.assertEqual(marks["POV:preto"], [11 + 3570])
        steps = sorted(int(r["frame"]) + 11 for r in self.rows if r["step"] >= 0.5)
        self.assertEqual(sorted(marks["POV:passo"]), steps)
        self.assertGreater(len(steps), 50)

    def test_rerun_is_safe_and_keeps_old_animation(self):
        scene = self.fresh_scene()
        imp.import_csv(CSV)
        first = scene.camera.animation_data.action
        imp.import_csv(CSV, step_markers=False)
        cam = scene.camera
        self.assertEqual([o.name for o in bpy.data.objects if o.name.startswith("POV_Head")], ["POV_Head"])
        self.assertEqual(len([m for m in scene.timeline_markers if m.name == "POV:s1"]), 1)
        self.assertTrue(first.use_fake_user)                              # animação anterior guardada
        self.assertIsNot(cam.animation_data.action, first)

    def test_existing_parent_rig_is_respected(self):
        scene = self.fresh_scene(with_camera=False)
        rig = bpy.data.objects.new("MeuRig", None)
        scene.collection.objects.link(rig)
        cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
        scene.collection.objects.link(cam)
        cam.parent = rig
        scene.camera = cam
        info = imp.import_csv(CSV)
        self.assertFalse(info["head_created"])
        self.assertNotIn("POV_Head", bpy.data.objects)
        self.assertEqual(cam.parent.name, "MeuRig")

    def test_cli_main_default_csv_and_save_roundtrip(self):
        scene = self.fresh_scene()
        scene.camera.name = "CamPrincipal"
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "ep01.blend"
            import os
            cwd = os.getcwd()
            os.chdir(d)                                    # CSV padrão é resolvido a partir do repositório
            try:
                info = imp.main(["--camera", "CamPrincipal", "--save", str(out), "--fov-deg", "70"])
            finally:
                os.chdir(cwd)
            self.assertEqual(info["frames"], 3600)
            bpy.ops.wm.open_mainfile(filepath=str(out))    # a animação sobrevive ao salvar/abrir
            scene = bpy.context.scene
            cam = bpy.data.objects["CamPrincipal"]
            self.assertEqual(scene.camera, cam)
            self.assertAlmostEqual(math.degrees(cam.data.angle), 70, delta=1.0)
            scene.frame_set(1 + 3570)
            self.assertEqual(cam["black"], 1.0)

    def test_unknown_camera_name_is_a_clear_error(self):
        self.fresh_scene()
        with self.assertRaisesRegex(SystemExit, "não encontrada"):
            imp.import_csv(CSV, camera_name="Nao existe")

    def test_creates_camera_when_scene_has_none(self):
        scene = self.fresh_scene(with_camera=False)
        imp.import_csv(CSV)
        self.assertIsNotNone(scene.camera)
        self.assertEqual(scene.camera.type, "CAMERA")


if __name__ == "__main__":
    unittest.main()
