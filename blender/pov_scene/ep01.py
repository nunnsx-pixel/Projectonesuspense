"""Ep. 1 — O Embarque em Campinas: rodoviária à noite, plataforma, o ônibus, a partida."""
from __future__ import annotations

import math

from . import bus as busmod
from . import kit, materials, props, routes, world
from .layout import BAG_SEAT, DOOR_HALF, DOOR_Y, DRIVER, FLOOR_Z, MY_SEAT, STAIRS

WORLD = ((0.010, 0.016, 0.034), 1.0)
TUBE, ENERGY = 6.0, 105.0
HALL_X0, HALL_X1, HALL_Y = 8.0, 52.0, 11.0
HALL_H = 4.4


def _terminal():
    M = kit.mat
    floor = materials.get("piso-encerado")                      # PBR: ladrilho de granilite encerado, com juntas
    wall = M("parede-rodoviaria", (0.45, 0.48, 0.50), rough=0.9)
    concrete = M("concreto", (0.12, 0.12, 0.13), rough=0.9)
    tube = M("fluorescente-estourada", (0.92, 0.96, 1.0), emit=22.0)
    kit.box("piso-saguao", (HALL_X1 - 1.3, 2 * HALL_Y, 0.1), ((HALL_X1 + 1.3) / 2, 0, -0.05), floor)
    for sy in (-1, 1):
        kit.box("parede-lateral", (HALL_X1 - HALL_X0, 0.3, HALL_H), ((HALL_X0 + HALL_X1) / 2, sy * HALL_Y, HALL_H / 2), wall)
    kit.box("parede-fundo", (0.3, 2 * HALL_Y, HALL_H), (HALL_X1, 0, HALL_H / 2), wall)
    kit.box("teto-saguao", (HALL_X1 - HALL_X0, 2 * HALL_Y, 0.2), ((HALL_X0 + HALL_X1) / 2, 0, HALL_H + 0.1), wall)
    kit.box("cobertura-plataforma", (HALL_X0 - 1.3, 2 * HALL_Y, 0.2), ((HALL_X0 + 1.3) / 2, 0, 3.6), concrete)
    for yy in (-6.0, 0.0, 6.0):                                        # fileiras de fluorescentes estouradas
        for x in range(10, 51, 4):
            kit.box("fluorescente", (1.4, 0.18, 0.06), (x, yy, HALL_H - 0.05), tube)
    for k, (x, y) in enumerate(((14, -3), (26, 3), (38, -3), (48, 3))):
        kit.light(f"luz-saguao-{k}", "AREA", 900, (0.85, 0.92, 1.0), (x, y, HALL_H - 0.3), size=3.0, rot=(180, 0, 0))
    kit.light("luz-plataforma", "AREA", 250, (0.7, 0.8, 1.0), (4.5, 0, 3.4), size=2.5, rot=(180, 0, 0))
    for x in range(12, 49, 6):
        for sy in (-8.0, 8.0):
            kit.box("pilar", (0.5, 0.5, HALL_H), (x, sy, HALL_H / 2), concrete)
    bench = M("banco-saguao", (0.10, 0.12, 0.16), rough=0.5)
    for x in range(12, 49, 6):
        for sy in (-9.8, 9.8):
            kit.box("banco-espera", (2.4, 0.5, 0.45), (x + 3, sy, 0.22), bench)
    kit.box("guiche", (3.0, 1.0, 1.1), (45, 7.5, 0.55), concrete)
    sign = M("letreiro", (0.95, 0.95, 0.95), emit=3.0)
    kit.text("letreiro-plataforma", "PLATAFORMA 7", 0.7, (HALL_X0 - 0.2, -4.2, 3.0), sign, rot=(90, 0, 90))
    kit.text("letreiro-rodoviaria", "RODOVIARIA DE CAMPINAS", 0.9, (HALL_X1 - 0.3, 0, 3.3), sign, rot=(90, 0, -90))
    kit.plane("asfalto", (60, 640), (-18, 280, 0.0), M("asfalto", (0.03, 0.03, 0.035), rough=0.9))
    kit.plane("plataforma", (7, 640), (4.8, 280, 0.005), M("laje", (0.10, 0.10, 0.11), rough=0.8))


def _street(ctx):
    """Poste e prédios para as luzes passarem pela janela quando o ônibus parte (o ônibus anda em +Y)."""
    M = kit.mat
    lamp = M("lampada", (1.0, 0.78, 0.45), emit=40.0)
    pole = M("poste", (0.05, 0.05, 0.06))
    dist = ctx.bus_distance()[-1]
    y = -30.0
    while y < dist + 60:
        kit.cyl("poste", 0.08, 6.5, (-5.5, y, 3.25), pole)
        kit.box("lampada", (0.7, 0.3, 0.12), (-5.0, y, 6.5), lamp)
        y += 13.0
    win = M("janela-prédio", (1.0, 0.85, 0.6), emit=6.0)
    kit.box("deposito", (6.0, 40.0, 7.0), (-26.0, 0.0, 3.5), M("deposito", (0.06, 0.06, 0.07)))
    for k in range(10):
        kit.box("janela", (0.1, 1.6, 1.0), (-22.95, -16.0 + k * 3.6, 4.0), win)
    for k in range(6):
        kit.box("janela-alta", (0.1, 1.6, 1.0), (-22.95, -12.0 + k * 4.5, 6.0), win)


def build(env):
    ctx, M = env.ctx, kit.mat
    env.refs = busmod.build_bus(env.bus, decayed=False, light_color=(0.85, 0.95, 0.90), tube_strength=TUBE,
                                light_energy=ENERGY)
    env.refs["headlights"][0].data.energy = env.refs["headlights"][1].data.energy = 1200
    env.track = routes.ep01(ctx)
    env.bus_moves = True
    world.fog(0.004, color=(0.55, 0.60, 0.75))
    world.moon(energy=0.8, color=(0.55, 0.65, 1.0), rot=(60, 0, -30))
    _terminal()
    _street(ctx)
    first, last = env.start_frame, env.start_frame + len(ctx.rows()) - 1

    # ---- motorista: boné, rosto na sombra; só acena --------------------------------------------------------------
    dx, dy = DRIVER
    drv = props.figure("motorista", env.bus, loc=(dx, dy - 0.05, FLOOR_Z + 0.5), cap=True, seated=True,
                       skin=(0.10, 0.08, 0.07), shirt="azul")                    # camisa social azul amarrotada
    pivot = kit.empty("braco-acena", (0.31, 0, 0.68), parent=drv["root"])
    kit.box("braco", (0.09, 0.09, 0.55), (0, 0, -0.25), materials.get("camisa-social", "azul"), parent=pivot)
    a0, a1 = ctx.beat("b2-aceno")
    with kit.interp("BEZIER"):
        for t, ang in ((a0 - 0.05, 0), (a0 + 0.25, -85), (a0 + 0.5, -62), (a0 + 0.75, -88), (a1, 0)):
            kit.key(pivot, "rotation_euler", env.f(t), (0, math.radians(ang), 0))

    # ---- portas abertas para o embarque; fecham antes de o ônibus partir (inferido) -----------------------------------
    t_close = ctx.beat("b3-partida")[0] - 3.0
    for leaf, s in zip(env.refs["door_leaves"], (-1, 1)):
        x0, y0, z0 = leaf.location
        with kit.interp("BEZIER"):
            kit.key(leaf, "location", first, (x0, y0 + s * DOOR_HALF * 0.95, z0))
            kit.key(leaf, "location", env.f(t_close), (x0, y0 + s * DOOR_HALF * 0.95, z0))
            kit.key(leaf, "location", env.f(t_close + 0.8), (x0, y0, z0))

    # ---- catraca gira logo depois do bip -----------------------------------------------------------------------------
    c0, _ = ctx.cue("catraca-giro")
    with kit.interp("BEZIER"):
        kit.key(env.refs["catraca_arms"], "rotation_euler", env.f(c0 - 0.05), (0, 0, 0))
        kit.key(env.refs["catraca_arms"], "rotation_euler", env.f(c0 + 0.7), (0, 0, math.radians(120)))

    # ---- mão esquerda com o celular rachado: 23:47 / 14% ------------------------------------------------------------------
    s, e = ctx.beat("b1-celular")
    grp, trem, _ = props.cam_hand(env.cam, "mao-esq", left=True)
    ph = props.phone("celular", trem, [("23:47", 0.03, 0.025), ("14%", 0.014, -0.012)])
    ph.location, ph.rotation_euler = (0.0, 0.085, -0.045), (0.35, 0.0, 0.0)
    rest, hold = (-0.16, -0.40, -0.28), (-0.035, -0.115, -0.26)
    props.reach_keys(env, grp, ((s - 0.1, rest), (s + 0.4, hold), (e - 0.45, hold), (e, rest)))
    kit.visible_between(grp, env.f(s - 0.1), env.f(e), first, last)

    # ---- mão direita com o bilhete na catraca ---------------------------------------------------------------------------------
    t0, t1 = ctx.beat("b2-bilhete")
    g2, tr2, _ = props.cam_hand(env.cam, "mao-dir-bilhete", left=False)
    tk = kit.box("bilhete", (0.045, 0.002, 0.09), (0.0, 0.07, -0.045), M("bilhete", (0.92, 0.92, 0.85)), parent=tr2, rot=(15, 0, 8))
    r_rest, r_hold = (0.17, -0.42, -0.30), (0.06, -0.20, -0.34)
    props.reach_keys(env, g2, ((t0 - 0.1, r_rest), (t0 + 0.45, r_hold), (t1 + 0.1, r_hold), (t1 + 0.55, r_rest)))
    kit.visible_between(g2, env.f(t0 - 0.1), env.f(t1 + 0.55), first, last)

    # ---- mão direita joga a mochila preta (com crachá) no banco ao lado ----------------------------------------------------------
    m0, m1 = ctx.beat("b3-mochila")
    g3, _, _ = props.cam_hand(env.cam, "mao-dir-joga", left=False)
    props.reach_keys(env, g3, ((m0 - 0.2, (0.17, -0.45, -0.30)), (m0 + 0.05, (0.08, -0.16, -0.34)),
                               (m0 + 0.32, (0.20, -0.08, -0.46)), (m1 + 0.1, (0.17, -0.45, -0.30))))
    kit.visible_between(g3, env.f(m0 - 0.2), env.f(m1 + 0.1), first, last)
    bag = props.backpack("mochila", env.bus, dusty=False)
    bx, by = BAG_SEAT
    land = (bx, by - 0.05, FLOOR_Z + 0.51)
    with kit.interp("BEZIER"):
        for t, loc, rot in ((m0, (MY_SEAT[0] + 0.2, MY_SEAT[1] + 0.05, 1.80), (0, 0, 0)),
                            (m0 + 0.15, (-0.68, -5.92, 2.05), (0.3, 0.2, 0.8)),
                            (m0 + 0.35, land, (0, 0, 0))):
            kit.key(bag, "location", env.f(t), loc)
            kit.key(bag, "rotation_euler", env.f(t), rot)
    kit.visible_between(bag, env.f(m0), env.f(ctx.duration + 1), first, last)


def wire(env):
    busmod.wire_light_channel(env.refs, env.cam, TUBE, ENERGY)
