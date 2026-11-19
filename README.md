# 🚌 Série TikTok 3D: O Ônibus do Ponto 348

Projeto de animação 3D em **Primeira Pessoa (POV)** dividido em 3 episódios de 60 segundos (formato vertical 9:16, 1080x1920, 60fps) para TikTok/Reels.

## 📁 Estrutura do Repositório
- `README.md` — Diretrizes visuais, câmera e atuação vocal.
- `ENTREGA.md` — Estado do projeto: o que está pronto, decisões fixadas e em aberto, e o que falta para os vídeos finais (voz, áudio, assets, render).
- `ep01-embarque-campinas.md` — Parte 1 (00:00 - 01:00): Terminal Rodoviário de Campinas.
- `ep02-despertar-escuro.md` — Parte 2 (00:00 - 01:00): A transição e o despertar na estrada de terra.
- `ep03-fim-da-linha.md` — Parte 3 (00:00 - 01:00): Confronto com o motorista e clímax.
- `scenes-config.json` — Janelas de tempo, falas e SFX resumidos de cada episódio.
- `ep01/` — Fontes sincronizadas do Ep. 01 (narração, cenas, SFX, câmera POV) + `build/` gerado. Veja `ep01/README.md`.
- `ep02/` — Idem para o Ep. 02 (BUM, luz com falha elétrica, estrada irregular). Veja `ep02/README.md`.
- `ep03/` — Idem para o Ep. 03 (dois falantes, batimentos cardíacos como SFX, revelação, porta e neblina vermelha). Veja `ep03/README.md`.
- `blender/` — Importador do `camera.csv` (60fps) **e montador da cena de cada episódio** em greybox: ônibus, cenário, personagens, luz e efeitos de tela, com o caminho-base da cabeça guiado pelos passos. Veja `blender/README.md`.
- `pipeline/` e `tests/` — Gerador (`python -m pipeline build ep01`), medição da voz real (`python -m pipeline audio ep01`, lê `ep01/audio/`) e testes (`python -m unittest discover -s tests`). Só biblioteca padrão do Python (o `ffmpeg` é opcional, só para áudio que não é WAV).

## 🎨 Especificações Técnicas (Claude Code / Pipeline 3D)
- **Perspectiva:** 100% Primeira Pessoa (POV) com *handheld camera shake* dinâmico sincronizado à respiração e batimentos cardíacos do protagonista.
- **Estilo Visual:** Estética 3D cinematográfica **realista e detalhada** (referência *Unreal Engine 5*), alto contraste (*chiaroscuro*), texturas ricas de desgaste e iluminação volumétrica. **Sem contornos pretos.** (A montagem atual no Blender é um *greybox* low-poly com materiais PBR procedurais, ponto de partida para os assets finais: veja `blender/TEXTURAS.md`.)
- **Objeto Âncora:** Mochila preta de estudante universitário com crachá/chaveiro pendurado (serve de referência visual para a passagem de tempo e deterioração entre os episódios).

## 🚌 Ambientação e Layout (padrão brasileiro)
- **O ônibus:** intermunicipal paulista vicinal. Poltronas de **tecido estampado antigo em tons de azul/cinza**, com altura **levemente abaixo da linha de visão** do protagonista ao sentar (ergonomia real, com leve afundamento). Balaústres em **aço inox** (enferrujados a partir do Ep. 2); piso **emborrachado escuro antiderrapante**.
- **Catraca:** fixa na parte dianteira, logo após a porta de embarque, **nos três episódios**. No Ep. 3 ele bate as costas na **divisória/parapeito logo atrás dela**.
- **Motorista:** modelado de **corpo inteiro** (tronco, braços, pernas e pés na cabine, mãos no volante), camisa social azul amarrotada e boné com aba sombreada. No Ep. 3: pele cinza-cadavérica, olhos brancos sem pupilas e **mandíbula que estica** ao virar o pescoço 180°.
- **Passageiro do fundo (o Duplo):** **completamente calvo** (crânio liso, sem cabelo), sentado na última fileira com **o mesmo moletom e a mesma mochila** do protagonista; no clímax do Ep. 3 vem pelo corredor (anda de verdade) com rosto e roupas em decomposição.
- **Som dos passos:** no ônibus o piso é emborrachado (passos abafados); o metal fica nos degraus, balaústres e chassi.

## 🎙️ Diretrizes de Áudio e Acting Vocal
- **Protagonista:** Estudante universitário brasileiro (~21 anos). Monólogo contínuo em voz alta.
- **O número 348** é sempre falado **"três quatro oito"** em todos os episódios (`lexicon` do `narration.json`).
- **Curva Emocional:**
  1. **Ep. 01:** Voz acelerada, cansada, tom coloquial e bocejos curtos -> respiração lenta e pesada no final.
  2. **Ep. 02:** Sustos secos (*gasps*), respiração curta e ofegante, voz trêmula e desconfiada.
  3. **Ep. 03:** Hiperventilação audível, voz embargada de pânico, gritos desesperados e batimentos cardíacos abafando o som ambiente.
