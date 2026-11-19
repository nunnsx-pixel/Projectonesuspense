# Áudio da voz — ep03

Coloque aqui a voz do episódio (WAV, ou mp3/m4a/ogg/flac se o `ffmpeg` estiver instalado). Os `.mp3` finais de cada bloco **vão para o git** (junto com este guia, o `PROMPTS.md`, o `offsets.json` e o `narration.measured.json` gerado a partir deles); backups (`rodadaN/`, `versoes_do_usuario/`) e a mixagem `.wav` ficam de fora.

Duas vozes, então um arquivo por cena **e por falante**:

- `s1.mp3` (protagonista) · `s2.motorista.mp3` · `s2.protagonista.mp3` · `s3.protagonista.mp3` · `s3.motorista.mp3`

(ou `narration.mp3` com o episódio inteiro, com t=0 no início do vídeo).

Cada arquivo é posicionado pelo roteiro (a 1ª fala dele cai no instante previsto; com duas vozes na mesma cena, a 2ª vem
depois da 1ª, com a folga prevista). Para fixar um arquivo em outro instante, crie `offsets.json`, ex.: `{"s2.motorista": 22.1}`.

```
python -m pipeline audio ep03 --dry-run   # análise: estimado × medido, confiança e o encaixe por cena
python -m pipeline audio ep03             # grava narration.measured.json e roda o build
```

Detalhes, limites e formato: `ep01/README.md` (seção "Quando existir a voz gravada").
