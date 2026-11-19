"""Render e montagem do vídeo final de um episódio.

  python -m pipeline render ep01 [--width 1080 --samples 96 --device auto]     # sequência de imagens em renders/ep01/
  python -m pipeline render ep01 --bench 6                                      # mede s/quadro e projeta o tempo total
  python -m pipeline render ep01 --chunks 8 --chunk 3                           # só o 4º de 8 lotes (granja de render)
  python -m pipeline assemble ep01                                              # renders + mix.wav -> out/ep01.mp4

O render roda `blender/render_episode.py` (Blender instalado, ou o módulo `bpy` do Python). A montagem usa o ffmpeg:
H.264 yuv420p, 60 fps, AAC 192 kb/s, `+faststart` (pronto para o TikTok). O vídeo só sai completo se houver TODOS os quadros;
`--allow-partial` segura o último quadro renderizado onde faltar (prévia).
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .timeline import FPS, ROOT


def _timeline(ep: str, root: Path) -> dict:
    p = root / ep / "build" / f"{ep}.timeline.json"
    if not p.exists():
        raise SystemExit(f"{p} não existe: rode `python -m pipeline build {ep}` antes")
    return json.loads(p.read_text(encoding="utf-8"))


def blender_command(args, root: Path = ROOT) -> list[str]:
    script = str(root / "blender" / "render_episode.py")
    if getattr(args, "python", None):
        return [args.python, script]
    exe = getattr(args, "blender", None) or os.environ.get("BLENDER") or shutil.which("blender")
    if exe:
        return [exe, "-b", "-P", script, "--"]
    if importlib.util.find_spec("bpy") is not None:
        return [sys.executable, script]
    raise SystemExit("não achei o Blender: instale-o (blender no PATH, ou --blender CAMINHO / variável BLENDER) "
                     "ou use um Python com o módulo bpy (--python CAMINHO)")


def frame_range(args, n: int) -> tuple[int, int]:
    first, last = args.first, (n - 1 if args.last is None else min(args.last, n - 1))
    if args.chunks:
        if not 0 <= args.chunk < args.chunks:
            raise SystemExit("--chunk precisa estar entre 0 e --chunks-1")
        size = -(-(last - first + 1) // args.chunks)
        first, last = first + args.chunk * size, min(last, first + (args.chunk + 1) * size - 1)
    return first, last


def run_render(args, root: Path = ROOT) -> int:
    tl = _timeline(args.episode, root)
    first, last = frame_range(args, tl["frames"])
    cmd = blender_command(args, root) + ["--episode", args.episode, "--out", str(Path(args.out).resolve()),
                                         "--width", str(args.width), "--samples", str(args.samples), "--device", args.device,
                                         "--first", str(first), "--last", str(last), "--step", str(args.step)]
    if args.height:
        cmd += ["--height", str(args.height)]
    if getattr(args, "backend", "auto") != "auto":
        cmd += ["--backend", args.backend]
    if args.threads:
        cmd += ["--threads", str(args.threads)]
    if args.bench:
        cmd += ["--bench", str(args.bench)]
    if args.overwrite:
        cmd += ["--overwrite"]
    if args.textures_dir:
        cmd += ["--textures-dir", args.textures_dir]
    print(" ".join(cmd))
    if args.dry_run:
        return 0
    return subprocess.run(cmd, cwd=root).returncode


def _frames_on_disk(folder: Path) -> dict[int, Path]:
    out = {}
    for f in folder.glob("f*.png"):
        try:
            out[int(f.stem[1:]) - 1] = f                      # f00001 = quadro 0 do CSV
        except ValueError:
            continue
    return out


def run_assemble(args, root: Path = ROOT) -> int:
    ep = args.episode
    tl = _timeline(ep, root)
    n = tl["frames"]
    folder = Path(args.renders).resolve() / ep
    have = _frames_on_disk(folder)
    missing = [k for k in range(n) if k not in have]
    audio = Path(args.audio) if args.audio else root / ep / "build" / f"{ep}.mix.wav"
    out = Path(args.out).resolve() / f"{ep}{args.suffix}.mp4"
    print(f"{ep}: {len(have)}/{n} quadros em {folder} · áudio {audio.name if audio.exists() else 'AUSENTE'}")
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg não encontrado no PATH")
    if not have:
        raise SystemExit("nenhum quadro renderizado: rode `python -m pipeline render` antes")
    if missing and not args.allow_partial:
        raise SystemExit(f"faltam {len(missing)} de {n} quadros (primeiro: {missing[0]}); termine o render ou use --allow-partial "
                         f"(segura o último quadro renderizado: serve só de prévia)")
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if not missing:
        cmd += ["-framerate", str(FPS), "-start_number", "1", "-i", str(folder / "f%05d.png")]
    else:                                                      # quadros esparsos: o ffconcat segura cada um até o próximo
        keys = sorted(have)
        lst = folder / "_concat.txt"
        with open(lst, "w", encoding="utf-8") as f:
            for i, k in enumerate(keys):
                nxt = keys[i + 1] if i + 1 < len(keys) else n
                f.write(f"file '{have[k].as_posix()}'\nduration {(nxt - (0 if i == 0 else k)) / FPS:.6f}\n")
            f.write(f"file '{have[keys[-1]].as_posix()}'\n")
        cmd += ["-f", "concat", "-safe", "0", "-i", str(lst)]
    have_audio = audio.exists()
    if have_audio:
        cmd += ["-i", str(audio)]
    vf = ["scale=1080:1920:flags=lanczos"] if args.upscale else []
    if missing:                                            # o ffconcat perde o último quadro: segura o final e `-t` fecha a conta exata
        vf.append("tpad=stop_mode=clone:stop_duration=1")
    cmd += (["-vf", ",".join(vf)] if vf else []) + ["-r", str(FPS), "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
                                                   "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if have_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    cmd += ["-frames:v", str(n), "-t", f"{n / FPS + 0.05:.6f}", str(out)]       # n quadros exatos; o -t só apara o áudio no fim
    r = subprocess.run(cmd)
    if r.returncode:
        return r.returncode
    info = probe(out)
    print(f"-> {out} · {info}")
    return 0


def probe(path: Path) -> str:
    try:
        o = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height,r_frame_rate,nb_read_frames,duration", "-of", "json", str(path)],
                           capture_output=True, text=True, check=True).stdout
        s = json.loads(o)["streams"][0]
        return f"{s['width']}x{s['height']} · {s['r_frame_rate']} · {s['nb_read_frames']} quadros · {float(s['duration']):.3f} s"
    except Exception as e:                                     # pragma: no cover
        return f"(ffprobe falhou: {e})"
