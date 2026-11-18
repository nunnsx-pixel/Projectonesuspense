"""Cenário externo compartilhado: estrada de terra vermelha, árvores mortas, placa, neblina."""
from __future__ import annotations

import math
import random

import bpy

from . import kit


def fog(density: float, color=(0.5, 0.35, 0.33), glow: float = 0.0):
    """Neblina de mundo. Com `glow` > 0 ela EMITE (Principled Volume): o fundo vira uma névoa luminosa da cor
    dada. Um Volume Scatter puro só extingue o fundo (céu preto) quando volume_bounces = 0."""
    nt = bpy.context.scene.world.node_tree
    out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputWorld")
    if glow > 0:
        v = nt.nodes.new("ShaderNodeVolumePrincipled")
        v.inputs["Color"].default_value = (*color, 1.0)
        v.inputs["Density"].default_value = density
        v.inputs["Emission Strength"].default_value = glow
        v.inputs["Emission Color"].default_value = (*color, 1.0)
    else:
        v = nt.nodes.new("ShaderNodeVolumeScatter")
        v.inputs["Color"].default_value = (*color, 1.0)
        v.inputs["Density"].default_value = density
    nt.links.new(v.outputs[0], out.inputs["Volume"])


def moon(energy=2.5, color=(0.85, 0.65, 0.6), rot=(55, 0, 25)):
    """Luz difusa vinda do céu nebuloso (só para o exterior ser legível; o teto do ônibus faz sombra)."""
    return kit.light("luz-do-ceu", "SUN", energy, color, (0, 0, 20), rot=rot, size=0.5)


def dirt_road(length: float, y0: float = -60.0, seed: int = 2, tree_gap=(6.0, 11.0), color=(0.28, 0.075, 0.045)):
    """Chão vermelho, faixa da estrada e árvores mortas retorcidas dos dois lados, de y0 até y0+length."""
    rnd = random.Random(seed)
    M = kit.mat
    kit.plane("terra", (300, length + 200), (0, y0 + length / 2, 0), M("terra", color, rough=1.0))
    kit.plane("estrada", (5.2, length + 200), (0, y0 + length / 2, 0.01), M("estrada", (0.35, 0.10, 0.06), rough=1.0))
    bark = M("tronco-morto", (0.06, 0.045, 0.04), rough=1.0)
    for side in (-1, 1):
        y = y0
        while y < y0 + length:
            y += rnd.uniform(*tree_gap)
            x = side * rnd.uniform(4.0, 13.0)
            h = rnd.uniform(3.0, 6.5)
            tilt = rnd.uniform(-10, 10)
            tr = kit.cyl("arvore", rnd.uniform(0.1, 0.2), h, (x, y, h / 2), bark, rot=(tilt, rnd.uniform(-8, 8), 0))
            for k in range(rnd.randint(2, 4)):                 # galhos secos e retorcidos
                bz = h * rnd.uniform(0.45, 0.95)
                ln = rnd.uniform(0.9, 2.0)
                kit.box("galho", (0.05, ln, 0.05), (x + rnd.uniform(-0.3, 0.3), y + rnd.uniform(-0.8, 0.8), bz), bark,
                        rot=(rnd.uniform(-50, 50), rnd.uniform(-40, 40), rnd.uniform(0, 180)))


def sign(x: float, y: float, face_x: float = 1.0, number: str = "348"):
    """Placa de metal enferrujada e torta com o número riscado."""
    M = kit.mat
    pole = M("poste-placa", (0.22, 0.1, 0.05), rough=0.9)
    plate = M("placa", (0.32, 0.18, 0.08), rough=0.7)
    root = kit.empty("placa-348", (x, y, 0), rot=(0, 0, 0))
    kit.cyl("poste", 0.04, 2.4, (0, 0, 1.2), pole, rot=(0, 4, 0), parent=root)
    p = kit.empty("chapa", (0, 0, 2.2), parent=root, rot=(0, 9 * face_x, 8))
    kit.box("chapa", (0.04, 0.95, 0.65), (0, 0, 0), plate, parent=p)
    txt = kit.text("numero", number, 0.34, (0.03 * face_x, 0, 0), M("numero-placa", (0.9, 0.85, 0.7), emit=0.6),
                   parent=p, rot=(90, 0, 90 if face_x > 0 else -90))
    red = M("risco", (0.6, 0.02, 0.02), emit=1.0)
    for rz in (35, -35):                                 # números RISCADOS
        kit.box("risco", (0.025, 0.85, 0.035), (0.045 * face_x, 0, 0), red, rot=(rz, 0, 0), parent=p)
    return root
