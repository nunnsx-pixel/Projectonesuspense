"""Adereços e figuras low-poly: mãos (POV), celular, mochila (objeto âncora), motorista, passageiros."""
from __future__ import annotations

from . import kit

SKIN = (0.55, 0.36, 0.28)
GREY_SKIN = (0.36, 0.38, 0.36)


def hand(name, parent, left=True, skin=SKIN, sleeve=(0.07, 0.07, 0.09)):
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
           eyes=False):
    """Figura humana low-poly. Origem nos pés (ou no quadril se sentada); +Y = frente."""
    M = kit.mat
    r = kit.empty(name, loc, parent=parent, rot=(0, 0, -heading))
    h0 = 0.0 if not seated else 0.0
    kit.box("tronco", (0.46, 0.26, 0.62), (0, 0, h0 + 1.0 if not seated else 0.35), M(f"roupa-{coat}", coat), parent=r)
    kit.box("ombros", (0.52, 0.2, 0.14), (0, 0, h0 + 1.28 if not seated else 0.68), M(f"roupa-{coat}", coat), parent=r)
    neck = kit.empty("pescoco", (0, 0, h0 + 1.38 if not seated else 0.78), parent=r)
    head = kit.empty("cabeca", (0, 0, 0.1), parent=neck)
    kit.ball("crânio", 0.115, (0, 0, 0), M(f"pele-{skin}", skin), parent=head, squash=(0.9, 1.0, 1.1))
    if cap:
        kit.box("bone", (0.26, 0.28, 0.07), (0, 0.04, 0.09), M("bone", (0.03, 0.03, 0.05)), parent=head)
        kit.box("aba", (0.2, 0.12, 0.015), (0, 0.17, 0.075), M("bone", (0.03, 0.03, 0.05)), parent=head)
    if eyes:                                    # olhos completamente brancos, sem pupila
        white = M("olho-branco", (1, 1, 1), emit=4.0)
        for s in (-1, 1):
            kit.ball("olho", 0.022, (s * 0.04, 0.1, 0.02), white, parent=head)
        kit.box("sorriso", (0.11, 0.01, 0.012), (0, 0.11, -0.05), M("sorriso", (0.9, 0.9, 0.85), emit=1.5), parent=head)
    if not seated:
        for s in (-1, 1):
            kit.box("perna", (0.17, 0.2, 0.9), (s * 0.12, 0, h0 + 0.45), M(f"roupa-{coat}", coat), parent=r)
            kit.box("braço", (0.1, 0.1, 0.6), (s * 0.31, 0, h0 + 1.0), M(f"roupa-{coat}", coat), parent=r)
    return {"root": r, "neck": neck, "head": head}


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
