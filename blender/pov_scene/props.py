"""Adereços e figuras low-poly: mãos (POV), celular, mochila (objeto âncora), motorista, passageiros."""
from __future__ import annotations

import math

from . import kit, layout as L, materials, rig

SKIN = (0.55, 0.36, 0.28)
GREY_SKIN = (0.36, 0.38, 0.36)
HOODIE = (0.07, 0.07, 0.09)                 # moletom do protagonista: a manga do POV, o duplo e a silhueta usam esta MESMA cor
HOODIE_ROT = (0.10, 0.11, 0.13)             # o mesmo moletom em decomposição (mofo, rasgos): um pouco mais claro e desbotado


def hand(name, parent, left=True, skin=SKIN, sleeve=HOODIE):
    """Mão apontando para -Z (para a frente da câmera, se `parent` for a câmera)."""
    s = -1 if left else 1
    r = kit.empty(name, parent=parent)
    M = kit.mat
    kit.box("palma", (0.085, 0.03, 0.09), (0, 0, 0), M(f"pele-{skin}", skin), parent=r)
    kit.box("dedos", (0.08, 0.026, 0.07), (0, 0, -0.075), M(f"pele-{skin}", skin), parent=r)
    kit.box("polegar", (0.03, 0.024, 0.06), (-s * 0.05, 0, -0.025), M(f"pele-{skin}", skin), rot=(0, s * 25, 0), parent=r)
    kit.box("manga", (0.07, 0.06, 0.26), (0, 0.005, 0.17), M(f"manga-{sleeve}", sleeve), parent=r)
    return r


def phone(name, parent, lines, crack=True):
    """Celular (tela acesa) com linhas de texto; `lines` = [(texto, tamanho, y)]."""
    M = kit.mat
    r = kit.empty(name, parent=parent)
    kit.box("corpo", (0.072, 0.15, 0.008), (0, 0, 0), M("celular", (0.02, 0.02, 0.025)), parent=r)
    screen = M("tela-celular", (0.7, 0.85, 1.0), emit=1.4)
    kit.plane("tela", (0.064, 0.138), (0, 0, 0.0046), screen, parent=r)
    txt = M("texto-celular", (0.02, 0.02, 0.03), emit=0.0)
    for k, (body, size, y) in enumerate(lines):
        kit.text(f"txt-{k}", body, size, (0, y, 0.0052), txt, parent=r)
    if crack:                                   # tela rachada: três riscos escuros
        c = M("rachadura", (0.01, 0.01, 0.012))
        for k, (x0, y0, rz, ln) in enumerate(((0.008, 0.03, 25, 0.045), (-0.012, -0.015, -40, 0.04), (0.015, -0.035, 70, 0.03))):
            kit.box(f"rachadura-{k}", (ln, 0.0016, 0.0006), (x0, y0, 0.0055), c, rot=(0, 0, rz), parent=r)
    return r


def backpack(name, parent, dusty=False, loc=(0, 0, 0), rot=(0, 0, 0)):
    """Mochila preta de estudante com crachá/chaveiro (objeto âncora da série)."""
    M = kit.mat
    r = kit.empty(name, loc, parent=parent, rot=rot)
    body = M("mochila", (0.02, 0.02, 0.025) if not dusty else (0.16, 0.16, 0.15), rough=0.95)
    kit.box("corpo", (0.30, 0.17, 0.42), (0, 0, 0.21), body, parent=r)
    kit.box("bolso", (0.26, 0.07, 0.22), (0, 0.11, 0.14), body, parent=r)
    for s in (-1, 1):
        kit.box("alça", (0.04, 0.03, 0.34), (s * 0.09, -0.1, 0.22), M("alca", (0.03, 0.03, 0.035)), parent=r)
    kit.box("cracha", (0.065, 0.004, 0.09), (0.12, 0.12, 0.2), M("cracha", (0.9, 0.9, 0.85)), rot=(0, 0, 15), parent=r)
    kit.box("cracha-faixa", (0.065, 0.005, 0.02), (0.12, 0.123, 0.235), M("cracha-faixa", (0.05, 0.2, 0.6)), rot=(0, 0, 15), parent=r)
    kit.cyl("chaveiro", 0.012, 0.025, (0.15, 0.1, 0.14), M("chaveiro", (0.7, 0.55, 0.1), rough=0.3), parent=r)
    if dusty:                                   # poeira cinza grossa + teias de aranha secas
        kit.box("poeira", (0.31, 0.18, 0.025), (0, 0, 0.43), M("poeira", (0.45, 0.45, 0.43)), parent=r)
        web = M("teia", (0.8, 0.8, 0.78))
        for k, (x, z, ln, rz) in enumerate(((0.1, 0.38, 0.22, 35), (-0.12, 0.3, 0.2, -50), (0.0, 0.43, 0.3, 8), (0.14, 0.2, 0.16, 70))):
            kit.box(f"teia-{k}", (ln, 0.002, 0.002), (x, 0.0, z), web, rot=(0, 0, rz), parent=r)
    return r


PANTS, PANTS_ROT = (0.05, 0.055, 0.075), (0.07, 0.08, 0.09)       # calça jeans escura; a mesma, desbotada
JAW_SIZE, JAW_LOC = (0.15, 0.11, 0.05), (0.0, 0.05, -0.095)         # mandíbula em repouso (referencial da cabeça)
SKULL_R, SKULL_SQUASH = 0.115, (0.9, 1.0, 1.1)


def _limb(name, joint, joint_pos, a, b, width, material):
    """Peça (caixa) de `a` até `b`, filha da junta `joint` (que está em `joint_pos`); os eixos das juntas são os da figura."""
    v = rig.sub(b, a)
    mid = rig.mul(rig.add(a, b), 0.5)
    return kit.box(name, (width, width * 0.9, rig.length(v)), rig.sub(mid, joint_pos), material,
                   rot=rig.limb_euler_deg(v), parent=joint)


def _skull_patch(name, u, size, material, parent, depth=0.005):
    """Mancha rente à superfície do crânio (elipsoide) na direção `u` a partir do centro: acompanha a curvatura, sem
    nada saltando acima do couro cabeludo (não pode parecer cabelo). `size` = (largura, comprimento, espessura)."""
    a, b, c = (SKULL_R * k for k in SKULL_SQUASH)
    u = rig.unit(u)
    k = 1.0 / math.sqrt((u[0] / a) ** 2 + (u[1] / b) ** 2 + (u[2] / c) ** 2)
    p = (u[0] * k, u[1] * k, u[2] * k)
    n = (p[0] / a ** 2, p[1] / b ** 2, p[2] / c ** 2)
    p = rig.sub(p, rig.mul(rig.unit(n), depth))
    return kit.box(name, size, p, material, rot=rig.limb_euler_deg(n), parent=parent)


def _bald_head(head, skin, decay, eyes):
    """Cabeça CALVA: crânio liso e brilhante, orelhas, nenhuma peça acima do couro cabeludo (sem cabelo, sobrancelha ou barba).
    Com `decay`: órbitas escuras, bochechas fundas, nariz aberto, couro solto, rachadura no crânio e dentes à mostra."""
    M = kit.mat
    skull = kit.ball("crânio", SKULL_R, (0, 0, 0), M(f"cranio-calvo-{skin}", skin, rough=0.32), parent=head, squash=SKULL_SQUASH)
    head["calvo"] = True
    skin_m = M(f"pele-{skin}", skin)
    for s in (-1, 1):
        kit.ball("orelha", 0.03, (s * 0.103, -0.005, -0.01), skin_m, parent=head, squash=(0.35, 0.8, 1.3))
    if decay:
        dark = M("decomposicao-escura", (0.02, 0.025, 0.012), rough=0.95)
        rot = M(f"couro-solto-{skin}", tuple(min(1.0, c * 1.35 + 0.015) for c in skin), rough=0.8)   # a própria pele, só mais pálida
        if not eyes:                                                     # órbitas vazias
            for s in (-1, 1):
                kit.ball("orbita", 0.027, (s * 0.04, 0.097, 0.02), dark, parent=head, squash=(1.0, 0.45, 1.1))
        for s in (-1, 1):                                                # bochechas fundas
            kit.ball("bochecha-funda", 0.03, (s * 0.062, 0.088, -0.035), dark, parent=head, squash=(0.9, 0.5, 1.3))
        kit.box("nariz-aberto", (0.03, 0.012, 0.035), (0, 0.112, -0.012), dark, rot=(15, 0, 0), parent=head)
        _skull_patch("rachadura-cranio", (0.05, 0.0, 1.0), (0.012, 0.10, 0.004), dark, head)       # fissura rente ao crânio
        _skull_patch("couro-solto", (-0.45, -0.25, 1.0), (0.055, 0.04, 0.006), rot, head)            # couro descolado, achatado
        _skull_patch("couro-solto", (0.6, 0.35, 0.8), (0.04, 0.03, 0.006), rot, head)
    return skull


def figure(name, parent, loc=(0, 0, 0), heading=0.0, coat=(0.05, 0.05, 0.06), skin=SKIN, cap=False, seated=False,
           eyes=False, shirt=None, hoodie=False, decay=False, bag=None, bald=False, grip="rest", pants=PANTS):
    """Figura humana de CORPO INTEIRO com esqueleto (juntas de verdade). Origem nos pés (ou no quadril se sentada); +Y = frente.

    Hierarquia:  figura -> quadril -> coluna -> {pescoço -> cabeça -> (crânio, mandíbula...), ombro -> cotovelo -> punho -> mão}
                            quadril -> {quadril-L/R -> joelho -> tornozelo -> pé};  o capuz, a mochila etc. ficam na coluna.
    shirt   variante de `camisa-social` (blender/materials.json): camisa social azul amarrotada no lugar de `coat`.
    hoodie  moletom com capuz caído e bolso canguru (`coat` = HOODIE). `decay`: mofo, rasgos e (se `bald`) rosto em decomposição.
    bag     None | "back" (mochila nas costas, em pé) | "lap" (mochila no colo, sentado): a MESMA mochila preta com crachá.
    bald    cabeça calva: crânio liso, sem cabelo (o passageiro do fundo / o Duplo).
    eyes    olhos brancos sem pupila e sorriso esticado; com `eyes` ou `bald` há MANDÍBULA (`mandibula`) animável.
    grip    sentado: "wheel" (mãos no volante), "lap" (mãos na mochila do colo) ou "rest" (mãos nas coxas).
    """
    M = kit.mat
    pose = rig.seated_pose(grip, L.WHEEL_REL) if seated else rig.standing_pose()
    r = kit.empty(name, loc, parent=parent, rot=(0, 0, -heading))
    cloth = materials.get("camisa-social", shirt) if shirt else M(f"roupa-{coat}", coat)
    pant_m = M(f"calca-{pants}", pants)
    skin_m = M(f"pele-{skin}", skin)
    shoe_m = M("sapato", (0.02, 0.02, 0.022))
    J = pose["joints"]

    def at(p, origin):                                   # posição no referencial de uma junta que está em `origin`
        return rig.sub(p, origin)

    pelvis_pos = (0.0, 0.0, pose["pelvis_z"])
    quad = kit.empty("quadril", pelvis_pos, parent=r)
    kit.box("pelve", (0.34, 0.22, 0.22), (0, 0, 0.0), pant_m, parent=quad)
    spine_pos = (0.0, 0.0, pose["spine_z"])
    spine = kit.empty("coluna", at(spine_pos, pelvis_pos), parent=quad)
    zt, zs, zn = pose["torso_z"], pose["shoulder_z"] + 0.02, pose["neck_z"]
    kit.box("tronco", (0.46, 0.26, 0.62), at((0, 0, zt), spine_pos), cloth, parent=spine)
    kit.box("ombros", (0.52, 0.2, 0.14), at((0, 0, zs), spine_pos), cloth, parent=spine)
    if hoodie:                                           # moletom: bolso canguru na frente, capuz caído atrás do pescoço
        kit.box("bolso-canguru", (0.34, 0.03, 0.15), at((0, 0.145, zt - 0.2), spine_pos), cloth, parent=spine)
        kit.box("capuz", (0.30, 0.15, 0.17), at((0, -0.14, zn - 0.04), spine_pos), cloth, parent=spine)
        if decay:                                        # mofo preto-esverdeado e um rasgo no ombro
            mofo = M("moletom-mofo", (0.025, 0.04, 0.025))
            for k, (x, z, w, hh) in enumerate(((-0.12, zt + 0.05, 0.14, 0.12), (0.1, zt - 0.14, 0.12, 0.10), (0.13, zs, 0.1, 0.06))):
                kit.box(f"mofo-moletom-{k}", (w, 0.012, hh), at((x, 0.135, z), spine_pos), mofo, parent=spine)
            kit.box("rasgo-ombro", (0.12, 0.215, 0.02), at((-0.15, 0.0, zs + 0.02), spine_pos), M("rasgo", (0.015, 0.012, 0.012)),
                    rot=(0, 15, 0), parent=spine)

    # ---- pescoço e cabeça -----------------------------------------------------------------------------------------------
    neck = kit.empty("pescoco", at((0, 0, zn), spine_pos), parent=spine)
    head = kit.empty("cabeca", (0, 0, 0.1), parent=neck)
    out = {"root": r, "pelvis": quad, "spine": spine, "neck": neck, "head": head, "joints": {}}
    if bald:
        _bald_head(head, skin, decay, eyes)
    else:
        kit.ball("crânio", SKULL_R, (0, 0, 0), skin_m, parent=head, squash=SKULL_SQUASH)
    if cap:
        kit.box("bone", (0.26, 0.28, 0.07), (0, 0.04, 0.09), M("bone", (0.03, 0.03, 0.05)), parent=head)
        kit.box("aba", (0.2, 0.12, 0.015), (0, 0.17, 0.075), M("bone", (0.03, 0.03, 0.05)), parent=head)
    if eyes:                                             # olhos completamente brancos, sem pupila
        white = M("olho-branco", (1, 1, 1), emit=4.0)
        for s in (-1, 1):
            kit.ball("olho", 0.022, (s * 0.04, 0.1, 0.02), white, parent=head)
        out["smile"] = kit.box("sorriso", (0.11, 0.01, 0.012), (0, 0.11, -0.05), M("sorriso", (0.9, 0.9, 0.85), emit=1.5), parent=head)
    if eyes or bald:
        bone = M("osso", (0.72, 0.69, 0.58), rough=0.55)
        out["jaw"] = kit.box("mandibula", JAW_SIZE, JAW_LOC, bone if (bald and decay) else skin_m, parent=head)
        if bald and decay:                               # dentes à mostra
            kit.box("dentes", (0.095, 0.012, 0.014), (0, 0.108, -0.066), bone, parent=head)

    # ---- braços e pernas (cada um é uma cadeia de juntas) -----------------------------------------------------------------------
    joints = out["joints"]
    joints.update(quadril=quad, coluna=spine)
    for side, s in rig.SIDES.items():
        j = J[side]
        sh = kit.empty(f"ombro-{side}", at(j["shoulder"], spine_pos), parent=spine)
        _limb(f"braco-sup-{side}", sh, j["shoulder"], j["shoulder"], j["elbow"], 0.085, cloth)
        el = kit.empty(f"cotovelo-{side}", at(j["elbow"], j["shoulder"]), parent=sh)
        _limb(f"antebraco-{side}", el, j["elbow"], j["elbow"], j["wrist"], 0.07, cloth)
        wr = kit.empty(f"punho-{side}", at(j["wrist"], j["elbow"]), parent=el)
        fdir = rig.unit(rig.sub(j["wrist"], j["elbow"]))
        hand_c = rig.add(j["wrist"], rig.mul(fdir, rig.HAND / 2))
        kit.box(f"palma-{side}", (0.085, 0.035, rig.HAND), at(hand_c, j["wrist"]), skin_m, rot=rig.limb_euler_deg(fdir), parent=wr)
        hp = kit.empty(f"quadril-{side}", at(j["hip"], pelvis_pos), parent=quad)
        _limb(f"coxa-{side}", hp, j["hip"], j["hip"], j["knee"], 0.15, pant_m)
        kn = kit.empty(f"joelho-{side}", at(j["knee"], j["hip"]), parent=hp)
        _limb(f"canela-{side}", kn, j["knee"], j["knee"], j["ankle"], 0.11, pant_m)
        an = kit.empty(f"tornozelo-{side}", at(j["ankle"], j["knee"]), parent=kn)
        kit.box(f"pe-{side}", (0.10, 0.26, 0.07), (0.0, 0.07, -0.045), shoe_m, parent=an)
        joints.update({f"ombro_{side}": sh, f"cotovelo_{side}": el, f"punho_{side}": wr,
                       f"quadril_{side}": hp, f"joelho_{side}": kn, f"tornozelo_{side}": an})

    # ---- mochila ------------------------------------------------------------------------------------------------------------
    if bag == "back":                                    # alças voltadas para o tronco: a mochila de costas
        backpack(f"mochila-{name}", spine, dusty=decay, loc=at((0, -0.235, pose["shoulder_z"] - 0.46), spine_pos), rot=(0, 0, 180))
    elif bag == "lap":
        backpack(f"mochila-{name}", r, dusty=decay, loc=(0, 0.26, 0.02))
    return out


def stretch_jaw(env, fig, keys):
    """Estica a mandíbula (e leva o sorriso junto, se houver) ao virar o pescoço: keys = [(tempo_s, fator)] (1 = repouso).
    Alonga em -Z mantendo o topo preso ao crânio, então a boca "desce" como a de um boneco desencaixado."""
    jaw, smile = fig["jaw"], fig.get("smile")
    sx, sy, sz = JAW_SIZE
    x, y, z = JAW_LOC
    with kit.interp("BEZIER"):
        for t, k in keys:
            f = env.f(t)
            kit.key(jaw, "scale", f, (sx, sy, sz * k))
            kit.key(jaw, "location", f, (x, y, z - sz * (k - 1) / 2))
            if smile is not None:
                kit.key(smile, "location", f, (0, 0.11, -0.05 - sz * (k - 1) * 0.9))


def walk_cycle(env, fig, t0, t1, period=0.56, hip_deg=28.0, arm_deg=20.0):
    """Marcha simples (quadris e ombros em contrafase) entre t0 e t1; volta à pose neutra no fim."""
    j = fig["joints"]
    half = period / 2
    n = max(1, int(round((t1 - t0) / half)))
    with kit.interp("BEZIER"):
        for name in ("quadril_esq", "quadril_dir", "ombro_esq", "ombro_dir"):
            kit.key(j[name], "rotation_euler", env.f(t0 - 0.1), (0.0, 0.0, 0.0))
        for k in range(n):
            t = t0 + k * (t1 - t0) / n
            sg = 1.0 if k % 2 == 0 else -1.0
            for name, amp in (("quadril_esq", hip_deg), ("quadril_dir", -hip_deg), ("ombro_esq", -arm_deg), ("ombro_dir", arm_deg)):
                kit.key(j[name], "rotation_euler", env.f(t), (math.radians(sg * amp), 0.0, 0.0))
        for name in ("quadril_esq", "quadril_dir", "ombro_esq", "ombro_dir"):
            kit.key(j[name], "rotation_euler", env.f(t1 + 0.3), (0.0, 0.0, 0.0))


def cam_hand(cam, name, left=True, skin=SKIN, sleeve=(0.07, 0.07, 0.09), tremor=0.0035):
    """Mão presa à câmera (POV): grupo animável + tremor por driver. Devolve (grupo, tremor, mão)."""
    grp = kit.empty(name, parent=cam)
    trem = kit.empty(name + "-tremor", parent=grp)
    k = 1.2 + 0.13 * (hash(name) % 7)
    kit.frame_driver(trem, "location", f"{tremor}*sin(frame*{k:.2f})", index=0)
    kit.frame_driver(trem, "location", f"{tremor * 0.85}*sin(frame*{k * 0.83:.2f}+1.0)", index=1)
    return grp, trem, hand(name + "-mao", trem, left, skin, sleeve)


def reach_keys(env, grp, seq):
    """seq = [(tempo_s, (x, y, z)), ...] em espaço de câmera; interpolação suave."""
    with kit.interp("BEZIER"):
        for t, pos in seq:
            kit.key(grp, "location", env.f(t), pos)
