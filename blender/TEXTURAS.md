# Texturas PBR e layout dos bancos — diretrizes

Fonte de verdade dos materiais: [`materials.json`](materials.json). Código: `pov_scene/materials.py`.
Este documento diz **como mapear texturas** e **o que muda** quando você trocar o procedural por imagens.

## Como funciona

```python
materials.get("metal-enferrujado", "enferrujado")     # devolve o material (cacheado)
```

1. Se existir um conjunto em `blender/textures/<id>/[<variante>/]<mapa>.<ext>`, ele é usado.
2. Senão vale o **procedural** (nós do Blender: cor, rugosidade, metalicidade, relevo e verniz), que já substitui o
   cinza em todos os cenários. Cada variante sobrescreve parâmetros (ex.: `mold`, `rust`).
3. A pasta pode ser trocada com `--textures-dir`. O material guarda `pov_source` (`procedural` ou `imagens:...`),
   `pov_variant` e `pov_params` (útil para conferir o que foi aplicado).

## Convenções de arquivo

| Mapa (nome do arquivo) | Espaço de cor | Uso |
|---|---|---|
| `albedo` | **sRGB** | cor base (sem sombra nem brilho embutidos) |
| `roughness` | **Non-Color** | 0 = espelho, 1 = fosco |
| `metallic` | **Non-Color** | 0 = dielétrico, 1 = metal |
| `ao` | **Non-Color** | oclusão ambiente, multiplica o albedo |
| `height` | **Non-Color** | relevo (vira *bump*; 0,5 = nível médio) |
| `normal` | **Non-Color**, **OpenGL** (+Y para cima), tangente | só em malhas com UV (ver abaixo) |

Formatos: `png`, `jpg`, `exr`. Texturas **sem emendas visíveis** (*seamless*). Sem sombras/luzes pintadas.
O carregador usa `colorspace_settings` automaticamente (sRGB só no `albedo`); não converta nada à mão.

## Mapeamento: sempre em metros

O `tile_m` de cada material é o **lado, em metros, de uma repetição da textura**. O greybox usa primitivas
escaladas de forma não uniforme, então o mapeamento é **em caixa (triplanar) escalado por `1/tile_m`**: um metro de
parede tem o mesmo tamanho de textura em qualquer objeto, sem esticar. Ajuste o `tile_m` no manifesto, não o objeto.

Resolução sugerida (a câmera chega perto: celular, estofado, mochila; vídeo final 1080×1920):

| Material | `tile_m` | Resolução por tile | Observação |
|---|---|---|---|
| `piso-encerado` | 1,2 m | 2048² | granilite com juntas; roughness baixo (0,04–0,22) |
| `estofado` | 0,35 m | 1024² | trama fina **com estampa** azul/cinza (losangos desbotados); mofo é máscara no albedo/roughness |
| `piso-emborrachado` | 0,5 m | 2048² | borracha escura com pastilhas em relevo (`height`); desgaste liso nas passagens |
| `camisa-social` | 0,4 m | 1024² | tecido fino; os **vincos** vêm do `height` (relevo suave e largo) |
| `metal-enferrujado` | 0,6 m | 1024² | `metallic` 1 no inox/aço limpo e 0 na ferrugem |
| `terra-vermelha` | 2,0 m | 2048² | com pedriscos no `height`; varia pouco em escala grande |
| `neblina-rasteira` | — | (volume, sem imagem) | ver "Neblina volumétrica" |

### Espaço de coordenadas (não mexa sem ler)

O ônibus anda ~600–800 m por episódio (`ONIBUS` é animado pela velocidade do CSV). Por isso:

- **`bus`** — a textura fica presa ao `ONIBUS` (coordenada de objeto do próprio ônibus): `estofado`, `metal-enferrujado`,
  `piso-emborrachado`, `camisa-social` (o motorista vai dentro do ônibus).
  Com coordenadas de mundo a textura "nadaria" sobre o ônibus enquanto ele anda.
- **`world`** — cenário fixo: `piso-encerado`, `terra-vermelha`, `neblina-rasteira`.

### Greybox × assets finais com UV

- No greybox (caixas/cilindros) vale o mapeamento em caixa acima, e o `normal` é **ignorado** (use `height`).
- Quando entrar o modelo final: faça UV com densidade de texel **uniforme**, mantenha o **nome do material**
  (`<id>.<variante>`), ligue `normal` (tangente, OpenGL) e troque o nó de coordenadas de `Box` para `UV`.
  Mantenha os nomes `ONIBUS`, `POV_Head` e `Camera`.

## Materiais e o que cada cenário pede

- **`piso-encerado`** (Ep. 1, Rodoviária de Campinas): ladrilho de granilite claro e lustroso, com juntas escuras
  finas, marcas de uso, **reflexo nítido das fluorescentes estouradas** (verniz/*coat* ~0,6). Variante `encerado`.
- **`estofado`** (todos): tecido **estampado antigo** de ônibus intermunicipal, em tons de azul e cinza (losangos
  desbotados sobre trama fina; `print_*` no manifesto). `limpo` (Ep. 1); `mofado` (bancos do Ep. 2 e 3);
  `podre` (o banco ao lado dele: espuma amarela exposta, manchas de mofo preto-esverdeado, rasgado). A estampa desbota
  conforme o desgaste (`print_amount` cai).
- **`metal-enferrujado`** (todos): balaústres, degraus, catraca, divisória, volante. **`inox`** (Ep. 1: aço inox
  escovado, quase sem ferrugem); `enferrujado` (Ep. 2 e 3: o inox oxida em manchas); `gasto` e `podre` (reserva).
  Ferrugem laranja-marrom, áspera, **sem brilho metálico**.
- **`piso-emborrachado`** (piso **do ônibus**, todos): borracha **escura antiderrapante** com pastilhas em relevo em grade
  e trechos lustrados onde se pisa. `limpo` (Ep. 1); `sujo` (Ep. 2 e 3: terra seca e poeira nos cantos). Não confundir
  com `piso-encerado`, que é o saguão da rodoviária.
- **`camisa-social`** (motorista): camisa social **azul amarrotada**; `azul` (Ep. 1) e `encardida` (Ep. 2 e 3: suor e
  sujeira amarelados, mais escura). O boné tem aba que sombreia o rosto.
- **`terra-vermelha`** (Ep. 2 e 3): barro seco avermelhado com variação, pedriscos, poças mais escuras e lisas.
  Variantes `terra` (chão) e `estrada` (faixa compactada, mais clara).
- **`neblina-rasteira`** (Ep. 3): volume, abaixo.

## Personagens e continuidade de figurino (briefing)

- **Protagonista (POV):** mãos com manga de moletom escuro. A cor é `props.HOODIE`; a mochila é preta com crachá.
- **O Duplo / passageiro do fundo:** **o mesmo moletom** (`HOODIE`, com capuz e bolso canguru) e **a mesma mochila**
  (preta, com crachá). Sentado na última fileira (Ep. 2 e 3) a mochila fica no colo; de pé (Ep. 3) vai nas costas.
  Em decomposição (Ep. 3) o moletom vira `HOODIE_ROT` (mesma peça desbotada, com mofo e rasgo) e a mochila fica
  empoeirada. As mãos que agarram o ombro usam o mesmo `HOODIE_ROT`.
- **Motorista:** `camisa-social`, boné com aba. No Ep. 3 a pele fica cinza-cadavérica, os olhos brancos sem pupila e
  a **mandíbula estica** (1× → 3,2×) a cada estalo do pescoço (`props.stretch_jaw`), levando o sorriso junto.
- **Sem contornos pretos:** nenhum Freestyle, modificador de contorno ou sombreador *toon* (testado).

## Neblina volumétrica (Ep. 3)

Um cubo (`size_m`) preso ao `ONIBUS` com *Principled Volume*. A densidade é
`density · e^(−z/height_m) · mancha`, onde `z` e o ruído usam **coordenadas de mundo**: a névoa fica no lugar e o
ônibus a atravessa; é mais densa rente ao chão e some com a altura. Soma-se à névoa de mundo emissiva
(`world.fog`), que dá a cor do horizonte. Parâmetros (todos no manifesto): `density`, `height_m`, `noise_scale`,
`color`, `glow`, `size_m`. Dica: se a cena escurecer demais, reduza `density` primeiro; o interior do ônibus fica
levemente enevoado porque o volume não tem paredes (o custo de render sobe ~30%).

## Altura dos olhos sentado (layout dos bancos)

Constantes em `pov_scene/layout.py`, testadas em `tests/test_scene_routes.py` e `tests/test_blender_scene.py`
(valores em metros acima do piso do ônibus):

| Constante | Valor | Significado |
|---|---|---|
| `SEAT_CUSHION_TOP` | 0,51 | topo da almofada |
| `SEAT_BACK_TOP` | 1,13 | topo do encosto |
| `HEADREST_TOP` | 1,29 | topo do apoio de cabeça |
| `EYE_ABOVE_HEADREST` | 0,05 | olhos **ligeiramente acima** dos bancos |
| `EYE_SEAT` | 1,34 | altura dos olhos sentado (0,83 m acima da almofada) |
| `SEAT_SINK` | 0,04 | ao sentar ele **afunda** 4 cm e se acomoda de volta (0,7 s) |

Assim, os encostos e assentos ficam um pouco abaixo da linha de visão, e o pouso da cabeça coincide com o baque
do banco (`k-sentar`). Em pé: `EYE_STAND` = 1,62; correndo: `EYE_RUN` = 1,55. A **catraca é fixa** ao pé da porta
(`CATRACA_DOOR`) nos 3 episódios; a divisória/parapeito logo atrás (`DIVIDER_*`) é onde o Ep. 3 bate as costas.

## Passo a passo: aplicar imagens

1. Gere/baixe um conjunto PBR *seamless* e salve em `blender/textures/<id>/` (ou `<id>/<variante>/`) com os nomes acima.
   Use só conjuntos cuja **licença** permita o uso (bibliotecas CC0 como ambientCG ou Poly Haven são pontos de
   partida comuns; confira a licença de cada pacote e anote a origem em `blender/textures/<id>/LICENCA.txt`).
2. Ajuste `tile_m` em `materials.json` para o tamanho real do padrão.
3. Monte e confira: `blender -b -P blender/assemble_scene.py -- --episode ep02 --render-frames 26.3,45.9 --out previews`.
   O material deve reportar `pov_source = imagens:...`.
4. Rode `python -m unittest discover -s tests` (o teste do manifesto garante que scripts e documentação não saiam do ar).

## Limitações atuais

Texturas procedurais, não fotográficas; sem *displacement* (só *bump*); `normal` só com UV; render em Cycles/CPU
(uma imagem de prévia leva ~15–25 s). `edge_blur` e `motion_blur` do CSV continuam só como propriedades da câmera.
