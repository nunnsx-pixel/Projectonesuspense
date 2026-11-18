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
  `step`; e, quando o CSV tem (Ep. 2 e 3): `light` (luz do ônibus, 1 = normal, com as quedas de falha
  elétrica), `motion_blur`, `bump` (batida da estrada) e `red_fog` (brilho da neblina vermelha da porta,
  0..1). `black`, `step`, `light` e `bump` são degraus (sem interpolar); os demais são lineares.
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

## Montar a cena do episódio (greybox)

Além de importar só a câmera, `assemble_scene.py` **monta a cena inteira** de um episódio — ônibus, cenário,
personagens, luz e efeitos de tela — a partir da timeline sincronizada. É um *greybox* low-poly estilizado, feito
para você **trocar pelos assets finais** (mantenha os nomes `ONIBUS`, `POV_Head` e `Camera`).

```
python -m pipeline build ep02            # gera build/ (timeline.json + camera.csv), se ainda não existir
blender -b -P blender/assemble_scene.py -- --episode ep02 --save ep02.blend
# prévias (Cycles/CPU, ~15 s por quadro a 270x480):
blender -b -P blender/assemble_scene.py -- --episode ep03 --render-frames 23.5,46.0,53.2 --out previews
```

**O que entra na cena**

| Peça | Como é feita |
|---|---|
| `ONIBUS` (empty) | Pai do ônibus e da cabeça. **Anda** pela integral do `speed_kmh` do CSV (Ep. 1: parado até a partida em 41,9 s; Ep. 2 e 3: estrada de terra, ~600–800 m). O cenário externo é fixo: as luzes/árvores/placa passam pela janela. |
| `POV_Head` (empty) | **Caminho-base da cabeça**: posição, altura dos olhos e direção. O avanço dos trechos a pé nasce dos **passos do CSV** (mesmos do SFX): o pé "planta" nos frames certos. Os trajetos ficam em `pov_scene/routes.py` (Python puro, testado sem Blender). |
| `Camera` | Filha do `POV_Head`; só recebe balanço e olhar do CSV (importador) e o FOV (vertical 80°). |
| Luz do ônibus | Tubos e luzes do teto ligados ao canal `light` por driver: a queda de luz do CSV apaga tudo junto. Ep. 1: fixa em 1. |
| Vinheta, pálpebras, preto | Planos na frente da câmera, ligados a `vignette`, `eyelid` e `black` por driver (sem compositor, que mudou de API entre o 4.x e o 5.x). |
| Adereços e personagens | Mãos POV (com tremor), celular (texto real: `23:47 / 14%`, `SEM SERVIÇO / 00:00`), bilhete, mochila preta com crachá (no Ep. 2, empoeirada, com teias), motorista (acena no Ep. 1; gira o pescoço em 3 trancos nos 3 estalos no Ep. 3), passageiro do fundo e seu duplo em decomposição (Ep. 3), catraca que gira no `catraca-giro`, portas pneumáticas, abismo vermelho com 34 mãos pálidas, placa **348 riscada**. Tudo entra e sai nos instantes dos beats. |
| Marcadores | `CENA:`, `BEAT:` e `VOZ:` (com o falante) na timeline; o importador ainda cria `POV:*`. |

**Decisões de montagem que mexem no olhar** (o CSV não foi alterado): o olhar do CSV é *relativo à cabeça*, então a
cena tem que ser coerente com ele. Onde não era, o corpo se move no caminho-base: no Ep. 2 o tronco **gira ~58°**
para o "banco ao lado" e ele **se inclina sobre o corredor** para ver a silhueta no último banco e a nuca do
motorista (dos bancos da janela os encostos bloqueiam a vista). Os testes de `routes.py` comparam a direção
geométrica (motorista, porta, banco, último banco) com o `look_yaw` do CSV.

**Layout fixo nos três episódios (decidido):** a catraca fica **ao pé da porta de embarque, na frente**
(`layout.CATRACA_DOOR`), igual no Ep. 1, 2 e 3. No Ep. 3, quando ele recua e bate as costas, bate na
**divisória/parapeito logo atrás da catraca** (`layout.DIVIDER_*`, cue `costas-divisoria`, trecho `recua-divisoria`).
O passageiro do fundo (duplo) fica parado do outro lado da divisória (`routes.DOUBLE_BEHIND`).

**Interior e figurino (briefing):** poltronas de tecido estampado azul/cinza, balaústres de inox (oxidam nos Ep. 2 e 3), piso
emborrachado escuro antiderrapante, motorista de camisa social azul amarrotada e boné com aba. No Ep. 3 a mandíbula do motorista
**estica** (1× → 3,2×) a cada estalo do pescoço. O duplo usa **o mesmo moletom e a mesma mochila** do protagonista (sentado: mochila no
colo; de pé: nas costas; podres no Ep. 3). Sem contornos pretos (Freestyle desligado; testado).

**Altura dos olhos sentado:** a câmera fica **ligeiramente acima** dos encostos e apoios de cabeça (1,34 m contra
1,29 m), com os bancos um pouco abaixo da linha de visão. Ao sentar, a cabeça **afunda 4 cm** com o baque e se
acomoda de volta em 0,7 s. Constantes em `layout.py`; tabela em [`TEXTURAS.md`](TEXTURAS.md).

**Texturas PBR:** os materiais vêm de [`materials.json`](materials.json) via `pov_scene/materials.py` (procedural por
padrão; conjuntos de imagens em `blender/textures/<id>/` entram sozinhos, com `--textures-dir` para mudar a pasta).
Piso encerado (Ep. 1), estofado mofado e metal enferrujado (Ep. 2 e 3), terra vermelha e neblina rasteira volumétrica
(Ep. 2 e 3). Mapeamento, resoluções, espaços (`bus`/`world`) e passo a passo em [`TEXTURAS.md`](TEXTURAS.md).

**O que NÃO está coberto:** assets finais e texturas fotográficas (os materiais são procedurais; veja `TEXTURAS.md`); `edge_blur` e `motion_blur` do CSV ficam só como
propriedades da câmera (ligue no compositor/pós); áudio (os cues estão nos marcadores/`timeline.json`);
animação de personagem além dos movimentos acima (andar do passageiro, rosto do duplo). A neblina de mundo
e a rasteira (Ep. 3) enevoam levemente o interior do ônibus (volumes não têm paredes).

## Testado

`tests/test_scene_routes.py` (Python puro): o caminho da cabeça (continuidade, passadas humanas, o pé nos frames dos
passos, degraus, sentar junto do baque, geometria × olhar do CSV). `tests/test_blender_scene.py` (precisa de `bpy`):
monta os 3 episódios e confere hierarquia, cabeça × trajeto, drivers de luz/vinheta/pálpebra/preto, marcadores,
visibilidade dos filhos, a catraca/divisória fixas, a altura dos olhos sentado × encostos, os materiais (procedural e conjuntos de imagens) e os bugs que já tivemos. `tests/test_blender_import.py`: a matemática de eixos/sinais roda em qualquer Python; os testes de cena
rodam o importador no Blender **4.2 LTS e 5.3** (módulo `bpy`, sem interface), com os CSVs dos três
episódios: direção do olhar (inclusive +148° e +172° para trás, e o mergulho final do Ep. 3 com pitch −70° e
roll 45°), roll, posição, FOV, flags em degrau, canais extras, marcadores, reimportação, rig existente,
salvar/reabrir o `.blend`.
**Não testado:** o botão *Run Script* da interface e o `blender -b -P` em si (mesmo código, outro
ponto de entrada). Para rodar os testes com Blender: `pip install bpy` e `python -m unittest tests.test_blender_import`.
