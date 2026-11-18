"""Medidas do ônibus e do cenário (metros, Z para cima). Sem bpy: usado pelas cenas e pelos testes.

Eixos do ônibus: +Y = frente, +X = direita, -X = esquerda. Pára-brisa em y=0; fundo em y=-10.5.
Direção (heading) em graus: 0 = frente (+Y), 90 = direita (+X), 180 = fundo, 270 = esquerda (-X).
O protagonista senta na 4ª fileira, banco da JANELA da esquerda; a mochila fica no banco do corredor,
à direita dele; a porta de embarque e a catraca ficam à direita, logo atrás da cabine do motorista.
"""
from __future__ import annotations

FLOOR_Z = 0.96                    # piso interno do ônibus (3 degraus de 0,32 m desde a plataforma)
CEIL_Z = FLOOR_Z + 2.15
HALF_W = 1.30
Y_FRONT, Y_REAR = 0.0, -10.5
AISLE_HALF = 0.30
ROW_Y = [-3.40 - 0.85 * i for i in range(9)]          # fileiras 1..9 (a 4ª = -5.95)
SEAT_X = {"left_window": -0.95, "left_aisle": -0.55, "right_aisle": 0.55, "right_window": 0.95}
MY_ROW = 4
MY_SEAT = (SEAT_X["left_window"], ROW_Y[MY_ROW - 1])           # protagonista (janela esquerda)
BAG_SEAT = (SEAT_X["left_aisle"], ROW_Y[MY_ROW - 1])           # mochila (banco ao lado, à direita dele)
DRIVER = (-0.95, -1.45)                                         # banco do motorista
DOOR_Y, DOOR_HALF = -1.0, 0.5                                   # porta na parede direita (x=+1,30)
STAIRS = [(2.55, 0.32), (2.05, 0.64), (1.55, 0.96)]             # (x do contato do pé, altura do degrau)
CATRACA_DOOR = (0.95, DOOR_Y)                                   # catraca FIXA nos 3 episódios: ao pé da porta, na frente
# Divisória (parapeito) logo atrás da catraca/cabine: o Ep. 3 recua 2 passos e bate as costas nela.
# Cobre o lado esquerdo (do motorista até a borda do corredor), deixando o corredor livre.
DIVIDER_Y, DIVIDER_T, DIVIDER_H = -2.95, 0.08, 1.05
DIVIDER_X = (-HALF_W, -AISLE_HALF - 0.02)

# ---- Bancos e altura dos olhos sentado (m acima do piso do ônibus) -------------------------------------------
# Ergonomia: olhos ~0,83 m acima da almofada e ~5 cm ACIMA do topo dos encostos/apoios de cabeça à frente,
# de modo que os bancos ficam ligeiramente abaixo da linha de visão. Ao sentar ele AFUNDA na almofada
# (SEAT_SINK) e se acomoda de volta; o baque da câmera (k-sentar) acompanha o pouso.
SEAT_CUSHION_TOP = 0.51
SEAT_BACK_H, HEADREST_H = 0.62, 0.16
SEAT_BACK_TOP = SEAT_CUSHION_TOP + SEAT_BACK_H                  # 1,13
HEADREST_TOP = SEAT_BACK_TOP + HEADREST_H                       # 1,29
EYE_ABOVE_HEADREST = 0.05
SEAT_SINK = 0.04
EYE_STAND, EYE_RUN = 1.62, 1.55
EYE_SEAT = round(HEADREST_TOP + EYE_ABOVE_HEADREST, 3)          # 1,34
LAST_SEAT = (0.0, ROW_Y[-1] - 0.05)                             # banco do fundo (silhueta)
