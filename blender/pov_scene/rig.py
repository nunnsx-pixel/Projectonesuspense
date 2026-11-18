"""Esqueleto low-poly das figuras: posições das juntas e orientação dos membros (Python puro, sem bpy).

Convenção da figura: origem nos pés (em pé) ou no quadril sentado; +Y = frente, +X = DIREITA da figura, Z para cima.
Cada junta é um `empty` sem rotação própria (rotação identidade), então a posição de cada filho é só a diferença
entre as posições; girar uma junta gira todo o membro abaixo dela (ombro -> cotovelo -> punho; quadril -> joelho -> tornozelo).

Os membros são resolvidos por IK de dois ossos (comprimentos fixos), então qualquer pose mantém as proporções.
"""
from __future__ import annotations

import math

THIGH, SHIN = 0.43, 0.45                 # coxa, canela
UPPER, FORE, HAND = 0.29, 0.27, 0.09     # braço, antebraço, mão
SIDES = {"esq": -1, "dir": 1}            # esquerda = -X, direita = +X (figura voltada para +Y)

STAND_HIP_Z, STAND_SHOULDER_Z = 0.92, 1.26
SEAT_HIP_Z, SEAT_SHOULDER_Z = 0.08, 0.66        # sentado: origem no quadril, almofada ~2,5 cm acima dela
SEAT_FLOOR_Z = -0.50                            # o piso fica 0,50 m abaixo do quadril sentado (almofada a 0,51 m)
ANKLE_H = 0.08


# ---- vetores ---------------------------------------------------------------------------------------------------
def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = length(a)
    if n < 1e-12:
        raise ValueError("vetor nulo")
    return (a[0] / n, a[1] / n, a[2] / n)


# ---- IK de dois ossos ---------------------------------------------------------------------------------------------
def two_bone_ik(root, target, l1, l2, pole):
    """Posição da junta do meio (cotovelo/joelho) e do fim (punho/tornozelo).

    O fim fica em `target` se ele estiver ao alcance; senão, no ponto mais próximo dele (braço esticado).
    `pole` diz para que lado a junta do meio dobra (só a parte perpendicular à linha raiz→alvo importa).
    """
    d = sub(target, root)
    dist = length(d)
    lo, hi = abs(l1 - l2) + 1e-4, l1 + l2 - 1e-4
    dist_c = min(max(dist, lo), hi)
    dhat = unit(d) if dist > 1e-9 else (0.0, 0.0, -1.0)
    end = add(root, mul(dhat, dist_c))
    a = (l1 * l1 - l2 * l2 + dist_c * dist_c) / (2 * dist_c)
    h = math.sqrt(max(l1 * l1 - a * a, 0.0))
    p = sub(pole, mul(dhat, dot(pole, dhat)))
    if length(p) < 1e-9:                                   # pólo alinhado com a linha: qualquer perpendicular serve
        p = cross(dhat, (1.0, 0.0, 0.0)) if abs(dhat[0]) < 0.9 else cross(dhat, (0.0, 1.0, 0.0))
    mid = add(add(root, mul(dhat, a)), mul(unit(p), h))
    return mid, end


# ---- orientação de peças ao longo de um vetor ---------------------------------------------------------------------------------
def limb_euler_deg(v):
    """Euler XYZ (graus, convenção do Blender: R = Rz·Ry·Rx) que leva o eixo +Z da peça até a direção `v`."""
    z = unit(v)
    ref = (0.0, 1.0, 0.0) if abs(z[1]) < 0.9 else (1.0, 0.0, 0.0)
    x = unit(cross(ref, z))
    y = cross(z, x)
    # colunas da matriz de rotação: x, y, z  =>  R[linha][coluna]
    r = ((x[0], y[0], z[0]), (x[1], y[1], z[1]), (x[2], y[2], z[2]))
    b = math.asin(max(-1.0, min(1.0, -r[2][0])))
    if abs(math.cos(b)) > 1e-6:
        a = math.atan2(r[2][1], r[2][2])
        c = math.atan2(r[1][0], r[0][0])
    else:                                                  # gimbal lock: fixa o giro em Z
        a = math.atan2(-r[1][2], r[1][1])
        c = 0.0
    return (math.degrees(a), math.degrees(b), math.degrees(c))


def apply_euler_deg(euler, v):
    """Rz·Ry·Rx aplicado a `v` (verificação dos testes e uso em cálculos de pose)."""
    a, b, c = (math.radians(e) for e in euler)
    x, y, z = v
    y, z = y * math.cos(a) - z * math.sin(a), y * math.sin(a) + z * math.cos(a)          # Rx
    x, z = x * math.cos(b) + z * math.sin(b), -x * math.sin(b) + z * math.cos(b)         # Ry
    x, y = x * math.cos(c) - y * math.sin(c), x * math.sin(c) + y * math.cos(c)          # Rz
    return (x, y, z)


# ---- poses ----------------------------------------------------------------------------------------------------------------------------
def _arm(side, shoulder, wrist_target, pole):
    s = SIDES[side]
    elbow, wrist = two_bone_ik(shoulder, wrist_target, UPPER, FORE, (s * pole[0], pole[1], pole[2]))
    return elbow, wrist


def _leg(side, hip, ankle_target, pole=(0.0, 1.0, 0.0)):
    return two_bone_ik(hip, ankle_target, THIGH, SHIN, pole)


def standing_pose():
    """Em pé: braços caídos com leve flexão, pernas retas com os joelhos um pouco à frente."""
    pose = {"pelvis_z": STAND_HIP_Z, "spine_z": STAND_HIP_Z + 0.04, "torso_z": 1.0, "shoulder_z": STAND_SHOULDER_Z,
            "neck_z": 1.38, "joints": {}}
    for side, s in SIDES.items():
        hip = (s * 0.11, 0.0, STAND_HIP_Z)
        knee, ankle = _leg(side, hip, (s * 0.11, 0.0, ANKLE_H))
        shoulder = (s * 0.29, 0.0, STAND_SHOULDER_Z)
        elbow, wrist = _arm(side, shoulder, (s * 0.31, 0.05, 0.76), (0.0, 1.0, -0.2))
        pose["joints"][side] = {"hip": hip, "knee": knee, "ankle": ankle, "shoulder": shoulder, "elbow": elbow, "wrist": wrist}
    return pose


def seated_pose(grip="rest", wheel=None):
    """Sentado: coxas sobre a almofada, canelas quase verticais, pés no piso.

    grip: "wheel" (mãos no volante, `wheel` = centro do volante no referencial da figura), "lap" (mãos sobre a
    mochila no colo) ou "rest" (mãos sobre as coxas).
    """
    pose = {"pelvis_z": SEAT_HIP_Z, "spine_z": SEAT_HIP_Z + 0.04, "torso_z": 0.35, "shoulder_z": SEAT_SHOULDER_Z,
            "neck_z": 0.78, "joints": {}}
    for side, s in SIDES.items():
        hip = (s * 0.11, 0.0, SEAT_HIP_Z)
        knee, ankle = _leg(side, hip, (s * 0.12, 0.50, SEAT_FLOOR_Z + ANKLE_H), pole=(0.0, 1.0, 1.0))
        shoulder = (s * 0.29, 0.0, SEAT_SHOULDER_Z)
        if grip == "wheel":
            if wheel is None:
                raise ValueError("grip='wheel' precisa do centro do volante")
            target = (s * 0.17, wheel[1] - 0.04, wheel[2] + 0.02)
        elif grip == "lap":
            target = (s * 0.10, 0.25, 0.40)
        else:
            target = (s * 0.15, 0.30, 0.18)
        elbow, wrist = _arm(side, shoulder, target, (0.6, -0.3, -1.0))
        pose["joints"][side] = {"hip": hip, "knee": knee, "ankle": ankle, "shoulder": shoulder, "elbow": elbow, "wrist": wrist}
    return pose
