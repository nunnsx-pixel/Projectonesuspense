#!/usr/bin/env bash
# Do zero ao mp4 final dos 3 episódios, numa máquina Linux com GPU e o Blender instalado.
#
#   ./render_tudo.sh                       # 1080x1920, 96 amostras, os 3 episódios
#   EPS="ep01" ./render_tudo.sh            # só um episódio
#   BENCH=1 ./render_tudo.sh               # só mede s/quadro (6 quadros) e projeta as horas; não renderiza
#   SAMPLES=48 WIDTH=720 ./render_tudo.sh  # mais barato (a montagem amplia para 1080x1920 se usar --upscale)
#   BLENDER=/opt/blender/blender ./render_tudo.sh
#   DRY_RUN=1 ./render_tudo.sh             # só mostra os comandos
#
# Antes: ponha os áudios de voz em ep01/audio, ep02/audio e ep03/audio (os mesmos 11 .mp3 da gravação) OU, se já tem a
# mixagem pronta, copie ep01.mix.wav, ep02.mix.wav e ep03.mix.wav para ep0X/build/ (este script não refaz a mix se o .wav existir).
# O render é retomável: se cair, rode de novo e ele continua dos quadros que faltam.
set -euo pipefail
cd "$(dirname "$0")"

EPS="${EPS:-ep01 ep02 ep03}"
SAMPLES="${SAMPLES:-96}"
WIDTH="${WIDTH:-1080}"
BLENDER_ARGS=()
[ -n "${BLENDER:-}" ] && BLENDER_ARGS=(--blender "$BLENDER")

run() { echo "+ $*"; [ -n "${DRY_RUN:-}" ] || "$@"; }

run python3 blender/tools/fetch_textures.py                       # texturas CC0 (Poly Haven); sem elas vale o procedural
for ep in $EPS; do
  run python3 -m pipeline build "$ep" --strict
  if [ ! -f "$ep/build/$ep.mix.wav" ]; then
    run python3 -m pipeline mix "$ep"
  fi
  if [ -n "${BENCH:-}" ]; then
    run python3 -m pipeline render "$ep" --width "$WIDTH" --samples "$SAMPLES" --bench 6 ${BLENDER_ARGS[@]+"${BLENDER_ARGS[@]}"}
    continue
  fi
  run python3 -m pipeline render "$ep" --width "$WIDTH" --samples "$SAMPLES" ${BLENDER_ARGS[@]+"${BLENDER_ARGS[@]}"}
  if [ "$WIDTH" -lt 1080 ]; then
    run python3 -m pipeline assemble "$ep" --upscale
  else
    run python3 -m pipeline assemble "$ep"
  fi
  echo "pronto: out/$ep.mp4"
done
