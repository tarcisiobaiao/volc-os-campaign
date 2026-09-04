# Gates

## Executados

- `backend/.venv/bin/python -m pytest backend/tests/test_meta_paused_birth.py -q`
  - 16 passed
- suíte focal Meta, incluindo domínio, adaptador read-only, sincronizador,
  read model e nascimento
  - 48 passed
- `python3 -m py_compile backend/app/trafego/meta_execucao/*.py`
  - passou
- `git diff --check`
  - passou
- `python3 scripts/verificar_segredos.py`
  - nenhum padrão forte

Todos os HTTPs dos testes usam `httpx.MockTransport`. Nenhuma chamada Graph
real, Supabase, Google Ads, WordPress ou n8n foi executada.

## Contraprovas cobertas

- objetivo, budget, placements, promoted object e Advantage fora da receita;
- aprovação com hash divergente ou capability ausente;
- `validate_only` não cria objetos dependentes;
- ordem validate → recibo → create → read-back em cada degrau;
- Campaign/Ad Set/Ad fora de `PAUSED` interrompem a saga;
- retomada não repete create;
- timeout vira ambiguidade sem retry;
- ausência de registro durável impede qualquer rede;
- nenhum identificador cru ou segredo aparece na projeção de resultado.

## Não executados nesta lane

- rota HTTP autenticada;
- adapter Supabase do registro;
- migration;
- `validate_only` real;
- Meta mutate real;
- teste visual/frontend.
