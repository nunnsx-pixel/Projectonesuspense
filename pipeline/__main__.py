"""Uso:  python -m pipeline build ep01 [--strict]   |   python -m pipeline audio ep01 [--dry-run] [--strict]
       python -m pipeline mix ep01 [--no-voice]   |   python -m pipeline render ep01 [...]   |   python -m pipeline assemble ep01 [...]"""
from __future__ import annotations

import argparse
import sys

from .build import build_episode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="gera ep0X/build/ a partir das fontes")
    b.add_argument("episode", help="id do episódio, ex.: ep01")
    b.add_argument("--strict", action="store_true", help="falha (exit 1) se houver avisos")
    a = sub.add_parser("audio", help="mede a voz real em ep0X/audio/, grava narration.measured.json e roda o build")
    a.add_argument("episode", help="id do episódio, ex.: ep01")
    a.add_argument("--audio-dir", help="pasta dos áudios (padrão: ep0X/audio)")
    a.add_argument("--dry-run", action="store_true", help="só mostra a análise; não grava nem roda o build")
    a.add_argument("--no-build", action="store_true", help="grava o measured.json mas não roda o build")
    a.add_argument("--force", action="store_true", help="sobrescreve um narration.measured.json escrito à mão (guarda .bak)")
    a.add_argument("--min-pause-ms", type=float, help="menor silêncio interno que vira âncora de palavra (padrão 100)")
    a.add_argument("--keep-on-error", action="store_true", help="mantém o measured.json mesmo se o build falhar com ele")
    a.add_argument("--strict", action="store_true", help="falha (exit 1) se houver avisos (da análise ou do build)")
    m = sub.add_parser("mix", help="mixa voz medida + SFX sintetizados -> ep0X/build/ep0X.mix.wav")
    m.add_argument("episode", help="id do episódio, ex.: ep01")
    m.add_argument("--no-voice", action="store_true", help="só os SFX (sem a voz de ep0X/audio)")
    r = sub.add_parser("render", help="renderiza o episódio em sequência de imagens (Blender; retomável, em lotes, com --bench)")
    r.add_argument("episode", help="id do episódio, ex.: ep01")
    r.add_argument("--out", default="renders", help="pasta das sequências (padrão: renders/)")
    r.add_argument("--width", type=int, default=1080)
    r.add_argument("--height", type=int, help="padrão: 16/9 da largura (1920 para 1080)")
    r.add_argument("--samples", type=int, default=96)
    r.add_argument("--device", default="auto", choices=("auto", "cpu", "gpu"))
    r.add_argument("--backend", default="auto", choices=("auto", "optix", "cuda", "hip", "metal", "oneapi"),
                   help="API da GPU (auto = a melhor disponível; no Colab, cuda é a aposta segura)")
    r.add_argument("--perfil", default="", choices=("", "t4"), help="perfil de memória (t4 = GPU T4 do Colab: ladrilhos 512, texturas 1k)")
    r.add_argument("--batch", type=int, default=0, help="quadros por lote: abre o Blender, renderiza N quadros e fecha (retomável; 0 = tudo de uma vez)")
    r.add_argument("--stage", help="pasta LOCAL rápida: o Blender grava aqui e cada lote é copiado para --out (use com o Google Drive)")
    r.add_argument("--retries", type=int, default=6, help="falhas seguidas de lote antes de desistir (cada falha reduz o lote à metade)")
    r.add_argument("--status", action="store_true", help="só mostra quantos quadros já existem em --out e o último registro do log")
    r.add_argument("--threads", type=int, default=0)
    r.add_argument("--first", type=int, default=0, help="1º quadro (0 = início do CSV)")
    r.add_argument("--last", type=int, help="último quadro (padrão: o último do episódio)")
    r.add_argument("--step", type=int, default=1, help="1 a cada K quadros (prévia)")
    r.add_argument("--chunks", type=int, help="divide o episódio em N lotes contíguos (granja de render)")
    r.add_argument("--chunk", type=int, default=0, help="qual lote renderizar (0..chunks-1)")
    r.add_argument("--bench", type=int, default=0, help="renderiza N quadros espalhados, mede e projeta o tempo total")
    r.add_argument("--overwrite", action="store_true", help="refaz quadros que já existem (padrão: retoma)")
    r.add_argument("--textures-dir", help="pasta de texturas (padrão: blender/textures)")
    r.add_argument("--blender", help="executável do Blender (padrão: $BLENDER ou o do PATH)")
    r.add_argument("--python", help="Python com o módulo bpy (alternativa ao executável do Blender)")
    r.add_argument("--dry-run", action="store_true", help="só mostra o comando")
    v = sub.add_parser("assemble", help="monta o mp4 (renders + mix.wav) com o ffmpeg e confere o arquivo")
    v.add_argument("episode", help="id do episódio, ex.: ep01")
    v.add_argument("--renders", default="renders", help="pasta das sequências (padrão: renders/)")
    v.add_argument("--out", default="out", help="pasta dos vídeos (padrão: out/)")
    v.add_argument("--audio", help="áudio mixado (padrão: ep0X/build/ep0X.mix.wav)")
    v.add_argument("--stage", help="pasta LOCAL: o ffmpeg codifica aqui e o mp4 pronto é copiado para --out (use com o Google Drive)")
    v.add_argument("--suffix", default="", help="sufixo do nome do arquivo (ex.: .previa -> out/ep01.previa.mp4)")
    v.add_argument("--allow-partial", action="store_true", help="aceita quadros faltando (segura o último): só prévia")
    v.add_argument("--upscale", action="store_true", help="amplia quadros pequenos para 1080x1920 (prévia)")
    v.add_argument("--preset", default="slow", help="preset do x264 (padrão: slow)")
    v.add_argument("--crf", type=int, default=16, help="qualidade do x264 (padrão: 16)")
    args = ap.parse_args(argv)

    if args.cmd == "render":
        from .render import run_render
        return run_render(args)
    if args.cmd == "assemble":
        from .render import run_assemble
        return run_assemble(args)
    if args.cmd == "mix":
        from .mix import run as run_mix
        return run_mix(args)
    if args.cmd == "audio":
        from .audio import run
        return run(args)
    tl = build_episode(args.episode)
    print(f"{tl['episode']}: {tl['frames']} frames @{tl['fps']}fps -> {args.episode}/build/")
    for s in tl["scenes"]:
        f = s["narration_fit"]
        print(f"  {s['id']}  fala {f['articulation_syl_s']:>5} sil/s (alvo {f['pace_target_syl_s']}) "
              f"· precisa {f['needed_s_at_target_pace']:>5}s / cabe {f['available_s']:>5}s · {f['status']}")
    for w in tl["warnings"]:
        print(f"  AVISO: {w}")
    return 1 if (args.strict and tl["warnings"]) else 0


if __name__ == "__main__":
    sys.exit(main())
