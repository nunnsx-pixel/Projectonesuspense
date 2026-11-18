"""Adereços e figuras low-poly: mãos (POV), celular, mochila (objeto âncora), motorista, passageiros."""
from __future__ import annotations

from . import kit, materials

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


def figure(name, parent, loc=(0, 0, 0), heading=0.0, coat=(0.05, 0.05, 0.06), skin=SKIN, cap=False, seated=False,
           eyes=False, shirt=None, hoodie=False, decay=False, bag=None):
    """Figura humana low-poly. Origem nos pés (ou no quadril se sentada); +Y = frente.

    shirt   variante de `camisa-social` (blender/materials.json): camisa social azul amarrotada no lugar de `coat`.
    hoodie  moletom com capuz e bolso canguru (o do protagonista; `coat` = HOODIE). `decay`: mofo e rasgos.
    bag     None | "back" (mochila nas costas, em pé) | "lap" (mochila no colo, sentado): a MESMA mochila preta com crachá.
    eyes    olhos brancos, sorriso esticado e MANDÍBULA (`mandibula`) que o episódio pode esticar ao virar o pescoço.
    """
    M = kit.mat
    r = kit.empty(name, loc, parent=parent, rot=(0, 0, -heading))
    h0 = 0.0 if not seated else 0.0
    cloth = materials.get("camisa-social", shirt) if shirt else M(f"roupa-{coat}", coat)
    zt, zs, zn = (h0 + 1.0, h0 + 1.28, h0 + 1.38) if not seated else (0.35, 0.68, 0.78)
    kit.box("tronco", (0.46, 0.26, 0.62), (0, 0, zt), cloth, parent=r)
    kit.box("ombros", (0.52, 0.2, 0.14), (0, 0, zs), cloth, parent=r)
    if hoodie:                                  # moletom: bolso canguru na frente, capuz caído atrás do pescoço
        kit.box("bolso-canguru", (0.34, 0.03, 0.15), (0, 0.145, zt - 0.2), cloth, parent=r)
        kit.box("capuz", (0.30, 0.15, 0.17), (0, -0.14, zn - 0.04), cloth, parent=r)
        if decay:                               # mofo preto-esverdeado e um rasgo no ombro
            rot = M("moletom-mofo", (0.025, 0.04, 0.025))
            for k, (x, z, w, hh) in enumerate(((-0.12, zt + 0.05, 0.14, 0.12), (0.1, zt - 0.14, 0.12, 0.10), (0.13, zs, 0.1, 0.06))):
                kit.box(f"mofo-moletom-{k}", (w, 0.012, hh), (x, 0.135, z), rot, parent=r)
            kit.box("rasgo-ombro", (0.12, 0.215, 0.02), (-0.15, 0.0, zs + 0.02), M("rasgo", (0.015, 0.012, 0.012)), rot=(0, 15, 0), parent=r)
    neck = kit.empty("pescoco", (0, 0, zn), parent=r)
    head = kit.empty("cabeca", (0, 0, 0.1), parent=neck)
    kit.ball("crânio", 0.115, (0, 0, 0), M(f"pele-{skin}", skin), parent=head, squash=(0.9, 1.0, 1.1))
    if cap:
        kit.box("bone", (0.26, 0.28, 0.07), (0, 0.04, 0.09), M("bone", (0.03, 0.03, 0.05)), parent=head)
        kit.box("aba", (0.2, 0.12, 0.015), (0, 0.17, 0.075), M("bone", (0.03, 0.03, 0.05)), parent=head)
    if eyes:                                    # olhos completamente brancos, sem pupila
        white = M("olho-branco", (1, 1, 1), emit=4.0)
        for s in (-1, 1):
            kit.ball("olho", 0.022, (s * 0.04, 0.1, 0.02), white, parent=head)
        sm = kit.box("sorriso", (0.11, 0.01, 0.012), (0, 0.11, -0.05), M("sorriso", (0.9, 0.9, 0.85), emit=1.5), parent=head)
        jaw = kit.box("mandibula", JAW_SIZE, JAW_LOC, M(f"pele-{skin}", skin), parent=head)
    if not seated:
        for s in (-1, 1):
            kit.box("perna", (0.17, 0.2, 0.9), (s * 0.12, 0, h0 + 0.45), M(f"roupa-{coat}", coat), parent=r)
            kit.box("braço", (0.1, 0.1, 0.6), (s * 0.31, 0, h0 + 1.0), cloth, parent=r)
    if bag == "back":                           # alças voltadas para o tronco: a mochila de costas
        backpack(f"mochila-{name}", r, dusty=decay, loc=(0, -0.235, h0 + 0.82), rot=(0, 0, 180))
    elif bag == "lap":
        backpack(f"mochila-{name}", r, dusty=decay, loc=(0, 0.26, 0.02))
    out = {"root": r, "neck": neck, "head": head}
    if eyes:
        out.update(jaw=jaw, smile=sm)
    return out


JAW_SIZE, JAW_LOC = (0.15, 0.11, 0.05), (0.0, 0.05, -0.095)      # mandíbula em repouso (cabeça = origem em `cabeca`)


def stretch_jaw(env, fig, keys):
    """Estica a mandíbula (e leva o sorriso junto) ao virar o pescoço: keys = [(tempo_s, fator)] (1 = repouso).
    Alonga em -Z mantendo o topo preso ao crânio, então a boca "desce" como a de um boneco desencaixado."""
    jaw, smile = fig["jaw"], fig["smile"]
    sx, sy, sz = JAW_SIZE
    x, y, z = JAW_LOC
    with kit.interp("BEZIER"):
        for t, k in keys:
            f = env.f(t)
            kit.key(jaw, "scale", f, (sx, sy, sz * k))
            kit.key(jaw, "location", f, (x, y, z - sz * (k - 1) / 2))
            kit.key(smile, "location", f, (0, 0.11, -0.05 - sz * (k - 1) * 0.9))


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
