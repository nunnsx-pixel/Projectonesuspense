"""Primitivas, materiais, drivers e marcadores do Blender (4.2 LTS e 5.x). Estilo: greybox low-poly."""
from __future__ import annotations

import contextlib
import math

import bmesh
import bpy

_MATS: dict[str, bpy.types.Material] = {}
_MESH: dict[str, bpy.types.Mesh] = {}


def reset() -> None:
    _MATS.clear()
    _MESH.clear()


# ---- materiais ---------------------------------------------------------------------------------
def mat(name: str, color=(0.5, 0.5, 0.5), rough: float = 0.85, emit: float = 0.0, emit_color=None):
    """Material cacheado. emit > 0 => Emission pura (luminárias, telas, neblina)."""
    if name in _MATS:
        return _MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if emit > 0:
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = (*(emit_color or color), 1.0)
        e.inputs["Strength"].default_value = emit
        nt.links.new(e.outputs[0], out.inputs["Surface"])
    else:
        b = nt.nodes.new("ShaderNodeBsdfPrincipled")
        b.inputs["Base Color"].default_value = (*color, 1.0)
        b.inputs["Roughness"].default_value = rough
        nt.links.new(b.outputs[0], out.inputs["Surface"])
    m.diffuse_color = (*color, 1.0)
    _MATS[name] = m
    return m


# ---- malhas ------------------------------------------------------------------------------------
def _unit(kind: str) -> bpy.types.Mesh:
    if kind in _MESH:
        return _MESH[kind]
    me = bpy.data.meshes.new(f"unit-{kind}")
    bm = bmesh.new()
    if kind == "cube":
        bmesh.ops.create_cube(bm, size=1.0)
    elif kind == "plane":
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
    elif kind == "cyl":
        bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.5, radius2=0.5, depth=1.0)
    elif kind == "cone":
        bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.5, radius2=0.0, depth=1.0)
    elif kind == "sphere":
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.5)
    bm.to_mesh(me)
    bm.free()
    _MESH[kind] = me
    return me


def _make(name, kind, size, loc, rot, material, parent, color_mesh=True):
    ob = bpy.data.objects.new(name, _unit(kind))
    ob.scale = size
    ob.location = loc
    ob.rotation_euler = tuple(math.radians(a) for a in rot)
    if material is not None:
        ob.data = ob.data                 # malha compartilhada; material por objeto
        ob.active_material = material
        ob.material_slots[0].link = "OBJECT"
        ob.material_slots[0].material = material
    if parent is not None:
        ob.parent = parent
    bpy.context.scene.collection.objects.link(ob)
    return ob


def box(name, size, loc, material=None, rot=(0, 0, 0), parent=None):
    return _make(name, "cube", size, loc, rot, material, parent)


def plane(name, size, loc, material=None, rot=(0, 0, 0), parent=None):
    return _make(name, "plane", (size[0], size[1], 1), loc, rot, material, parent)


def cyl(name, radius, height, loc, material=None, rot=(0, 0, 0), parent=None):
    return _make(name, "cyl", (radius * 2, radius * 2, height), loc, rot, material, parent)


def cone(name, radius, height, loc, material=None, rot=(0, 0, 0), parent=None):
    return _make(name, "cone", (radius * 2, radius * 2, height), loc, rot, material, parent)


def ball(name, radius, loc, material=None, parent=None, squash=(1, 1, 1)):
    return _make(name, "sphere", (radius * 2 * squash[0], radius * 2 * squash[1], radius * 2 * squash[2]),
                 loc, (0, 0, 0), material, parent)


def empty(name, loc=(0, 0, 0), parent=None, rot=(0, 0, 0)):
    ob = bpy.data.objects.new(name, None)
    ob.location = loc
    ob.rotation_euler = tuple(math.radians(a) for a in rot)
    if parent is not None:
        ob.parent = parent
    bpy.context.scene.collection.objects.link(ob)
    return ob


def text(name, body, size, loc, material, parent=None, rot=(0, 0, 0), align="CENTER"):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.size = size
    cu.align_x = align
    cu.align_y = "CENTER"
    cu.materials.append(material)
    ob = bpy.data.objects.new(name, cu)
    ob.location = loc
    ob.rotation_euler = tuple(math.radians(a) for a in rot)
    if parent is not None:
        ob.parent = parent
    bpy.context.scene.collection.objects.link(ob)
    return ob


def light(name, kind, energy, color, loc, parent=None, size=0.5, rot=(0, 0, 0)):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = color
    if kind == "AREA":
        ld.size = size
    else:
        ld.shadow_soft_size = size
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    ob.rotation_euler = tuple(math.radians(a) for a in rot)
    if parent is not None:
        ob.parent = parent
    bpy.context.scene.collection.objects.link(ob)
    return ob


# ---- animação --------------------------------------------------------------------------------------
@contextlib.contextmanager
def interp(kind: str):
    """Interpolação padrão dos próximos keyframes: LINEAR | CONSTANT | BEZIER."""
    prefs = bpy.context.preferences.edit
    old = prefs.keyframe_new_interpolation_type
    prefs.keyframe_new_interpolation_type = kind
    try:
        yield
    finally:
        prefs.keyframe_new_interpolation_type = old


def key(ob, path: str, frame: int, value, index: int = -1):
    setattr(ob, path, value)
    ob.keyframe_insert(path, frame=frame, index=index)


def visible_between(ob, f0: int, f1: int, first: int, last: int):
    """Objeto só aparece no render entre f0 e f1 (degraus; fora disso oculto)."""
    with interp("CONSTANT"):                       # esconder o pai NÃO esconde os filhos: aplica a todos
        for o in (ob, *ob.children_recursive):
            for f, hid in ((first, True), (f0, False), (f1, True)):
                if f < first or f > last:
                    continue
                o.hide_render = hid
                o.hide_viewport = hid
                o.keyframe_insert("hide_render", frame=f)
                o.keyframe_insert("hide_viewport", frame=f)


def driver(target, path: str, expr: str, src, prop: str, index: int = -1, var: str = "v"):
    """Liga `target.path` a `src[prop]` (propriedade custom) por uma expressão simples (sem Python)."""
    fc = target.driver_add(path, index) if index >= 0 else target.driver_add(path)
    fcs = fc if isinstance(fc, (list, tuple)) else [fc]
    for f in fcs:
        d = f.driver
        d.type = "SCRIPTED"
        v = d.variables.new()
        v.name = var
        v.type = "SINGLE_PROP"
        v.targets[0].id = src
        v.targets[0].data_path = f'["{prop}"]'
        d.expression = expr


def frame_driver(target, path: str, expr: str, index: int = -1):
    """Driver só de tempo (ex.: tremor das mãos: 0.004*sin(frame*0.9))."""
    fc = target.driver_add(path, index) if index >= 0 else target.driver_add(path)
    fcs = fc if isinstance(fc, (list, tuple)) else [fc]
    for f in fcs:
        f.driver.type = "SCRIPTED"
        f.driver.expression = expr


def marker(scene, name: str, frame: int):
    scene.timeline_markers.new(name, frame=frame)


# ---- cena / render --------------------------------------------------------------------------------------
def new_scene(world_color=(0.01, 0.012, 0.02), world_strength=1.0) -> bpy.types.Scene:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    reset()
    sc = bpy.context.scene
    sc.render.use_freestyle = False             # SEM contornos pretos (briefing): nada de Freestyle nem modificador de contorno
    w = bpy.data.worlds.new("Mundo")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (*world_color, 1.0)
    bg.inputs[1].default_value = world_strength
    sc.world = w
    return sc


def preview_settings(sc, width=270, height=480, samples=24):
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 4
    sc.cycles.volume_bounces = 0
    sc.render.resolution_x, sc.render.resolution_y = width, height
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.view_settings.view_transform = "Standard"
