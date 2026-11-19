"""Renderiza um episódio em sequência de imagens (retomável, em lotes, com benchmark).

  blender -b -P blender/render_episode.py -- --episode ep01 --out renders [--width 1080 --samples 96 --device auto]
  python -m pipeline render ep01 ...        (chama este script; veja `pipeline/render.py`)

  --first/--last N   faixa de quadros (0 = 1º do CSV; padrão: tudo). --step K renderiza 1 a cada K (prévia).
  --bench N          renderiza N quadros espalhados pelo episódio, mede e projeta o tempo total (não grava a sequência).
  --resume           (padrão) pula quadros que já existem; --overwrite refaz.
  --device auto|cpu|gpu  auto = GPU (OptiX/CUDA/HIP/Metal/oneAPI) se houver, senão CPU.

Saída: <out>/<ep>/f00001.png ... (numeração do Blender: quadro do CSV + 1). 1080x1920 a 60 fps é o padrão do episódio.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import bpy  # noqa: E402

import assemble_scene as asm  # noqa: E402


def pick_device(sc, want: str, backend: str = "auto") -> str:
    """Liga a melhor GPU disponível (ou a do `backend` pedido); devolve 'CPU' ou 'GPU:<tipo>'."""
    sc.cycles.device = "CPU"
    if want == "cpu":
        return "CPU"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except KeyError:
        return "CPU"
    kinds = ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI") if backend == "auto" else (backend.upper(),)
    for kind in kinds:
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
        except Exception:                                   # tipo não suportado nesta compilação
            continue
        gpus = [d for d in prefs.devices if d.type != "CPU"]
        if gpus:
            for d in prefs.devices:
                d.use = d.type != "CPU" or want == "auto-cpu"
            sc.cycles.device = "GPU"
            return f"GPU:{kind}"
    return "CPU"


def configure(sc, width, height, samples, device, threads, backend="auto"):
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    used = pick_device(sc, device, backend)
    cy.samples = samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.02
    cy.use_denoising = True
    try:
        cy.denoiser = "OPTIX" if used == "GPU:OPTIX" else "OPENIMAGEDENOISE"
    except TypeError:
        pass
    cy.max_bounces, cy.volume_bounces = 4, 0
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = width, height, 100
    sc.render.fps, sc.render.fps_base = 60, 1.0
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.image_settings.compression = 15
    sc.view_settings.view_transform = "Standard"
    sc.render.use_persistent_data = True                     # reaproveita a cena entre quadros (muito mais rápido)
    if threads:
        sc.render.threads_mode = "FIXED"
        sc.render.threads = threads
    return used


def main(argv=None):
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser(prog="render_episode.py")
    ap.add_argument("--episode", required=True)
    ap.add_argument("--out", default="renders")
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int)
    ap.add_argument("--samples", type=int, default=96)
    ap.add_argument("--device", default="auto", choices=("auto", "cpu", "gpu"))
    ap.add_argument("--backend", default="auto", choices=("auto", "optix", "cuda", "hip", "metal", "oneapi"),
                    help="API da GPU (auto = a melhor disponível; no Colab, cuda é a aposta segura)")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--first", type=int, default=0)
    ap.add_argument("--last", type=int)
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--bench", type=int, default=0)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--textures-dir")
    a = ap.parse_args(argv)
    env = asm.assemble(a.episode, textures_dir=a.textures_dir)
    sc = env.sc
    height = a.height or round(a.width * 16 / 9)
    used = configure(sc, a.width, height, a.samples, a.device, a.threads, a.backend)
    if a.device == "gpu" and used == "CPU":
        sys.exit(f"[RENDER] --device gpu pedido, mas nenhuma GPU com a API {a.backend} foi encontrada (veja nvidia-smi)")
    n = len(env.ctx.rows())
    last = n - 1 if a.last is None else min(a.last, n - 1)
    out = Path(a.out).resolve() / a.episode
    out.mkdir(parents=True, exist_ok=True)
    print(f"[RENDER] {a.episode}: {a.width}x{height} @60fps · {a.samples} amostras · {used} · quadros {a.first}..{last} (passo {a.step}) -> {out}")
    if a.bench:
        picks = [round(i * (n - 1) / max(a.bench - 1, 1)) for i in range(a.bench)]
        times = []
        for k in picks:
            sc.frame_set(env.start_frame + k)
            sc.render.filepath = str(out / f"bench_{k:05d}.png")
            t0 = time.time()
            bpy.ops.render.render(write_still=True)
            times.append(time.time() - t0)
            print(f"[BENCH] quadro {k}: {times[-1]:.1f} s")
        mean = sum(times) / len(times)
        print(f"[BENCH] média {mean:.1f} s/quadro -> episódio inteiro ({n} quadros) ≈ {mean * n / 3600:.1f} h neste hardware")
        return 0
    todo = [k for k in range(a.first, last + 1, a.step)]
    done = skipped = 0
    t_start = time.time()
    for k in todo:
        f = out / f"f{env.start_frame + k:05d}.png"
        if f.exists() and not a.overwrite:
            skipped += 1
            continue
        sc.frame_set(env.start_frame + k)
        sc.render.filepath = str(f.with_suffix(""))
        bpy.ops.render.render(write_still=True)
        done += 1
        if done % 10 == 0 or k == todo[-1]:
            el = time.time() - t_start
            left = (len(todo) - skipped - done) * el / done
            print(f"[RENDER] {done + skipped}/{len(todo)} · {el / done:.1f} s/quadro · faltam ≈ {left / 60:.0f} min", flush=True)
    print(f"[RENDER] pronto: {done} novos, {skipped} já existiam")
    return 0


if __name__ == "__main__":
    sys.exit(main())
