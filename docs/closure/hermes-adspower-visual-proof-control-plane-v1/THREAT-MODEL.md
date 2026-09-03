# Threat Model — AdsPower Broker + Visual Proof

## Ativos protegidos

- Valor da API key do AdsPower resolvido via cofre.
- Referência lógica de cofre e `user_id` AdsPower da allowlist do broker.
- Sessão autenticada do perfil AdsPower.
- Screenshot de superfície autenticada.
- Identidade de owner/ativo/job/recibo.

## Fronteiras

| Fronteira | Defesa implementada/provada |
|---|---|
| VOLC → broker | Bearer próprio, `hmac.compare_digest`, rota única de operação, campo desconhecido recusado |
| broker → cofre | resolvedor recebe referência da allowlist, não do payload público; stdout/stderr de erro do `op` não são ecoados |
| broker → AdsPower | endpoint literal de loopback, porta allowlisted, API verification obrigatória, sem nome DNS |
| browser → superfície | URL HTTPS pública, domínio esperado, todos os IPs resolvidos públicos, redirect revalidado |
| recibo → frontend | motivo/URL/console sanitizados; sem cookie/proxy/token/user_id/localizador; screenshot por referência/hash |

## Ameaças e status

| Ameaça | Status |
|---|---|
| Segredo aceito no payload do broker | refutado por campo desconhecido e allowlist |
| Referência incompleta resolvida | recusada no preflight do perfil autorizado |
| Valor secreto em log/erro/recibo | testado por sentinela e varredura estrutural |
| Bind público | recusado no preflight; não há flag de relaxamento |
| API verification desligada | recusada no preflight |
| Profile ID alheio/arbitrário | `user_id` só na allowlist; payload público não aceita `user_id` |
| Owner A usar job/perfil de B | recusado por domínio/aplicação/broker |
| Operação fora da allowlist | recusada antes de resolver segredo |
| Endpoint externo ou DNS privado | recusado; endpoint AdsPower exige IP literal loopback |
| Redirect para rede privada | URL final e saltos revalidados |
| Retry duplicar execução | idempotência por impressão do pedido |
| Concorrência executar duas vezes | lease em memória provado; durabilidade ainda é handoff |
| Timeout virar aprovação | falha técnica vira `indeterminate` |
| Screenshot ausente virar aprovado | ausência de imagem vira `indeterminate` |
| Falha AdsPower reprovar editorialmente página | falha técnica vira `indeterminate` |
| Frontend mostrar indeterminado como verde | testado: só `aprovado` tem tom `sucesso` |

## Limitações honestas

- Lease/idempotência são em memória; produção multi-processo precisa persistência governada.
- Driver real CDP/Playwright/Puppeteer não foi implementado; `NavegadorNaoImplementado` recusa.
- Fake AdsPower segue documentação oficial consultada, mas não prova comportamento do AdsPower real.
- Nenhum perfil/página real foi executado.
