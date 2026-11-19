# Áudio da voz — ep01

Coloque aqui a voz do episódio (WAV, ou mp3/m4a/ogg/flac se o `ffmpeg` estiver instalado). Os `.mp3` finais de cada bloco **vão para o git** (junto com este guia, o `PROMPTS.md`, o `offsets.json` e o `narration.measured.json` gerado a partir deles); backups (`rodadaN/`, `versoes_do_usuario/`) e a mixagem `.wav` ficam de fora.

Um arquivo por cena (a voz do protagonista): `s1.mp3`, `s2.mp3`, `s3.mp3`.

Cada arquivo é posicionado pelo roteiro (a 1ª fala dele cai no instante previsto; com duas vozes na mesma cena, a 2ª vem
depois da 1ª, com a folga prevista). Para fixar um arquivo em outro instante, crie `offsets.json`, ex.: `{"s2.motorista": 22.1}`.

```
python -m pipeline audio ep01 --dry-run   # análise: estimado × medido, confiança e o encaixe por cena
python -m pipeline audio ep01             # grava narration.measured.json e roda o build
```

Detalhes, limites e formato: `ep01/README.md` (seção "Quando existir a voz gravada").
