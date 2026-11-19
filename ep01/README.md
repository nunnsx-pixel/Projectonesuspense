# Episódio 1 — estrutura de cenas, narração, SFX e câmera POV

Tudo que acontece nos 60 s (3600 frames @60fps, 1080x1920) vive numa **única linha do tempo**.
Voz, respiração, SFX, passos e câmera não têm tempos digitados à mão: eles são **ancorados**
em palavras da fala, em *beats* de cena ou uns nos outros. Mudou a fala? Todo o resto acompanha.

```
python -m pipeline build ep01          # regenera ep01/build/
python -m pipeline build ep01 --strict # sai com erro se houver avisos (ex.: fala que não cabe)
python -m unittest discover -s tests   # 264 testes (93 exigem o módulo bpy; sem ele são pulados)
```

## Arquivos

| Você edita (fonte) | O que é |
|---|---|
| `narration.json` | Falas, respirações e pausas por cena + janela de tempo de cada cena. Sem tempos: o pipeline calcula. |
| `scenes/s1…s3-*.json` | Cenário (local, luz, props) e **beats** visuais de cada cena, ancorados na fala. |
| `sfx.json` | Cues de SFX e automação de mixagem. `origin`: `roteiro` (está no `.md`) ou `inferido` (som implícito numa ação; pode apagar). |
| `camera.json` | Rig POV: passada, respiração, coração, mão, ônibus, impactos, olhar, vinheta/blur/pálpebra. |
| `narration.measured.json` | *(opcional)* tempos reais da gravação — ver abaixo. |

| Gerado em `build/` (não edite) | Para quem |
|---|---|
| `ep01.timeline.json` | Tudo, em segundos **e** frames (`*_frame`, `*_tc`): cenas, beats, voz com tempo **por palavra**, respiros, SFX, passos, olhar. |
| `ep01.camera.csv` | 3600 linhas (1 por frame) para o motor 3D. |
| `ep01.cue-sheet.md` | Lista cronológica legível de tudo + orçamento de fala por cena. **Comece por aqui.** |
| `ep01.overview.svg` | Painel com todas as trilhas no mesmo eixo, para conferir a sincronia a olho. |

Para levar a câmera ao Blender: `blender/import_camera_csv.py` (ver `blender/README.md`).

`scenes-config.json` continua sendo a fonte das janelas de cena (00:00/00:15/00:35/01:00). O build
**recusa** o episódio se o texto de `narration.json` divergir do `dialogue` de lá.

## Como a sincronia funciona

- **Passos = câmera = SFX.** Cada pisada é um evento único (`camera.make_steps`): a cabeça fica no ponto
  mais baixo exatamente no frame do passo e o SFX de passo cai nesse mesmo frame (`step=1` no CSV).
  Cadência: corrida 2,85/s → caminhada → parada na plataforma; 3 degraus metálicos; passos lentos e abafados no **piso emborrachado** do corredor.
- **Respiração da câmera = respiração da fala.** O peito sobe nos respiros do roteiro (*inspiração rápida*,
  *suspiro*, *funga*, *bocejo*, *respiração profunda*) e, além disso, num respiro antes de cada frase
  (marcados `explicit: false`; só movem a câmera, não são áudio pedido). Fora da fala segue `breath_rate`.
- **Coração** (`hr_bpm`: 148→60) dá o pulso *lub-dub* na câmera; **hand-held** é ruído suave determinístico.
- **Ônibus**: vibração do motor, balanço de pista e inclinação por aceleração vêm de `speed_kmh`. A mesma
  curva dirige a altura (pitch) do ronco do motor (`motor-onibus.automation.pitch_semitones`).
- **Cena 3, "som abafando"**: `lowpass_hz` + queda de volume no motor, `narration_gain_db` na voz,
  vinheta/blur de borda e pálpebra no CSV — tudo na mesma janela 44 s → 59,5 s.
- **Final**: pálpebra fecha por completo em 59,3 s; corte seco para preto em 59,5 s (30 frames de preto).

### `ep01.camera.csv`

`shake_*` = camada **aditiva** (posição em cm, rotação em graus) para somar ao caminho/animação base da
câmera. `look_*` = intenção de olhar (para onde a cabeça aponta). Rotação final = `look + shake`.
`fov_pct` = variação % do FOV. `vignette`, `edge_blur`, `eyelid` ∈ [0,1]; `black` = 1 a partir do corte.
`breath`, `heart`, `speed_kmh`, `step` são os canais de sincronia (úteis para ligar áudio/efeitos).
Convenção de eixos: `+X` direita, `+Y` cima, `+Z` frente; yaw+ direita, pitch+ cima, roll+ inclina à
direita (o importador do Blender já converte). `intensity` em `camera.json` escala todo o balanço de uma vez.

## Orçamento de fala (todas as cenas cabem)

| Cena | Janela | Fala efetiva | Pretendido | Situação |
|---|---|---|---|---|
| s1 | 0,15–14,75 s | 6,65 sil/s | 6,4 | ok (a mais apertada: bem rápido) |
| s2 | 16,0–34,6 s | 5,1 sil/s | 5,0 | ok |
| s3 | 37,2–58,4 s | 4,38 sil/s | 4,4 (arrastado) | ok (encaixa quase exatamente) |

O texto longo do briefing ("Meu olho tá pesando demais… Faltam umas paradas até Jundiaí, mas o meu ponto é exato
o 348, na marginal da rodovia. Se eu passar do ponto 348, eu tô frito…") pede ~32 s para 21 s de janela (**ESTOURA**,
fala a 6,4 sil/s num trecho que é para ser arrastado). O corte aprovado mantém **as duas menções ao ponto 348** e a
redação do briefing, e tira só o que não cabe: `s3-03` ("Meu olho tá pesando demais…", `"skip": true`: o bocejo e a
pálpebra já mostram o sono), "Faltam umas paradas até Jundiaí, mas o", "da rodovia" e o "clássico" do fim da 1ª
frase. Roteiro ativo da cena 3 (idêntico ao `dialogue` em `scenes-config.json`):

> Pronto, mochila no banco do lado pra ninguém sentar junto. *(bocejo)* Meu ponto é exato o 348, na marginal.
> Se eu passar do ponto 348, eu tô frito. *(respiração profunda e lenta)* Ai, fechar o olho só cinco minutinhos…

`"skip": true` tira a fala do roteiro ativo sem apagar o texto; o `dialogue` de `scenes-config.json`
precisa bater com as falas **não puladas** (o build recusa se divergir). `--strict` falha se alguma cena
voltar a não caber.

## Quando existir a voz gravada

Os tempos das falas hoje são **estimados** (sílabas + pontuação), não medidos. Com a voz em mãos há dois caminhos.

**Automático** (`pipeline/audio.py`): ponha o áudio em `ep01/audio/` e rode

```
python -m pipeline audio ep01 --dry-run     # só mostra a análise (tabela estimado × medido, confiança, avisos)
python -m pipeline audio ep01               # grava narration.measured.json e roda o build
```

- **Onde (`ep01/audio/`):** `narration.wav` (a voz do episódio inteiro, com t=0 no início do vídeo) **ou** um arquivo por
  **bloco**: `s1`, `s2`, `s3` (todas as vozes da cena) ou, quando cada voz é gerada à parte, `s2.motorista`,
  `s2.protagonista`, `s3.protagonista`... (o falante vem do `speakers` do `narration.json`). WAV é lido sem dependências;
  mp3/m4a/ogg/flac precisam do `ffmpeg` no PATH. Nome que não bate com isso é recusado (para não ignorar um arquivo por typo).
- **Posição na linha do tempo:** o bloco é **posicionado pelo roteiro**: a 1ª fala dele cai no instante previsto e o resto
  vem com as durações e pausas da gravação; havendo mais de um bloco na mesma cena (vozes diferentes), cada um começa
  depois do anterior, com a folga prevista entre os dois. Para fixar onde um arquivo realmente começa, crie
  `ep01/audio/offsets.json`, ex.: `{"s2.motorista": 22.1}` (segundos).
- **Cena sem áudio:** os itens ficam na posição estimada (deslocados junto com a cena) e o aviso lista quais.
- **Se não couber:** o comando mostra, por cena, o que o roteiro previu × o que a gravação ocupa e quanto passa do fim da
  cena. Se a voz estourar os 60 s (ou qualquer âncora sair do episódio), o build falha e o `measured.json` **não é
  mantido** (`--keep-on-error` guarda assim mesmo, para depurar); gere a voz de novo mais rápida/com menos pausas ou
  corte texto.
- **Como mede:** energia por quadro de 10 ms + cruzamento de zero separam fala, respiração (ruído fraco) e silêncio, com
  limiares relativos ao nível da própria gravação. Programação dinâmica escolhe, entre as pausas do áudio, as fronteiras que
  melhor separam as falas do roteiro (pausas longas a favor; duração muito diferente da esperada contra). Respirações
  (`breath`) e trechos sem voz (`silence`) ocupam as folgas entre as falas. As **pausas internas** de cada fala
  (reticências, vírgulas) viram `pauses` e ancoram as palavras (o build faz o mapeamento linear por partes).
- **O que sai:** `narration.measured.json` (início/fim por item, `pauses`, `conf` de 0 a 1 e `note` quando algo foi
  estimado) e, depois do build, o resumo do que se re-sincronizou. Respiração não encontrada no áudio fica na posição
  estimada, com `conf` baixa. Um `narration.measured.json` escrito à mão só é sobrescrito com `--force` (fica um `.bak`).
- **Limites (valem para a análise por amplitude, sem reconhecimento de fala):** falas coladas com menos de ~0,1 s de pausa
  são ambíguas; texto gravado diferente do roteiro desalinha; ruído de fundo alto pede revisão. Se a análise não
  consegue separar as falas, ela diz isso em vez de chutar. Foi validada em voz **sintética** (`tests/test_audio.py`) e
  com a voz **real** gerada no ElevenLabs (`ep0X/audio/PROMPTS.md`).
- **Respirações soadas (suspiro, gasp, bocejo, ofegar):** têm tom, e o detector as toma por fala. O roteiro diz onde há uma
  respiração e quantos trechos ela deve ter (ofegar = 3, hiperventilar = 5); a análise reserva, entre as falas, um **bloco**
  de trechos de voz para ela (e, antes da 1ª fala, os trechos que sobram viram a respiração inicial). Se a respiração
  gravada for bem mais longa/curta que a prevista (ou emendada na fala seguinte sem pausa), o resultado pode escorregar:
  confira o `--dry-run` e, se for o caso, regere a respiração mais curta ou deixe uma pausa clara (≥ 0,25 s) antes da fala.
- **Início do bloco:** se a respiração/fala inicial do arquivo começaria antes da janela da cena, o bloco inteiro é
  empurrado até o começo da janela (aviso "empurrado"). Trechos mudos (`silence`) mantêm a duração prevista e não invadem
  a cena anterior.

**À mão:** crie `narration.measured.json` com o início/fim reais de cada item e rode o build:

```json
{ "items": { "s1-02": { "start": 0.52, "end": 3.07 }, "s1-03": { "start": 3.40, "end": 4.00, "pauses": [[3.7, 3.8]] } } }
```

As palavras são redistribuídas dentro do intervalo (e, com `pauses`, em volta delas) e tudo que está ancorado (celular
entrando, bip da catraca, mochila, bocejo, partida do ônibus, passos de degrau…) se move junto. Itens medidos não podem
se sobrepor aos vizinhos (o build avisa quais).

## Mixagem, render e vídeo final

```
python -m pipeline mix ep01               # voz medida + SFX -> ep01/build/ep01.mix.wav (48 kHz estéreo, 60,000 s)
python -m pipeline render ep01 --bench 6  # mede s/quadro no seu hardware e projeta as horas do episódio
python -m pipeline render ep01            # sequência de imagens 1080x1920 @60 fps (retomável; --chunks 8 --chunk 3 para granja)
python -m pipeline assemble ep01          # sequência + mix.wav -> mp4 H.264/AAC (out/ep01.mp4), conferido com o ffprobe
```

- **Mix:** a voz entra onde o `measured.json` a mediu (`audio.<arquivo>.offset`, já com o empurrão para dentro da janela da
  cena), nivelada pela fala mais forte; cada cue/passo/batida do `timeline.json` entra no seu instante e ganho. Os sons são
  **sintetizados** (determinísticos): são o marcador final de timbre e nível, trocáveis por foley de biblioteca em
  `pipeline/mix.py`. Precisa de numpy e, para mp3, do ffmpeg.
- **Render:** `blender/render_episode.py` (Cycles; GPU OptiX/CUDA/HIP/Metal/oneAPI se houver, senão CPU). `--step K` rende 1 a cada K
  quadros (prévia), `--width/--samples` mudam a qualidade, `--blender`/`--python` escolhem o executável.
- **Montagem:** recusa montar com quadros faltando (`--allow-partial` segura o último quadro renderizado, só para prévia).

## Premissas que assumi (ajuste se discordar)

- O "348" é falado **"três quatro oito"** (`lexicon`). Não use "três-meia-oito": "meia" é 6 (seria 368).
- Janela à **esquerda** do protagonista e banco do corredor à direita (a mão direita joga a mochila).
- A caminhada pelo corredor começa em ~31,9 s (cena 2, em "mas beleza…") e termina ao sentar (36,9 s),
  para que ele já esteja sentado quando diz "Pronto, mochila…".
- Os 3 cochilos (52,3 / 55,0 / 57,1 s), a pálpebra pesada no bocejo e a partida do ônibus (ao fim de
  "…sentar junto.", aos 40,7 s, logo antes do bocejo; o ônibus chega a 62 km/h no último segundo) são coreografia minha
  em cima do roteiro; olhares e props marcados `inferido` também.
