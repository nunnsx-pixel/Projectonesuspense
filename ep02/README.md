# Episódio 2 — O Despertar no Escuro

Mesma estrutura e mesmos comandos do Ep. 1 (leia `ep01/README.md` para a lógica de âncoras, a convenção de
eixos e como regravar com voz real). Aqui só o que é **novo ou diferente**.

```
python -m pipeline build ep02          # regenera ep02/build/
python -m pipeline build ep02 --strict # sai com erro se houver avisos
python -m unittest discover -s tests   # inclui tests/test_ep02.py
```

Arquivos: `narration.json`, `scenes/s1…s3-*.json`, `sfx.json`, `camera.json` (fontes) e `build/` (gerado:
`ep02.timeline.json`, `ep02.camera.csv`, `ep02.cue-sheet.md`, `ep02.overview.svg`). Comece pelo cue sheet.

## O que o roteiro do Ep. 2 exigiu de novo

- **O BUM é um evento só.** Aos 0,50 s (frame 30), logo após 0,5 s de tela preta, caem no mesmo frame: o SFX
  `bum-buraco`, o chacoalhão da câmera (3 impactos de mola: sobe, sacode para os lados, rebote), o início do
  *motion blur* e a queda total da luz. As pálpebras abrem em 0,55–0,80 s e o gasp vem em 0,60 s.
- **Luz verde com falha elétrica** (`camera.json > flicker`): 5 quedas marcadas à mão (as lâmpadas morrem no
  BUM e voltam falhando) + 51 rajadas aleatórias com semente fixa (mais raras na cena 2, mais frequentes ao
  fim). Cada queda é **o mesmo evento** em três lugares: canal `light` do CSV (1 = normal, 0 = apagada),
  lista `sfx.flicker` (um estalo de falha elétrica no mesmo frame) e o zumbido elétrico de fundo.
- **Terreno irregular** (`camera.json > road`): 96 batidas da estrada em instantes aleatórios (semente fixa),
  mais frequentes na cena 3 (cascalho). Cada batida é um solavanco da câmera (`bump=1` no CSV) **e** um
  SFX (`rangido-chassi`, `batida-suspensao`, `cascalho-batida`) no mesmo frame — as batidas fortes viram
  `batida-suspensao`.
- **Respirações novas:** `gasp` (inspira seco e já grita), `pant` (*huh-huh-huh*: 3 ciclos rápidos) e
  `swallow` (engolir seco). Como o personagem **ofega**, há um respiro antes de cada frase mesmo com pausas
  curtas (`breath_min_gap` por cena).
- **Direções de atuação:** anotações do `.md` que não são som (*Sussurra apavorado*, *Voz falha*) ficam no
  campo `direction` da fala e valem até a próxima anotação.
- **Câmera sentada:** não há passos; o balanço vem do ônibus (vibração, balanço de pista, batidas), da
  respiração/coração acelerados e do tremor. Olhares extremos: para trás (+148°, a silhueta no último banco) e
  a placa passando (−128°).
- **CSV com 3 colunas extras** (pedidas em `csv_extra`): `light`, `motion_blur`, `bump`. O Ep. 1 continua com o
  CSV de sempre.

## Orçamento de fala (todas as cenas cabem)

| Cena | Janela | Fala efetiva | Pretendido | Situação |
|---|---|---|---|---|
| s1 | 0,6–14,2 s | 4,6 sil/s | 5,2 | ok — a fala acaba aos 14,2 s; os 3,8 s finais são silêncio, respiração, luz piscando e rangidos |
| s2 | 18,3–39,2 s | 5,5 sil/s | 5,2 | ok |
| s3 | 40,6–57,6 s | 6,2 sil/s | 6,0 (acelerado) | ok — depois de "ei, motorista!" ficam 2,4 s de silêncio sobre a nuca |

Números e siglas falados (decididos, em `lexicon`): "348" = **três quatro oito**; "GPS" = **gê pê ésse**;
"4G" = **quatro gê**.

## Premissas que assumi (ajuste se discordar)

- **Fim do episódio sem tela preta.** O roteiro diz só "Corte seco" na nuca do motorista (diferente do Ep. 1,
  que diz "preto absoluto"). Como o Ep. 3 abre com o protagonista de pé, o vídeo **termina na nuca**, com um
  zoom lento (FOV −16%) e a câmera quase parada, e o corte é o fim do vídeo. Para forçar preto: `fx.black_ranges`
  em `camera.json`.
- **Continuidade com o Ep. 1:** janela à **esquerda**, banco do corredor (mochila) à **direita**, celular na mão
  **esquerda**. Se os dois episódios forem postados em sequência, há 0,5 s de preto do fim do Ep. 1 + 0,5 s do
  início do Ep. 2 = 1 s.
- **Ônibus:** ~40 km/h na estrada de terra (o Ep. 1 termina a 62 km/h no asfalto; entre eles passam "umas três
  horas"). O motor começa abafado (como no fim do Ep. 1) e abre de uma vez no BUM.
- **Inferidos (podem ser apagados):** o ronco do motor, as quedas de luz como SFX individuais, olhares
  (janela, motorista, teto), 3 piscadas de pálpebra, e a velocidade/zoom da nuca. O que **está** no roteiro:
  baque, metal rangendo, zumbido elétrico, chassi rangendo, vento nas frestas, chiado do celular e cascalho.
- **Distribuição aleatória** das batidas e das rajadas de luz usa semente fixa (`seed` em `camera.json`): é
  reproduzível, mas **mudar a semente muda onde caem**. Se uma batida/queda específica incomodar, é mais
  seguro mover a fala/beat ao redor do que a semente.
