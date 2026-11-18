"""Importa ep0X/build/ep0X.camera.csv para a câmera principal do Blender (60fps).

O que o script faz
  * Ajusta a cena: 60fps, 1080x1920 (desligue com --keep-render-settings), frame inicial/final.
  * Anima a CÂMERA PRINCIPAL (localmente, 1 keyframe por frame): posição = balanço (shake_*_cm),
    rotação = olhar + balanço (look_* + shake_*), FOV = FOV base x (1 + fov_pct/100), keyado em `lens`.
  * Se a câmera não tem pai, cria o empty `POV_Head` (na posição atual da câmera) e a põe como filha:
    o CAMINHO-BASE (corrida, escada, corredor, sentar) é animado no POV_Head; a câmera só recebe o
    balanço e o olhar. Se já tem pai (o seu rig), nada é criado: o pai precisa seguir a convenção do
    Blender (+Y frente, +Z cima).
  * Expõe os canais de sincronia como propriedades custom da câmera, também keyadas por frame:
    vignette, edge_blur, eyelid, black, breath, heart, speed_kmh, step (use em drivers/compositor).
  * Cria marcadores na timeline: cenas (POV:s1...), corte para preto (POV:preto) e,
    com --step-markers, cada pisada (POV:passo = frame de contato do pé, para plantar os pés).

Convenção do CSV -> Blender (head-space)
  +X direita -> X | +Y cima -> Z | +Z frente -> Y ; cm -> unidades da cena (respeita unit scale)
  yaw+ = direita -> rot Z = -yaw | pitch+ = cima -> rot X = +pitch | roll+ = inclina à direita -> rot Y = +roll
  Rotação final (intrínseca yaw->pitch->roll) x correção de câmera do Blender (-Z olha para +Y).

Reexecutar é seguro: a animação anterior da câmera é guardada (fake user) e substituída;
marcadores `POV:*` antigos são recriados; o POV_Head é reaproveitado.

Uso (interface): abra este arquivo no Text Editor, ajuste CSV_PATH e clique em "Run Script".
Uso (terminal):
  blender cena.blend -b -P blender/import_camera_csv.py -- \
      --csv ep01/build/ep01.camera.csv [--camera NOME] [--start-frame 1] [--fov-deg 70] \
      [--step-markers] [--keep-render-settings] [--save saida.blend]
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

try:
    import bpy
except ImportError:           # a matemática abaixo roda (e é testada) fora do Blender
    bpy = None

# ---- ajuste aqui se rodar pela interface do Blender ------------------------------------
CSV_PATH = "ep01/build/ep01.camera.csv"       # relativo a este repositório ou ao .blend
# ----------------------------------------------------------------------------------------

HEAD_NAME = "POV_Head"
MARK = "POV:"
SMOOTH_PROPS = ("vignette", "edge_blur", "eyelid", "breath", "heart", "speed_kmh")
CONSTANT_PROPS = ("black", "step")                   # flags: degrau, sem interpolar
REQUIRED = ["frame", "scene", "shake_x_cm", "shake_y_cm", "shake_z_cm",
            "shake_yaw", "shake_pitch", "shake_roll", "look_yaw", "look_pitch", "look_roll",
            "fov_pct", *SMOOTH_PROPS, *CONSTANT_PROPS]


# =========================================================================================
# Matemática pura (sem bpy)
# =========================================================================================
def _rx(a):
    c, s = math.cos(a), math.sin(a)
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def _ry(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def _rz(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _unwrap(angle, prev):
    if prev is None:
        return angle
    return angle + 2 * math.pi * round((prev - angle) / (2 * math.pi))


def euler_xyz(m, prev=None):
    """Euler 'XYZ' do Blender (R = Rz(g) Ry(b) Rx(a)), contínuo em relação a `prev`."""
    sb = -m[2][0]
    if abs(sb) < 0.99999:
        b = math.asin(sb)
        a = math.atan2(m[2][1], m[2][2])
        g = math.atan2(m[1][0], m[0][0])
    else:                                   # gimbal lock (não ocorre nas poses desta câmera)
        b = math.copysign(math.pi / 2, sb)
        a = math.atan2(-m[1][2], m[1][1])
        g = 0.0
    if prev is None:
        return (a, b, g)
    return (_unwrap(a, prev[0]), _unwrap(b, prev[1]), _unwrap(g, prev[2]))


def camera_rotation_matrix(yaw_deg, pitch_deg, roll_deg):
    """Orientação da câmera no espaço do pai (Y frente, Z cima) a partir de yaw/pitch/roll do CSV."""
    yaw, pitch, roll = (math.radians(v) for v in (yaw_deg, pitch_deg, roll_deg))
    shake = _mul(_mul(_rz(-yaw), _rx(pitch)), _ry(roll))     # yaw -> pitch -> roll (intrínseco)
    return _mul(shake, _rx(math.pi / 2))                      # câmera do Blender olha para -Z


def camera_pose(row, cm_to_bu, prev_euler=None):
    """(location, euler XYZ em radianos) locais da câmera para uma linha do CSV."""
    loc = (row["shake_x_cm"] * cm_to_bu, row["shake_z_cm"] * cm_to_bu, row["shake_y_cm"] * cm_to_bu)
    m = camera_rotation_matrix(row["look_yaw"] + row["shake_yaw"],
                               row["look_pitch"] + row["shake_pitch"],
                               row["look_roll"] + row["shake_roll"])
    return loc, euler_xyz(m, prev_euler)


def read_rows(path):
    """Lê o CSV, valida colunas e frames contíguos (0..N-1)."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: faltam colunas {missing} (gere de novo com `python -m pipeline build`)")
        rows = []
        for r in reader:
            rows.append({k: (v if k == "scene" else float(v)) for k, v in r.items()})
    if not rows:
        raise ValueError(f"{path}: CSV vazio")
    if [int(r["frame"]) for r in rows] != list(range(len(rows))):
        raise ValueError(f"{path}: os frames precisam ser contíguos a partir de 0")
    return rows


# =========================================================================================
# Blender
# =========================================================================================
def _pick_camera(scene, name):
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "CAMERA":
            raise SystemExit(f"Câmera {name!r} não encontrada (objetos de câmera: "
                             f"{[o.name for o in bpy.data.objects if o.type == 'CAMERA']})")
    elif scene.camera is not None:
        obj = scene.camera
    else:
        data = bpy.data.cameras.new("POV_Camera")
        obj = bpy.data.objects.new("POV_Camera", data)
        scene.collection.objects.link(obj)
    scene.camera = obj
    return obj


def _ensure_head(cam):
    if cam.parent is not None:
        return cam.parent, False
    bpy.context.view_layer.update()                 # matrix_world em dia antes de ler a posição
    head = bpy.data.objects.get(HEAD_NAME)
    if head is None:
        head = bpy.data.objects.new(HEAD_NAME, None)
        head.empty_display_type = "ARROWS"
        head.empty_display_size = 0.4
        for coll in (cam.users_collection or [bpy.context.scene.collection]):
            coll.objects.link(head)
    head.location = cam.matrix_world.translation.copy()
    cam.parent = head
    cam.matrix_parent_inverse.identity()
    return head, True


def _stash_animation(id_block):
    """Guarda (fake user) e solta a action anterior, em vez de destruí-la."""
    ad = id_block.animation_data
    if ad is not None and ad.action is not None:
        old = ad.action
        old.use_fake_user = True
        ad.action = None
        return old.name
    return None


def _set_marker(scene, name, frame):
    scene.timeline_markers.new(MARK + name, frame=frame)


def import_csv(csv_path, camera_name=None, start_frame=1, fov_deg=None, keep_render_settings=False,
               step_markers=False, scene=None):
    if bpy is None:
        raise RuntimeError("Este script precisa rodar dentro do Blender (ou do módulo bpy).")
    scene = scene or bpy.context.scene
    rows = read_rows(csv_path)
    n = len(rows)

    if not keep_render_settings:
        scene.render.fps, scene.render.fps_base = 60, 1.0
        scene.render.resolution_x, scene.render.resolution_y = 1080, 1920
        scene.render.resolution_percentage = 100
    scene.frame_start, scene.frame_end = start_frame, start_frame + n - 1

    cam = _pick_camera(scene, camera_name)
    head, created = _ensure_head(cam)
    stashed = [_stash_animation(cam), _stash_animation(cam.data)]
    for m in [m for m in scene.timeline_markers if m.name.startswith(MARK)]:
        scene.timeline_markers.remove(m)

    cam.rotation_mode = "XYZ"
    if fov_deg is not None:
        cam.data.angle = math.radians(fov_deg)
    base_angle = cam.data.angle
    cm_to_bu = 0.01 / scene.unit_settings.scale_length
    for p in SMOOTH_PROPS + CONSTANT_PROPS:
        cam[p] = 0.0

    prefs = bpy.context.preferences.edit
    old_interp = prefs.keyframe_new_interpolation_type
    try:
        prefs.keyframe_new_interpolation_type = "LINEAR"      # 1 key/frame: reproduz o CSV exato
        prev = None
        for r in rows:
            f = start_frame + int(r["frame"])
            loc, prev = camera_pose(r, cm_to_bu, prev)
            cam.location = loc
            cam.rotation_euler = prev
            cam.data.angle = base_angle * (1.0 + r["fov_pct"] / 100.0)   # `angle` não é animável: o Blender
            cam.keyframe_insert("location", frame=f, group="POV rig")     # converte em `lens` (respeita sensor_fit)
            cam.keyframe_insert("rotation_euler", frame=f, group="POV rig")
            cam.data.keyframe_insert("lens", frame=f, group="POV rig")
            for p in SMOOTH_PROPS:
                cam[p] = r[p]
                cam.keyframe_insert(f'["{p}"]', frame=f, group="POV sync")
        prefs.keyframe_new_interpolation_type = "CONSTANT"    # flags viram degraus
        for r in rows:
            f = start_frame + int(r["frame"])
            for p in CONSTANT_PROPS:
                cam[p] = r[p]
                cam.keyframe_insert(f'["{p}"]', frame=f, group="POV sync")
    finally:
        prefs.keyframe_new_interpolation_type = old_interp

    for obj in (cam, cam.data):
        if obj.animation_data and obj.animation_data.action:
            obj.animation_data.action.name = f"{Path(csv_path).stem}"

    last_scene = None
    for r in rows:
        f = start_frame + int(r["frame"])
        if r["scene"] != last_scene:
            _set_marker(scene, r["scene"], f)
            last_scene = r["scene"]
    first_black = next((r for r in rows if r["black"] >= 0.5), None)
    if first_black is not None:
        _set_marker(scene, "preto", start_frame + int(first_black["frame"]))
    if step_markers:
        for r in rows:
            if r["step"] >= 0.5:
                _set_marker(scene, "passo", start_frame + int(r["frame"]))
    scene.frame_set(start_frame)

    return {"camera": cam.name, "head": head.name, "head_created": created, "frames": n,
            "frame_range": (scene.frame_start, scene.frame_end), "stashed_actions": [s for s in stashed if s]}


def _resolve_csv(path_str):
    p = Path(path_str)
    if p.is_absolute() or p.exists():
        return p
    here = Path(__file__).resolve().parent.parent if "__file__" in globals() else None
    for base in (here, Path(bpy.path.abspath("//")) if bpy else None):
        if base and (base / p).exists():
            return base / p
    return p


def main(argv=None):
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="import_camera_csv.py", description=__doc__.split("\n")[0])
    ap.add_argument("--csv", default=CSV_PATH)
    ap.add_argument("--camera", help="nome do objeto de câmera (padrão: câmera ativa da cena)")
    ap.add_argument("--start-frame", type=int, default=1, help="frame do Blender para o frame 0 do CSV")
    ap.add_argument("--fov-deg", type=float, help="FOV base (graus, no eixo do sensor_fit); padrão: o da câmera")
    ap.add_argument("--step-markers", action="store_true", help="marcador em cada pisada (frame de contato)")
    ap.add_argument("--keep-render-settings", action="store_true", help="não mexer em fps/resolução")
    ap.add_argument("--save", help="salvar o .blend neste caminho depois de importar")
    args = ap.parse_args(argv)

    info = import_csv(_resolve_csv(args.csv), args.camera, args.start_frame, args.fov_deg,
                      args.keep_render_settings, args.step_markers)
    print(f"[POV] {info['frames']} frames -> câmera {info['camera']!r} "
          f"(frames {info['frame_range'][0]}..{info['frame_range'][1]} @60fps); "
          f"pai {info['head']!r}{' (criado)' if info['head_created'] else ''}")
    if info["stashed_actions"]:
        print(f"[POV] animação anterior guardada com fake user: {info['stashed_actions']}")
    if args.save:
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save).resolve()))
        print(f"[POV] salvo em {args.save}")
    return info


if __name__ == "__main__":
    if bpy is None:
        raise SystemExit("Rode dentro do Blender:  blender cena.blend -b -P blender/import_camera_csv.py -- --csv ...")
    main()
