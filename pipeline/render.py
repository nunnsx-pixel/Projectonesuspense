"""Render e montagem do vídeo final de um episódio.

  python -m pipeline render ep01 [--width 1080 --samples 96 --device auto]     # sequência de imagens em renders/ep01/
  python -m pipeline render ep01 --bench 6                                      # mede s/quadro e projeta o tempo total
  python -m pipeline render ep01 --chunks 8 --chunk 3                           # só o 4º de 8 lotes (granja de render)
  python -m pipeline render ep01 --batch 30 --stage /content/stage --out /drive/out/quadros   # Colab: lotes curtos com checkpoint
  python -m pipeline render ep01 --status --out /drive/out/quadros              # quantos quadros já existem
  python -m pipeline assemble ep01                                              # renders + mix.wav -> out/ep01.mp4

LOTES (`--batch N`): o Blender é aberto para N quadros por vez e fechado em seguida (a memória volta ao zero a cada lote), e cada
quadro pronto é gravado de forma atômica na pasta final (`--out`, p.ex. o Google Drive). Com `--stage` o Blender grava numa pasta
LOCAL rápida e cada lote é copiado para a pasta final antes do próximo. O que falta é sempre recalculado do que já está na pasta
final, então depois de uma queda basta rodar o mesmo comando: ele continua do primeiro quadro que falta. Lote que falha (falta
de memória, Blender morto) é repetido com metade dos quadros.

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
import time
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


def _common_args(args, first: int, last: int) -> list[str]:
    cmd = ["--episode", args.episode, "--width", str(args.width), "--samples", str(args.samples), "--device", args.device,
           "--first", str(first), "--last", str(last), "--step", str(args.step)]
    if args.height:
        cmd += ["--height", str(args.height)]
    if getattr(args, "backend", "auto") != "auto":
        cmd += ["--backend", args.backend]
    if getattr(args, "perfil", ""):
        cmd += ["--perfil", args.perfil]
    if args.threads:
        cmd += ["--threads", str(args.threads)]
    if args.textures_dir:
        cmd += ["--textures-dir", args.textures_dir]
    return cmd


def _spawn(cmd: list[str], cwd: Path) -> int:
    """Roda um lote (tests trocam esta função por uma falsa)."""
    return subprocess.run(cmd, cwd=cwd).returncode


def png_ok(path: Path) -> bool:
    """PNG inteiro? (assinatura no começo e o bloco IEND no fim: um arquivo cortado no meio da gravação falha aqui)."""
    try:
        if path.stat().st_size < 67:
            return False
        with open(path, "rb") as f:
            if f.read(8) != b"\x89PNG\r\n\x1a\n":
                return False
            f.seek(-12, 2)
            return f.read(12) == b"\x00\x00\x00\x00IEND\xaeB`\x82"
    except OSError:
        return False


def sync_stage(stage: Path, final: Path) -> list[int]:
    """Move os quadros prontos da pasta local para a final (copia para `.part`, confere o tamanho e renomeia: nunca deixa
    quadro pela metade na pasta final). Devolve os quadros que chegaram. Quadro corrompido na pasta local é descartado."""
    got = []
    for src in sorted(stage.glob("f*.png")):
        try:
            k = int(src.stem[1:]) - 1
        except ValueError:
            continue
        if not png_ok(src):
            src.unlink(missing_ok=True)
            continue
        dst = final / src.name
        part = final / (src.name + ".part")
        shutil.copyfile(src, part)
        if part.stat().st_size != src.stat().st_size:
            part.unlink(missing_ok=True)
            continue
        os.replace(part, dst)
        src.unlink(missing_ok=True)
        got.append(k)
    for stray in stage.glob("_w*.png"):                      # sobra de um Blender morto no meio de um quadro
        stray.unlink(missing_ok=True)
    return got


def memory_line() -> str:
    """RAM e VRAM em uso (para o log: mostra se a queda foi falta de memória)."""
    parts = []
    try:
        info = {k: int(v.split()[0]) for k, v in (ln.split(":", 1) for ln in open("/proc/meminfo", encoding="utf-8"))
                if k in ("MemTotal", "MemAvailable")}
        parts.append(f"RAM {(info['MemTotal'] - info['MemAvailable']) / 1048576:.1f}/{info['MemTotal'] / 1048576:.1f} GB")
    except (OSError, KeyError, ValueError):
        pass
    try:
        import resource
        parts.append(f"pico do Blender {resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1048576:.1f} GB")
    except (ImportError, OSError):
        pass
    if shutil.which("nvidia-smi"):
        try:
            o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, timeout=10).stdout.split(",")
            parts.append(f"VRAM {int(o[0]) / 1024:.1f}/{int(o[1]) / 1024:.1f} GB")
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            pass
    return " · ".join(parts)


def run_status(args, root: Path = ROOT) -> int:
    tl = _timeline(args.episode, root)
    n = tl["frames"]
    final = Path(args.out).resolve() / args.episode
    have = _frames_on_disk(final) if final.exists() else {}
    target = list(range(args.first, (n - 1 if args.last is None else min(args.last, n - 1)) + 1, args.step))
    done = sum(1 for k in target if k in have)
    print(f"{args.episode}: {done}/{len(target)} quadros ({100 * done / max(len(target), 1):.0f}%) em {final}")
    log = final.parent / f"{args.episode}.log"
    if log.exists():
        lines = log.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            print(f"último registro: {lines[-1]}")
    return 0


def _batched(args, root: Path, n: int, first: int, last: int) -> int:
    ep = args.episode
    final = Path(args.out).resolve() / ep
    stage = Path(args.stage).resolve() / ep if args.stage else None
    final.mkdir(parents=True, exist_ok=True)
    if stage:
        stage.mkdir(parents=True, exist_ok=True)
        sync_stage(stage, final)                             # sobras da área local (a célula foi interrompida no meio)
    have = set(_frames_on_disk(final))
    target = list(range(first, last + 1, args.step))
    base = blender_command(args, root) + _common_args(args, first, last)
    out_arg = str(Path(args.stage).resolve() if stage else Path(args.out).resolve())
    log = final.parent / f"{ep}.log"
    batch, failures, t0, start_done = args.batch, 0, time.time(), sum(1 for k in target if k in have)
    print(f"[LOTE] {ep}: {start_done}/{len(target)} quadros já prontos em {final}")
    while True:
        todo = [k for k in target if k not in have]
        if not todo:
            break
        part = todo[:batch]
        cmd = base + ["--out", out_arg, "--frames", ",".join(str(k) for k in part)]
        print(f"[LOTE] quadros {part[0]}..{part[-1]} ({len(part)}) · faltam {len(todo)}", flush=True)
        if args.dry_run:
            print(" ".join(cmd))
            return 0
        t1 = time.time()
        rc = _spawn(cmd, root)
        if stage:
            sync_stage(stage, final)
        new = {k for k in part if (final / f"f{k + 1:05d}.png").exists()}
        have |= new
        done_now = sum(1 for k in target if k in have)
        per = (time.time() - t1) / max(len(new), 1)
        line = (f"{time.strftime('%Y-%m-%d %H:%M:%S')} {ep} lote de {len(part)} · +{len(new)} quadros · {done_now}/{len(target)} · "
                f"{per:.1f} s/quadro · {memory_line()}")
        print(f"[LOTE] {line}", flush=True)
        try:
            with open(log, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
        if rc != 0 or not new:
            failures += 1
            batch = max(4, batch // 2)
            print(f"[LOTE] o lote falhou (código {rc}); tentativa {failures}/{args.retries}; o próximo terá {batch} quadros", flush=True)
            if failures >= args.retries:
                print(f"[LOTE] desisti depois de {failures} falhas seguidas; rode o mesmo comando para retomar do quadro {todo[0]}")
                return rc or 1
        else:
            failures, batch = 0, min(args.batch, batch * 2)
    print(f"[LOTE] {ep}: todos os {len(target)} quadros prontos ({(time.time() - t0) / 60:.0f} min nesta rodada)")
    return 0


def run_render(args, root: Path = ROOT) -> int:
    if getattr(args, "status", False):
        return run_status(args, root)
    tl = _timeline(args.episode, root)
    first, last = frame_range(args, tl["frames"])
    if getattr(args, "batch", 0) and not args.bench:
        return _batched(args, root, tl["frames"], first, last)
    cmd = blender_command(args, root) + _common_args(args, first, last) + ["--out", str(Path(args.out).resolve())]
    if args.bench:
        cmd += ["--bench", str(args.bench)]
    if args.overwrite:
        cmd += ["--overwrite"]
    print(" ".join(cmd))
    if args.dry_run:
        return 0
    return _spawn(cmd, root)


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
    step = max(getattr(args, "step", 1), 1)                       # --step 2: o render foi a 30 fps (quadros 0, 2, 4...) e o mp4 também
    expected = list(range(0, n, step))
    missing = [k for k in expected if k not in have]
    fps_out = FPS // step
    audio = Path(args.audio) if args.audio else root / ep / "build" / f"{ep}.mix.wav"
    out = Path(args.out).resolve() / f"{ep}{args.suffix}.mp4"
    print(f"{ep}: {sum(1 for k in expected if k in have)}/{len(expected)} quadros ({fps_out} fps) em {folder} · áudio {audio.name if audio.exists() else 'AUSENTE'}")
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg não encontrado no PATH")
    if not have:
        raise SystemExit("nenhum quadro renderizado: rode `python -m pipeline render` antes")
    if missing and not args.allow_partial:
        raise SystemExit(f"faltam {len(missing)} de {len(expected)} quadros (primeiro: {missing[0]}); termine o render ou use --allow-partial "
                         f"(segura o último quadro renderizado: serve só de prévia)")
    out.parent.mkdir(parents=True, exist_ok=True)
    stage = getattr(args, "stage", None)
    work_dir = Path(stage).resolve() if stage else out.parent
    work_dir.mkdir(parents=True, exist_ok=True)
    part = work_dir / (out.name + ".part")                        # codifica num .part e só renomeia quando termina: mp4 existente = mp4 inteiro
    cmd = ["ffmpeg", "-v", "error", "-y"]
    concat = bool(missing) or step > 1
    if not concat:
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
    if concat:                                             # o ffconcat perde o último quadro: segura o final e `-t` fecha a conta exata
        vf.append("tpad=stop_mode=clone:stop_duration=1")
    cmd += (["-vf", ",".join(vf)] if vf else []) + ["-r", str(fps_out), "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
                                                   "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if getattr(args, "maxrate", None):                     # teto de bitrate (ex.: 1500k): mantém o arquivo pequeno
        cmd += ["-maxrate", args.maxrate, "-bufsize", f"{2 * int(args.maxrate.rstrip('kK'))}k"]
    if have_audio:
        cmd += ["-c:a", "aac", "-b:a", getattr(args, "audio_bitrate", "192k"), "-ar", "48000"]
    cmd += ["-frames:v", str(len(expected)), "-t", f"{n / FPS + 0.05:.6f}", "-f", "mp4", str(part)]   # n quadros exatos; o -t só apara o áudio no fim
    r = subprocess.run(cmd)
    if r.returncode:
        part.unlink(missing_ok=True)
        return r.returncode
    if stage:
        shutil.copyfile(part, out.with_name(out.name + ".part"))
        part.unlink(missing_ok=True)
        part = out.with_name(out.name + ".part")
    os.replace(part, out)
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
