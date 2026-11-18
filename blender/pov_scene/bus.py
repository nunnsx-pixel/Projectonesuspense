"""Ônibus intermunicipal em greybox low-poly (azul e branco desgastado), igual nos 3 episódios.

Tudo é filho do empty `ONIBUS` (que o episódio anima para o ônibus andar). Devolve referências
para o episódio animar portas, luzes, catraca etc.
"""
from __future__ import annotations

from . import kit, materials
from .layout import (AISLE_HALF, BAG_SEAT, CATRACA_DOOR, CEIL_Z, DIVIDER_H, DIVIDER_T, DIVIDER_X, DIVIDER_Y, DOOR_HALF,
                     DOOR_Y, DRIVER, FLOOR_Z, HALF_W, HEADREST_H, ROW_Y, SEAT_BACK_H, SEAT_BACK_TOP, SEAT_CUSHION_TOP,
                     SEAT_X, STAIRS, Y_FRONT, Y_REAR)


def build_bus(root, *, decayed: bool = False, light_color=(0.75, 0.95, 0.8), tube_strength=6.0, light_energy=40.0):
    M = kit.mat
    blue = M("azul", (0.04, 0.16, 0.38) if not decayed else (0.10, 0.20, 0.34))
    white = M("branco", (0.62, 0.62, 0.58) if not decayed else (0.55, 0.57, 0.52))
    seat_m = materials.get("estofado", "mofado" if decayed else "limpo")          # PBR (blender/materials.json)
    dark = M("escuro", (0.025, 0.025, 0.03))
    metal = rust = materials.get("metal-enferrujado", "enferrujado" if decayed else "gasto")
    floor_m = M("piso", (0.08, 0.08, 0.085), rough=0.4)
    refs: dict = {"root": root}
    P = root

    # ---- piso, teto, fundo -------------------------------------------------------------------
    kit.box("piso", (2 * HALF_W, Y_FRONT - Y_REAR, 0.1), (0, (Y_FRONT + Y_REAR) / 2, FLOOR_Z - 0.05), floor_m, parent=P)
    kit.box("teto", (2 * HALF_W + 0.2, Y_FRONT - Y_REAR + 0.4, 0.1), (0, (Y_FRONT + Y_REAR) / 2, CEIL_Z + 0.05), white, parent=P)
    kit.box("fundo", (2 * HALF_W, 0.1, CEIL_Z - FLOOR_Z), (0, Y_REAR, (CEIL_Z + FLOOR_Z) / 2), blue, parent=P)
    kit.box("chassi", (2 * HALF_W - 0.3, Y_FRONT - Y_REAR, 0.45), (0, (Y_FRONT + Y_REAR) / 2, FLOOR_Z - 0.35), dark, parent=P)

    # ---- paredes com janelas (vãos abertos) ------------------------------------------------------
    for side, x in (("esq", -HALF_W), ("dir", HALF_W)):
        h_low = 0.78
        for y0, y1 in ((Y_REAR, Y_FRONT),) if side == "esq" else ((Y_REAR, DOOR_Y - DOOR_HALF), (DOOR_Y + DOOR_HALF, Y_FRONT)):
            kit.box(f"parede-baixa-{side}", (0.08, y1 - y0, h_low), (x, (y0 + y1) / 2, FLOOR_Z + h_low / 2), blue, parent=P)
            kit.box(f"parede-alta-{side}", (0.08, y1 - y0, 0.4), (x, (y0 + y1) / 2, CEIL_Z - 0.2), white, parent=P)
        for i, ry in enumerate(ROW_Y):
            py = ry + 0.425
            if side == "dir" and DOOR_Y - DOOR_HALF - 0.1 < py < DOOR_Y + DOOR_HALF + 0.1:
                continue
            kit.box(f"pilar-{side}-{i}", (0.09, 0.09, CEIL_Z - FLOOR_Z), (x, py, (CEIL_Z + FLOOR_Z) / 2), white, parent=P)
    kit.box("verga-porta", (0.1, 2 * DOOR_HALF + 0.1, 0.4), (HALF_W, DOOR_Y, CEIL_Z - 0.2), white, parent=P)

    # ---- frente: painel, para-brisa (aberto), cabine do motorista ---------------------------------------
    kit.box("painel", (2 * HALF_W, 0.5, 0.9), (0, -0.25, FLOOR_Z + 0.45), dark, parent=P)
    kit.box("frente-alta", (2 * HALF_W, 0.1, 0.35), (0, Y_FRONT, CEIL_Z - 0.18), white, parent=P)
    for x in (-HALF_W + 0.05, 0.0, HALF_W - 0.05):
        kit.box("pilar-para-brisa", (0.08, 0.08, CEIL_Z - FLOOR_Z), (x, Y_FRONT, (CEIL_Z + FLOOR_Z) / 2), white, parent=P)
    dx, dy = DRIVER
    refs["driver_seat"] = kit.box("banco-motorista", (0.5, 0.5, 0.15), (dx, dy, FLOOR_Z + 0.45), dark, parent=P)
    kit.box("encosto-motorista", (0.5, 0.12, 0.75), (dx, dy - 0.28, FLOOR_Z + 0.82), dark, parent=P)
    kit.box("pedestal-motorista", (0.3, 0.3, 0.4), (dx, dy, FLOOR_Z + 0.2), dark, parent=P)
    kit.cyl("volante", 0.19, 0.04, (dx, dy + 0.62, FLOOR_Z + 0.95), metal, rot=(65, 0, 0), parent=P)

    # ---- bancos 2+2 (com os rangidos de um ônibus velho) --------------------------------------------------------
    pole_x = AISLE_HALF + 0.03
    for i, ry in enumerate(ROW_Y):
        for name, sx in SEAT_X.items():
            torn = decayed and (sx, ry) == BAG_SEAT
            m = materials.get("estofado", "podre") if torn else seat_m
            kit.box(f"assento-{i}-{name}", (0.46, 0.48, 0.12), (sx, ry, FLOOR_Z + 0.45), m, parent=P)
            kit.box(f"pedestal-{i}-{name}", (0.3, 0.38, 0.4), (sx, ry, FLOOR_Z + 0.2), dark, parent=P)
            kit.box(f"encosto-{i}-{name}", (0.46, 0.12, SEAT_BACK_H), (sx, ry - 0.25, FLOOR_Z + SEAT_CUSHION_TOP + SEAT_BACK_H / 2), m,
                    parent=P)
            kit.box(f"apoio-{i}-{name}", (0.30, 0.1, HEADREST_H), (sx, ry - 0.27, FLOOR_Z + SEAT_BACK_TOP + HEADREST_H / 2), m,
                    parent=P)
        for s in (-1, 1):
            kit.cyl(f"balaustre-{i}-{s}", 0.022, CEIL_Z - FLOOR_Z, (s * pole_x, ry - 0.25, (CEIL_Z + FLOOR_Z) / 2), rust, parent=P)
    if decayed:                                    # banco ao lado: espuma amarela podre e mofo preto
        bx, by = BAG_SEAT
        foam = M("espuma", (0.55, 0.42, 0.10))
        mold = M("mofo", (0.01, 0.012, 0.01))
        for k, (ox, oy, s) in enumerate(((-0.12, 0.05, 0.16), (0.1, -0.08, 0.12), (0.0, 0.12, 0.1))):
            kit.box(f"espuma-{k}", (s, s, 0.06), (bx + ox, by + oy, FLOOR_Z + 0.53), foam, rot=(0, 0, 25 * k), parent=P)
        for k, (ox, oy) in enumerate(((0.15, 0.1), (-0.15, -0.12), (0.05, 0.0))):
            kit.box(f"mofo-{k}", (0.13, 0.11, 0.02), (bx + ox, by + oy, FLOOR_Z + 0.52), mold, parent=P)
        kit.box("mofo-encosto", (0.3, 0.02, 0.3), (bx, by - 0.19, FLOOR_Z + 0.85), mold, parent=P)

    # ---- degraus, catraca ---------------------------------------------------------------------------------------------------
    for k, (x, z) in enumerate(STAIRS):
        kit.box(f"degrau-{k + 1}", (0.5, 1.0, z), (x, DOOR_Y, z / 2), metal, parent=P)
    cx, cy = CATRACA_DOOR                           # a catraca NÃO muda de lugar entre os episódios
    cat = kit.empty("catraca", (cx, cy, FLOOR_Z), parent=P, rot=(0, 0, 90))
    kit.cyl("catraca-poste", 0.05, 1.0, (0, 0, 0.5), metal, parent=cat)
    kit.box("catraca-leitor", (0.12, 0.12, 0.1), (0, 0, 1.05), M("leitor", (0.05, 0.9, 0.3), emit=3.0), parent=cat)
    arms = kit.empty("catraca-braços", (0, 0, 0.85), parent=cat)
    for k in range(3):
        kit.box(f"catraca-braço-{k}", (0.5, 0.04, 0.04), (0.25, 0, 0), metal, rot=(0, 0, 120 * k), parent=kit.empty(f"b{k}", (0, 0, 0), parent=arms, rot=(0, 0, 120 * k)))
    refs["catraca"], refs["catraca_arms"] = cat, arms

    # divisória/parapeito atrás da catraca e da cabine (o Ep. 3 bate as costas nela); corredor livre
    dw = DIVIDER_X[1] - DIVIDER_X[0]
    refs["divider"] = kit.box("divisoria", (dw, DIVIDER_T, DIVIDER_H), ((DIVIDER_X[0] + DIVIDER_X[1]) / 2, DIVIDER_Y, FLOOR_Z + DIVIDER_H / 2),
                              blue, parent=P)
    kit.cyl("divisoria-corrimao", 0.025, dw, ((DIVIDER_X[0] + DIVIDER_X[1]) / 2, DIVIDER_Y, FLOOR_Z + DIVIDER_H + 0.03), metal,
            rot=(0, 90, 0), parent=P)
    kit.cyl("divisoria-poste", 0.03, 1.55, (DIVIDER_X[1], DIVIDER_Y, FLOOR_Z + 0.78), metal, parent=P)

    # ---- portas pneumáticas (duas folhas na parede direita) ----------------------------------------------------------------------------
    leaf = M("porta", (0.10, 0.12, 0.16), rough=0.3)
    refs["door_leaves"] = []
    for k, s in enumerate((-1, 1)):
        refs["door_leaves"].append(kit.box(f"porta-{k}", (0.05, DOOR_HALF, CEIL_Z - FLOOR_Z - 0.4),
                                           (HALF_W + 0.03, DOOR_Y + s * DOOR_HALF / 2, FLOOR_Z + (CEIL_Z - FLOOR_Z - 0.4) / 2),
                                           leaf, parent=P))

    # ---- rodas e faróis -------------------------------------------------------------------------------------------------------------------
    for y in (-2.6, -8.2):
        for x in (-1.12, 1.12):
            kit.cyl("roda", 0.5, 0.3, (x, y, 0.5), dark, rot=(0, 90, 0), parent=P)
    for x in (-0.8, 0.8):
        kit.box("farol", (0.3, 0.06, 0.18), (x, Y_FRONT + 0.03, FLOOR_Z + 0.25), M("farol", (1, 0.95, 0.8), emit=12.0), parent=P)
    refs["headlights"] = [kit.light(f"farol-{k}", "SPOT", 3500, (1.0, 0.95, 0.8), (x, Y_FRONT + 0.1, FLOOR_Z + 0.25),
                                    parent=P, size=0.1, rot=(90, 0, 0)) for k, x in enumerate((-0.8, 0.8))]
    for ld in refs["headlights"]:
        ld.data.spot_size = 1.2

    # ---- luminárias do teto: o canal `light` do CSV liga tudo (tubos + luzes) ------------------------------------------------------------------------
    tube = M("tubo", light_color, emit=tube_strength)
    refs["tube_mat"] = tube
    refs["lights"] = []
    for k, y in enumerate((-1.2, -3.3, -5.4, -7.5, -9.6)):
        kit.box(f"tubo-{k}", (0.12, 1.1, 0.05), (0.0, y, CEIL_Z - 0.02), tube, parent=P)
        refs["lights"].append(kit.light(f"luz-{k}", "AREA", light_energy, light_color, (0.0, y, CEIL_Z - 0.15),
                                        parent=P, size=0.9, rot=(180, 0, 0)))
    for k, y in enumerate((-3.3, -7.5)):           # preenchimento à altura dos bancos (também piscam com `light`)
        refs["lights"].append(kit.light(f"preenchimento-{k}", "POINT", light_energy * 0.8, light_color,
                                        (0.0, y, FLOOR_Z + 1.5), parent=P, size=0.3))
    return refs


def wire_light_channel(refs, cam, tube_strength: float, light_energy: float):
    """Quedas do canal `light` (falha elétrica): derrubam a emissão dos tubos e a energia das luzes."""
    nt = refs["tube_mat"].node_tree
    emit = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeEmission")
    emit.name = "Emissao"
    kit.driver(nt, 'nodes["Emissao"].inputs[1].default_value', f"v*{tube_strength}", cam, "light")
    for ld in refs["lights"]:
        kit.driver(ld.data, "energy", f"v*{light_energy}", cam, "light")
