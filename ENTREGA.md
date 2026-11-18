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
| Testes | Pura (sincronia, rotas, esqueleto, manifesto, áudio) e com Blender (cena montada) | `tests/` |

Cada `ep0X/README.md` explica as premissas daquele episódio (o que veio do roteiro e o que foi inferido).

## Como regenerar tudo

```
python -m pipeline build ep01 --strict      # idem ep02, ep03: regenera ep0X/build/
python -m unittest discover -s tests         # 242 testes (86 exigem o módulo bpy; sem ele são pulados)
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

## Decisões em aberto (nada foi mudado sem sua confirmação)

1. **Ep. 1, cenas 1 e 2:** o briefing tem pequenas diferenças de redação ("Cadê o ônibus dessa desgraça" × "Cadê a plataforma"). A cena 1 já está no limite de encaixe (6,65 sílabas/s para alvo 6,4).
2. **Ep. 2, abertura:** o repositório diz "gasp, depois CARALHO!"; o briefing escreve "CARALHO! (gasp)". Inverter muda a sincronia com a abertura das pálpebras.

## O que falta para chegar aos vídeos finais

1. **Voz.** **Feita e medida (18/11/2026).** Os 11 blocos foram gerados pelo conector do ElevenLabs (modelo `eleven_v4`, voz Eduardo e a voz criada "Horror motorista"); os prompts da versão final de cada bloco e o ajuste de ffmpeg aplicado (tempo sem mudar o tom, corte de silêncios) estão em `ep0X/audio/PROMPTS.md`. Os áudios **não ficam no git** (ficam em `ep0X/audio/`, ignorados); o que vale no repositório é o `ep0X/narration.measured.json`, gerado por `python -m pipeline audio ep0X` (mede fala, pausas e respirações, grava o `measured.json` e roda o build; câmera, passos e SFX se re-sincronizam sozinhos; detalhes em `ep01/README.md`). Todas as cenas cabem na janela: Ep. 1 = 0,9–14,5 / 18,0–34,5 / 37,2–58,2 s; Ep. 2 = 1,7–13,3 / 18,3–38,9 / 40,6–58,2 s; Ep. 3 = 4,5–17,8 / 22,3–41,7 / 46,8–56,0 s (voz medida × janelas 0–15/15–35/35–60, 0–18/18–40/40–60 e 0–20/20–42/42–60 s). Se regerar uma voz, rode o comando de novo (o `measured.json` é regravado; um escrito à mão só com `--force`).
2. **Áudio.** O cue sheet (`ep0X/build/ep0X.cue-sheet.md`) e `timeline.json > sfx` dizem quando cada som entra, com ganho, origem (roteiro/inferido) e superfície dos passos. O som em si ainda não foi produzido.
3. **Assets finais.** Hoje é *greybox* (caixas) com materiais procedurais. Para chegar ao "realista e detalhado": modelos com UV, conjuntos PBR em `blender/textures/<id>/` (o passo a passo está em `blender/TEXTURAS.md`), rostos e roupas de verdade, animação de personagem além do aceno, da mandíbula e da marcha.
4. **Render.** 1080x1920 a 60 fps em Cycles. A prévia leva ~1 min por quadro a 405x720 em CPU; o render final pede GPU ou fazenda de render. `edge_blur` e `motion_blur` do CSV ficam como propriedades da câmera (ligue na pós).
5. **Montagem.** Juntar imagem, voz e SFX seguindo o cue sheet e conferir o corte seco do Ep. 3 aos 59,0 s (silêncio absoluto até 60,0 s).

## Limitações conhecidas

- Tempos de fala **medidos** só onde há áudio em `ep0X/audio/` (ele não vai para o git); sem o áudio o build usa o `narration.measured.json` já gravado. A análise é por amplitude (sem reconhecimento de fala): confira o `--dry-run` quando a voz mudar (itens de confiança baixa vêm avisados).
- Texturas procedurais, não fotográficas; mapa `normal` só vale em malhas com UV; sem *displacement*.
- As neblinas volumétricas enevoam levemente o interior do ônibus e encarecem o render (~30%).
- Testado com o módulo `bpy` (4.2 LTS e 5.3); o botão *Run Script* da interface e o `blender -b -P` em si usam o mesmo código, mas não foram exercitados.
