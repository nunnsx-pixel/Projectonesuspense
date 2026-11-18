"""Esqueleto das figuras (blender/pov_scene/rig.py): IK de dois ossos, orientação das peças e poses. Python puro."""
from __future__ import annotations

import math
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "blender"))
sys.path.insert(0, str(ROOT))

from pov_scene import layout as L  # noqa: E402
from pov_scene import rig  # noqa: E402


def d(a, b):
    return rig.length(rig.sub(a, b))


class IK(unittest.TestCase):
    def test_bones_keep_their_length_for_any_reachable_target(self):
        rnd = random.Random(3)
        for _ in range(500):
            root = (rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))
            target = rig.add(root, rig.mul(rig.unit((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))), rnd.uniform(0.05, 0.56)))
            mid, end = rig.two_bone_ik(root, target, 0.3, 0.28, (rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1)))
            self.assertAlmostEqual(d(root, mid), 0.3, places=6)
            self.assertAlmostEqual(d(mid, end), 0.28, places=6)
            self.assertLess(d(end, target), 1e-6)

    def test_unreachable_target_gives_a_straight_limb(self):
        mid, end = rig.two_bone_ik((0, 0, 0), (0, 0, -2.0), 0.3, 0.3, (0, 1, 0))
        self.assertAlmostEqual(d((0, 0, 0), end), 0.6, places=3)                     # esticou até onde dá
        self.assertLess(abs(mid[1]), 0.02)                                          # e ficou praticamente reto

    def test_the_middle_joint_bends_towards_the_pole(self):
        mid, _ = rig.two_bone_ik((0, 0, 1.0), (0, 0, 0.5), 0.3, 0.3, (0, 1, 0))
        self.assertGreater(mid[1], 0.1)                                              # joelho para a frente (+Y)
        mid, _ = rig.two_bone_ik((0, 0, 1.0), (0, 0, 0.5), 0.3, 0.3, (0, -1, 0))
        self.assertLess(mid[1], -0.1)


class Orientation(unittest.TestCase):
    def test_euler_takes_z_to_any_direction(self):
        rnd = random.Random(1)
        dirs = [(0, 0, 1), (0, 0, -1), (0, 1, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0)]
        dirs += [(rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1)) for _ in range(1000)]
        for v in dirs:
            if rig.length(v) < 0.05:
                continue
            got = rig.apply_euler_deg(rig.limb_euler_deg(v), (0, 0, 1))
            want = rig.unit(v)
            self.assertLess(max(abs(a - b) for a, b in zip(got, want)), 1e-6, v)


class Poses(unittest.TestCase):
    def test_standing_has_feet_on_the_floor_and_straight_hanging_arms(self):
        p = rig.standing_pose()
        for side, j in p["joints"].items():
            self.assertAlmostEqual(j["ankle"][2], rig.ANKLE_H, places=6)                        # pé no piso
            self.assertAlmostEqual(d(j["hip"], j["knee"]), rig.THIGH, places=6)
            self.assertAlmostEqual(d(j["knee"], j["ankle"]), rig.SHIN, places=6)
            self.assertGreater(j["knee"][1], j["hip"][1] + 0.05)                                 # joelhos um pouco à frente
            self.assertLess(j["wrist"][2], 0.9)                                                  # mãos caídas ao lado do corpo
            self.assertAlmostEqual(d(j["shoulder"], j["elbow"]), rig.UPPER, places=6)
            self.assertAlmostEqual(d(j["elbow"], j["wrist"]), rig.FORE, places=6)
        self.assertLess(p["joints"]["esq"]["hip"][0], 0.0 < p["joints"]["dir"]["hip"][0])        # direita = +X

    def test_seated_feet_rest_on_the_floor_and_thighs_on_the_cushion(self):
        for grip in ("wheel", "lap", "rest"):
            p = rig.seated_pose(grip, L.WHEEL_REL)
            for side, j in p["joints"].items():
                self.assertAlmostEqual(j["ankle"][2], rig.SEAT_FLOOR_Z + rig.ANKLE_H, places=6, msg=grip)
                self.assertGreater(j["knee"][1] - j["hip"][1], 0.3, grip)                         # coxas para a frente
                self.assertLess(abs(j["knee"][2] - j["hip"][2]), 0.12, grip)                      # quase horizontais
                self.assertLess(j["knee"][2], rig.SEAT_HIP_Z + 0.02, grip)                        # joelho não sobe acima do quadril

    def test_driver_hands_land_on_the_wheel_rim(self):
        p = rig.seated_pose("wheel", L.WHEEL_REL)
        for side, j in p["joints"].items():
            fdir = rig.unit(rig.sub(j["wrist"], j["elbow"]))
            hand = rig.add(j["wrist"], rig.mul(fdir, rig.HAND / 2))
            self.assertLess(abs(d(hand, L.WHEEL_REL) - 0.19), 0.06, side)                        # raio do volante: 0,19 m
            self.assertGreater(d(j["shoulder"], j["wrist"]), 0.3)                                 # braço dobrado, não esticado
            self.assertLess(d(j["shoulder"], j["wrist"]), rig.UPPER + rig.FORE - 0.04)

    def test_the_wheel_is_within_reach_of_the_seat(self):
        self.assertLess(abs(L.WHEEL_REL[0]), 1e-6)                                                # centrado no corpo
        self.assertTrue(0.35 < L.WHEEL_REL[1] < 0.6)                                              # nem colado nem longe
        self.assertEqual(L.WHEEL[1], L.DRIVER[1] + 0.42)


if __name__ == "__main__":
    unittest.main()
