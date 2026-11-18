"""Testes da cena montada no Blender (blender/assemble_scene.py). Só rodam onde existe o módulo `bpy`.

Cada classe monta UM episódio e confere o que importa: hierarquia, caminho-base da cabeça (== trajeto puro),
drivers (luz, vinheta, pálpebra, preto), animação de adereços/personagens nos instantes dos beats e os bugs
que já tivemos (objetos da porta fora do ônibus; filhos que não somem com o pai).
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "blender"))
sys.path.insert(0, str(ROOT))

try:
    import bpy
except ImportError:
    bpy = None

if bpy is not None:
    import assemble_scene as A
    from pov_scene import layout as L


def at(env, t):
    env.sc.frame_set(env.f(t))
    bpy.context.view_layer.update()


def vis(ob, env, t):
    at(env, t)
    return not ob.hide_render


@unittest.skipUnless(bpy is not None, "módulo bpy não instalado")
class Base:
    EP = ""

    @classmethod
    def setUpClass(cls):
        cls.env = A.assemble(cls.EP)
        cls.ctx = cls.env.ctx
        cls.obj = bpy.data.objects

    # ---- comum a todos ------------------------------------------------------------------------
    def test_scene_hierarchy_and_settings(self):
        e = self.env
        self.assertEqual(e.cam.parent, e.head)
        self.assertEqual(e.head.parent, e.bus)
        self.assertEqual(e.sc.camera, e.cam)
        self.assertEqual((e.sc.render.fps, e.sc.render.resolution_x, e.sc.render.resolution_y), (60, 1080, 1920))
        self.assertEqual((e.sc.frame_start, e.sc.frame_end), (1, 3600))
        self.assertAlmostEqual(math.degrees(e.cam.data.angle), 80, delta=1.5)

    def test_head_follows_the_route_frame_by_frame(self):
        e = self.env
        for t in (0.0, 2.5, 10.0, 20.0, 31.0, 37.5, 45.0, 55.0, 59.9):
            at(e, t)
            p = e.track.sample(t)
            self.assertAlmostEqual(e.head.location.x, p.x, places=3, msg=f"t={t}")
            self.assertAlmostEqual(e.head.location.y, p.y, places=3, msg=f"t={t}")
            self.assertAlmostEqual(e.head.location.z, p.z, places=3, msg=f"t={t}")
            self.assertAlmostEqual(math.degrees(-e.head.rotation_euler.z) % 360, p.heading % 360, delta=0.1, msg=f"t={t}")

    def test_bus_moves_exactly_as_much_as_the_csv_speed_says(self):
        e = self.env
        dist = self.ctx.bus_distance()
        for t in (10.0, 41.0, 50.0, 59.9):
            at(e, t)
            self.assertAlmostEqual(e.bus.location.y, dist[min(len(dist) - 1, round(t * 60))], delta=0.8, msg=f"t={t}")

    def test_light_channel_drives_every_ceiling_light_and_the_tubes(self):
        e = self.env
        rows = self.ctx.rows()
        tube = next(n for n in e.refs["tube_mat"].node_tree.nodes if n.bl_idname == "ShaderNodeEmission")
        if "light" not in rows[0]:                                               # Ep. 1: a luz não pisca, mas TEM que estar acesa
            at(e, 30.0)
            self.assertTrue(all(ld.data.energy > 0.0 for ld in e.refs["lights"]))
            self.assertGreater(tube.inputs[1].default_value, 0.0)
            return
        dark = next(r for r in rows if r["light"] == 0.0)
        lit = next(r for r in rows if r["light"] == 1.0 and r["frame"] > dark["frame"])
        at(e, dark["t"])                                                         # queda de luz: tudo apaga junto
        self.assertTrue(all(ld.data.energy == 0.0 for ld in e.refs["lights"]))
        self.assertEqual(tube.inputs[1].default_value, 0.0)
        at(e, lit["t"])                                                          # luz normal: tudo volta
        self.assertTrue(all(ld.data.energy > 0.0 for ld in e.refs["lights"]))
        self.assertGreater(tube.inputs[1].default_value, 0.0)

    def test_screen_overlays_follow_vignette_eyelid_and_black(self):
        e = self.env
        for r in self.ctx.rows()[::300]:
            at(e, r["t"])
            self.assertAlmostEqual(self.obj["fx-vinheta"].active_material.node_tree.nodes["A"].outputs[0].default_value,
                                   r["vignette"], places=2, msg=f"t={r['t']}")
            self.assertAlmostEqual(self.obj["fx-preto"].active_material.node_tree.nodes["A"].outputs[0].default_value,
                                   r["black"], places=2)
            up = self.obj["fx-palpebra-cima"].location.y
            self.assertAlmostEqual(up, 0.30 - 0.19 * r["eyelid"], places=2)

    def test_timeline_markers_for_every_beat_and_line(self):
        names = {m.name: m.frame for m in self.env.sc.timeline_markers}
        for b in self.ctx.beats.values():
            self.assertEqual(names[f"BEAT:{b['id']}"], self.ctx.frame(b["start"]), b["id"])
        speech = [i for i in self.ctx.tl["narration"] if i["kind"] == "speech"]
        self.assertEqual(len([n for n in names if n.startswith("VOZ:")]), len(speech))
        self.assertEqual({n for n in names if n.startswith("CENA:")}, {"CENA:s1", "CENA:s2", "CENA:s3"})

    def test_children_hide_with_their_parent(self):
        """Esconder um pai NÃO esconde os filhos no Blender: todo objeto animado tem que ser escondido junto."""
        e = self.env
        for ob in self.obj:
            if ob.animation_data and ob.animation_data.action and ob.children_recursive:
                keyed = {fc.data_path for fc in _fcurves(ob.animation_data.action)}
                if "hide_render" in keyed:
                    for ch in ob.children_recursive:
                        self.assertIsNotNone(ch.animation_data, f"{ob.name} esconde, mas o filho {ch.name} não")
                        self.assertIn("hide_render", {fc.data_path for fc in _fcurves(ch.animation_data.action)})


def _fcurves(action):
    if hasattr(action, "fcurves"):
        return list(action.fcurves)
    out = []                                                    # Blender 5: actions com camadas/slots
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                out += list(bag.fcurves)
    return out


class Ep01(Base, unittest.TestCase):
    EP = "ep01"

    def test_doors_open_for_boarding_and_close_before_the_bus_leaves(self):
        e = self.env
        leaf = e.refs["door_leaves"][0]
        at(e, 20.0)
        opened = leaf.location.y                                                  # aberta no embarque (degraus + catraca)
        at(e, 41.0)
        closed = leaf.location.y                                                  # fechada antes de o ônibus partir (41,9 s)
        self.assertAlmostEqual(closed, L.DOOR_Y - L.DOOR_HALF / 2, places=3)
        self.assertGreater(abs(opened - closed), 0.4)

    def test_catraca_turns_right_after_the_beep(self):
        e = self.env
        t0 = self.ctx.cue("catraca-giro")[0]
        at(e, t0 - 0.2)
        self.assertAlmostEqual(e.refs["catraca_arms"].rotation_euler.z, 0.0, places=3)
        at(e, t0 + 1.0)
        self.assertAlmostEqual(math.degrees(e.refs["catraca_arms"].rotation_euler.z), 120, delta=1)

    def test_backpack_is_thrown_onto_the_aisle_seat_at_the_word_mochila(self):
        e = self.env
        bag = self.obj["mochila"]
        m0, m1 = self.ctx.beat("b3-mochila")
        self.assertFalse(vis(bag, e, m0 - 1.0))                                   # ainda nas costas dele (oculta)
        self.assertTrue(vis(bag, e, m0 + 0.1))
        at(e, m0 + 0.4)
        bx, by = L.BAG_SEAT
        self.assertAlmostEqual(bag.location.x, bx, places=2)                      # pousou no banco ao lado (direita)
        self.assertAlmostEqual(bag.location.z, L.FLOOR_Z + 0.51, places=2)
        self.assertTrue(vis(bag, e, 59.0))

    def test_phone_hand_enters_with_the_words_quase_meia_noite(self):
        e = self.env
        grp = self.obj["mao-esq"]
        s, ee = self.ctx.beat("b1-celular")
        quase = self.ctx.word("s1-04", "quase")[0]
        self.assertLessEqual(s, quase)
        self.assertFalse(vis(grp, e, s - 1.0))
        self.assertTrue(vis(grp, e, quase + 0.6))
        self.assertFalse(vis(grp, e, ee + 0.5))
        texts = {o.data.body for o in self.obj if o.type == "FONT"}
        self.assertTrue({"23:47", "14%"} <= texts)                                # o celular mostra 23:47 / 14%

    def test_driver_waves_during_the_aceno_beat(self):
        e = self.env
        a0, a1 = self.ctx.beat("b2-aceno")
        piv = self.obj["braco-acena"]
        at(e, a0 - 0.2)
        self.assertAlmostEqual(piv.rotation_euler.y, 0.0, places=3)
        at(e, a0 + 0.3)
        self.assertLess(math.degrees(piv.rotation_euler.y), -60)                  # braço levantado
        at(e, a1 + 0.3)
        self.assertAlmostEqual(piv.rotation_euler.y, 0.0, places=3)

    def test_terminal_lights_recede_through_the_window_when_the_bus_leaves(self):
        e = self.env
        at(e, 40.0)
        y0 = e.bus.location.y
        at(e, 58.0)
        self.assertGreater(e.bus.location.y - y0, 60)                             # andou: as luzes ficam para trás


class Ep02(Base, unittest.TestCase):
    EP = "ep02"

    def test_everything_outside_is_where_the_window_is(self):
        """O cenário externo é fixo e o ônibus anda: a placa 348 precisa passar pela janela em b3-placa."""
        e = self.env
        sign = self.obj["placa-348"]
        b0, b1 = self.ctx.beat("b3-placa")
        at(e, b0 + 0.55)
        head_y = e.bus.location.y + e.head.location.y
        self.assertLess(abs(sign.location.y - head_y), 1.5)                       # ao lado da janela
        self.assertLess(sign.location.x, e.bus.location.x - 2.0)                  # à esquerda (janela do protagonista)
        self.assertGreater(sum(1 for o in self.obj if o.name.startswith("arvore")), 100)   # árvores mortas dos dois lados

    def test_dusty_backpack_on_the_aisle_seat_and_silhouette_at_the_last_seat(self):
        bag = self.obj["mochila"]
        self.assertEqual(bag.parent, self.env.bus)
        self.assertAlmostEqual(bag.location.x, L.BAG_SEAT[0], places=2)
        self.assertIn("poeira", {o.name.split(".")[0] for o in bag.children})
        sil = self.obj["silhueta"]
        self.assertAlmostEqual(sil.location.y, L.LAST_SEAT[1], places=2)

    def test_phone_says_sem_servico_and_00_00_in_the_left_hand(self):
        e = self.env
        texts = {o.data.body for o in self.obj if o.type == "FONT"}
        self.assertTrue({"SEM SERVIÇO", "00:00"} <= texts)
        grp = self.obj["mao-celular"]
        s, ee = self.ctx.beat("b3-celular")
        self.assertFalse(vis(grp, e, s - 1.0))
        self.assertTrue(vis(grp, e, s + 1.0))
        self.assertFalse(vis(grp, e, ee + 0.5))

    def test_lights_die_with_the_bum(self):
        e = self.env
        at(e, 0.6)                                                                # 12 frames apagada após o BUM (frame 30)
        self.assertTrue(all(ld.data.energy == 0.0 for ld in e.refs["lights"]))


class Ep03(Base, unittest.TestCase):
    EP = "ep03"

    def test_abyss_and_hands_belong_to_the_bus_so_the_door_opens_onto_them(self):
        """Regressão: o abismo estava no mundo e o ônibus andava 800 m, então a porta abria para o nada."""
        e = self.env
        for name in ("abismo", "luz-vermelha", "mao-0", "mao-33"):
            self.assertEqual(self.obj[name].parent, e.bus, name)
        at(e, 53.0)
        door_world = e.bus.matrix_world @ self.obj["abismo"].location
        self.assertLess((door_world - e.head.matrix_world.translation).length, 8.0)

    def test_red_fog_light_and_glow_follow_the_csv_when_the_door_opens(self):
        e = self.env
        p0 = self.ctx.beat("b3-porta")[0]
        at(e, p0 - 0.5)
        self.assertEqual(self.obj["luz-vermelha"].data.energy, 0.0)
        at(e, p0 + 1.2)
        self.assertAlmostEqual(self.obj["luz-vermelha"].data.energy, 900.0, delta=1)
        glow = bpy.data.materials["neblina-vermelha"].node_tree.nodes["Emission"].inputs[1].default_value
        self.assertAlmostEqual(glow, 6.0, places=2)
        leaf = e.refs["door_leaves"][0]
        at(e, p0 - 0.1)
        closed = leaf.location.y
        at(e, p0 + 0.6)
        self.assertGreater(abs(leaf.location.y - closed), 0.4)                    # folha deslizou

    def test_driver_head_turns_in_three_jerks_on_the_neck_cracks(self):
        e = self.env
        head = next(o for o in self.obj if o.name == "cabeca" and o.parent and o.parent.name == "pescoco"
                    and o.parent.parent and o.parent.parent.parent == e.bus and o.parent.parent.location.x < 0)
        cr = [self.ctx.cue(f"estalo-pescoco-{n}")[0] for n in (1, 2, 3)]
        angles = []
        for t in (cr[0] - 0.1, cr[0] + 0.3, cr[1] - 0.1, cr[1] + 0.3, cr[2] - 0.1, cr[2] + 0.3):
            at(e, t)
            angles.append(round(math.degrees(head.rotation_euler.z)))
        self.assertEqual(angles[0], 0)
        self.assertAlmostEqual(angles[1], -55, delta=3)                           # 1º estalo
        self.assertAlmostEqual(angles[2], angles[1], delta=3)                     # e retém até o 2º
        self.assertAlmostEqual(angles[3], -120, delta=3)
        self.assertAlmostEqual(angles[5], -180, delta=3)                          # rosto para a câmera

    def test_the_double_stands_up_and_walks_only_after_the_beat(self):
        e = self.env
        dbl, sil = self.obj["duplo"], self.obj["silhueta"]
        up0, _ = self.ctx.beat("b3-levanta")
        self.assertTrue(vis(sil, e, 30.0))
        self.assertFalse(vis(dbl, e, 30.0))
        self.assertFalse(vis(sil, e, up0 + 1.0))
        self.assertTrue(vis(dbl, e, up0 + 1.0))
        at(e, self.ctx.beat("b3-revela")[0])
        self.assertGreater(dbl.location.y, -5.0)                                  # já saiu do fundo (era -10)
        at(e, 56.0)
        self.assertLess(math.dist((dbl.location.x, dbl.location.y), (-0.70, -3.35)), 0.2)     # parado logo atrás dele

    def test_handrail_grabs_reach_forward_on_the_same_frames_as_the_sfx(self):
        e = self.env
        for n, hand in ((1, "mao-dir-balaustre"), (2, "mao-esq-balaustre"), (3, "mao-dir-balaustre"), (4, "mao-esq-balaustre")):
            t = self.ctx.cue(f"mao-balaustre-{n}")[0]
            at(e, t)
            self.assertAlmostEqual(self.obj[hand].location.y, -0.06, delta=0.02, msg=f"agarrão {n}")   # no balaústre
            at(e, t - 0.6)
            self.assertLess(self.obj[hand].location.y, -0.3)                                           # fora de quadro

    def test_rotten_hand_enters_the_frame_at_the_shoulder_beat(self):
        e = self.env
        grp = self.obj["mao-podre"]
        o0, _ = self.ctx.beat("b3-ombro")
        self.assertFalse(vis(grp, e, o0 - 1.0))
        self.assertTrue(vis(grp, e, o0 + 0.1))
        at(e, o0 + 0.1)
        self.assertGreater(grp.location.x, 0.1)                                   # entra pelo canto direito


if __name__ == "__main__":
    unittest.main()
