"""Uso:  python -m pipeline build ep01 [--strict]   |   python -m pipeline audio ep01 [--dry-run] [--strict]"""
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
    a.add_argument("--strict", action="store_true", help="falha (exit 1) se houver avisos (da análise ou do build)")
    args = ap.parse_args(argv)

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
