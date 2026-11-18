# 🚌 Série TikTok 3D: O Ônibus do Ponto 348

Projeto de animação 3D em **Primeira Pessoa (POV)** dividido em 3 episódios de 60 segundos (formato vertical 9:16, 1080x1920, 60fps) para TikTok/Reels.

## 📁 Estrutura do Repositório
- `README.md` — Diretrizes visuais, câmera e atuação vocal.
- `ep01-embarque-campinas.md` — Parte 1 (00:00 - 01:00): Terminal Rodoviário de Campinas.
- `ep02-despertar-escuro.md` — Parte 2 (00:00 - 01:00): A transição e o despertar na estrada de terra.
- `ep03-fim-da-linha.md` — Parte 3 (00:00 - 01:00): Confronto com o motorista e clímax.
- `scenes-config.json` — Janelas de tempo, falas e SFX resumidos de cada episódio.
- `ep01/` — Fontes sincronizadas do Ep. 01 (narração, cenas, SFX, câmera POV) + `build/` gerado. Veja `ep01/README.md`.
- `blender/` — Importador do `camera.csv` para a câmera principal do Blender (60fps). Veja `blender/README.md`.
- `pipeline/` e `tests/` — Gerador (`python -m pipeline build ep01`) e testes (`python -m unittest discover -s tests`). Só biblioteca padrão do Python.

## 🎨 Especificações Técnicas (Claude Code / Pipeline 3D)
- **Perspectiva:** 100% Primeira Pessoa (POV) com *handheld camera shake* dinâmico sincronizado à respiração e batimentos cardíacos do protagonista.
- **Estilo Visual:** Estética 3D estilizada de alto contraste (referência *Unreal Engine 5* / *Low-Poly* moderno expressivo), iluminação volumétrica, sombras profundas (*chiaroscuro*) e texturas de desgaste realistas.
- **Objeto Âncora:** Mochila preta de estudante universitário com crachá/chaveiro pendurado (serve de referência visual para a passagem de tempo e deterioração entre os episódios).

## 🎙️ Diretrizes de Áudio e Acting Vocal
- **Protagonista:** Estudante universitário brasileiro (~21 anos). Monólogo contínuo em voz alta.
- **O número 348** é sempre falado **"três quatro oito"** em todos os episódios (`lexicon` do `narration.json`).
- **Curva Emocional:**
  1. **Ep. 01:** Voz acelerada, cansada, tom coloquial e bocejos curtos -> respiração lenta e pesada no final.
  2. **Ep. 02:** Sustos secos (*gasps*), respiração curta e ofegante, voz trêmula e desconfiada.
  3. **Ep. 03:** Hiperventilação audível, voz embargada de pânico, gritos desesperados e batimentos cardíacos abafando o som ambiente.
