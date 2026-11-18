"""Ep. 3 — O Fim da Linha: corredor do ônibus, revelação do motorista e do passageiro, porta e neblina vermelha."""
from __future__ import annotations

import math

from . import bus as busmod
from . import kit, materials, props, routes, world
from .layout import DOOR_HALF, DOOR_Y, DRIVER, FLOOR_Z, HALF_W, LAST_SEAT, MY_SEAT, ROW_Y
from .path import smoothstep

WORLD = ((0.16, 0.085, 0.075), 3.0)
TUBE, ENERGY = 4.0, 90.0
FOG_RED = (1.0, 0.07, 0.05)


def _abyss(env):
    """Porta aberta: abismo de neblina vermelha com dezenas de mãos pálidas (o brilho segue `red_fog`)."""
    M = kit.mat
    red = M("neblina-vermelha", FOG_RED, emit=6.0)
    pale = M("mao-palida", (0.62, 0.60, 0.58), rough=0.9)
    # tudo que pertence à porta é filho do ÔNIBUS (ele anda ~800 m); o abismo anda junto com a porta
    glow = kit.plane("abismo", (9, 14), (HALF_W + 3.5, DOOR_Y, 2.2), red, rot=(0, -90, 0), parent=env.bus)   # emite p/ -X
    kit.driver(red.node_tree, "nodes[\"Emission\"].inputs[1].default_value", "v*6", env.cam, "red_fog")
    ld = kit.light("luz-vermelha", "POINT", 0, FOG_RED, (HALF_W + 0.6, DOOR_Y, FLOOR_Z + 1.4), parent=env.bus, size=0.6)
    kit.driver(ld.data, "energy", "v*900", env.cam, "red_fog")
    import random
    rnd = random.Random(3)
    for k in range(34):                                         # mãos pálidas estendidas para dentro
        y = DOOR_Y + rnd.uniform(-2.6, 2.6)
        z = FLOOR_Z + rnd.uniform(-0.5, 3.0)
        x = HALF_W + rnd.uniform(0.15, 2.8)
        ang = rnd.uniform(-25, 25)
        h = kit.empty(f"mao-{k}", (x, y, z), parent=env.bus, rot=(rnd.uniform(-25, 25), 0, 90 + ang))
        kit.box("palma", (0.09, 0.2, 0.025), (0, 0, 0), pale, parent=h)
        for f in range(4):
            kit.box("dedo", (0.02, 0.15, 0.02), ((f - 1.5) * 0.026, 0.17, 0), pale, rot=(0, 0, rnd.uniform(-12, 12)), parent=h)
        kit.box("braco", (0.06, 0.6, 0.05), (0, -0.4, 0), pale, parent=h)
    return ld


def build(env):
    ctx, M = env.ctx, kit.mat
    env.refs = busmod.build_bus(env.bus, decayed=True, light_color=(0.30, 0.95, 0.50), tube_strength=TUBE,
                                light_energy=ENERGY)
    env.track = routes.ep03(ctx)
    env.bus_moves = True
    dist = ctx.bus_distance()
    world.dirt_road(dist[-1] + 160, y0=-90, seed=3)
    world.fog(0.02, color=(0.60, 0.34, 0.30), glow=0.03)
    materials.ground_fog(env.bus)                                # neblina volumétrica rasteira, anda com o ônibus
    world.moon(energy=6.0)
    _abyss(env)
    first, last = env.start_frame, env.start_frame + len(ctx.rows()) - 1
    pi, e = math.pi, ctx.duration

    # ---- motorista: gira o pescoço 180° em 3 estalos; rosto cinza, olhos brancos, sorriso ----------------------------
    dx, dy = DRIVER
    drv = props.figure("motorista", env.bus, loc=(dx, dy - 0.05, FLOOR_Z + 0.5), cap=True, seated=True,
                       coat=(0.05, 0.06, 0.07), skin=props.GREY_SKIN, eyes=True)
    cr = [ctx.cue(f"estalo-pescoco-{n}")[0] for n in (1, 2, 3)]
    with kit.interp("BEZIER"):
        prev = 0
        for t, ang in zip(cr, (-55, -120, -180)):                  # cada estalo = um tranco curto; entre eles, retém
            kit.key(drv["head"], "rotation_euler", env.f(t - 0.03), (0, 0, math.radians(prev)))
            kit.key(drv["head"], "rotation_euler", env.f(t + 0.12), (0, 0, math.radians(ang)))
            prev = ang
    # (o motorista fica de costas até o pescoço virar; os olhos/sorriso só aparecem de frente)

    # ---- as 4 mãos que agarram os balaústres (cada uma = SFX + solavanco de câmera no mesmo frame) -----------------------------
    gR, _, _ = props.cam_hand(env.cam, "mao-dir-balaustre", left=False, tremor=0.006)
    gL, _, _ = props.cam_hand(env.cam, "mao-esq-balaustre", left=True, tremor=0.006)
    far_R, far_L = (0.20, -0.48, -0.30), (-0.20, -0.48, -0.30)
    reach_R, reach_L = (0.15, -0.06, -0.46), (-0.15, -0.06, -0.46)
    seqs = {gR: [], gL: []}
    for n in (1, 2, 3, 4):
        t = ctx.cue(f"mao-balaustre-{n}")[0]
        g, rest, reach = (gR, far_R, reach_R) if n % 2 else (gL, far_L, reach_L)
        seqs[g] += [(t - 0.28, rest), (t, reach), (t + 0.5, reach), (t + 0.85, rest)]
    for g in (gR, gL):
        props.reach_keys(env, g, [(0.0, far_R if g is gR else far_L)] + seqs[g])

    # ---- passageiro do fundo: sentado e imóvel; levanta; vem pelo corredor; a MESMA mochila e roupa; rosto em decomposição ----------
    lx, ly = LAST_SEAT
    sil = props.figure("silhueta", env.bus, loc=(lx, ly, FLOOR_Z + 0.5), seated=True, coat=(0.02, 0.02, 0.025), skin=(0.05, 0.05, 0.05))
    up0, up1 = ctx.beat("b3-levanta")
    walk0, walk1 = ctx.beat("b3-caminha")
    rev0, _ = ctx.beat("b3-revela")
    kit.visible_between(sil["root"], first, env.f(up0 + 0.2), first, last)
    dbl = props.figure("duplo", env.bus, loc=(lx, ly, FLOOR_Z), heading=0, coat=(0.20, 0.22, 0.28), skin=(0.40, 0.46, 0.36), eyes=False)
    props.backpack("mochila-duplo", dbl["root"], dusty=True, loc=(0, -0.22, 0.95))
    behind = routes.DOUBLE_BEHIND
    with kit.interp("BEZIER"):
        for t, loc in ((up0 + 0.2, (lx, ly, FLOOR_Z)), (walk0, (lx, ly + 0.2, FLOOR_Z)), (walk1, (-0.05, -4.2, FLOOR_Z)),
                       (walk1 + 1.0, (behind[0], behind[1], FLOOR_Z))):
            kit.key(dbl["root"], "location", env.f(t), loc)
    kit.visible_between(dbl["root"], env.f(up0 + 0.2), env.f(e + 1), first, last)

    # ---- a mão podre que agarra o ombro (entra no canto da tela) -----------------------------------------------------------------------
    o0, o1 = ctx.beat("b3-ombro")
    gO, _, _ = props.cam_hand(env.cam, "mao-podre", left=False, skin=props.GREY_SKIN, sleeve=(0.20, 0.22, 0.28), tremor=0.005)
    props.reach_keys(env, gO, ((o0 - 0.3, (0.32, -0.30, -0.05)), (o0, (0.13, -0.13, -0.20)), (e, (0.12, -0.12, -0.20))))
    kit.visible_between(gO, env.f(o0 - 0.3), env.f(e + 1), first, last)

    # ---- as portas pneumáticas abrem com o chiado -------------------------------------------------------------------------------------------
    p0, _ = ctx.beat("b3-porta")
    for leaf, s in zip(env.refs["door_leaves"], (-1, 1)):
        y0 = leaf.location[1]
        with kit.interp("BEZIER"):
            kit.key(leaf, "location", env.f(p0 - 0.02), (leaf.location[0], y0, leaf.location[2]))
            kit.key(leaf, "location", env.f(p0 + 0.45), (leaf.location[0], y0 + s * DOOR_HALF * 0.95, leaf.location[2]))


def wire(env):
    busmod.wire_light_channel(env.refs, env.cam, TUBE, ENERGY)
