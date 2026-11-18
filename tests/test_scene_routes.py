"""Testes do caminho-base da cabeça (blender/pov_scene/routes.py). Python puro: não precisa do Blender."""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "blender"))

from pov_scene import layout as L          # noqa: E402
from pov_scene import routes               # noqa: E402
from pov_scene.ctx import Ctx              # noqa: E402
from pov_scene.path import Leg, Phase, Track, interp   # noqa: E402


def bearing(p, q):
    """Azimute (graus; 0 = +Y/frente, 90 = +X/direita) de p para q."""
    return math.degrees(math.atan2(q[0] - p[0], q[1] - p[1]))


def rel(angle):
    return (angle + 180) % 360 - 180


class PathMath(unittest.TestCase):
    def test_phase_is_integer_on_every_footfall_and_extrapolates(self):
        ph = Phase([1.0, 1.5, 2.1, 2.8])
        for i, t in enumerate([1.0, 1.5, 2.1, 2.8]):
            self.assertAlmostEqual(ph.at(t), i)
            self.assertAlmostEqual(ph.time(i), t)
        self.assertAlmostEqual(ph.at(0.75), -0.5)               # meio passo antes do 1º contato
        self.assertGreater(ph.at(3.2), 3.0)

    def test_progress_follows_footfalls_not_the_clock(self):
        steps = [0.0, 0.5, 1.0, 2.0, 3.0]                         # parou de acelerar: passos mais lentos no fim
        leg = Leg("a", [(0, 0), (4, 0)], steps=steps)
        xs = [leg.pose(leg.progress(t)).x for t in steps]
        self.assertEqual([round(x, 6) for x in xs], [0.0, 1.0, 2.0, 3.0, 4.0])    # 1 m por passo, sempre

    def test_standing_leg_without_steps_holds_pose(self):
        leg = Leg("sit", [(1, 1), (1, 1)], 0, 0.96, [[0, 1.6], [1, 1.15]], span=(10, 11))
        self.assertAlmostEqual(leg.pose(leg.progress(9)).z, 0.96 + 1.6)
        self.assertAlmostEqual(leg.pose(leg.progress(12)).z, 0.96 + 1.15)

    def test_overlapping_legs_are_rejected(self):
        a = Leg("a", [(0, 0), (1, 0)], span=(0, 2))
        b = Leg("b", [(1, 0), (2, 0)], span=(1, 3))
        with self.assertRaisesRegex(ValueError, "sobrepostos"):
            Track([a, b])

    def test_interp_keys(self):
        self.assertEqual(interp(270, 0.3), 270)
        self.assertAlmostEqual(interp([[0, 0], [1, 10]], 0.5), 5.0)
        self.assertEqual(interp([[0, 0], [1, 10]], 2), 10)


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = {ep: Ctx(ep) for ep in ("ep01", "ep02", "ep03")}
        cls.tr = {ep: fn(cls.ctx[ep]) for ep, fn in routes.ROUTES.items()}

    def test_no_teleports_between_legs(self):
        for ep, tr in self.tr.items():
            for a, b, dist, dh in tr.gaps():
                self.assertLess(dist, 0.05, f"{ep}: {a}->{b} salta {dist:.3f} m")
                self.assertLess(dh, 5.0, f"{ep}: {a}->{b} gira {dh:.1f}° de repente")

    def test_strides_and_speeds_are_human(self):
        for ep, tr in self.tr.items():
            for leg in tr.legs:
                if leg.stride is None:
                    continue
                self.assertTrue(0.3 <= leg.stride <= 1.4, f"{ep}/{leg.id}: passada {leg.stride:.2f} m")
        run = next(l for l in self.tr["ep01"].legs if l.id == "corrida")
        self.assertLess(run.length / (run.t1 - run.t0), 4.0)                         # < 14 km/h médios
        stairs = next(l for l in self.tr["ep01"].legs if l.id == "degraus")
        self.assertAlmostEqual(stairs.stride, 0.5, places=2)                         # profundidade de um degrau

    def test_foot_lands_on_the_camera_step_frames(self):
        """O avanço de cada trecho a pé é uma função dos contatos: em cada passo a fase é inteira."""
        for ep, seg, leg_id in (("ep01", "corrida-saguao", "corrida"), ("ep01", "corredor", "corredor"),
                                ("ep03", "cambaleio-corredor", "cambaleia"), ("ep03", "recua-catraca", "recua-2-passos")):
            leg = next(l for l in self.tr[ep].legs if l.id == leg_id)
            steps = self.ctx[ep].steps(seg)
            for i, t in enumerate(steps):
                self.assertAlmostEqual(leg.phase.at(t), i, places=6)
            for t0, t1 in zip(steps, steps[1:]):                                       # avança entre os contatos
                self.assertGreater(leg.progress(t1), leg.progress(t0) - 1e-9)

    def test_ep01_climbs_the_three_stairs_on_the_step_frames(self):
        tr, ctx = self.tr["ep01"], self.ctx["ep01"]
        for t, (x, z) in zip(ctx.steps("degraus"), L.STAIRS):
            p = tr.sample(t)
            self.assertAlmostEqual(p.x, x, places=2)                                   # pé no degrau
            self.assertAlmostEqual(p.floor, z, places=2)                               # na altura do degrau
        stairs = next(l for l in tr.legs if l.id == "degraus")
        before = tr.sample(stairs.t0)                                                  # um passo antes do 1º degrau
        self.assertEqual((round(before.x, 2), before.floor), (L.STAIRS[0][0] + 0.5, 0.0))   # ainda na plataforma
        self.assertAlmostEqual(tr.sample(26).floor, L.FLOOR_Z)                         # e depois no piso do ônibus

    def test_ep01_ends_seated_in_the_window_seat_after_the_sit_beat(self):
        tr, ctx = self.tr["ep01"], self.ctx["ep01"]
        s0, s1 = ctx.beat("b3-senta")
        self.assertAlmostEqual(tr.sample(s0 - 0.45).eye, L.EYE_STAND, places=2)        # ainda de pé
        self.assertAlmostEqual(tr.sample(s0 + 0.2).eye, L.EYE_SEAT, places=2)          # já POUSOU: junto do baque do banco
        end = tr.sample(s1 + 0.5)
        self.assertAlmostEqual(end.eye, L.EYE_SEAT, places=2)
        self.assertAlmostEqual(end.x, L.MY_SEAT[0], places=3)
        self.assertAlmostEqual(end.y, L.MY_SEAT[1], places=3)
        self.assertAlmostEqual(rel(end.heading), 0.0, places=3)                        # sentado olhando para a frente
        self.assertLess(end.x, 0.0)                                                    # janela à esquerda
        self.assertLess(end.x, L.BAG_SEAT[0])                                          # banco do corredor à direita dele

    def test_ep01_looks_at_the_driver_where_the_csv_looks(self):
        """A geometria do cenário tem que bater com o olhar do CSV (yaw -17° ao ver o motorista que acena)."""
        tr, ctx = self.tr["ep01"], self.ctx["ep01"]
        t = ctx.beat("b2-aceno")[0] + 0.15                                              # chave "olha o motorista"
        p = tr.sample(t)
        want = rel(bearing((p.x, p.y), L.DRIVER) - p.heading)
        got = min(ctx.rows(), key=lambda r: abs(r["t"] - t))["look_yaw"]
        self.assertAlmostEqual(want, got, delta=10)

    def test_ep02_body_turns_so_the_look_hits_the_seat_the_silhouette_and_the_driver(self):
        tr, ctx = self.tr["ep02"], self.ctx["ep02"]
        rows = {round(r["t"], 3): r for r in ctx.rows()}
        look = lambda t: rows[round(round(t * 60) / 60, 3)]["look_yaw"]                # noqa: E731
        # "o banco ao lado" (a mochila): azimute absoluto = direção do corpo + olhar relativo
        t = ctx.beat("b2-mochila")[0] + 1.0
        p = tr.sample(t)
        self.assertLess(abs(rel(p.heading + look(t) - bearing((p.x, p.y), L.BAG_SEAT))), 28)
        # "um maluco lá no fundo": o último banco
        t = ctx.word("s2-08", "estátua")[0]
        p = tr.sample(t)
        self.assertLess(abs(rel(p.heading + look(t) - bearing((p.x, p.y), L.LAST_SEAT))), 12)
        self.assertGreater(p.x, L.MY_SEAT[0] + 0.5)                                    # inclinado sobre o corredor
        # nuca do motorista no fim
        t = 59.0
        p = tr.sample(t)
        self.assertLess(abs(rel(p.heading + look(t) - bearing((p.x, p.y), L.DRIVER))), 15)
        self.assertGreater(p.x, -0.2)                                                  # fora dos encostos dos bancos
        self.assertGreater(p.eye, L.EYE_SEAT)

    def test_ep03_geometry_matches_the_look(self):
        tr, ctx = self.tr["ep03"], self.ctx["ep03"]
        rows = ctx.rows()
        row = lambda t: min(rows, key=lambda r: abs(r["t"] - t))                        # noqa: E731
        t = ctx.beat("b1-olha")[0] + 0.05                                               # "tenta ver o rosto do motorista"
        p = tr.sample(t)
        self.assertAlmostEqual(p.x, routes.S0[0], places=2)
        self.assertAlmostEqual(p.y, routes.S0[1], places=2)
        self.assertAlmostEqual(rel(bearing((p.x, p.y), L.DRIVER) - p.heading), row(t)["look_yaw"], delta=12)
        t = ctx.beat("b1-porta")[0] + 0.9                                               # olha a porta (à direita)
        door = (L.HALF_W, L.DOOR_Y)
        self.assertAlmostEqual(rel(bearing((p.x, p.y), door) - p.heading), row(t)["look_yaw"], delta=15)

    def test_ep03_run_to_the_driver_then_two_steps_back_into_the_turnstile_then_pushed_out(self):
        tr, ctx = self.tr["ep03"], self.ctx["ep03"]
        run = next(l for l in tr.legs if l.id == "cambaleia")
        self.assertAlmostEqual(run.pose(0).x, L.MY_SEAT[0])                                 # sai do banco da janela
        self.assertAlmostEqual(run.pose(0).y, L.MY_SEAT[1])
        self.assertEqual(len(ctx.steps("cambaleio-corredor")), 12)
        catraca = routes.CATRACA_EP03
        end = tr.sample(35.0)
        self.assertLess(math.dist((end.x, end.y), catraca), 0.25)                            # as costas na catraca
        self.assertEqual(len(ctx.steps("recua-catraca")), 2)
        out = tr.sample(ctx.duration - 0.01)
        self.assertGreater(out.x, L.HALF_W + 0.8)                                            # caiu para fora da porta
        self.assertLess(out.floor, 0.1)
        self.assertLess(abs(tr.sample(58.2).y - L.DOOR_Y), 0.2)                              # passando pela porta

    def test_all_poses_are_physical(self):
        for ep, tr in self.tr.items():
            for r in self.ctx[ep].rows()[::12]:
                p = tr.sample(r["t"])
                self.assertTrue(0.4 < p.eye < 1.8, f"{ep} t={r['t']}: olhos a {p.eye:.2f} m do piso")
                self.assertTrue(-12 < p.y < 2 and -3 < p.x < 50, f"{ep} t={r['t']}: fora de qualquer cenário ({p.x:.1f},{p.y:.1f})")

    def test_bus_distance_is_the_integral_of_the_csv_speed(self):
        d1 = self.ctx["ep01"].bus_distance()
        self.assertEqual(d1[int(41.0 * 60)], 0.0)                                            # parado até a partida
        self.assertGreater(d1[-1], 100)
        self.assertGreater(self.ctx["ep03"].bus_distance()[-1], 700)                          # 55 km/h por 60 s


if __name__ == "__main__":
    unittest.main()
