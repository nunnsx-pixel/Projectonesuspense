# Episódio 3 — O Fim da Linha

Mesma estrutura e mesmos comandos dos Ep. 1 e 2 (veja `ep01/README.md` para a lógica de âncoras e a
convenção de eixos, e `ep02/README.md` para luz, estrada e as colunas extras do CSV). Aqui só o que é
**novo ou diferente**.

```
python -m pipeline build ep03          # regenera ep03/build/
python -m pipeline build ep03 --strict # sai com erro se houver avisos
python -m unittest discover -s tests   # inclui tests/test_ep03.py
```

Arquivos: `narration.json`, `scenes/s1…s3-*.json`, `sfx.json`, `camera.json` (fontes) e `build/` (gerado:
`ep03.timeline.json`, `ep03.camera.csv`, `ep03.cue-sheet.md`, `ep03.overview.svg`). Comece pelo cue sheet.

## O que o roteiro do Ep. 3 exigiu de novo

- **Batimentos cardíacos como SFX.** "Batimentos acelerados crescendo no fundo" é som do roteiro. São
  gerados da **mesma lista de batidas** que faz a câmera pulsar (`sfx.json > heartbeat`): 167 batimentos, de
  150 a 190 bpm e de −30 a −2 dB, cada um no frame do pulso da câmera (o canal `heart` do CSV). O volume
  cresce e a ambiência é abafada (`mix.ambience_gain_db`). O Ep. 1 e o Ep. 2 não usam isso.
- **Dois falantes.** `speaker` em cada fala (padrão: protagonista; o motorista é explícito) e `pace_syl_s`
  próprio por fala: o motorista fala devagar (4,6 sil/s na cena 2, 3,2 sil/s no final), o protagonista
  atropelado de terror. As notas de voz do motorista ("grave, distorcida como rádio antigo ecoando") ficam
  em `speakers` (com `fx_suggestion` de processamento: pitch, banda, distorção, eco), e o chiado de rádio AM
  (`radio-am`) cresce com o giro do pescoço, cola na voz dele e recua quando o protagonista fala.
- **Trechos sem voz de duração fixa** (`silence`): o pescoço do motorista girando (2,0 s: só estalos e rádio)
  e o passageiro vindo do fundo (4,4 s). A fala se encaixa em volta deles.
- **Cambaleio no corredor.** Passos pesados em piso metálico (12 passos, 0,35–6,0 s) com balanço lateral e roll
  muito maiores que no Ep. 1 e 4 agarrões de balaústre (cada um é SFX **e** solavanco de câmera no mesmo
  frame). A estrada é irregular o tempo todo (132 batidas): o ônibus **não reduz a velocidade**.
- **A revelação.** O passageiro do fundo se levanta (42,8 s), anda rápido, e a luz pisca **três vezes** a
  caminho (44,4 / 45,3 / 46,3 s): a última queda de luz, de 9 frames, é a revelação do rosto (46,4 s) e só
  depois vem o grito (46,8 s). A câmera olha 172° para trás o tempo todo.
- **A porta.** O motorista aperta o botão vermelho (51,5 s), a porta chia (51,85 s), a luz cai e a **neblina
  vermelha** sobe até 1,0 em 0,9 s (nova coluna `red_fog` do CSV). A fala do motorista cai com a porta já
  aberta (52,4 s).
- **Final.** A mão podre agarra o ombro aos 57,0 s (logo que o motorista termina), o empurrão leva à porta
  (3 passos) e a câmera despenca girando na neblina (pitch −70°, roll 45°, FOV abrindo). **Corte seco aos
  59,0 s:** tela preta de 59,0 a 60,0 s; o som de freada/metal soa de 59,0 a 59,6 s e **depois há silêncio
  absoluto** (todo o resto corta em 59,0 s; o teste confirma que nenhum som gerado cai depois disso).
- **CSV** com 4 colunas extras: `light`, `motion_blur`, `bump` e `red_fog`.

## Orçamento de fala (todas as cenas cabem; a cena 2 é a mais apertada)

| Cena | Janela | Fala efetiva | Pretendido | Situação |
|---|---|---|---|---|
| s1 | 0,6–19,2 s | 4,8 sil/s | 5,6 | ok (a fala se estica: entre soluços e hiperventilação) |
| s2 | 20,3–41,8 s | 6,1 sil/s | 6,5 | **ok, mas no limite (0,87)** |
| s3 | 42,4–57,0 s | 3,3 sil/s | 6,0 | ok (o protagonista grita alongado; o motorista fala devagar) |

**Cena 2:** são 101 sílabas (o motorista tem 51 e o protagonista responde com 50). Só cabe com o motorista a
4,6 sílabas/s e o pescoço girando em 2,0 s; **mais lento que isso, estoura** (a 3,5 sil/s o ônibus pediria
~28 s para 21,5 s de janela). Se quiser o motorista mais arrastado, é preciso cortar texto (por exemplo "Eu
tenho aula amanhã de manhã!" ou "Você tá louco!"). Falado: "348" = **três quatro oito** e "2019" =
**dois mil e dezenove**.

## Premissas que assumi (ajuste se discordar)

- **Janela e porta.** Continuidade dos Ep. 1 e 2: o protagonista estava na janela da **esquerda**; a porta de
  embarque fica à **direita** da cabine (o olhar para a porta é yaw +56° a +58°). Para a revelação ele olha para
  trás (yaw 172°).
- **"Ele vira para a frente"** (roteiro, cena 3): li como o **protagonista** virando para a frente, de modo
  que o passageiro o agarra "por trás". Se for o passageiro que vira, é só mudar a coreografia do olhar.
- **Corte para preto aos 59,0 s.** O roteiro diz "Corte Seco [00:59]" e "silêncio absoluto e tela preta". Assumi
  que a imagem corta em 59,0 s junto com o som de freada, e que os 0,4 s finais são silêncio com tela preta.
  Trocar o instante: `fx.black_ranges` (camera.json) e o beat `b3-corte`.
- **Inferidos (podem ser apagados):** o ronco do motor, o rangido dos balaústres, as costas na catraca, o clique
  do botão, a mão no ombro, os passos do passageiro, o brilho/falha das lâmpadas como SFX individuais, e todos os
  olhares (porta, para-brisa, motorista). **Do roteiro:** batimentos, passos pesados, chassi, estalo de ossos,
  rádio AM, porta pneumática, vento, murmúrios e a freada com metal retorcendo.
- **Aleatoriedade com semente fixa** (batidas da estrada e rajadas de luz): reproduzível, mas mudar a semente
  muda onde caem. As piscadas da revelação são marcadas à mão (não aleatórias).
