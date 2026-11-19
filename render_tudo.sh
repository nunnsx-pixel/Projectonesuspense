#!/usr/bin/env bash
# Do zero ao mp4 final dos 3 episódios, numa máquina Linux com GPU e o Blender instalado.
#
#   ./render_tudo.sh                       # 1080x1920, 96 amostras, os 3 episódios
#   EPS="ep01" ./render_tudo.sh            # só um episódio
#   BENCH=1 ./render_tudo.sh               # só mede s/quadro (6 quadros) e projeta as horas; não renderiza
#   SAMPLES=48 WIDTH=720 ./render_tudo.sh  # mais barato (a montagem amplia para 1080x1920 se usar --upscale)
#   BLENDER=/opt/blender/blender ./render_tudo.sh
#   GPU_BACKEND=cuda ./render_tudo.sh      # força a API da GPU (cuda no Colab; padrão: a melhor disponível)
#   RENDERS_DIR=/pasta/renders OUT_DIR=/pasta/out ./render_tudo.sh   # onde ficam os quadros e os mp4 (ex.: Google Drive)
#   KEEP_FRAMES=0 ./render_tudo.sh         # apaga os quadros de um episódio depois de montar o mp4 (poupa disco)
#   BATCH=30 ./render_tudo.sh              # lotes curtos: abre o Blender a cada 30 quadros (memória volta a zero; cai sem perder nada)
#   STAGE_DIR=/content/stage ./render_tudo.sh   # o Blender grava numa pasta LOCAL e cada lote é copiado para RENDERS_DIR (Drive)
#   PERFIL=t4 ./render_tudo.sh             # poupa RAM/VRAM (ladrilhos 512, texturas 1k, menos rebatidas): GPU T4 do Colab
#   TEXTURES_DIR=/content/textures ./render_tudo.sh   # pasta das texturas (baixadas para lá se faltarem); padrão: blender/textures
#   FORCE=1 ./render_tudo.sh               # refaz o mp4 de um episódio que já está pronto (padrão: pula)
#   DRY_RUN=1 ./render_tudo.sh             # só mostra os comandos
#
# Antes: ponha os áudios de voz em ep01/audio, ep02/audio e ep03/audio (os mesmos 11 .mp3 da gravação) OU, se já tem a
# mixagem pronta, copie ep01.mix.wav, ep02.mix.wav e ep03.mix.wav para ep0X/build/ (este script não refaz a mix se o .wav existir).
# O render é retomável: se cair, rode o MESMO comando de novo. Ele recalcula o que falta a partir da pasta RENDERS_DIR e continua do
# primeiro quadro que falta; episódio cujo mp4 já existe em OUT_DIR é pulado.
set -euo pipefail
cd "$(dirname "$0")"

EPS="${EPS:-ep01 ep02 ep03}"
SAMPLES="${SAMPLES:-96}"
WIDTH="${WIDTH:-1080}"
RENDERS_DIR="${RENDERS_DIR:-renders}"
OUT_DIR="${OUT_DIR:-out}"
KEEP_FRAMES="${KEEP_FRAMES:-1}"
BATCH="${BATCH:-0}"
RETRIES="${RETRIES:-6}"
STAGE_DIR="${STAGE_DIR:-}"
PERFIL="${PERFIL:-}"
FORCE="${FORCE:-0}"
TEXTURES_DIR="${TEXTURES_DIR:-}"
BLENDER_ARGS=()
[ -n "${BLENDER:-}" ] && BLENDER_ARGS=(--blender "$BLENDER")
[ -n "${GPU_BACKEND:-}" ] && BLENDER_ARGS+=(--backend "$GPU_BACKEND" --device gpu)
[ -n "$PERFIL" ] && BLENDER_ARGS+=(--perfil "$PERFIL")
FETCH_ARGS=()
if [ -n "$TEXTURES_DIR" ]; then
  FETCH_ARGS=(--dest "$TEXTURES_DIR")
  BLENDER_ARGS+=(--textures-dir "$TEXTURES_DIR")
fi
RENDER_ARGS=()
[ "$BATCH" -gt 0 ] && RENDER_ARGS+=(--batch "$BATCH" --retries "$RETRIES")
[ -n "$STAGE_DIR" ] && RENDER_ARGS+=(--stage "$STAGE_DIR")
STAGE_ARGS=()
[ -n "$STAGE_DIR" ] && STAGE_ARGS=(--stage "$STAGE_DIR")

run() { echo "+ $*"; [ -n "${DRY_RUN:-}" ] || "$@"; }

run python3 blender/tools/fetch_textures.py ${FETCH_ARGS[@]+"${FETCH_ARGS[@]}"}   # texturas CC0 (Poly Haven); só baixa o que falta
for ep in $EPS; do
  if [ -z "${BENCH:-}" ] && [ "$FORCE" != "1" ] && [ -f "$OUT_DIR/$ep.mp4" ]; then
    echo "já pronto: $OUT_DIR/$ep.mp4 (FORCE=1 para refazer)"
    continue
  fi
  run python3 -m pipeline build "$ep" --strict
  if [ ! -f "$ep/build/$ep.mix.wav" ]; then
    run python3 -m pipeline mix "$ep"
  fi
  if [ -n "${BENCH:-}" ]; then
    run python3 -m pipeline render "$ep" --width "$WIDTH" --samples "$SAMPLES" --bench 6 --out "$RENDERS_DIR" ${BLENDER_ARGS[@]+"${BLENDER_ARGS[@]}"}
    continue
  fi
  run python3 -m pipeline render "$ep" --width "$WIDTH" --samples "$SAMPLES" --out "$RENDERS_DIR" ${RENDER_ARGS[@]+"${RENDER_ARGS[@]}"} ${BLENDER_ARGS[@]+"${BLENDER_ARGS[@]}"}
  UP=()
  [ "$WIDTH" -lt 1080 ] && UP=(--upscale)
  run python3 -m pipeline assemble "$ep" --renders "$RENDERS_DIR" --out "$OUT_DIR" ${STAGE_ARGS[@]+"${STAGE_ARGS[@]}"} ${UP[@]+"${UP[@]}"}
  echo "pronto: $OUT_DIR/$ep.mp4"
  if [ "$KEEP_FRAMES" = "0" ] && [ -f "$OUT_DIR/$ep.mp4" ] && [ -d "$RENDERS_DIR/$ep" ]; then
    find "$RENDERS_DIR/$ep" -maxdepth 1 -name 'f*.png' -delete                 # só os quadros deste episódio, e só depois do mp4
  fi
done
