"""Uso:  python -m pipeline build ep01 [--strict]"""
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
    args = ap.parse_args(argv)

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
