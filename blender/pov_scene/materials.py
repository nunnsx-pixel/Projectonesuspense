"""Materiais PBR da série (blender/materials.json): procedurais por padrão, mapas de imagem quando existirem.

  materials.get("metal-enferrujado", "enferrujado")     -> material (cacheado)

Se existir um conjunto em  blender/textures/<id>/[<variante>/]{albedo,roughness,metallic,ao,height,normal}.{png,jpg,exr}
ele é usado no lugar do procedural (mapeamento em caixa, em metros: ver blender/TEXTURAS.md).

Espaço de coordenadas: 'bus' prende a textura ao ônibus (ele anda ~800 m; coordenadas de mundo a fariam "nadar");
'world' serve ao cenário fixo. Funciona no Blender 4.2 LTS e 5.x (usa só nós estáveis entre as versões).
"""
from __future__ import annotations

import json
from pathlib import Path

import bpy

from . import kit

BLENDER_DIR = Path(__file__).resolve().parents[1]
MANIFEST_PATH = BLENDER_DIR / "materials.json"
TEXTURES_DIR = BLENDER_DIR / "textures"
MAPS = ("albedo", "roughness", "metallic", "ao", "height", "normal")
EXTS = ("png", "jpg", "jpeg", "exr")

_S: dict = {"bus": None, "textures": TEXTURES_DIR, "cache": {}, "manifest": None}


# ---- manifesto / configuração ---------------------------------------------------------------------------
def manifest() -> dict:
    if _S["manifest"] is None:
        _S["manifest"] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return _S["manifest"]


def configure(bus_root=None, textures_dir=None):
    _S["bus"] = bus_root
    _S["textures"] = Path(textures_dir) if textures_dir else TEXTURES_DIR


def reset():
    _S["cache"].clear()
    _S["bus"] = None
    _S["textures"] = TEXTURES_DIR


def params(mat_id: str, variant: str | None = None) -> dict:
    spec = manifest()["materials"][mat_id]
    p = dict(spec["procedural"])
    variants = spec.get("variants", {})
    variant = variant or (next(iter(variants)) if variants else None)
    if variant is not None:
        if variant not in variants:
            raise KeyError(f"{mat_id}: variante {variant!r} inexistente (há {list(variants)})")
        p.update(variants[variant])
    return p


def find_maps(mat_id: str, variant: str | None = None) -> dict[str, Path]:
    """Mapas de imagem disponíveis: textures/<id>/<variante>/<mapa>.<ext> (ou textures/<id>/<mapa>.<ext>)."""
    base = _S["textures"] / mat_id
    found: dict[str, Path] = {}
    for folder in ([base / variant] if variant else []) + [base]:
        for m in MAPS:
            if m in found:
                continue
            for ext in EXTS:
                f = folder / f"{m}.{ext}"
                if f.is_file():
                    found[m] = f
                    break
    return found


# ---- nós auxiliares ------------------------------------------------------------------------------------------------
def _sock(node, ident: str, inputs=True):
    return next(s for s in (node.inputs if inputs else node.outputs) if s.identifier == ident)


class _B:
    """Construtor de grafos de nós (mantém o NodeTree e atalhos)."""

    def __init__(self, mat):
        self.nt = mat.node_tree
        self.nt.nodes.clear()

    def n(self, kind: str, **kw):
        node = self.nt.nodes.new(kind)
        for k, v in kw.items():
            setattr(node, k, v)
        return node

    def link(self, out, inp):
        self.nt.links.new(out, inp)

    def vector(self, space: str, tile: float):
        if space == "bus" and _S["bus"] is not None:
            tc = self.n("ShaderNodeTexCoord")
            tc.object = _S["bus"]
            src = tc.outputs["Object"]
        else:
            src = self.n("ShaderNodeNewGeometry").outputs["Position"]
        m = self.n("ShaderNodeMapping")
        m.inputs["Scale"].default_value = (1 / tile,) * 3
        self.link(src, m.inputs["Vector"])
        return m.outputs["Vector"]

    def noise(self, vec, scale, detail=4.0, rough=0.5):
        t = self.n("ShaderNodeTexNoise")
        t.inputs["Scale"].default_value = scale
        t.inputs["Detail"].default_value = detail
        t.inputs["Roughness"].default_value = rough
        self.link(vec, t.inputs["Vector"])
        return t.outputs["Fac"]

    def voronoi(self, vec, scale):
        t = self.n("ShaderNodeTexVoronoi")
        t.inputs["Scale"].default_value = scale
        self.link(vec, t.inputs["Vector"])
        return t.outputs["Distance"]

    def rng(self, value, f0, f1, t0=0.0, t1=1.0):
        r = self.n("ShaderNodeMapRange")
        r.inputs["From Min"].default_value, r.inputs["From Max"].default_value = f0, f1
        r.inputs["To Min"].default_value, r.inputs["To Max"].default_value = t0, t1
        self.link(value, r.inputs["Value"])
        return r.outputs["Result"]

    def mix(self, fac, a, b):
        """Mistura de cores: a (fac=0) -> b (fac=1). a/b podem ser tuplas RGB ou sockets."""
        m = self.n("ShaderNodeMix", data_type="RGBA")
        f = _sock(m, "Factor_Float")
        if isinstance(fac, (int, float)):
            f.default_value = fac
        else:
            self.link(fac, f)
        for ident, v in (("A_Color", a), ("B_Color", b)):
            s = _sock(m, ident)
            if isinstance(v, (tuple, list)):
                s.default_value = (*v, 1.0)
            else:
                self.link(v, s)
        return _sock(m, "Result_Color", inputs=False)

    def bump(self, height, strength, distance=0.01):
        b = self.n("ShaderNodeBump")
        b.inputs["Strength"].default_value = strength
        b.inputs["Distance"].default_value = distance
        self.link(height, b.inputs["Height"])
        return b.outputs["Normal"]

    def principled(self, color=None, rough=None, metal=None, normal=None, coat=None):
        out = self.n("ShaderNodeOutputMaterial")
        bsdf = self.n("ShaderNodeBsdfPrincipled")
        self.link(bsdf.outputs[0], out.inputs["Surface"])
        for name, v in (("Base Color", color), ("Roughness", rough), ("Metallic", metal), ("Normal", normal)):
            if v is None:
                continue
            s = bsdf.inputs[name]
            if isinstance(v, (tuple, list)):
                s.default_value = (*v, 1.0)
            elif isinstance(v, (int, float)):
                s.default_value = v
            else:
                self.link(v, s)
        if coat is not None:
            for name in ("Coat Weight", "Clearcoat"):                 # 4.x / 3.x
                if name in bsdf.inputs:
                    bsdf.inputs[name].default_value = coat
                    break
        return bsdf


# ---- procedurais -----------------------------------------------------------------------------------------------------
def _waxed_floor(b: _B, vec, p):
    brick = b.n("ShaderNodeTexBrick", offset=0.0)
    brick.inputs["Color1"].default_value = (*p["color"], 1.0)
    brick.inputs["Color2"].default_value = (*p["color2"], 1.0)
    brick.inputs["Mortar"].default_value = (*p["joint_color"], 1.0)
    brick.inputs["Mortar Size"].default_value = p["joint"]
    brick.inputs["Mortar Smooth"].default_value = 0.1
    brick.inputs["Brick Width"].default_value = 1.0
    brick.inputs["Row Height"].default_value = 1.0
    brick.inputs["Scale"].default_value = 1.0
    b.link(vec, brick.inputs["Vector"])
    smudge = b.noise(vec, 1.6, detail=6.0)                             # manchas/riscos de uso
    color = b.mix(b.rng(smudge, 0.45, 0.8, 0.0, p["scuffs"]), brick.outputs["Color"], (0.05, 0.055, 0.06))
    lo, hi = p["roughness"]
    rough = b.rng(b.noise(vec, 2.5, detail=5.0), 0.35, 0.7, lo, hi)
    return b.principled(color=color, rough=rough, metal=0.0, coat=p["coat"])


def _diamonds(b: _B, vec, scale):
    """Estampa de losangos (xadrez girado 45°): padrão geométrico de tecido de ônibus. Devolve 0/1."""
    mp = b.n("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0.0, 0.0, 0.7853982)
    mp.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
    b.link(vec, mp.inputs["Vector"])
    ck = b.n("ShaderNodeTexChecker")
    ck.inputs["Scale"].default_value = scale
    b.link(mp.outputs["Vector"], ck.inputs["Vector"])
    return ck.outputs["Fac"]


def _fabric(b: _B, vec, p):
    fine = b.noise(vec, p["weave"], detail=1.0, rough=0.7)             # trama
    shade = b.rng(fine, 0.2, 0.8, 0.0, 1.0)
    c = tuple(p["color"])
    color = b.mix(shade, tuple(v * 0.78 for v in c), tuple(min(1.0, v * 1.12) for v in c))
    if p["print_amount"] > 0:                                           # estampa antiga e desbotada em azul/cinza
        fade = b.rng(b.noise(vec, 3.0, detail=4.0), 0.3, 0.7, 0.55, 1.0)  # o desbotado varia pelo banco
        pat = b.rng(_diamonds(b, vec, p["print_scale"]), 0.0, 1.0, 0.0, p["print_amount"])
        mask = b.n("ShaderNodeMath", operation="MULTIPLY")
        b.link(pat, mask.inputs[0])
        b.link(fade, mask.inputs[1])
        color = b.mix(mask.outputs[0], color, tuple(p["print_color"]))
    rough = p["roughness"]
    if p["mold"] > 0:
        t = 0.74 - 0.30 * p["mold"]                                    # mais mofo => limiar menor => mais área
        mask = b.rng(b.noise(vec, p["mold_scale"], detail=9.0, rough=0.62), t, t + 0.10)
        tint = b.mix(b.noise(vec, 11.0, detail=3.0), tuple(p["mold_color"]), tuple(p["mold_green"]))
        color = b.mix(mask, color, tint)
        rough = b.rng(mask, 0.0, 1.0, p["roughness"], min(1.0, p["roughness"] + 0.06))
    normal = b.bump(fine, p["weave_bump"], 0.004)
    return b.principled(color=color, rough=rough, metal=0.0, normal=normal)


def _rubber_floor(b: _B, vec, p):
    """Borracha antiderrapante: pastilhas em grade (relevo), desgaste liso e, se `dirt`, terra seca nos cantos."""
    studs = b.voronoi(vec, p["stud_scale"])                             # distância ao centro da célula => bolinhas
    dome = b.rng(studs, 0.0, 0.42, 1.0, 0.0)                            # 1 no centro, 0 na borda
    color = b.mix(b.noise(vec, 2.2, detail=5.0), tuple(p["color"]), tuple(v * 1.9 for v in p["color"]))
    worn = b.rng(b.noise(vec, 1.1, detail=6.0), 0.5, 0.78, 0.0, p["wear"])
    rough = b.rng(worn, 0.0, 1.0, p["roughness"], max(0.25, p["roughness"] - 0.45))   # onde pisam, a borracha lustra
    if p["dirt"] > 0:
        t = 0.72 - 0.30 * p["dirt"]
        d = b.rng(b.noise(vec, 3.4, detail=7.0, rough=0.6), t, t + 0.12)
        color = b.mix(d, color, tuple(p["dirt_color"]))
    normal = b.bump(dome, p["stud_bump"], 0.004)
    return b.principled(color=color, rough=rough, metal=0.0, normal=normal)


def _shirt(b: _B, vec, p):
    """Camisa social amarrotada: tecido fino com vincos (ruído esticado) e, se `stain`, manchas amareladas."""
    wr = b.noise(vec, p["wrinkle_scale"], detail=7.0, rough=0.65)
    fine = b.noise(vec, 120.0, detail=1.0, rough=0.6)                  # trama bem fina
    c = tuple(p["color"])
    color = b.mix(b.rng(wr, 0.3, 0.7), tuple(v * 0.8 for v in c), tuple(min(1.0, v * 1.1) for v in c))
    if p["stain"] > 0:
        t = 0.72 - 0.35 * p["stain"]
        st = b.rng(b.noise(vec, 2.4, detail=6.0), t, t + 0.12)
        color = b.mix(st, color, tuple(p["stain_color"]))
    folds = b.n("ShaderNodeMath", operation="ADD")
    b.link(wr, folds.inputs[0])
    b.link(b.rng(fine, 0.3, 0.7, 0.0, 0.08), folds.inputs[1])
    normal = b.bump(folds.outputs[0], p["wrinkle_bump"], 0.008)
    return b.principled(color=color, rough=p["roughness"], metal=0.0, normal=normal)


def _rust_metal(b: _B, vec, p):
    n1 = b.noise(vec, p["rust_scale"], detail=10.0, rough=0.62)
    t = 1.0 - 0.62 * p["rust"]                                          # mais ferrugem => limiar menor
    mask = b.rng(n1, t - 0.05, t + 0.08)
    rust = b.mix(b.noise(vec, 14.0, detail=4.0), tuple(p["rust_color"]), tuple(p["rust_dark"]))
    color = b.mix(mask, tuple(p["metal_color"]), rust)
    metal = b.rng(mask, 0.0, 1.0, 1.0, 0.0)                              # aço limpo = metálico; ferrugem = dielétrica
    rough = b.rng(mask, 0.0, 1.0, p["metal_roughness"], p["rust_roughness"])
    relief = b.rng(n1, 0.3, 0.8)
    normal = b.bump(relief, p["bump"], 0.006)
    return b.principled(color=color, rough=rough, metal=metal, normal=normal)


def _red_dirt(b: _B, vec, p):
    large = b.noise(vec, 0.7, detail=4.0)
    fine = b.noise(vec, 9.0, detail=8.0)
    color = b.mix(b.rng(large, 0.3, 0.7), tuple(p["color2"]), tuple(p["color"]))
    color = b.mix(b.rng(fine, 0.35, 0.75, 0.0, 0.35), color, (0.06, 0.02, 0.015))
    wet = b.rng(b.noise(vec, 0.38, detail=3.0), 0.62, 0.74, 0.0, p["wet"])       # poças: mais escuras e mais lisas
    color = b.mix(wet, color, (0.07, 0.025, 0.02))
    rough = b.rng(wet, 0.0, 1.0, p["roughness"], 0.55)
    peb = b.voronoi(vec, p["pebble_scale"])
    normal = b.bump(peb, 0.5 * p["pebbles"], 0.04)
    return b.principled(color=color, rough=rough, metal=0.0, normal=normal)


_PROCEDURAL = {"piso-encerado": _waxed_floor, "piso-emborrachado": _rubber_floor, "estofado": _fabric, "camisa-social": _shirt,
               "metal-enferrujado": _rust_metal, "terra-vermelha": _red_dirt}


def _from_images(b: _B, vec, p, files: dict, mat_id: str):
    """Conjunto PBR em imagens, mapeado em caixa (triplanar) em metros."""
    def tex(mapname):
        t = b.n("ShaderNodeTexImage")
        t.image = bpy.data.images.load(str(files[mapname]), check_existing=True)
        t.image.colorspace_settings.name = "sRGB" if mapname == "albedo" else "Non-Color"
        t.projection, t.projection_blend, t.extension = "BOX", 0.25, "REPEAT"
        b.link(vec, t.inputs["Vector"])
        return t.outputs["Color"]
    color = tex("albedo") if "albedo" in files else tuple(p.get("color", p.get("metal_color", (0.5, 0.5, 0.5))))
    if "ao" in files:
        m = b.n("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
        _sock(m, "Factor_Float").default_value = 1.0
        if isinstance(color, tuple):
            _sock(m, "A_Color").default_value = (*color, 1.0)
        else:
            b.link(color, _sock(m, "A_Color"))
        b.link(tex("ao"), _sock(m, "B_Color"))
        color = _sock(m, "Result_Color", inputs=False)
    rough = tex("roughness") if "roughness" in files else None
    metal = tex("metallic") if "metallic" in files else None
    normal = b.bump(tex("height"), 0.6, 0.01) if "height" in files else None
    return b.principled(color=color, rough=rough, metal=metal, normal=normal)


# ---- API ---------------------------------------------------------------------------------------------------------------------
def get(mat_id: str, variant: str | None = None, use_images: bool = True):
    spec = manifest()["materials"][mat_id]
    if spec.get("kind") == "volume":
        raise ValueError(f"{mat_id} é um volume: use ground_fog()")
    variant = variant or next(iter(spec.get("variants", {})), None)
    key = (mat_id, variant, use_images, str(_S["textures"]))
    if key in _S["cache"]:
        return _S["cache"][key]
    p = params(mat_id, variant)
    m = bpy.data.materials.new(f"{mat_id}.{variant}" if variant else mat_id)
    m.use_nodes = True
    b = _B(m)
    vec = b.vector(spec["space"], spec["tile_m"])
    files = find_maps(mat_id, variant) if use_images else {}
    if files:
        _from_images(b, vec, p, files, mat_id)
        m["pov_source"] = "imagens:" + ",".join(sorted(files))
    else:
        _PROCEDURAL[mat_id](b, vec, p)
        m["pov_source"] = "procedural"
    m["pov_id"], m["pov_variant"], m["pov_params"] = mat_id, variant or "", json.dumps(p)
    c = p.get("color") or p.get("metal_color") or (0.5, 0.5, 0.5)
    m.diffuse_color = (*c, 1.0)
    _S["cache"][key] = m
    return m


def ground_fog(parent, variant: str | None = None):
    """Neblina volumétrica rasteira: cubo preso ao ônibus (anda com ele); a densidade cai com a altura do MUNDO e o
    ruído usa coordenadas de MUNDO, então a névoa fica no lugar enquanto o ônibus atravessa."""
    p = params("neblina-rasteira", variant)
    m = bpy.data.materials.new("neblina-rasteira")
    m.use_nodes = True
    b = _B(m)
    pos = b.n("ShaderNodeNewGeometry").outputs["Position"]
    sep = b.n("ShaderNodeSeparateXYZ")
    b.link(pos, sep.inputs["Vector"])
    fall = b.n("ShaderNodeMath", operation="MULTIPLY")
    b.link(sep.outputs["Z"], fall.inputs[0])
    fall.inputs[1].default_value = -1.0 / p["height_m"]
    expo = b.n("ShaderNodeMath", operation="EXPONENT")          # unário: e^x (a densidade cai com a altura)
    b.link(fall.outputs[0], expo.inputs[0])
    mp = b.n("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (p["noise_scale"],) * 3
    b.link(pos, mp.inputs["Vector"])
    patch = b.rng(b.noise(mp.outputs["Vector"], 1.0, detail=4.0), 0.3, 0.7, 0.35, 1.5)   # manchas: 0,35x a 1,5x
    d1 = b.n("ShaderNodeMath", operation="MULTIPLY")
    b.link(expo.outputs[0], d1.inputs[0])
    b.link(patch, d1.inputs[1])
    d2 = b.n("ShaderNodeMath", operation="MULTIPLY")
    b.link(d1.outputs[0], d2.inputs[0])
    d2.inputs[1].default_value = p["density"]
    vol = b.n("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (*p["color"], 1.0)
    vol.inputs["Emission Strength"].default_value = p["glow"]
    vol.inputs["Emission Color"].default_value = (*p["color"], 1.0)
    b.link(d2.outputs[0], vol.inputs["Density"])
    out = b.n("ShaderNodeOutputMaterial")
    b.link(vol.outputs[0], out.inputs["Volume"])
    sx, sy, sz = p["size_m"]
    ob = kit.box("neblina-rasteira", (sx, sy, sz), (0.0, -5.0, sz / 2 - 0.3), m, parent=parent)
    for attr in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission"):
        if hasattr(ob, attr):
            setattr(ob, attr, False)
    m["pov_id"], m["pov_params"] = "neblina-rasteira", json.dumps(p)
    return ob
