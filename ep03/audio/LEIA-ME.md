# Áudio da voz — ep03

Coloque aqui a voz do episódio (WAV, ou mp3/m4a/ogg/flac se o `ffmpeg` estiver instalado):

- `narration.wav` — a voz do episódio inteiro, com t=0 no início do vídeo; **ou**
- um arquivo por cena: `s1.wav`, `s2.wav`, `s3.wav` (o t=0 de cada um cai no início previsto do 1º item da cena;
  para dizer onde ele realmente começa, crie `offsets.json`, ex.: `{"s2": 18.3}`, em segundos).

Depois:

```
python -m pipeline audio ep03 --dry-run   # confere a análise (estimado × medido, confiança)
python -m pipeline audio ep03             # grava narration.measured.json e roda o build
```

Detalhes, limites e formato do `narration.measured.json`: `ep01/README.md` (seção "Quando existir a voz gravada").
