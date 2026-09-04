# Gates — meta-creation-engine-operator-experience-v1

Rodados na worktree `/private/tmp/volc-os-operacao-80-20`, branch
`execution/volc-os-operacao-80-20`. Nenhum gate falou com a Meta, com o
Supabase oficial ou com a rede de produção.

| # | Gate | Comando | Resultado |
|---|------|---------|-----------|
| 1 | Testes focais Meta (novos) | `backend/.venv/bin/python -m pytest backend/tests/test_meta_contrato_endurecido.py -q` | 23 passaram |
| 2 | Suíte Meta do backend | `backend/.venv/bin/python -m pytest backend/tests -k meta -q` | 174 passaram, 0 falharam |
| 3 | Testes de UI da criação Meta | `./node_modules/.bin/vitest run src/pages/trafego/__tests__/meta-criacao-bancada.test.tsx src/pages/trafego/__tests__/meta-operacao-demo.test.tsx src/components/trafego/meta/__tests__/meta-read-preview.test.tsx src/pages/__tests__/meta-campaign-insights.test.tsx` | 16 passaram |
| 4 | TypeScript | `npx tsc --noEmit -p tsconfig.app.json` | 77 erros — **exatamente os mesmos 77 do HEAD**, medidos numa cópia limpa via `git archive HEAD`. Zero erros introduzidos. Ver Ressalvas. |
| 5 | Build Vite | `npm run build` | ✓ built in 6.42s |
| 6 | Ciclo da migration candidata | `./scripts/provar-ciclo-meta-create-paused.sh` | ✓ aplicar → **usar** → reverter → reaplicar, em PostgreSQL 15 descartável |
| 7 | Whitespace | `git diff --check` | limpo |
| 8 | Scanner de segredos | `python3 scripts/verificar_segredos.py` | nenhum padrão forte encontrado |
| 9 | Frescor do grafo | `python3 scripts/atualizar_grafo_volc_os.py --check` | reconstruído nesta lane e verificado ao final |

## Suíte de front inteira

`npm test` termina com 16 testes vermelhos em 6 arquivos, todos dentro de
`src/components/trafego/inventario/**` e `src/features/work-road/**` — nenhum
deles tocado nesta missão (`git status` confirma). A mesma cópia de HEAD,
extraída com `git archive` e rodada com o mesmo `node_modules`, falha nos
mesmos arquivos: 5 falhas idênticas quando `onze-estados` e `qg-logic` rodam
isolados nas duas árvores. É defeito herdado, registrado uma vez e não
perseguido nesta lane.

## Ressalvas honestas

- **Ratchet do TypeScript.** `scripts/gate_tsc_ratchet.py` guarda baseline 76 e
  acusa vermelho em 77. Medido: **HEAD já produz 77**. O baseline está velho em
  relação aos três commits locais anteriores, não em relação a este trabalho.
  Nenhum erro novo foi introduzido; o baseline não foi alterado por esta lane
  porque mexer nele esconderia a dívida em vez de declará-la.
- **Sem verificação visual no navegador.** A extensão do Chrome não estava
  conectada nesta sessão. A rota responde 200 em `http://localhost:8080/trafego/meta/nova`,
  o módulo é servido pelo Vite desta worktree e os testes de UI renderizam a
  página inteira em jsdom, mas ninguém olhou a tela renderizada.
- **Nenhuma chamada real à Meta.** Todo HTTP dos testes é `httpx.MockTransport`
  ou mock de `pautadorApi`. A forma exata do form-urlencoded aceita pela Graph
  API v26 continua sem confirmação contra a conta real.

## Rodada corretiva

Codex (`gpt-5.6-sol`, reasoning high, sandbox read-only) revisou os cinco
primeiros commits e devolveu **doze achados**. Cada um foi verificado no código
antes de qualquer ação; **os doze eram reais** e foram fechados no commit
`fix(meta): fechar os doze achados da revisão adversarial corretiva`, com teste
para cada correção. Os gates acima foram rodados de novo depois disso.

O mesmo revisor confirmou como corretos, entre outros: ausência de
`destination_type` em OUTCOME_TRAFFIC, `advantage_audience` explícito no
payload determinístico, comparação de `start_time` por instante, cobertura dos
três caminhos de dependência, ordem e ordinalidade dos passos no banco, ausência
de rota de criação/aprovação/ativação, `criar_pausada` sem chamador de produção,
e nenhum vazamento novo de identificador Meta na interface.
