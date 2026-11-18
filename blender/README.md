# Importador de câmera para o Blender

`import_camera_csv.py` leva `ep0X/build/ep0X.camera.csv` (1 linha por frame, 60fps) para a **câmera
principal** do Blender: um keyframe por frame em posição, rotação e FOV, mais os canais de sincronia.

## Passo a passo

1. Gere o CSV: `python -m pipeline build ep01`.
2. Abra a sua cena no Blender e deixe a câmera principal como câmera ativa (ou use `--camera`).
3. **Interface:** no *Text Editor* abra `blender/import_camera_csv.py`, ajuste `CSV_PATH` (caminho
   absoluto é o mais seguro) e clique em *Run Script*.
   **Terminal:**
   ```
   blender cena.blend -b -P blender/import_camera_csv.py -- --csv ep01/build/ep01.camera.csv --save cena.blend
   ```
4. Opções: `--camera NOME`, `--start-frame 1`, `--fov-deg 70` (FOV base; padrão: o da câmera),
   `--step-markers` (marcador em cada pisada), `--keep-render-settings` (não mexer em fps/resolução).

Importar leva alguns segundos (3600 frames x ~14 canais).

## O que acontece na cena

- **Cena:** 60 fps, 1080x1920, frames 1–3600 (o frame 0 do CSV vira o `--start-frame`).
- **Câmera:** transformação *local* keyada. Posição = balanço (`shake_*_cm`, convertido para as unidades
  da cena, respeitando *unit scale*); rotação = olhar + balanço; `lens` acompanha `fov_pct`.
- **`POV_Head`:** se a câmera não tem pai, o script cria este empty na posição atual da câmera e a põe
  como filha. **O caminho-base (corrida, escada, corredor, sentar) você anima no `POV_Head`**; a câmera
  só recebe o balanço e o olhar, por cima. Se a câmera já tem pai (o seu rig), nada é criado, mas esse
  pai precisa seguir a convenção do Blender: +Y frente, +Z cima.
- **Canais de sincronia** como propriedades custom da câmera, keyadas por frame (use em drivers, nós do
  compositor ou materiais): `vignette`, `edge_blur`, `eyelid`, `black`, `breath`, `heart`, `speed_kmh`,
  `step`; e, quando o CSV tem (Ep. 2): `light` (luz do ônibus, 1 = normal, com as quedas de falha elétrica),
  `motion_blur` e `bump` (batida da estrada). `black`, `step`, `light` e `bump` são degraus (sem
  interpolar); os demais são lineares.
- **Marcadores** `POV:s1/s2/s3` (início das cenas), `POV:preto` (início de **cada** tela preta: no Ep. 1 o
  corte final, frame 3571 com início em 1; no Ep. 2 a tela preta inicial, frame 1) e,
  com `--step-markers`, `POV:passo` em cada pisada — são os frames de contato do pé: plante os pés
  da animação do personagem neles, e o som de passo (do `timeline.json`) já cai no mesmo frame.
- **Reimportar é seguro:** a animação anterior da câmera é guardada com *fake user* (não é perdida),
  os marcadores `POV:*` são recriados e o `POV_Head` é reaproveitado.

## Convenção de eixos (CSV → Blender)

| CSV | Blender |
|---|---|
| +X direita / +Y cima / +Z frente (cm) | X / Z / Y (unidades da cena) |
| yaw+ = olha p/ a direita | rotação Z = −yaw |
| pitch+ = olha p/ cima | rotação X = +pitch |
| roll+ = inclina p/ a direita | rotação Y = +roll |

Rotação final = `look_*` + `shake_*`, composta como yaw→pitch→roll e combinada com a correção de
câmera do Blender (a câmera olha para −Z). Os ângulos são keyados em Euler XYZ, contínuos (sem viradas).

## Testado

`tests/test_blender_import.py`: a matemática de eixos/sinais roda em qualquer Python; os testes de cena
rodam o importador no Blender **4.2 LTS e 5.3** (módulo `bpy`, sem interface), com os CSVs do Ep. 1 e do
Ep. 2: direção do olhar (inclusive +148° para trás), roll, posição, FOV, flags em degrau, canais extras,
marcadores, reimportação, rig existente, salvar/reabrir o `.blend`.
**Não testado:** o botão *Run Script* da interface e o `blender -b -P` em si (mesmo código, outro
ponto de entrada). Para rodar os testes com Blender: `pip install bpy` e `python -m unittest tests.test_blender_import`.
