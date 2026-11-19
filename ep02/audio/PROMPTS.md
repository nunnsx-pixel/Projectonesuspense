# Prompts do ElevenLabs — Ep. 2

Gerado pelo conector do ElevenLabs em 18/11/2026, modelo **`eleven_v4`** (as sensações vão em tags entre colchetes, que o
v4 interpreta; o 348 e as siglas já estão na forma falada). Cada bloco abaixo traz o prompt **da versão que ficou** (alguns
foram regerados em rodadas seguintes para caber na janela de tempo da cena e para trazer as respirações do roteiro) e, quando
houve, o **ajuste de pós-produção com ffmpeg** (tempo sem mudar o tom, corte de silêncios longos). Os arquivos originais, sem
ajuste, ficam em `rodadaN_sem_ajuste/` (local, não vai para o git). Para regerar, cole o prompt do bloco no ElevenLabs com a
voz indicada, salve com o nome do arquivo e, se houver ajuste listado, aplique o mesmo comando.

Vozes: **Eduardo - Brazilian Portuguese** (`H2bV051FngNxkuTNROyc`) para o protagonista; **Horror motorista**
(`s2fKMQgcCT73E4EtwZXg`, voz criada na conta) para o motorista.

## `s1.mp3 (cena 1)`

Voz: Eduardo - Brazilian Portuguese · duração gerada: 14,0 s

Ajuste: (1) `atempo=1.06` no arquivo inteiro → 13,2 s; (2) o ofegar ("huh-huh-huh", de 6,43 s a 8,53 s do arquivo) a **1,5×** (`atrim` + `atempo=1.5`) e **0,25 s de silêncio** antes de "Mano..." (`anullsrc`), para o ciclo do ofegar ficar abaixo de 0,5 s, como o roteiro pede, e a fala seguinte não se confundir com ele → 12,8 s. Comando completo: `ffmpeg -i s1_antes.mp3 -f lavfi -t 0.25 -i anullsrc=r=44100:cl=mono -filter_complex "[0:a]atrim=0:6.43,asetpts=PTS-STARTPTS[a];[0:a]atrim=6.43:8.53,asetpts=PTS-STARTPTS,atempo=1.5[b];[0:a]atrim=8.53,asetpts=PTS-STARTPTS[c];[a][b][1:a][c]concat=n=4:v=0:a=1[o]" -map "[o]" -c:a libmp3lame -q:a 2 s1.mp3` (os instantes de corte dependem da gravação; regerando o bloco, ache o ofegar de novo).

```
[gasps] [screaming in shock] [out of breath] CARALHO!
[shocked] [breathless] Que barulho foi esse?!
[disoriented] [panicked] Que que pegou?!
[terrified] A gente bateu?!
[calling out] [desperate] Moço?!
[panting heavily] [gasping for air] [short rapid breaths] ... [breathless] Mano...
[in shock] [trembling voice] o ônibus deu um tranco que parece que arrancou o eixo.
```

## `s2.mp3 (cena 2)`

Voz: Eduardo - Brazilian Portuguese · duração gerada: 20,7 s

```
[trembling voice] [suspicious] Espera aí...
[trembling voice] [confused] por que a luz tá verde assim...?
[gulps] [scared] Mano, o banco tá...
[in shock] por que tá tudo podre?!
[distressed] A minha mochila tá imunda, velho!
[confused] E cadê todo mundo que tava embarcando...?
[scared] [low voice] Só tem um maluco lá no fundo... sentado duro que nem estátua...
[terrified whisper] Onde a gente tá...?
[stunned] [weak voice] Campinas já ficou umas três horas pra trás...
```

## `s3.mp3 (cena 3)`

Voz: Eduardo - Brazilian Portuguese · duração gerada: 17,9 s

```
[desperate] [breathless] Não é possível... O gê pê ésse morreu!
[panicked] [rushed] O quatro gê sumiu totalmente!
[apprehensive] [breathless] E aquela placa ali fora...
[incredulous] [rushed] tava escrito três quatro oito?!
[denying] [nervous] Não, o ponto três quatro oito era um posto na beira da pista, ali fora é só...
[terrified] [voice breaking] é só mato morto!
[voice breaking] [softly] Motorista...
[pleading] [on the verge of tears] ei... motorista?!
```
