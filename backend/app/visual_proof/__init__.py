"""Prova visual da superfície publicada — domínio, casos de uso e adaptadores.

## Por que este domínio NÃO mora dentro de `asset_vault`

A missão permite criar este pacote apenas com justificativa escrita. Ela é:

1. **O Cofre responde; a prova visual executa.** O contrato de handoff
   (`docs/architecture/COFRE-HANDOFF-PRODUCAO-E-PUBLICACAO.md`) e o próprio
   docstring de `asset_vault.aplicacao.CasosDeUso.handoff` afirmam, em texto,
   que o Cofre "não cria job, não abre navegador, não publica". Colocar o motor
   que abre navegador dentro do módulo cuja fronteira é *não abrir navegador*
   apagaria a única linha que hoje separa inventário de execução.

2. **As duas camadas têm fronteiras de confiança diferentes.** Todo
   `asset_vault.rotas` roda sob `exigir_admin`, com sessão do Supabase, no
   processo do FastAPI. O broker roda em OUTRO host, em loopback, com
   autenticação própria e sem sessão de navegador. Um pacote que misturasse os
   dois teria de importar `fastapi` e `httpx` para o lado que precisa ser
   `stdlib`-only e portátil para o host isolado.

3. **A dependência é de mão única.** `visual_proof` não importa `asset_vault`.
   O que os dois compartilham — a gramática de nome lógico e a lista de campos
   proibidos — é PROVADO igual por teste
   (`backend/tests/test_visual_proof_fronteira_cofre.py`), no mesmo padrão com
   que `test_cofre_ativos.py` prova a concordância entre `dominio.py` e o SQL.

O caminho inverso (o Cofre passar a conhecer VisualProof) também não acontece:
a rota de prontidão em `asset_vault/rotas.py` fala com uma PORTA
(`LeitorDeProvaVisual`), cuja implementação padrão declara honestamente que
não há persistência.
"""
