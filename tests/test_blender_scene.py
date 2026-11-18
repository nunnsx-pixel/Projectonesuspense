"""Testes da cena montada no Blender (blender/assemble_scene.py). Só rodam onde existe o módulo `bpy`.

Cada classe monta UM episódio e confere o que importa: hierarquia, caminho-base da cabeça (== trajeto puro),
drivers (luz, vinheta, pálpebra, preto), animação de adereços/personagens nos instantes dos beats e os bugs
que já tivemos (objetos da porta fora do ônibus; filhos que não somem com o pai).
"""
from __future__ import annotations

import math
import re
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
    from pov_scene import props, routes


def at(env, t):
    env.sc.frame_set(env.f(t))
    bpy.context.view_layer.update()


def under(root, prefix):
    """Descendentes de `root` cujo nome começa com `prefix` (Blender acrescenta .001 aos nomes repetidos)."""
    return [o for o in root.children_recursive if o.name.startswith(prefix)]


def color_of(ob):
    return tuple(round(c, 3) for c in ob.active_material.diffuse_color[:3])


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

    def test_catraca_is_fixed_at_the_door_and_the_divider_sits_behind_it(self):
        cat = self.obj["catraca"]
        self.assertEqual((round(cat.location.x, 3), round(cat.location.y, 3), round(cat.location.z, 3)),
                         (L.CATRACA_DOOR[0], L.CATRACA_DOOR[1], round(L.FLOOR_Z, 3)))   # igual nos 3 episódios
        self.assertAlmostEqual(math.degrees(cat.rotation_euler.z), 90, places=3)
        div = self.obj["divisoria"]
        self.assertAlmostEqual(div.location.y, L.DIVIDER_Y, places=3)
        self.assertLess(div.location.y, cat.location.y)                                # atrás da catraca
        self.assertAlmostEqual(div.location.x + div.dimensions.x / 2, L.DIVIDER_X[1], places=3)
        self.assertLess(div.location.x + div.dimensions.x / 2, -L.AISLE_HALF)           # corredor livre
        self.assertAlmostEqual(div.dimensions.z, L.DIVIDER_H, places=3)

    SEATED_T = None

    def test_seated_eye_is_slightly_above_every_seat_back_and_headrest(self):
        if self.SEATED_T is None:
            self.skipTest("episódio sem trecho sentado estável")
        e = self.env
        at(e, self.SEATED_T)
        eye = e.head.location.z - L.FLOOR_Z                                              # altura acima do piso do ônibus
        self.assertAlmostEqual(eye, L.EYE_SEAT, places=3)
        tops = {"apoio": [], "encosto": [], "assento": []}
        for o in self.obj:                                                               # só os bancos dos passageiros (não o do motorista)
            for k in tops:
                if re.match(rf"{k}-\d+-", o.name) and o.type == "MESH":
                    tops[k].append(o.location.z + o.dimensions.z / 2 - L.FLOOR_Z)
        self.assertEqual(len(tops["apoio"]), 36)                                          # 9 fileiras x 4 bancos
        self.assertAlmostEqual(max(tops["apoio"]), L.HEADREST_TOP, places=3)
        self.assertAlmostEqual(max(tops["encosto"]), L.SEAT_BACK_TOP, places=3)
        self.assertAlmostEqual(max(tops["assento"]), L.SEAT_CUSHION_TOP, places=3)
        margin = eye - max(tops["apoio"])
        self.assertTrue(0.03 <= margin <= 0.10, f"olhos {margin * 100:.0f} cm acima dos apoios")   # "ligeiramente acima"
        self.assertTrue(0.75 <= eye - max(tops["assento"]) <= 0.90)                       # ergonomia sentado

    def test_no_black_outlines_anywhere(self):
        """Briefing: 'Sem contornos pretos' (nem Freestyle, nem casca invertida/solidify, nem linhas de contorno)."""
        self.assertFalse(self.env.sc.render.use_freestyle)
        for o in self.obj:
            self.assertFalse([m for m in getattr(o, "modifiers", []) if m.type in ("SOLIDIFY", "SKIN")], o.name)
            self.assertNotEqual(o.type, "GPENCIL", o.name)
        self.assertFalse(any(n.bl_idname == "ShaderNodeBsdfToon" for m in bpy.data.materials if m.node_tree
                             for n in m.node_tree.nodes))

    def test_bus_floor_is_dark_non_slip_rubber(self):
        floor = self.obj["piso"].active_material
        self.assertEqual((floor["pov_id"], floor["pov_source"]), ("piso-emborrachado", "procedural"))
        self.assertEqual(floor["pov_variant"], "sujo" if self.EP != "ep01" else "limpo")
        kinds = {n.bl_idname for n in floor.node_tree.nodes}
        self.assertIn("ShaderNodeTexVoronoi", kinds)                                      # pastilhas antiderrapantes
        self.assertIn("ShaderNodeBump", kinds)                                            # em relevo
        bsdf = next(n for n in floor.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
        self.assertEqual(bsdf.inputs["Metallic"].default_value, 0.0)                      # borracha não é metal
        self.assertTrue(all(c < 0.06 for c in json_params(floor)["color"]))               # escura

    def test_upholstery_is_an_old_printed_fabric_in_blues_and_greys(self):
        for name in ("assento-0-left_window", "encosto-3-right_aisle", "apoio-1-left_window"):
            m = self.obj[name].active_material
            p = json_params(m)
            self.assertEqual(m["pov_id"], "estofado")
            self.assertGreater(p["print_amount"], 0.2, name)                              # tem estampa
            r, g, b = p["print_color"]
            self.assertTrue(abs(r - g) < 0.08 and b >= r, name)                           # cinza-azulado
            self.assertIn("ShaderNodeTexChecker", {n.bl_idname for n in m.node_tree.nodes}, name)
            self.assertGreater(p["color"][2], p["color"][0] * 2, name)                    # base azul

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


def json_params(mat):
    import json
    return json.loads(mat["pov_params"])


def manifest():
    import json
    return json.loads((ROOT / "blender" / "materials.json").read_text(encoding="utf-8"))


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
    SEATED_T = 39.0

    def test_pbr_floor_seats_and_steel(self):
        floor = self.obj["piso-saguao"].active_material
        self.assertEqual((floor["pov_id"], floor["pov_source"]), ("piso-encerado", "procedural"))
        kinds = {n.bl_idname for n in floor.node_tree.nodes}
        self.assertIn("ShaderNodeTexBrick", kinds)                                        # ladrilhos com juntas
        self.assertIn("ShaderNodeBsdfPrincipled", kinds)
        bsdf = next(n for n in floor.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
        self.assertGreater(bsdf.inputs["Coat Weight"].default_value, 0.3)                 # cera = verniz
        self.assertEqual(self.obj["assento-0-left_window"].active_material["pov_variant"], "limpo")
        self.assertEqual(self.obj["balaustre-0--1"].active_material["pov_variant"], "inox")     # aço inox escovado
        self.assertLess(json_params(self.obj["balaustre-0--1"].active_material)["rust"], 0.06)

    def test_driver_wears_a_wrinkled_blue_dress_shirt_and_a_cap_with_a_brim(self):
        drv = self.obj["motorista"]
        torso = under(drv, "tronco")[0].active_material
        self.assertEqual((torso["pov_id"], torso["pov_variant"]), ("camisa-social", "azul"))
        p = json_params(torso)
        self.assertTrue(p["color"][2] > p["color"][0] * 2 and p["color"][2] > p["color"][1])   # azul
        self.assertGreater(p["wrinkle_bump"], 0.3)                                              # amarrotada
        self.assertIn("ShaderNodeBump", {n.bl_idname for n in torso.node_tree.nodes})
        self.assertEqual(self.obj["braco"].active_material["pov_id"], "camisa-social")          # o braço que acena também
        brim, cap = under(drv, "aba")[0], under(drv, "bone")[0]
        self.assertGreater(brim.location.y, cap.location.y)                                     # a aba sai para a frente...
        self.assertLess(brim.location.z, cap.location.z)                                        # ...e fica abaixo do boné (sombreia o rosto)

    def test_sit_sinks_into_the_cushion_then_settles(self):
        e = self.env
        s0 = self.ctx.beat("b3-senta")[0]
        at(e, s0 + 0.2)
        self.assertAlmostEqual(e.head.location.z - L.FLOOR_Z, L.EYE_SEAT - L.SEAT_SINK, places=2)
        at(e, s0 + 1.5)
        self.assertAlmostEqual(e.head.location.z - L.FLOOR_Z, L.EYE_SEAT, places=3)

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
    SEATED_T = 12.0

    def test_pbr_moldy_upholstery_rusty_metal_and_red_dirt_in_world_space(self):
        seat = self.obj["assento-0-left_window"].active_material
        self.assertEqual(seat["pov_variant"], "mofado")
        self.assertGreater(json_params(seat)["mold"], 0.5)
        self.assertEqual(self.obj["assento-3-left_aisle"].active_material["pov_variant"], "podre")   # o banco rasgado, ao lado dele
        self.assertEqual(json_params(self.obj["assento-3-left_aisle"].active_material)["mold"], 1.0)
        pole = self.obj["balaustre-0--1"].active_material
        self.assertEqual((pole["pov_id"], pole["pov_variant"]), ("metal-enferrujado", "enferrujado"))
        self.assertGreater(json_params(pole)["rust"], 0.5)
        ground = self.obj["terra"].active_material
        self.assertEqual((ground["pov_id"], ground["pov_variant"]), ("terra-vermelha", "terra"))
        self.assertEqual(self.obj["estrada"].active_material["pov_variant"], "estrada")
        # espaço de coordenadas: bus-local para o que anda com o ônibus; mundo para o cenário fixo
        tc = next(n for n in seat.node_tree.nodes if n.bl_idname == "ShaderNodeTexCoord")
        self.assertEqual(tc.object, self.env.bus)
        self.assertTrue(any(n.bl_idname == "ShaderNodeNewGeometry" for n in ground.node_tree.nodes))
        self.assertFalse(any(n.bl_idname == "ShaderNodeTexCoord" for n in ground.node_tree.nodes))
        for m in (seat, pole, ground):                                                      # mapeamento em metros
            mp = next(n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeMapping")
            tile = manifest()["materials"][m["pov_id"]]["tile_m"]
            self.assertAlmostEqual(mp.inputs["Scale"].default_value[0], 1 / tile, places=4)

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

    def test_back_passenger_wears_the_protagonists_hoodie_and_backpack(self):
        sil = self.obj["silhueta"]
        self.assertEqual(color_of(under(sil, "tronco")[0]), tuple(round(c, 3) for c in props.HOODIE))   # o MESMO moletom
        self.assertTrue(under(sil, "capuz") and under(sil, "bolso-canguru"))                            # capuz e bolso canguru
        bag = under(sil, "mochila-silhueta")
        self.assertEqual(len(bag), 1)                                                                   # a mochila preta...
        self.assertTrue(under(bag[0], "cracha"))                                                       # ...com o crachá
        self.assertEqual(sil.parent, self.env.bus)                                                      # sentado na última fileira
        self.assertAlmostEqual(sil.location.x, L.LAST_SEAT[0], places=2)

    def test_driver_shirt_is_the_same_blue_dress_shirt_but_grimy(self):
        torso = under(self.obj["motorista"], "tronco")[0].active_material
        self.assertEqual((torso["pov_id"], torso["pov_variant"]), ("camisa-social", "encardida"))

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

    def test_ground_fog_follows_the_bus_and_thins_out_with_height(self):
        """Neblina volumétrica rasteira presa ao ônibus; densidade = base·e^(−z/h)·mancha (EXPONENT é unário!)."""
        fog = self.obj["neblina-rasteira"]
        self.assertEqual(fog.parent, self.env.bus)
        nt = fog.active_material.node_tree
        kinds = {n.bl_idname for n in nt.nodes}
        self.assertIn("ShaderNodeVolumePrincipled", kinds)
        expo = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeMath" and n.operation == "EXPONENT")
        self.assertTrue(expo.inputs[0].is_linked)                                           # regressão: antes era constante (e^2,7 ≈ 15x)
        vol = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeVolumePrincipled")
        self.assertTrue(vol.inputs["Density"].is_linked)
        out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
        self.assertTrue(out.inputs["Volume"].is_linked)
        self.assertFalse(out.inputs["Surface"].is_linked)                                    # só volume
        pos = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeNewGeometry")           # mundo: a névoa não nada
        self.assertTrue(pos.outputs["Position"].is_linked)

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

    def test_jaw_stretches_as_the_neck_turns_and_the_smile_goes_down_with_it(self):
        e = self.env
        drv = next(o for o in self.obj if o.name == "motorista" and o.parent == e.bus)
        jaw, smile = under(drv, "mandibula")[0], under(drv, "sorriso")[0]
        cr = [self.ctx.cue(f"estalo-pescoco-{n}")[0] for n in (1, 2, 3)]
        rest_z = props.JAW_SIZE[2]
        zs, drops = [], []
        for t in (cr[0] - 0.1, cr[0] + 0.3, cr[1] + 0.3, cr[2] + 0.3, cr[2] + 2.0):
            at(e, t)
            zs.append(jaw.scale.z / rest_z)
            drops.append(smile.location.z)
        self.assertAlmostEqual(zs[0], 1.0, places=2)                              # antes de virar: normal
        self.assertTrue(all(b > a + 0.2 for a, b in zip(zs[:4], zs[1:4])))        # estica a cada estalo
        self.assertAlmostEqual(zs[3], 3.2, delta=0.1)                             # esticada no rosto revelado
        self.assertAlmostEqual(zs[4], zs[3], delta=0.02)                          # e fica assim
        self.assertLess(drops[3], drops[0] - 0.08)                                 # o sorriso desceu junto
        top = jaw.location.z + jaw.scale.z / 2                                    # o topo continua preso ao crânio
        self.assertAlmostEqual(top, props.JAW_LOC[2] + rest_z / 2, places=3)
        self.assertEqual(color_of(jaw), color_of(under(drv, "crânio")[0]))        # mesma pele cinza

    def test_driver_shirt_is_the_same_blue_dress_shirt_but_grimy(self):
        drv = next(o for o in self.obj if o.name == "motorista" and o.parent == self.env.bus)
        self.assertEqual(under(drv, "tronco")[0].active_material["pov_variant"], "encardida")

    def test_the_double_wears_the_same_hoodie_and_backpack_now_rotten(self):
        sil, dbl = self.obj["silhueta"], self.obj["duplo"]
        self.assertEqual(color_of(under(sil, "tronco")[0]), tuple(round(c, 3) for c in props.HOODIE))   # sentado: o moletom dele
        self.assertEqual(color_of(under(dbl, "tronco")[0]), tuple(round(c, 3) for c in props.HOODIE_ROT))
        self.assertLess(max(abs(a - b) for a, b in zip(props.HOODIE, props.HOODIE_ROT)), 0.07)           # mesmo moletom, desbotado
        self.assertTrue(under(dbl, "capuz") and under(dbl, "bolso-canguru"))
        self.assertGreaterEqual(len(under(dbl, "mofo-moletom")), 3)                                      # mofo no moletom
        bag = under(dbl, "mochila-duplo")[0]
        self.assertEqual(bag.parent, dbl)                                                                # nas costas
        self.assertLess(bag.location.y, 0.0)
        self.assertTrue(under(bag, "cracha") and under(bag, "poeira"))                                   # crachá e poeira
        self.assertTrue(under(self.obj["silhueta"], "mochila-silhueta"))                                  # a mesma mochila, no colo dele

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
        self.assertLess(math.dist((dbl.location.x, dbl.location.y), routes.DOUBLE_BEHIND), 0.2)   # parado atrás da divisória

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


@unittest.skipUnless(bpy is not None, "módulo bpy não instalado")
class ImageTextureSets(unittest.TestCase):
    """Conjuntos PBR em imagens assumem no lugar do procedural (mapeamento em caixa, em metros)."""

    def setUp(self):
        import tempfile
        from pov_scene import kit, materials
        self.kit, self.materials = kit, materials
        bpy.ops.wm.read_factory_settings(use_empty=True)
        kit.reset()
        materials.reset()
        self.tmp = Path(tempfile.mkdtemp())
        materials.configure(textures_dir=self.tmp)

    def make(self, folder, names):
        d = self.tmp / folder
        d.mkdir(parents=True, exist_ok=True)
        for n in names:
            img = bpy.data.images.new(f"t-{folder}-{n}", 4, 4)
            img.filepath_raw = str(d / f"{n}.png")
            img.file_format = "PNG"
            img.save()

    def test_without_images_the_procedural_is_used(self):
        m = self.materials.get("metal-enferrujado", "enferrujado")
        self.assertEqual(m["pov_source"], "procedural")
        self.assertEqual(self.materials.find_maps("metal-enferrujado"), {})

    def test_image_set_replaces_the_procedural_with_box_projection_and_right_colorspaces(self):
        self.make("metal-enferrujado", ["albedo", "roughness", "metallic", "height"])
        m = self.materials.get("metal-enferrujado", "enferrujado")
        self.assertEqual(m["pov_source"], "imagens:albedo,height,metallic,roughness")
        tex = [n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeTexImage"]
        self.assertEqual(len(tex), 4)
        self.assertTrue(all(t.projection == "BOX" and t.extension == "REPEAT" for t in tex))
        spaces = {Path(t.image.filepath).stem: t.image.colorspace_settings.name for t in tex}
        self.assertEqual(spaces["albedo"], "sRGB")
        self.assertTrue(all(v == "Non-Color" for k, v in spaces.items() if k != "albedo"))
        bsdf = next(n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
        self.assertTrue(bsdf.inputs["Base Color"].is_linked and bsdf.inputs["Roughness"].is_linked)
        self.assertTrue(bsdf.inputs["Metallic"].is_linked and bsdf.inputs["Normal"].is_linked)   # height -> bump
        mp = next(n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeMapping")
        self.assertAlmostEqual(mp.inputs["Scale"].default_value[0], 1 / 0.6, places=4)              # tile_m = 0,6 m

    def test_variant_folder_wins_over_the_base_folder(self):
        self.make("estofado", ["albedo"])
        self.make("estofado/podre", ["albedo", "roughness"])
        self.assertEqual(sorted(self.materials.find_maps("estofado", "podre")), ["albedo", "roughness"])
        self.assertEqual(self.materials.find_maps("estofado", "podre")["albedo"].parent.name, "podre")
        self.assertEqual(sorted(self.materials.find_maps("estofado", "limpo")), ["albedo"])          # sem pasta própria: usa a base

    def test_unknown_variant_is_an_error(self):
        with self.assertRaises(KeyError):
            self.materials.get("estofado", "inexistente")


if __name__ == "__main__":
    unittest.main()
