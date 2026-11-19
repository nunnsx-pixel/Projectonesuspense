#!/usr/bin/env bash
# Instala o Blender 4.2 LTS num Linux sem Blender (ex.: Google Colab).
#
#   blender/tools/instalar_blender.sh [PASTA_DO_CACHE] [DESTINO]     # padrão: /content  /content/blender
#
# O .tar.xz baixado fica em PASTA_DO_CACHE (no Colab: uma pasta do Google Drive), então depois de uma queda a reinstalação é só
# descompactar, sem baixar de novo. Se o DESTINO já tem o Blender, não faz nada.
set -euo pipefail
CACHE="${1:-/content}"
DEST="${2:-/content/blender}"

if [ -x "$DEST/blender" ]; then
  echo "Blender já instalado: $("$DEST/blender" -b --version | head -1)"
  exit 0
fi
if [ -z "${SKIP_APT:-}" ] && command -v apt-get >/dev/null 2>&1; then
  apt-get -qq update
  apt-get -qq install -y libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libsm6 libxkbcommon0 libegl1 xz-utils > /dev/null
fi

mkdir -p "$CACHE"
TAR="$CACHE/blender-4.2.tar.xz"
size() { stat -c %s "$1" 2>/dev/null || echo 0; }
if [ "$(size "$TAR")" -lt 100000000 ]; then
  rm -f "$TAR" "$TAR.part"
  ok=0
  for V in 4.2.23 4.2.18 4.2.12 4.2.9 4.2.5 4.2.3; do                         # a 1ª que existir no servidor
    URL="https://download.blender.org/release/Blender4.2/blender-${V}-linux-x64.tar.xz"
    if wget -q --spider "$URL"; then
      echo "baixando o Blender $V ..."
      wget -q "$URL" -O "$TAR.part" && mv "$TAR.part" "$TAR" && ok=1 && break
    fi
  done
  [ "$ok" = 1 ] || { echo "ERRO: não consegui baixar o Blender 4.2 de download.blender.org"; exit 1; }
else
  echo "usando o Blender do cache: $TAR"
fi

tmp="$(mktemp -d)"
tar -xf "$TAR" -C "$tmp"
rm -rf "$DEST"
mv "$tmp"/blender-*-linux-x64 "$DEST"
rmdir "$tmp" 2>/dev/null || true
"$DEST/blender" -b --version | head -1
