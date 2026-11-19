# Prompts do ElevenLabs — Ep. 3

Gerado pelo conector do ElevenLabs em 18/11/2026, modelo **`eleven_v4`** (as sensações vão em tags entre colchetes, que o
v4 interpreta; o 348 e as siglas já estão na forma falada). Cada bloco abaixo traz o prompt **da versão que ficou** (alguns
foram regerados em rodadas seguintes para caber na janela de tempo da cena e para trazer as respirações do roteiro) e, quando
houve, o **ajuste de pós-produção com ffmpeg** (tempo sem mudar o tom, corte de silêncios longos). Os arquivos originais, sem
ajuste, ficam em `rodadaN_sem_ajuste/` (local, não vai para o git). Para regerar, cole o prompt do bloco no ElevenLabs com a
voz indicada, salve com o nome do arquivo e, se houver ajuste listado, aplique o mesmo comando.

Vozes: **Eduardo - Brazilian Portuguese** (`H2bV051FngNxkuTNROyc`) para o protagonista; **Horror motorista**
(`s2fKMQgcCT73E4EtwZXg`, voz criada na conta) para o motorista.

## `s1.mp3 (cena 1, protagonista)`

Voz: Eduardo - Brazilian Portuguese · duração gerada: 17,6 s

```
[hyperventilating] [gasping for air] [panting heavily] ... [desperate] Moço, para o ônibus!
[pleading] [voice breaking] Pelo amor de Deus, abre a porta e me deixa descer!
[panicked] [on the verge of tears] Eu preciso descer no ponto três quatro oito, já passou muito!
[trembling voice] O senhor tá me levando pra onde?!
[crying] [pleading] Olha pra mim, caramba!
[shouting] [desperate] PARA ESSE ÔNIBUS!
```

## `s2.motorista.mp3 (cena 2, motorista)`

Voz: Horror motorista · duração gerada: 10,5 s

Ajuste: tempo por trecho: 0,94× até 5,0 s e 1,06× depois (`atrim` + `atempo` + `concat`), mantendo a duração total e deixando a 2ª frase um pouco mais rápida.

```
[deep voice] [slowly] [eerie, like an old radio] Você pegou esse ônibus em Campinas em dois mil e dezenove, estudante...
[deep voice] [slowly] [cold and final] O ponto três quatro oito não existe mais desde que a gente caiu na ribanceira.
```

## `s2.protagonista.mp3 (cena 2, protagonista)`

Voz: Eduardo - Brazilian Portuguese · duração gerada: 10,4 s

Ajuste: `ffmpeg -i s2.protagonista.mp3 -filter:a "atempo=1.14" -b:a 192k` → 9,2 s.

```
[sharp gasp] [inhales sharply] ... [choked voice] [rushed] Do que você tá falando?!
[incredulous] [terrified] [fast-paced] Eu saí de Campinas agorinha pouco!
[distraught] [rushed] Eu tenho aula amanhã de manhã!
[terrified] [fast-paced] Você tá louco!
[shouting] [desperate] [rushed] Abre essa porta agora, seu maluco!
```

## `s3.protagonista.mp3 (cena 3, protagonista)`

Voz: Eduardo - Brazilian Portuguese · duração gerada: 5,6 s

Ajuste: `ffmpeg -i s3.protagonista.mp3 -af "silenceremove=stop_periods=-1:stop_duration=0.1:stop_threshold=-35dB:stop_silence=0.08,atempo=1.08" -b:a 192k` → 4,4 s (tira os silêncios longos entre os gritos e acelera um pouco).

```
[shouting] [absolute panic] NÃO!
[shouting] [desperate] NÃO!
[screaming] [terrified] SAI DE PERTO DE MIM!
[screaming] [pleading] SOCORRO!
```

## `s3.motorista.mp3 (cena 3, motorista)`

Voz: Horror motorista · duração gerada: 3,4 s

Ajuste: `ffmpeg -i s3.motorista.mp3 -af "atempo=0.86" -b:a 192k` → 3,9 s (mais lento, como o motorista pede: menos de 3,5 sílabas/s).

```
[deep voice] [slowly] [calm and menacing] Chegou a sua vez de esperar no ponto.
```
