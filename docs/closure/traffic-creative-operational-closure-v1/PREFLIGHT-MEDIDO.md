# Preflight medido — missão tráfego + criativos

Fatos medidos pelo lead antes de qualquer alteração, sobre a base limpa.
Tudo aqui é saída de comando, não leitura de documento.

## Procedência da base

| item | valor |
|---|---|
| worktree | `/private/tmp/volc-traffic-creative-operational-closure-v1` |
| branch | `sprint/traffic-creative-operational-closure-v1` |
| base | `sprint/search-production-closure-v1` |
| SHA base | `3462b1407cb18c9f1fae3775d1db64608f56f3e9` |
| árvore na criação | limpa |

## Baseline dos gates (medido no SHA base, árvore limpa)

| gate | comando | resultado |
|---|---|---|
| TypeScript | `npx tsc --noEmit -p tsconfig.app.json` | **76 erros herdados do webgo** |
| Pytest | `backend/.venv/bin/python -m pytest backend/tests volc_ads -q` | **2319 passed, 53 skipped, 0 failed** (73,54s) |

A suíte Python está 100% verde na base. Não existe falha herdada de pytest em
que uma regressão possa se esconder: qualquer vermelho é novo.

O gate TypeScript só é real com `-p tsconfig.app.json`. O `tsconfig.json` da raiz
é solution-style (`files: []`), então `npx tsc --noEmit` puro compila zero arquivos
e sai 0 — um gate que sempre passa.

## Ambiente da worktree — defeito encontrado e corrigido

A worktree nasceu sem `node_modules`, sem `backend/.venv` e sem `.venv-graphify`.
Sem isso os gates de TypeScript, build, vitest, pytest e grafo não rodariam — e
"não rodou" teria sido lido como "passou". Corrigido por symlink para a worktree
de origem (mesmo SHA, mesmo lockfile); os três caminhos são ignorados pelo git e
não aparecem no diff.

O interpretador canônico do repositório é `backend/.venv/bin/python` (pytest 9.1.1).
O `python3` do sistema não tem pytest instalado.

## Google Ads — alcançabilidade e segurança

Biblioteca instalada: `google-ads 31.3.0`, que traz `v21..v25`.
`volc_ads/gads/client.py:25` fixa `VERSAO_API = "v25"`. **v25 é real e disponível.**

Leitura executada contra a conta alvo (somente leitura, autorizada):

```
SELECT customer.id, customer.descriptive_name, customer.currency_code,
       customer.test_account, customer.manager
FROM customer LIMIT 1
```
customer_id `5478096539`, login_customer_id `6016739364`. Resposta literal:

```
id=5478096539 nome='Portal Mundo Mais' moeda=BRL test_account=False manager=False
```

### O achado que importa

**`test_account=False`.** A conta 547-809-6539 não é uma conta de teste do Google
Ads. É conta de produção, em BRL, e é onde vive a campanha canário `24195821946`
PAUSED. "Conta de teste" nesta missão é um papel operacional do VOLC, não o flag
técnico do Google.

Consequências assumidas:

- `validate_only=True` permanece seguro e autorizado — a API valida e descarta;
- um `validate_only=False` acidental criaria campanha real gastando dinheiro real;
- a validação é mais estrita do que seria numa test account, o que torna a prova
  mais forte, não mais fraca;
- nenhum teste pode depender de comportamento específico de test account.

### Trava de escrita — verificada, não presumida

`volc_ads/gads/modo.py` bloqueia escrita por padrão. Executado:

```
modo.exigir_leitura_apenas('teste do lead')
-> EscritaBloqueada: o forge está em modo somente-leitura.
   Para liberar seria preciso destravar() no código E FORGE_PERMITIR_ESCRITA=1
   no ambiente. Nenhum dos dois está ativo — nada foi enviado.
```

São duas condições simultâneas, uma em código e outra em ambiente.
`client.py::mutar` (linha 176) passa pela trava antes de montar a requisição;
`client.py::validar_mutacoes` (linha 146) força `validate_only=True` e não toca
na trava. O caminho de mutação real está fechado por construção.

O furo residual não é a trava: é alguém montar um `MutateGoogleAdsRequest`
próprio com `validate_only=False`, contornando `client.py`. Isso é item de
revisão adversarial obrigatória no diff final.

## Estado do Mapa Vivo na abertura

`python3 scripts/atualizar_grafo_volc_os.py --check` devolve
`{"current": false, "reason": "UPDATE_STATUS.json ausente"}`.

Esperado numa worktree nova: `UPDATE_STATUS.json` é gerado e não versionado.
Não é regressão. O grafo é reconstruído na convergência.

## Frente paralela de frontend — não integrável nesta missão

`/private/tmp/volc-search-measurement-ux-v1` (`feat/search-measurement-ux-v1`)
estava **ativa e suja** na abertura: modificações não commitadas em
`src/components/trafego/Lancamento.tsx`, `src/pages/trafego/CampanhaCanonPage.tsx`,
`src/pages/trafego/NovaCampanhaPage.tsx`, `src/types/trafego.ts`, mais
`src/components/trafego/medicao/` não rastreado. Seu último commit é ancestral
desta base.

Sem commit final limpo, não há o que integrar. Inspecionada somente em leitura.
A convergência desta missão evita reescrever aqueles quatro arquivos.
