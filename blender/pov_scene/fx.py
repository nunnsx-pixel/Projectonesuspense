"""Efeitos de tela como GEOMETRIA na frente da câmera, ligados às propriedades do CSV por drivers.

Evita o compositor (a API mudou entre Blender 4.x e 5.x): vinheta, pálpebras e tela preta funcionam em
qualquer versão e em qualquer render. `edge_blur` (blur de borda) NÃO é desenhado: fica como propriedade
da câmera para você ligar no compositor/pós.
"""
from __future__ import annotations

from . import kit

DIST = 0.20                       # distância dos planos à câmera (m)
H = 0.168                         # meia-altura visível a essa distância (FOV vertical 80°)
ASPECT = 9 / 16


def _overlay_mat(name: str, radial: bool):
    """Material preto com alfa = valor do nó `A` (o driver escreve nele); radial = só nas bordas."""
    if name in kit._MATS:
        return kit._MATS[name]
    import bpy
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    mix = nt.nodes.new("ShaderNodeMixShader")
    clear = nt.nodes.new("ShaderNodeBsdfTransparent")
    black = nt.nodes.new("ShaderNodeEmission")
    black.inputs["Color"].default_value = (0, 0, 0, 1)
    a = nt.nodes.new("ShaderNodeValue")
    a.name = "A"
    a.outputs[0].default_value = 0.0
    nt.links.new(clear.outputs[0], mix.inputs[1])
    nt.links.new(black.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    if radial:
        uv = nt.nodes.new("ShaderNodeTexCoord")
        sub = nt.nodes.new("ShaderNodeVectorMath")
        sub.operation = "SUBTRACT"
        sub.inputs[1].default_value = (0.5, 0.5, 0.0)
        ln = nt.nodes.new("ShaderNodeVectorMath")
        ln.operation = "LENGTH"
        rng = nt.nodes.new("ShaderNodeMapRange")
        rng.inputs["From Min"].default_value = 0.18
        rng.inputs["From Max"].default_value = 0.62
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        nt.links.new(uv.outputs["UV"], sub.inputs[0])
        nt.links.new(sub.outputs[0], ln.inputs[0])
        nt.links.new(ln.outputs["Value"], rng.inputs["Value"])
        nt.links.new(rng.outputs["Result"], mul.inputs[0])
        nt.links.new(a.outputs[0], mul.inputs[1])
        nt.links.new(mul.outputs[0], mix.inputs[0])
    else:
        nt.links.new(a.outputs[0], mix.inputs[0])
    kit._MATS[name] = m
    return m


def _ghost(ob):
    for attr in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter"):
        if hasattr(ob, attr):
            setattr(ob, attr, False)


def build(cam):
    """Cria vinheta, pálpebras e preto como filhos da câmera e liga aos canais `vignette`, `eyelid`, `black`."""
    w, h = 2 * H * ASPECT * 1.15, 2 * H * 1.15
    vig = kit.plane("fx-vinheta", (w, h), (0, 0, -DIST), _overlay_mat("fx-vinheta", True), parent=cam)
    kit.driver(vig.active_material.node_tree, 'nodes["A"].outputs[0].default_value', "v", cam, "vignette")
    lids = []
    for name, s in (("fx-palpebra-cima", 1), ("fx-palpebra-baixo", -1)):
        m = _overlay_mat(name, False)
        kit.driver(m.node_tree, 'nodes["A"].outputs[0].default_value', "1", cam, "eyelid")   # sempre opaca
        lid = kit.plane(name, (w, 0.24), (0, s * 0.30, -DIST + 0.002), m, parent=cam)
        kit.driver(lid, "location", f"{s}*(0.30-0.19*v)", cam, "eyelid", index=1)
        lids.append(lid)
    blk = kit.plane("fx-preto", (w, h), (0, 0, -DIST + 0.004), _overlay_mat("fx-preto", False), parent=cam)
    kit.driver(blk.active_material.node_tree, 'nodes["A"].outputs[0].default_value', "v", cam, "black")
    for ob in (vig, blk, *lids):
        _ghost(ob)
    return {"vignette": vig, "lids": lids, "black": blk}
