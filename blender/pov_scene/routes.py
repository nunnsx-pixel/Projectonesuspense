"""Caminho-base da cabeça dos 3 episódios (sem bpy). Cada função recebe um Ctx e devolve um Track.

O avanço dos trechos a pé é guiado pelos PASSOS da timeline (mesmos do CSV e do SFX); os trechos parados
(sentar, girar o tronco, inclinar-se) são por tempo. Coordenadas no referencial do ônibus (ver layout.py).
"""
from __future__ import annotations

from .layout import (DIVIDER_T, DIVIDER_Y, DOOR_Y, EYE_RUN, EYE_SEAT, EYE_STAND, FLOOR_Z, MY_SEAT, SEAT_SINK, STAIRS)
from .path import Leg, Track

AISLE_LEAN = (MY_SEAT[0] + 0.85, MY_SEAT[1])          # inclina-se sobre o corredor (x = -0,10): fora dos encostos
RUN_START, FOOT_OF_STAIRS = (46.0, DOOR_Y), (3.05, DOOR_Y)
S0 = (-0.75, -2.20)                                     # Ep. 3: de pé diante do motorista (ele a ~15° à esquerda)
AFTER_RECOIL = (-0.75, DIVIDER_Y + DIVIDER_T / 2 + 0.115)   # Ep. 3: costas na DIVISÓRIA (face dela + meia espessura do corpo)
DOUBLE_BEHIND = (-0.72, DIVIDER_Y - DIVIDER_T / 2 - 0.15)   # Ep. 3: o duplo, do outro lado da divisória, ao alcance do ombro


def ep01(ctx) -> Track:
    st = ctx.steps
    t_bip = ctx.cue("bip-catraca")[0]
    run = st("corrida-saguao")
    stairs = st("degraus")
    walk = st("corredor")
    seat0 = (0.0, -5.7)
    sit_end = ctx.beat("b3-senta")[0] + 0.15            # o corpo POUSA no banco junto do baque (k-sentar)
    top = STAIRS[-1][0]
    return Track([
        Leg("corrida", [RUN_START, FOOT_OF_STAIRS], 270, 0.0, EYE_RUN, steps=run, from_time=0.0),
        Leg("para", [FOOT_OF_STAIRS, FOOT_OF_STAIRS], 270, 0.0, [[0, EYE_RUN], [1, EYE_STAND]], span=(run[-1], run[-1] + 1.0)),
        Leg("degraus", [FOOT_OF_STAIRS, (top, DOOR_Y)], 270, [[0, 0], [1 / 3, STAIRS[0][1]], [2 / 3, STAIRS[1][1]], [1, STAIRS[2][1]]],
            EYE_STAND, steps=stairs, phase0=-1.0, phase1=2.0),
        Leg("passa-catraca", [(top, DOOR_Y), (0.3, DOOR_Y)], 270, FLOOR_Z, EYE_STAND, steps=st("passa-catraca"),
            from_time=t_bip + 0.2),
        Leg("corredor", [(0.3, DOOR_Y), (0.0, -1.5), seat0], [[0, 270], [0.25, 180], [1, 180]], FLOOR_Z, EYE_STAND,
            steps=walk, from_time=walk[0] - 0.4),
        Leg("senta", [seat0, (MY_SEAT[0] + 0.4, MY_SEAT[1]), MY_SEAT], [[0, 180], [0.45, 270], [1, 360]], FLOOR_Z,
            [[0, EYE_STAND], [0.5, EYE_STAND], [1, EYE_SEAT - SEAT_SINK]], span=(walk[-1], sit_end)),     # afunda na almofada
        Leg("acomoda", [MY_SEAT, MY_SEAT], 0, FLOOR_Z, [[0, EYE_SEAT - SEAT_SINK], [1, EYE_SEAT]], span=(sit_end, sit_end + 0.7)),
    ])


def ep02(ctx) -> Track:
    """Sentado. O olhar do CSV é RELATIVO à cabeça; para a geometria bater, o CORPO gira/inclina:
    "o banco ao lado" fica a 90° à direita (olhar do CSV ~+25°): o tronco gira ~58°; "olhar rápido para
    trás" e o chamado final: dos bancos da janela os encostos bloqueiam a vista, então ele se inclina
    para o corredor e vira um pouco o corpo."""
    seat = [MY_SEAT, MY_SEAT]
    b0, _ = ctx.beat("b2-banco")
    _, m1 = ctx.beat("b2-mochila")
    s0, _ = ctx.beat("b2-silhueta")
    u0, _ = ctx.beat("b2-sussurro")
    g0, _ = ctx.beat("b3-motorista")
    lean = EYE_SEAT + 0.12
    return Track([
        Leg("sentado", seat, 0, FLOOR_Z, EYE_SEAT, span=(0, b0 - 0.5)),
        Leg("gira-p/-banco", seat, [[0, 0], [1, 58]], FLOOR_Z, EYE_SEAT, span=(b0 - 0.5, b0 + 0.3)),
        Leg("volta", seat, [[0, 58], [1, 0]], FLOOR_Z, EYE_SEAT, span=(m1 + 0.2, m1 + 1.0)),
        Leg("inclina-corredor", [MY_SEAT, AISLE_LEAN], [[0, 0], [1, 35]], FLOOR_Z, [[0, EYE_SEAT], [1, lean]],
            span=(s0 - 0.55, s0 - 0.05)),
        Leg("volta-ao-banco", [AISLE_LEAN, MY_SEAT], [[0, 35], [1, 0]], FLOOR_Z, [[0, lean], [1, EYE_SEAT]],
            span=(u0 + 0.5, u0 + 1.3)),
        Leg("inclina-p/-chamar", [MY_SEAT, AISLE_LEAN], 0, FLOOR_Z, [[0, EYE_SEAT], [1, lean]], span=(g0 + 0.2, g0 + 1.1)),
    ])


def ep03(ctx) -> Track:
    st = ctx.steps
    stumble = st("cambaleio-corredor")
    back = st("recua-divisoria")
    pushed = st("empurrado")
    t_push = ctx.beat("b3-empurra")[0]
    door = (1.45, DOOR_Y)
    return Track([
        Leg("levanta-num-salto", [MY_SEAT, MY_SEAT], 0, FLOOR_Z, [[0, EYE_SEAT], [1, EYE_RUN]], span=(0.0, stumble[0])),
        Leg("cambaleia", [MY_SEAT, (-0.05, -5.6), (-0.05, -2.6), S0], 0, FLOOR_Z, EYE_RUN, steps=stumble,     # pelo corredor, por cima da divisória
            from_time=stumble[0]),
        Leg("recua-2-passos", [S0, AFTER_RECOIL], 0, FLOOR_Z, EYE_RUN, steps=back, from_time=ctx.item("s2-05")[0]),
        Leg("empurrado", [AFTER_RECOIL, (0.5, -1.6), door], [[0, 0], [0.6, 40], [1, 80]], FLOOR_Z, [[0, EYE_RUN], [1, 1.40]],
            steps=pushed, from_time=t_push),
        Leg("cai-na-neblina", [door, (2.5, DOOR_Y)], [[0, 80], [1, 100]], [[0, FLOOR_Z], [1, 0.0]], [[0, 1.40], [1, 0.9]],
            span=(pushed[-1], ctx.duration)),
    ])


ROUTES = {"ep01": ep01, "ep02": ep02, "ep03": ep03}
