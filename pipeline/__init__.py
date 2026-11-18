"""Pipeline do projeto "O Ônibus do Ponto 348".

Lê as fontes editáveis de cada episódio (narration.json, sfx.json, camera.json
e scenes/*.json), sincroniza tudo numa única linha do tempo @60fps e gera os
arquivos de `build/` que o motor 3D / editor de áudio consomem.

Só usa a biblioteca padrão do Python (3.10+).
"""
