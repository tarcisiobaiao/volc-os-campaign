"""Dependências compartilhadas do FastAPI.

## O que havia aqui, e por que saiu

`require_api_key` era o único portão do backend, e tinha dois defeitos que o
tornavam inútil como autenticação:

1. **Falhava ABERTO.** `if not expected: return` — sem `PAUTADOR_API_KEY` no
   ambiente, o portão simplesmente não existia. Um deploy com credenciais reais
   e essa variável esquecida ficava aberto e *parecia* protegido, que é a pior
   combinação possível: ninguém procura o buraco que acha que já tapou.
2. **A chave viajava para o navegador.** O front a enviava como `X-API-Key`
   lendo `VITE_PAUTADOR_API_KEY`, e tudo que começa com `VITE_` é substituído
   pelo valor literal no build. Um segredo compartilhado com o navegador é
   público — bastava abrir o DevTools para ter o portão inteiro.

Além disso ele cobria 24 das 64 rotas. As outras 40 não tinham portão nenhum.

## O que existe no lugar

`app.seguranca.identidade`, com duas vias separadas por origem:

    navegador → sessão do Supabase (JWT), validada CONTRA o Supabase
    serviço   → credencial própria, que NUNCA chega ao navegador

As dependências são `exigir_usuario`, `exigir_admin` e `exigir_servico`, e elas
falham FECHADAS em todos os caminhos — inclusive quando a configuração está
ausente, que responde 503 em vez de deixar passar.

Os routers aplicam `exigir_usuario` no nível do `APIRouter`, para que uma rota
nova nasça fechada em vez de nascer aberta.
"""

from __future__ import annotations

__all__: list[str] = []
