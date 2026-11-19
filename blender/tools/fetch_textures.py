"""Baixa os conjuntos PBR (CC0, Poly Haven) listados em blender/textures_sources.json para blender/textures/.

  python blender/tools/fetch_textures.py [--only terra-vermelha] [--force]

Só biblioteca padrão. Cada conjunto vira blender/textures/<id>/[<variante>/]{albedo,roughness,ao,height,normal[,metallic]}.<ext>
(os nomes que blender/pov_scene/materials.py espera) mais um LICENCA.txt com a origem. Os arquivos de imagem ficam fora do git.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BLENDER = HERE.parent
API = "https://api.polyhaven.com/files/"
UA = {"User-Agent": "projectonesuspense-texture-fetch/1.0"}
ORDER = {"height": ("png", "jpg"), "normal": ("png", "jpg")}          # o resto: jpg primeiro (menor)


def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def fetch_set(mat: str, variant: str, spec: dict, maps: dict, dest_root: Path, force: bool) -> list[str]:
    folder = dest_root / mat / variant if variant else dest_root / mat
    folder.mkdir(parents=True, exist_ok=True)
    files = json.loads(_get(API + spec["slug"]))
    got = []
    for ours, theirs in maps.items():
        if theirs not in files or ours in spec.get("skip", ()):
            continue
        by_res = files[theirs].get(spec["res"]) or files[theirs].get("1k")
        if not by_res:
            continue
        for ext in ORDER.get(ours, ("jpg", "png")):
            if ext in by_res:
                dst = folder / f"{ours}.{ext}"
                if force or not dst.exists():
                    dst.write_bytes(_get(by_res[ext]["url"]))
                got.append(dst.name)
                break
    (folder / "LICENCA.txt").write_text(
        f"CC0 1.0 Universal — Poly Haven\nConjunto: {spec['slug']} ({spec['res']})\n"
        f"Origem: https://polyhaven.com/a/{spec['slug']}\nUsado em: {mat}{'/' + variant if variant else ''}\n"
        f"Baixado por blender/tools/fetch_textures.py (blender/textures_sources.json).\n", encoding="utf-8")
    return got


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="só este material (id do materials.json)")
    ap.add_argument("--force", action="store_true", help="baixa de novo mesmo se o arquivo existir")
    ap.add_argument("--dest", default=str(BLENDER / "textures"))
    a = ap.parse_args(argv)
    src = json.loads((BLENDER / "textures_sources.json").read_text(encoding="utf-8"))
    for mat, variants in src["sets"].items():
        if a.only and a.only != mat:
            continue
        for variant, spec in variants.items():
            got = fetch_set(mat, variant, spec, src["mapas"], Path(a.dest), a.force)
            print(f"{mat}{'/' + variant if variant else ''}: {spec['slug']} {spec['res']} -> {', '.join(got)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
