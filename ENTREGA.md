# Entrega — O Ônibus do Ponto 348

Estado do projeto para quem for continuar (produção de voz, áudio, assets finais e render). Tudo aqui foi verificado:
os três episódios têm **60,0 s exatos, 3600 quadros a 60 fps, 1080x1920**, sem avisos no `--strict`, e a suíte de testes passa
no Blender 4.2 LTS e no 5.3 (módulo `bpy`).

## O que está pronto

| Camada | O que existe | Onde |
|---|---|---|
| Roteiro | Roteiro humano de cada episódio + janelas/falas/SFX resumidos | `ep01-embarque-campinas.md`, `ep02-despertar-escuro.md`, `ep03-fim-da-linha.md`, `scenes-config.json` |
| Sincronia | Uma linha do tempo por episódio: falas (com respirações e pausas), SFX, passos, batidas do chassi, luz, câmera, tudo preso às mesmas âncoras | `ep0X/narration.json`, `ep0X/scenes/`, `ep0X/sfx.json`, `ep0X/camera.json` |
| Gerado | `timeline.json`, `camera.csv` (60 fps), cue sheet (para o áudio) e mapa visual de cada episódio | `ep0X/build/` |
| Câmera POV | Balanço de caminhada, respiração, batimento, vibração do ônibus, solavancos e olhar, quadro a quadro | `ep0X/build/ep0X.camera.csv`, `blender/import_camera_csv.py` |
| Cena 3D | Ônibus, cenário, personagens de corpo inteiro com esqueleto, luzes, efeitos de tela, materiais PBR procedurais | `blender/assemble_scene.py`, `blender/pov_scene/` |
| Materiais | Manifesto + diretrizes de mapeamento de textura | `blender/materials.json`, `blender/TEXTURAS.md` |
| Voz real | Mede o áudio gravado e re-sincroniza o projeto (`python -m pipeline audio ep0X`) | `pipeline/audio.py`, `tests/test_audio.py` |
| Mixagem | Voz medida + SFX sintetizados nos instantes do roteiro, com loudness e corte seco do Ep. 3 (`python -m pipeline mix ep0X`) | `pipeline/mix.py`, `tests/test_mix.py` |
| Texturas | Conjuntos PBR CC0 (Poly Haven) aplicados, com o estado narrativo vindo do manifesto | `blender/textures_sources.json`, `blender/tools/fetch_textures.py`, `blender/pov_scene/materials.py` |
| Render e montagem | Sequência de imagens retomável/em lotes e mp4 final com áudio (`python -m pipeline render` / `assemble`) | `blender/render_episode.py`, `pipeline/render.py`, `tests/test_render.py` |
| Testes | Pura (sincronia, rotas, esqueleto, manifesto, áudio) e com Blender (cena montada) | `tests/` |

Cada `ep0X/README.md` explica as premissas daquele episódio (o que veio do roteiro e o que foi inferido).

## Como regenerar tudo

```
python -m pipeline build ep01 --strict      # idem ep02, ep03: regenera ep0X/build/
python -m unittest discover -s tests         # 264 testes (93 exigem o módulo bpy; sem ele são pulados)
python -m pipeline mix ep01                 # ep01.mix.wav (voz + SFX), idem ep02, ep03
python blender/tools/fetch_textures.py      # texturas CC0 (uma vez)
python -m pipeline render ep01 --bench 6    # s/quadro neste hardware; sem --bench renderiza tudo (retomável)
python -m pipeline assemble ep01            # mp4 final com áudio
blender -b -P blender/assemble_scene.py -- --episode ep01 --save ep01.blend
blender -b -P blender/assemble_scene.py -- --episode ep03 --render-frames 23.8,46.8 --out previews --width 405 --samples 32
```

O build é determinístico: rodar de novo não muda nenhum arquivo gerado (conferido). Os `.blend` e as imagens **não** ficam no repositório.

## Decisões fixadas

- **348** é sempre falado "três quatro oito" (`lexicon` de cada `narration.json`).
- **Catraca** fixa ao pé da porta de embarque, na frente, nos 3 episódios; no Ep. 3 ele bate as costas na **divisória/parapeito** logo atrás dela.
- **Altura dos olhos sentado:** 5 cm acima dos apoios de cabeça, afundando 4 cm ao sentar (`blender/pov_scene/layout.py`).
- **Ônibus:** piso emborrachado escuro (passos abafados; metal só nos degraus, balaústres e chassi), poltronas de tecido estampado azul/cinza, balaústres de inox no Ep. 1 e enferrujados nos Ep. 2 e 3.
- **Motorista:** corpo inteiro, camisa social azul amarrotada, boné com aba; no Ep. 3 pele cinza, olhos brancos e mandíbula que estica a cada estalo do pescoço.
- **O Duplo (passageiro do fundo):** completamente calvo; mesmo moletom e mesma mochila do protagonista; decomposição no Ep. 3.
- **Ep. 1, cena 3:** texto do briefing cortado para caber na janela, mantendo as duas menções ao 348 (`ep01/README.md`); o ônibus parte aos 40,7 s.
- **Ep. 2 e 3:** redação do briefing aplicada.
- **Sem contornos pretos** (Freestyle desligado, testado).
- **Tela preta é preto de verdade** (corte final do Ep. 1 e do Ep. 3, abertura do Ep. 2): o plano preto fica a 5 cm da câmera, é maior que o campo de visão e zera a névoa por driver; antes o corte do Ep. 3 saía vermelho-escuro (testado).

## Decisões em aberto (nada foi mudado sem sua confirmação)

1. **Ep. 1, cenas 1 e 2:** o briefing tem pequenas diferenças de redação ("Cadê o ônibus dessa desgraça" × "Cadê a plataforma"). A cena 1 já está no limite de encaixe (6,65 sílabas/s para alvo 6,4).
2. **Ep. 2, abertura:** o repositório diz "gasp, depois CARALHO!"; o briefing escreve "CARALHO! (gasp)". Inverter muda a sincronia com a abertura das pálpebras.

## O que falta para chegar aos vídeos finais

1. **Voz.** **Feita e medida (18/11/2026).** Os 11 blocos foram gerados pelo conector do ElevenLabs (modelo `eleven_v4`, voz Eduardo e a voz criada "Horror motorista"); os prompts da versão final de cada bloco e o ajuste de ffmpeg aplicado (tempo sem mudar o tom, corte de silêncios) estão em `ep0X/audio/PROMPTS.md`. Os 11 `.mp3` finais **estão no git** (em `ep0X/audio/`; os backups das rodadas e a mixagem .wav ficam de fora); a medição vale pelo `ep0X/narration.measured.json`, gerado por `python -m pipeline audio ep0X` (mede fala, pausas e respirações, grava o `measured.json` e roda o build; câmera, passos e SFX se re-sincronizam sozinhos; detalhes em `ep01/README.md`). Todas as cenas cabem na janela: Ep. 1 = 0,9–14,5 / 18,0–34,5 / 37,2–58,2 s; Ep. 2 = 1,7–13,3 / 18,3–38,9 / 40,6–58,2 s; Ep. 3 = 4,5–17,8 / 22,3–41,7 / 46,8–56,0 s (voz medida × janelas 0–15/15–35/35–60, 0–18/18–40/40–60 e 0–20/20–42/42–60 s). Se regerar uma voz, rode o comando de novo (o `measured.json` é regravado; um escrito à mão só com `--force`).
2. **Áudio.** **Mixagem pronta.** `python -m pipeline mix ep0X` junta a voz medida (na posição do `measured.json`, com o nível igualado) e os SFX do cue sheet num arquivo estéreo de 48 kHz e 60,000 s (`ep0X.mix.wav`, em `ep0X/build/`; não vai para o git): camas (ambiência, motor que segue a velocidade do CSV, chiado, vento...), sons pontuais (catraca, bip, estalos, BUM, freada...), passos, batidas da estrada, falhas de luz e batimentos, cada um no instante e com o ganho do roteiro, mais a automação do episódio (voz que abaixa no fim do Ep. 1, ambiência que cai no Ep. 3) e o **silêncio absoluto** do Ep. 3 depois da freada. Volume: -15,7 / -17,0 / -14,5 LUFS (Ep. 1/2/3), picos em -1 dBFS. **Os sons são sintetizados** (ruído filtrado, senos e envelopes, determinísticos): marcam timbre, nível e instante, mas não substituem foley gravado. Para trocar um som por um arquivo de biblioteca, mude a receita dele em `pipeline/mix.py` (`SHOT`, `STEP`, `BED`); a sincronia não muda.
3. **Assets finais.** As **texturas** estão aplicadas conforme `blender/TEXTURAS.md`: conjuntos CC0 do Poly Haven (baixados por `blender/tools/fetch_textures.py`, fora do git, com licença em cada pasta) para piso encerado, piso do ônibus, camisa, metal e terra; o estado narrativo de cada variante continua vindo do `materials.json`. O estofado estampado segue procedural. O resto ainda é *greybox* (caixas): faltam modelos com UV, rostos e roupas de verdade e animação de personagem além do aceno, da mandíbula e da marcha.
4. **Render.** `python -m pipeline render ep0X` (Blender ou módulo `bpy`) escreve a sequência de imagens 1080x1920 a 60 fps; é retomável (`--resume`), roda em lotes (`--chunks N --chunk i`) e mede o hardware (`--bench N`: s/quadro e horas por episódio). **Não deu para renderizar aqui:** o ambiente tem 4 núcleos de CPU e nenhuma GPU, e o Cycles levou ~9 min por quadro a 1080x1920 (64 amostras) e ~6 s a 270x480; o episódio inteiro são 3600 quadros (10.800 nos três). Faltam, portanto, **horas de GPU** (ou uma granja de render); no Google Colab (GPU) abra `colab_render.ipynb`: a célula ▶ RETOMAR instala tudo e renderiza em lotes curtos com checkpoint no Google Drive (depois de qualquer queda, rode só ela de novo e o render continua do primeiro quadro que falta; `BATCH`, `STAGE_DIR` e `PERFIL=t4` do script cuidam de memória e retomada); numa máquina Linux com GPU e Blender, `./render_tudo.sh` faz tudo (texturas, build, mix, render retomável e mp4 de cada episódio; `BENCH=1` só mede o tempo): com uma GPU de uso geral a ~20 s/quadro seriam ~20 h por episódio, e o `--bench 6` no seu hardware dá o número exato.
5. **Montagem.** `python -m pipeline assemble ep0X` junta a sequência e o `ep0X.mix.wav` num mp4 H.264 yuv420p 60 fps, AAC 192 kb/s, `+faststart` (1080x1920, 60,000 s, 3600 quadros) e confere o arquivo com o ffprobe; recusa montar se faltarem quadros (`--allow-partial` segura o último quadro: só prévia). **Prévias já montadas** neste ambiente (216x384 ampliadas, 1 quadro a cada 24, com a mixagem final): nos arquivos `ep0X.previa.mp4` da pasta de saída `out`. Servem para conferir sincronia de voz, SFX e cortes; **não** são o vídeo final.

## Limitações conhecidas

- Tempos de fala **medidos** só onde há áudio em `ep0X/audio/` (ele não vai para o git); sem o áudio o build usa o `narration.measured.json` já gravado. A análise é por amplitude (sem reconhecimento de fala): confira o `--dry-run` quando a voz mudar (itens de confiança baixa vêm avisados).
- Texturas procedurais, não fotográficas; mapa `normal` só vale em malhas com UV; sem *displacement*.
- As neblinas volumétricas enevoam levemente o interior do ônibus e encarecem o render (~30%).
- Testado com o módulo `bpy` (4.2 LTS e 5.3); o botão *Run Script* da interface e o `blender -b -P` em si usam o mesmo código, mas não foram exercitados.
