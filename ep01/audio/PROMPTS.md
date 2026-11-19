# Prompts do ElevenLabs — Ep. 1

Gerado pelo conector do ElevenLabs em 18/11/2026, modelo **`eleven_v4`** (as sensações vão em tags entre colchetes, que o
v4 interpreta; o 348 e as siglas já estão na forma falada). Cada bloco abaixo traz o prompt **da versão que ficou** (alguns
foram regerados em rodadas seguintes para caber na janela de tempo da cena e para trazer as respirações do roteiro) e, quando
houve, o **ajuste de pós-produção com ffmpeg** (tempo sem mudar o tom, corte de silêncios longos). Os arquivos originais, sem
ajuste, ficam em `rodadaN_sem_ajuste/` (local, não vai para o git). Para regerar, cole o prompt do bloco no ElevenLabs com a
voz indicada, salve com o nome do arquivo e, se houver ajuste listado, aplique o mesmo comando.

Vozes: **Eduardo - Brazilian Portuguese** (`H2bV051FngNxkuTNROyc`) para o protagonista; **Horror motorista**
(`s2fKMQgcCT73E4EtwZXg`, voz criada na conta) para o motorista.

## `s1.mp3 (cena 1)`

Voz: Eduardo - Brazilian Portuguese · duração gerada: 15,8 s

Ajuste: `ffmpeg -i s1.mp3 -filter:a "atempo=1.09" -b:a 192k` → 14,5 s (cabe na janela de 0–15 s).

```
[inhales sharply] [out of breath] [irritated] [fast-paced] Mano, sério, eu odeio fazer trabalho em grupo!
[irritated] [rushed] Juro por Deus.
[out of breath] [complaining] [fast-paced] Sábado quase meia-noite saindo de Campinas pra Jundiaí.
[sarcastic] [out of breath] [rushed] olha o estado dessa rodoviária, parece cenário de filme de terror mudo, velho.
[impatient] [irritated] [fast-paced] Cadê a plataforma dessa desgraça?!
```

## `s2.mp3 (cena 2)`

Voz: Eduardo - Brazilian Portuguese · duração gerada: 17,8 s

```
[sighs deeply with relief] [long exhale] ... [relieved] Ainda bem que deu tempo.
[polite] [relieved] Boa noite, moço.
[friendly] [tired] Vai pro lado de Jundiaí, né?
[tired] [wary] Linha vicinal...
[sniffs] [disgusted] Nossa, o cheiro aqui dentro tá um catinga de graxa velha misturada com naftalina...
[resigned] [tired] mas beleza, só quero sentar e capotar.
```

## `s3.mp3 (cena 3)`

Voz: Eduardo - Brazilian Portuguese · duração gerada: 22,4 s

Ajuste: `ffmpeg -i s3.mp3 -filter:a "atempo=1.04" -b:a 192k` → 21,5 s.

```
[tired] [slowly] Pronto, mochila no banco do lado pra ninguém sentar junto.
[long yawn] [yawning widely] ... [sleepy] [slowly] Meu ponto é exato o três quatro oito, na marginal.
[sleepy] [worried] Se eu passar do ponto três quatro oito, eu tô frito.
[deep slow breath] [exhales slowly] ... [drowsy] [whispers] Ai, fechar o olho só cinco minutinhos...
```
