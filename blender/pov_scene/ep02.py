"""Ep. 2 — O Despertar no Escuro: ônibus apodrecido em estrada de terra vermelha, protagonista sentado."""
from __future__ import annotations

from . import bus as busmod
from . import kit, props, routes, world
from .layout import BAG_SEAT, DRIVER_HIP, FLOOR_Z, LAST_SEAT

WORLD = ((0.16, 0.085, 0.075), 3.0)
TUBE, ENERGY = 4.0, 90.0


def build(env):
    ctx, M = env.ctx, kit.mat
    env.refs = busmod.build_bus(env.bus, decayed=True, light_color=(0.30, 0.95, 0.50), tube_strength=TUBE,
                                light_energy=ENERGY)
    env.track = routes.ep02(ctx)
    env.bus_moves = True
    dist = ctx.bus_distance()

    # ---- fora: estrada de terra vermelha, árvores mortas, neblina e a placa 348 riscada ------------------------
    world.dirt_road(dist[-1] + 160, y0=-90, seed=2)
    world.fog(0.02, color=(0.60, 0.34, 0.30), glow=0.03)
    world.moon(energy=6.0)
    b0, b1 = ctx.beat("b3-placa")
    t_pass = b0 + 0.55
    world.sign(-4.0, dist[min(len(dist) - 1, int(round(t_pass * ctx.fps)))] - 5.95, face_x=1.0)

    # ---- dentro: mochila empoeirada no banco ao lado, motorista (nuca cinza), silhueta no último banco ---------------
    bx, by = BAG_SEAT
    props.backpack("mochila", env.bus, dusty=True, loc=(bx, by - 0.05, FLOOR_Z + 0.51))
    dx, dy, dz = DRIVER_HIP
    props.figure("motorista", env.bus, loc=(dx, dy, FLOOR_Z + dz), cap=True, seated=True, grip="wheel",
                 skin=props.GREY_SKIN, shirt="encardida")                      # corpo inteiro; camisa social azul amarrotada e suja
    lx, ly = LAST_SEAT                                                         # o duplo: CALVO, mesmo moletom e mesma mochila (no colo)
    props.figure("silhueta", env.bus, loc=(lx, ly, FLOOR_Z + 0.5), seated=True, coat=props.HOODIE, hoodie=True, decay=True,
                 bag="lap", bald=True, grip="lap", pants=props.PANTS_ROT, skin=(0.05, 0.05, 0.05))

    # ---- mão esquerda com o celular morto (SEM SERVIÇO / 00:00), tremendo ---------------------------------------------
    grp = kit.empty("mao-celular", parent=env.cam)
    trem = kit.empty("tremor", parent=grp)
    kit.frame_driver(trem, "location", "0.0035*sin(frame*1.31)", index=0)
    kit.frame_driver(trem, "location", "0.0030*sin(frame*1.07+1.0)", index=1)
    props.hand("mao-esquerda", trem, left=True)
    ph = props.phone("celular", trem, [("SEM SERVIÇO", 0.0075, 0.03), ("00:00", 0.028, -0.012)])
    ph.location, ph.rotation_euler = (0.0, 0.085, -0.045), (0.35, 0.0, 0.0)
    s, e = ctx.beat("b3-celular")
    first, last = env.start_frame, env.start_frame + len(ctx.rows()) - 1
    rest, hold = (-0.16, -0.40, -0.28), (-0.035, -0.115, -0.26)
    with kit.interp("BEZIER"):
        for t, pos in ((s - 0.15, rest), (s + 0.4, hold), (e - 0.45, hold), (e, rest)):
            kit.key(grp, "location", env.f(t), pos)
    kit.visible_between(grp, env.f(s - 0.15), env.f(e), first, last)


def wire(env):
    busmod.wire_light_channel(env.refs, env.cam, TUBE, ENERGY)
