# QG Consolidation — 2026-09-03

## Veredito

Cinco lanes independentes foram reconciliadas sobre `origin/volc-os-v2`
`34dc7b41bce901bd8bebfdec0a01e293678cbf08`, numa branch de integração
isolada. Nenhuma migration foi aplicada, nenhum workflow foi ativado e nenhuma
chamada de escrita externa foi executada.

O candidato aceito para P10-T17 é o Grok final
`fa48cbaa918b3589214f157bd105a08ece6bbada`. O candidato Hermes
`2e882a91db354777417ac5060de9f30678e7ab57` não foi integrado: a adjudicação
posterior confirmou que ele não cobria concorrência real em toda a matriz nem
o fechamento contra lote em voo.

## Lanes integradas

| Lane | SHA aceito | Resultado operacional |
|---|---|---|
| Crédito Up Search ground truth | `d6b04474c50178eba82a7779a106787a17efc17b` | evidência sanitizada; nenhuma coleta nova |
| P10-T17 concorrência v12_04 | `fa48cbaa918b3589214f157bd105a08ece6bbada` | concorrência local fechada; migration oficial pendente |
| Search Delivery Sentinel 72h | `27c972094aaff826edf3562558b5c3bcb5c32d1b` | diagnóstico causal e janela 72h implementados; rotina/persistência pendentes |
| Paid Destination Policy Spine v2 | `b7192990a248003188a66c9c2c39f85f8400c1b2` | três barreiras + reauditoria em duas etapas; recibo oficial ainda não emitido |
| Paid Keyword Eligibility | código `5be28ee9d39e05a535634432d94877bd7ade8a28`; evidência final `68a8eaf2f7326d5924b1405d68ba376b0bd91a21` | conjunto positivo aprovado selado antes da rede; negativas pós-lançamento pendentes; suíte integral reconfirmada fora do sandbox |

Os conflitos em `backend/app/routers/trafego.py` e
`backend/tests/test_trafego_canario.py` foram resolvidos preservando os dois
portões independentes: destino pago e conjunto de keywords aprovado.

## Gates no resultado integrado

- Python focal de coexistência: **228 passed**.
- Python amplo, excluindo apenas três arquivos incompatíveis com o sandbox
  local por exigirem `bind()`/`initdb`: **4113 passed, 112 skipped**.
- Execução Python literal incluindo esses arquivos: **4122 passed, 113
  skipped, 9 failed, 99 errors**; todos os vermelhos foram causados pela
  proibição ambiental de sockets/cluster local, não pelas lanes integradas.
- FunnelForge engine: **748 passed**.
- Vitest com as variáveis locais canônicas: **1483 passed, 3 skipped**.
- Build Vite: verde.
- TypeScript: **76 erros herdados**, mesma dívida conhecida antes da
  consolidação; nenhum erro novo atribuído ao ownership integrado.
- Gate de ausência de mutação Google: **3/3**, incluindo 5 contraprovas da
  rota.
- v12_04, concorrência real em PostgreSQL 16.14 descartável: **17/0**.
- v12_04, ciclo apply → operate → rollback → reapply: **116/0**.
- Autoridade Supabase: `https://database.agenciavolc.com.br` confirmada por
  leitura; nenhuma escrita.
- Secret scan e `git diff --check`: verdes.

Após a consolidação inicial, a própria lane de Paid Keyword Eligibility
reexecutou a suíte integral fora da restrição de `bind()`/`initdb` e registrou
**3348 passed, 112 skipped, 0 failed**, além de **117 passed, 1 skipped** nos
três arquivos antes impedidos pelo sandbox. O commit `68a8eaf` contém somente
essa evidência; nenhum código ou estado operacional mudou.

## Roadmap e leitura de progresso

A fórmula canônica do QG exclui itens `reserved` e usa os pesos do próprio
Roadmap (`done=1`, `partial=0.5`, `risk=0.25`, `todo=0`).

- Base oficial antes da consolidação: **43,2%** — 150 tarefas contáveis.
- Resultado consolidado: **44,3%** — 153 tarefas contáveis.
- Distribuição consolidada: **39 done, 57 partial, 56 todo, 1 risk**, além de
  11 reservadas fora do percentual.

O aumento líquido parece pequeno porque três riscos que estavam implícitos
viraram tarefas explícitas P09-T16/T17/T18. Isso aumenta o denominador e evita
um percentual artificialmente otimista. Materialmente, P10-T17 virou `done` e
P05-T09, P05-T13, P06-T05 e P10-T12 passaram de `todo` para `partial`.

## Resíduos prioritários honestos

1. P09-T16: retirar a credencial WordPress do alcance direto do CLI do motor.
2. P09-T17: inventariar e fechar todos os caminhos de criação de campanha fora
   de `/subir`.
3. P09-T18: incluir detectores, limiares e severidades no fingerprint da
   política de destino.
4. P10-T16: janela separada para migration v12_04 oficial, import inativo,
   canário, leitura real, heartbeat e ativação única no n8n.
5. P05-T08/P05-T09/P06-T05: fechar o ciclo pós-lançamento de termos/negativas e
   persistir os incidentes do guardião 72h.

Os textos antigos de `HANDOFF.md`/`REMAINING-RISKS.md` da lane de destino que
dizem que não existe emissor de recibo live representam um checkpoint anterior
aos commits finais `3ab2f11` e `b719299`; foram preservados como histórico. A
verdade consolidada está no `CURATION-HANDOFF.json`, neste recibo, no Roadmap e
na curadoria operacional reconstruída.

## Limites e zero mutação

Zero merge em `main`; zero deploy; zero Google Ads mutate/validate-only; zero
Supabase write ou migration oficial; zero n8n import/write/activation; zero
publicação WordPress; zero mudança de landing page viva. A branch de integração
não deve ser enviada a `volc-os-v2` sem autorização literal do proprietário.
