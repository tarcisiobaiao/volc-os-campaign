# Revisão adversarial — Codex, read-only

Revisor: `codex-cli 0.151.0`, `model_reasoning_effort=high`, sandbox
`read-only`. Alvo: `37258f1c..1ad7b8a`. Nenhum arquivo foi alterado pelo
revisor, nenhum teste rodado por ele, nenhuma chamada de rede.

**Oito achados. Sete verificados como reais e corrigidos; um verificado e
rejeitado, com a razão registrada.** O veredito do revisor foi REPROVADO, e ele
estava certo: dois dos achados eram caminhos concretos de duplicação de
campanha.

---

## Adjudicação

| # | Achado | Veredito | Onde ficou |
|---|---|---|---|
| 1 | Duplicação por mudar só um filho, ou por reaprovar após expiração/falha | **REAL** | sonda por `(conta, passo, payload)` em `prepare_step`, salt 1603 |
| 2 | Reconciliação prova "ausência" com o despachante ainda em voo | **REAL** | `p_idade_minima_s` em `resolve_absent`, piso de 60 s, padrão 120 s |
| 3 | Read-back divergente não fica registrado no recibo | **REAL, remédio recusado** | `readback_error` + `flag_readback`; a ORDEM não mudou — ver abaixo |
| 4 | Objeto antigo homônimo adotado pela reconciliação | **REAL** | correlação por `created_time` vs `prepared_at`; criativo nunca fecha por leitura |
| 5 | Ambiguidade apresentada como 422 sem reconciliação | **REAL** | `exige_reconciliacao` na exceção; a rota parou de adivinhar por lista de códigos |
| 6 | AdCreative nasce ACTIVE | **REJEITADO** | contradiz a receita aprovada — ver abaixo |
| 7 | Validação escreve no ledger com a criação fechada | **REAL** | `criacao_liberada()` passou a condicionar a gravação do recibo |
| 8 | Keychain aberto antes de provar o recibo de validação | **REAL** | `validation_lookup` + `_exigir_validacao_utilizavel`, antes do segredo |

Cada correção nasceu com um teste que reproduz o CENÁRIO do achado, não a
existência do conserto — eles ficam vermelhos se alguém reverter a correção.
Os sete estão em `backend/tests/test_meta_criacao_pausada_rotas.py` (bloco
"OS ACHADOS DA REVISÃO ADVERSARIAL") e em
`scripts/provar-ciclo-meta-create-paused.sh` (blocos `$duplicacao$` e `$tempo$`).

---

## O achado 3 estava certo; o remédio proposto, não

O revisor propôs fechar o passo **depois** do read-back. Isso seria uma
regressão: o id que a Meta acabou de devolver precisa estar gravado antes de
qualquer outra coisa, senão uma queda entre o `POST` e o `INSERT` perde para
sempre a única prova de que o objeto nasceu — e a reconciliação teria que
procurá-lo às cegas.

O que estava faltando não era a ordem, era o **registro da divergência**. O
recibo dizia apenas `CREATED`, e quem o lesse depois concluiria que estava tudo
certo. A coluna `readback_error` conserta isso sem inverter a ordem que protege
o id.

## O achado 6 foi rejeitado, e a razão é a receita

O revisor apontou que o `AdCreative` nasce `ACTIVE` e que isso contraria "nenhum
objeto pode chegar a ACTIVE/ENABLE". A missão que governa esta lane declara o
contrário, literalmente:

> - Campaign: PAUSED;
> - AdSet: PAUSED;
> - Ad: PAUSED;
> - **Creative não é veiculável.**

Um `AdCreative` não veicula sozinho: ele só entrega através de um `Ad`, e a Meta
o devolve `ACTIVE` por construção — não existe payload que o faça nascer pausado.
O executor já declara isso no recibo (`veiculavel: false`) e a tela mostra "Não"
na coluna de veiculação. Mudar isso exigiria mudar a receita aprovada, e a
receita é o que esta lane está proibida de mexer.

---

## O relatório do revisor, na íntegra

## Veredito: REPROVADO

Revisão estática de `37258f1c..1ad7b8a`, estritamente somente leitura. Não executei testes, migrations ou chamadas de rede. A migration continua apenas candidata.

A skill `adversarial-review` orientou as lentes de concorrência, limites arquiteturais e simplificação, mas a etapa cross-model não foi executada porque exigiria rede e arquivos temporários, contrariando suas restrições.

### O que verifiquei e considerei correto

- As rotas de aprovação, criação, reconciliação e recibo exigem host local, ADMIN e as duas flags principais.
- `META_VALIDATE_ONLY_ENABLED` não autoriza diretamente `criar-pausada`.
- No caminho normal, hash mostrado, hash gravado e hash recompilado são comparados.
- Manifesto, quantidade de operações, orçamento, moeda e conta são reconferidos.
- O ledger serializa passos da mesma aprovação e exige o ordinal anterior como `CREATED`.
- Campaign, AdSet e Ad são enviados com `status=PAUSED`, e o read-back exige conta, pais e estado.
- Não encontrei rota ou botão de ativação.
- As respostas normais usam referências opacas e não devolvem IDs externos, `image_hash`, URL assinada ou service role.

### Achados, do mais grave ao menos grave

1. **CRITICO — A idempotência por hash do plano inteiro permite duplicar a campanha ao alterar somente um filho ou ao reaprovar depois de expiração/falha.**

   Cenário concreto: P1 cria a campanha, mas o AdSet falha ou fica ambíguo. O operador altera apenas `start_time`, headline ou outro campo de filho. Isso produz P2 com outro hash, embora o payload da campanha permaneça idêntico. A aprovação de P2 passa, cria um ledger novo e despacha novamente a mesma campanha.

   O hash incorpora todas as operações ([compilador.py:197](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/compilador.py:197)). O bloqueio procura somente aprovação com o mesmo `plan_sha256` ([migration:441](/private/tmp/volc-os-operacao-80-20/supabase/migrations/20260904183418_meta_create_paused_executor.sql:441)), enquanto os passos são únicos apenas dentro do `approval_id` ([migration:205](/private/tmp/volc-os-operacao-80-20/supabase/migrations/20260904183418_meta_create_paused_executor.sql:205)). O executor começa novamente por `campaign` e despacha quando o novo ledger responde `DESPACHAR` ([executor.py:272](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/executor.py:272), [executor.py:291](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/executor.py:291), [executor.py:307](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/executor.py:307)).

   Mesmo sem alterar o plano, a proteção termina quando a aprovação expira ou possui qualquer passo `FAILED`. O próprio script prova e exige que esses casos liberem uma nova aprovação ([provar-ciclo:540](/private/tmp/volc-os-operacao-80-20/scripts/provar-ciclo-meta-create-paused.sh:540), [provar-ciclo:549](/private/tmp/volc-os-operacao-80-20/scripts/provar-ciclo-meta-create-paused.sh:549)). Não existe identidade idempotente por operação/conta nem reaproveitamento governado do prefixo já criado.

2. **CRITICO — A reconciliação pode provar “ausência” enquanto o despachante original ainda não enviou, fechando `FAILED` antes de o objeto nascer.**

   Cenário concreto:

   1. Sessão A grava `IN_FLIGHT` e recebe `DESPACHAR`.
   2. Antes de A efetivamente enviar o POST, sessão B reentra; o SQL converte o passo de `IN_FLIGHT` para `AMBIGUOUS`.
   3. A reconciliação lista a conta, ainda não encontra o objeto e fecha o passo como `FAILED`.
   4. A retoma e envia o POST; a Meta cria o objeto, mas `close_step` falha porque o ledger já está `FAILED`.
   5. Uma nova aprovação é permitida e pode criar o mesmo objeto outra vez.

   A preparação retorna antes do POST ([executor.py:291](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/executor.py:291), [executor.py:307](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/executor.py:307)); a reentrada transforma unilateralmente `IN_FLIGHT` em `AMBIGUOUS` ([migration:550](/private/tmp/volc-os-operacao-80-20/supabase/migrations/20260904183418_meta_create_paused_executor.sql:550)). Uma listagem vazia vira `AUSENTE` imediatamente ([reconciliacao.py:159](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/reconciliacao.py:159)) e a RPC grava `FAILED` ([migration:673](/private/tmp/volc-os-operacao-80-20/supabase/migrations/20260904183418_meta_create_paused_executor.sql:673)).

   Não há lease, fencing token, idade mínima de reconciliação ou confirmação de que nenhum despachante ainda possui autoridade para enviar.

3. **ALTO — O passo é fechado como `CREATED` antes do read-back; uma leitura ausente ou divergente deixa recibo verde sem prova.**

   Cenário concreto: a Meta devolve ID para a campanha; o ledger é fechado; o read-back depois devolve `ACTIVE`, corpo inválido ou timeout. A rota responde 502, mas o recibo já afirma `CREATED` e `has_external_id=true`. A reconciliação encontra zero passos ambíguos e não corrige esse estado.

   A ordem atual é: guardar o ID, chamar `fechar_passo`, e somente depois `_read_one`/`_validar_read_back` ([executor.py:329](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/executor.py:329), [executor.py:346](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/executor.py:346)). A RPC transforma imediatamente o passo em `CREATED` ([migration:605](/private/tmp/volc-os-operacao-80-20/supabase/migrations/20260904183418_meta_create_paused_executor.sql:605)). Quando não há `AMBIGUOUS`, `/reconciliar` simplesmente devolve o recibo ([trafego_meta_criacao.py:483](/private/tmp/volc-os-operacao-80-20/backend/app/routers/trafego_meta_criacao.py:483)).

   Não existe estado intermediário “ID recebido, aguardando read-back” nem transição de `CREATED` para ambíguo após falha de leitura.

4. **ALTO — A reconciliação pode atribuir ao recibo um objeto antigo apenas porque nome e configuração coincidem.**

   Cenário concreto: a conta já contém uma campanha PAUSED chamada “Campanha X” com a mesma receita. O novo POST falha antes de criar qualquer coisa e deixa o passo ambíguo. A reconciliação encontra exatamente a campanha antiga, valida seus campos e fecha o passo com o ID antigo. Uma reentrada passa a criar o novo AdSet sob essa campanha antiga e pode terminar com sucesso falso.

   A busca usa somente o nome aprovado ([reconciliacao.py:130](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/reconciliacao.py:130), [reconciliacao.py:231](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/reconciliacao.py:231)); encontrar exatamente um resultado e fazê-lo passar pelo read-back basta para concluir `CRIADO` ([reconciliacao.py:165](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/reconciliacao.py:165)). Os campos lidos nem incluem `created_time` ou um marcador de correlação ([executor.py:163](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/executor.py:163)).

   A unicidade de nomes validada pelo contrato vale apenas dentro do lote, não dentro da conta. Não há nonce da operação, etiqueta idempotente ou janela temporal que prove que o objeto nasceu deste despacho.

5. **ALTO — Respostas remotas ambíguas podem ser apresentadas como 422 sem necessidade de reconciliação.**

   Cenário concreto: depois do POST de criação, a Meta ou um gateway devolve HTTP 500 com um objeto `error`, ou uma resposta JSON inválida. `_post` não considera a criação descartada; o executor marca o passo `AMBIGUOUS`. Entretanto, o router devolve 422 e `reconciliacao_necessaria=false`, sem refletir o estado durável real.

   `_post` só define `criacao_descartada` para resposta Meta reconhecível entre 400 e 499 ([executor.py:430](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/executor.py:430), [executor.py:451](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/executor.py:451)); os demais erros após despacho são marcados como ambíguos ([executor.py:315](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/executor.py:315)). Porém `META_REMOTE_CREATE_FAILED` e `META_INVALID_RESPONSE` não pertencem à lista de códigos ambíguos do router ([trafego_meta_criacao.py:183](/private/tmp/volc-os-operacao-80-20/backend/app/routers/trafego_meta_criacao.py:183)), levando a 422 e reconciliação falsa ([trafego_meta_criacao.py:191](/private/tmp/volc-os-operacao-80-20/backend/app/routers/trafego_meta_criacao.py:191)).

6. **MEDIO — O fluxo cria deliberadamente um AdCreative `ACTIVE`, contrariando o requisito literal de que nenhum objeto possa chegar a ACTIVE/ENABLE.**

   Cenário concreto: toda criação estática monta o payload do creative sem `status`; a Meta o devolve `ACTIVE`; o read-back aceita isso e a resposta pública pode mostrar `ACTIVE`.

   O payload do creative contém apenas `name` e `object_story_spec` ([compilador.py:173](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/compilador.py:173)). A guarda `status == PAUSED` exclui explicitamente `creative` ([executor.py:274](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/executor.py:274)), e seu read-back somente recusa `DELETED` ou `WITH_ISSUES`, aceitando `ACTIVE` ([executor.py:549](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/executor.py:549)).

   O creative não é veiculável sozinho, mas o código ainda cria e confirma um objeto em `ACTIVE`; portanto não satisfaz a condição absoluta solicitada.

7. **MEDIO — A validação escreve no ledger com `META_CREATE_PAUSED_ENABLED` fechada.**

   Cenário concreto: `META_VALIDATE_ONLY_ENABLED=1`, `META_CREATE_LEDGER_WRITE_ENABLED=1` e `META_CREATE_PAUSED_ENABLED` ausente. Uma validação aceita chama a RPC e insere `trafego_meta_validation_receipt`.

   A rota verifica somente a flag de validate-only ([trafego_meta_validacao.py:338](/private/tmp/volc-os-operacao-80-20/backend/app/routers/trafego_meta_validacao.py:338)) e depois chama `registrar_validacao` ([trafego_meta_validacao.py:397](/private/tmp/volc-os-operacao-80-20/backend/app/routers/trafego_meta_validacao.py:397)). O adaptador de ledger exige apenas `META_CREATE_LEDGER_WRITE_ENABLED` ([registro.py:61](/private/tmp/volc-os-operacao-80-20/backend/app/trafego/meta_execucao/registro.py:61)).

   Assim, há escrita no ledger sem as duas flags exigidas pelo critério da revisão, embora não haja criação de objeto Meta nesse caminho.

8. **MEDIO — `/aprovar` abre o Keychain e consulta a Meta antes de provar que o recibo de validação submetido existe e é utilizável.**

   Cenário concreto: um ADMIN local envia confirmação correta e um `validation_id` inventado, expirado ou pertencente a outro ator. A rota lê o token e recompila — realizando leituras na Meta — antes de o banco rejeitar o recibo.

   Depois das flags, a rota chama `_credencial_salva` e `_compilar` nas linhas 329–330, mas somente chama `registro.aprovar` na linha 339 ([trafego_meta_criacao.py:324](/private/tmp/volc-os-operacao-80-20/backend/app/routers/trafego_meta_criacao.py:324)). A existência, ator, conta, hash e idade do recibo só são conferidos dentro dessa RPC ([migration:400](/private/tmp/volc-os-operacao-80-20/supabase/migrations/20260904183418_meta_create_paused_executor.sql:400)).

   O código não oferece uma leitura/validação durável anterior à resolução do segredo. Nenhum objeto é criado nesse cenário, mas a ordem “ledger comprovado antes do Keychain” não é cumprida.
