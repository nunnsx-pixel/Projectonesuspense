"""Monta a cena do Blender de um episódio a partir da timeline sincronizada.

  blender -b -P blender/assemble_scene.py -- --episode ep02 --save ep02.blend [--render-frames 30,600,2400 --out previews]

O que entra na cena (greybox low-poly estilizado, para você trocar pelos assets finais):
  * ônibus, cenário e personagens do episódio (blender/pov_scene/epXX.py);
  * POV_Head: caminho-base da cabeça guiado pelos PASSOS do CSV (o pé planta nos frames dos passos);
  * Camera (filha do POV_Head) com o balanço/olhar do CSV (import_camera_csv.py) e FOV;
  * luz do ônibus, vinheta, pálpebra e tela preta ligadas aos canais do CSV por drivers;
  * marcadores BEAT:/VOZ:/CENA: na timeline.
"""
from __future__ import annotations

import argparse
import importlib
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import bpy  # noqa: E402

import import_camera_csv as imp  # noqa: E402
from pov_scene import fx, kit, materials  # noqa: E402
from pov_scene.ctx import Ctx  # noqa: E402


@dataclass
class Env:
    sc: object
    ctx: Ctx
    bus: object                      # empty ONIBUS (anda quando o ônibus anda)
    head: object                     # empty POV_Head (caminho-base da cabeça, no referencial do ônibus)
    cam: object
    track: object = None             # pov_scene.path.Track
    bus_moves: bool = False
    refs: dict = field(default_factory=dict)
    start_frame: int = 1

    def f(self, t: float) -> int:
        return self.ctx.frame(t, self.start_frame)


def _key_head(env: Env):
    last = env.start_frame + len(env.ctx.rows()) - 1
    with kit.interp("LINEAR"):
        for r in env.ctx.rows():
            t = r["t"]
            p = env.track.sample(t)
            f = env.start_frame + int(r["frame"])
            env.head.location = (p.x, p.y, p.z)
            env.head.rotation_euler = (0.0, 0.0, -math.radians(p.heading))
            env.head.keyframe_insert("location", frame=f)
            env.head.keyframe_insert("rotation_euler", frame=f)
    return last


def _key_bus(env: Env):
    dist = env.ctx.bus_distance()
    with kit.interp("LINEAR"):
        for i in list(range(0, len(dist), 6)) + [len(dist) - 1]:
            env.bus.location = (0.0, dist[i], 0.0)
            env.bus.keyframe_insert("location", frame=env.start_frame + i)


def _markers(env: Env):
    sc, ctx = env.sc, env.ctx
    for s in ctx.tl["scenes"]:
        kit.marker(sc, f"CENA:{s['id']}", env.f(s["start"]))
        for b in s["beats"]:
            kit.marker(sc, f"BEAT:{b['id']}", env.f(b["start"]))
    for i in ctx.tl["narration"]:
        if i["kind"] == "speech":
            who = i.get("speaker", "")
            kit.marker(sc, f"VOZ:{i['id']}{'/' + who if who else ''}", env.f(i["start"]))


def assemble(ep: str, root=None, save: str | None = None, camera_name: str = "Camera", textures_dir=None):
    ctx = Ctx(ep, root)
    mod = importlib.import_module(f"pov_scene.{ep}")
    sc = kit.new_scene(*mod.WORLD)
    materials.reset()
    bus = kit.empty("ONIBUS")
    materials.configure(bus_root=bus, textures_dir=textures_dir)   # texturas 'bus' ficam presas ao ônibus
    head = kit.empty("POV_Head", parent=bus)
    cd = bpy.data.cameras.new(camera_name)
    cd.sensor_fit = "VERTICAL"
    cd.angle = math.radians(80)
    cd.clip_start = 0.03
    cam = bpy.data.objects.new(camera_name, cd)
    sc.collection.objects.link(cam)
    cam.parent = head
    sc.camera = cam
    env = Env(sc, ctx, bus, head, cam)
    mod.build(env)
    # Ep. 1: a luz não pisca e o CSV não tem `light`; sem a coluna, os drivers das luzes valeriam 0
    imp.import_csv(ctx.csv_path, camera_name=camera_name, start_frame=env.start_frame, extra_constants={"light": 1.0})
    fx.build(cam)
    if hasattr(mod, "wire"):
        mod.wire(env)
    _key_head(env)
    if env.bus_moves:
        _key_bus(env)
    _markers(env)
    sc.frame_set(env.start_frame)
    if save:
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(save).resolve()))
    return env


def render_frames(env: Env, frames, outdir, width=270, height=480, samples=24):
    """Renderiza quadros (por tempo em segundos) em PNG; restaura a resolução depois."""
    sc = env.sc
    old = (sc.render.resolution_x, sc.render.resolution_y, sc.render.engine)
    kit.preview_settings(sc, width, height, samples)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    paths = []
    for t in frames:
        sc.frame_set(env.f(t))
        sc.render.filepath = str(outdir / f"{env.ctx.ep}_{t:06.2f}s.png")
        bpy.ops.render.render(write_still=True)
        paths.append(sc.render.filepath)
    sc.render.resolution_x, sc.render.resolution_y, sc.render.engine = old
    return paths


def main(argv=None):
    if argv is None:                      # dentro do Blender os argumentos vêm depois de "--"; com o módulo bpy, direto
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser(prog="assemble_scene.py")
    ap.add_argument("--episode", required=True, help="ep01 | ep02 | ep03")
    ap.add_argument("--save", help="salvar o .blend")
    ap.add_argument("--render-frames", help="tempos (s) separados por vírgula para renderizar prévias")
    ap.add_argument("--out", default="previews", help="pasta das prévias")
    ap.add_argument("--samples", type=int, default=24)
    ap.add_argument("--textures-dir", help="pasta com conjuntos PBR (padrão: blender/textures); sem imagens, vale o procedural")
    a = ap.parse_args(argv)
    env = assemble(a.episode, save=None, textures_dir=a.textures_dir)
    if a.render_frames:
        render_frames(env, [float(x) for x in a.render_frames.split(",")], a.out, samples=a.samples)
    if a.save:
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(a.save).resolve()))
        print(f"[POV] cena salva em {a.save}")
    return env


if __name__ == "__main__":
    main()
