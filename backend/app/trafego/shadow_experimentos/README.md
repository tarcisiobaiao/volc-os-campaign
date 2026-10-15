# Projeções de recomendação em sombra

Esta pasta é a cópia mínima empacotável dos experimentos cuja fonte autoral
fica em `tools/freedom-lab/experimentos/`. O runtime do backend lê daqui porque
o deploy da Vercel inclui `app/**`, mas não inclui `tools/**`.

Cada subpasta deve conter somente o contrato necessário à leitura:

- `experimento.json`;
- `resultado.json`;
- `transformacao.csv`.

`backend/tests/test_recomendacao_shadow.py` compara os bytes desta projeção com
a fonte autoral. Alterar apenas um dos lados faz o gate falhar. Esses arquivos
não autorizam nenhuma ação: a rota é ADMIN-only, não oferece escrita e recusa
recomendações vencidas.
