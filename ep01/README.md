# Episódio 1 — estrutura de cenas, narração, SFX e câmera POV

Tudo que acontece nos 60 s (3600 frames @60fps, 1080x1920) vive numa **única linha do tempo**.
Voz, respiração, SFX, passos e câmera não têm tempos digitados à mão: eles são **ancorados**
em palavras da fala, em *beats* de cena ou uns nos outros. Mudou a fala? Todo o resto acompanha.

```
python -m pipeline build ep01          # regenera ep01/build/
python -m pipeline build ep01 --strict # sai com erro se houver avisos (ex.: fala que não cabe)
python -m unittest discover -s tests   # 20 testes (sincronia, validações, re-sincronização)
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

`scenes-config.json` continua sendo a fonte das janelas de cena (00:00/00:15/00:35/01:00). O build
**recusa** o episódio se o texto de `narration.json` divergir do `dialogue` de lá.

## Como a sincronia funciona

- **Passos = câmera = SFX.** Cada pisada é um evento único (`camera.make_steps`): a cabeça fica no ponto
  mais baixo exatamente no frame do passo e o SFX de passo cai nesse mesmo frame (`step=1` no CSV).
  Cadência: corrida 2,85/s → caminhada → parada na plataforma; 3 degraus metálicos; passos lentos no corredor.
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
direita — **converta para o seu motor**. `intensity` em `camera.json` escala todo o balanço de uma vez.

## ⚠️ Cena 3: o texto não cabe

O build mede quanto a fala pede. Cenas 1 e 2 cabem (cena 1 é apertada: 6,6 sílabas/s, bem rápido).
**A cena 3 pede ~42 s no ritmo "arrastado" do roteiro e só tem 21 s** (mesmo em ritmo normal, sem
arrastar, pediria ~33 s). Enquanto o texto estiver inteiro, a linha do tempo da cena 3 é só ilustrativa —
a fala sairia a ~8,6 sílabas/s e os respiros ficam sem espaço (o `--strict` falha por isso).

Para testar um corte sem apagar nada, marque `"skip": true` nos itens de `narration.json`.
Medido: cortar `s3-03` e `s3-04` leva a cena a ~4,6 sil/s (**apertado**, cabe); falar "348" como
"três quatro oito" (em `lexicon`) melhora mais um pouco. Só cortar `s3-03` não basta.

## Quando existir a voz gravada

Os tempos das falas hoje são **estimados** (sílabas + pontuação), não medidos. Crie
`narration.measured.json` com o início/fim reais de cada item e rode o build:

```json
{ "items": { "s1-02": { "start": 0.52, "end": 3.07 }, "s1-03": { "start": 3.40, "end": 4.00 } } }
```

As palavras são redistribuídas dentro do intervalo e tudo que está ancorado (celular entrando, bip da
catraca, mochila, bocejo, partida do ônibus, passos de degrau…) se move junto. Itens medidos não podem
se sobrepor aos vizinhos (o build avisa quais).

## Premissas que assumi (ajuste se discordar)

- O "348" é falado *trezentos e quarenta e oito* (`lexicon`); muda ~1,5 s de fala por ocorrência.
- Janela à **esquerda** do protagonista e banco do corredor à direita (a mão direita joga a mochila).
- A caminhada pelo corredor começa em ~31,9 s (cena 2, em "mas beleza…") e termina ao sentar (36,9 s),
  para que ele já esteja sentado quando diz "Pronto, mochila…".
- Os 3 cochilos (52,3 / 55,0 / 57,1 s), a pálpebra pesada no bocejo e a partida do ônibus (após o bocejo)
  são coreografia minha em cima do roteiro; olhares e props marcados `inferido` também.
