# RED TEAM — veredito independente sobre a V2 integrada (17/10/2026)

Alvo revisado: branch `lab/fable-viability-kernel-v2-20261017`, SHA `6bde76b164bbbc2600a592e31c6ceb22e227998a`, worktree do integrador (árvore limpa, lida sem modificação).
Suíte RED usada: exatamente o commit `055ca6b4` (confirmado: `git diff 055ca6b4 6bde76b1 -- tests/data-intelligence/viability/adversarial` vazio; `git log` do diretório mostra só `3c89d05b` e `055ca6b4`).
Python: 3.13 do lab (`data-intelligence-overnight-20261015/.venv`). Tudo abaixo foi executado, não inferido.

## 1. Contagens

| Execução | V1 (2e982a82) | V2 (6bde76b1) |
|---|---|---|
| `tests/data-intelligence/viability/adversarial` (RED, 58 testes) | 44 failed / 14 passed | **58 passed / 0 failed** |
| `tests/data-intelligence/viability` (kernel + RED) | 106 (sem RED) | **262 passed** (204 kernel + 58 RED) |

Todos os 44 testes que falhavam na V1 passam na V2; os 14 controles continuam passando (nenhuma regressão no comportamento que a V1 já acertava).

## 2. Matriz achado → teste RED → V1 → V2

| # | Achado | Teste | V1 | V2 |
|---|---|---|---|---|
| 1 | Custo de dia maduro sem receita filtrado | `test_red01…` | `already_profitable` (+150 com perda real de 450) | PASS — custo soma 900; cobertura 3/4 é lacuna |
| 2 | Break-even por visita | `test_red02…` | 1,50/visita > CPC 1,00 ("favorável") | PASS — `rpc_por_clique` 0,75 decide; por visita só reportada |
| 2b | visitas=0 cai para cliques | `test_red02b…` | `visitas_elegiveis=100` | PASS — `rpc_por_visita_indisponivel="visitas_zero"` |
| 3a/3b | Custo/cliques PROJECTED | `test_red03a/b…` | `already_profitable`, `high` | PASS — `realizada` exige custo e cliques; invariante cobre |
| 3c | Receita observada há 10 d (SLA 7) | `test_red03c…` | sem `observado_em` (construção) | PASS — `stale` bloqueante → `insufficient_evidence` |
| 3d/3e | Flag `invalid_*` (entrada/medida) | `test_red03d/e…` | ignorada / inexistente | PASS — `invalid_flag` bloqueante |
| 4 | Intervalos USD + perda BRL sem câmbio | `test_red04…` | teto em "BRL" com micros USD | PASS — `perda_maxima_moeda_incompativel` |
| 5 | Simulação USD vs economia BRL | `test_red05…` | curva analisada | PASS — `CurvaIndisponivel(moeda_incompativel)` |
| 6 | Stop-loss por gasto bruto | `test_red06…` (1000/999/200) | `parar_por_stop_loss` | PASS — perda líquida realizada vs tolerância |
| 7 | Valor bruto negativo | `test_red07…` ×2 | aceito | PASS — recusado; contribuição negativa continua permitida |
| 8a/8b | Câmbio/taxa do futuro | `test_red08a/b…` ×4 | sem data (construção) | PASS — `effective_at`/`disponivel_em` > as_of recusados |
| 8c | Autorização do futuro | `test_red08c…` ×2 | sem `Autorizacao` | PASS |
| 9 | Datas duplicadas | `test_red09…` | `dias_maduros=4`, custo em dobro | PASS — dedup + `datas_duplicadas=1` |
| 10a–10d | `verify` com artefato/campo faltante ou adulterado | `test_red10a/b/c/d…` | exit 0 (ou 2) | PASS — exit 4 em todos |
| 10f | Recibo com commit, ambiente, relatório | `test_red10f…` | faltavam | PASS |
| 11 | `perda_maxima` por texto/sem proveniência | `test_red11…` (adapter ×3, de_json ×5, construtor, issuer ×5, hash) | aceito | PASS — só com `Autorizacao` válida |
| 12 | Moedas heterogêneas no ledger | `test_red12…` | somadas | PASS — `moedas_heterogeneas` |
| 13a | Vocabulário de vereditos | `test_red13a…` | `structurally_unviable` | PASS — `unviable_under_declared_scenarios` |
| 13b | `viable_candidate` alcançável | `test_red13b…` | `already_profitable` com 300 cliques | PASS — `viable_candidate`, confiança ≤ medium |

## 3. Reconciliações do integrador — julgamento

**(a) Stop-loss = perda líquida REALIZADA `max(0, custo − receita comparável) > max_loss`; perda conservadora vira aviso.** Executado com o critério do owner (gasto 1.000, receita 950, max_loss 100): `test_with_cap · propor_teste_limitado · medium`, razão `perda_conservadora_acima_da_tolerancia`, `net_loss_observed=50`, `net_loss_conservative=195`, invariantes ok. **Aceitável e correto**: parada é sobre dinheiro já perdido; a perda sob premissas é projeção e fica visível como aviso com os dois números no resultado. O gasto bruto não é comparado em lugar nenhum (`gate.py`, ramo 2).

**(b) Senac com `cobertura_receita_ppm=None`.** Honesto: o experimento de origem não estrutura cobertura. Consequência verificada: `cobertura_receita_incompleta` em `missing_evidence`, e tanto o gate (`bloqueia_positivo`) quanto a invariante impedem veredito positivo com cobertura desconhecida — a fixture é `unviable_under_declared_scenarios` por economia, não por cobertura. **Aceitável.** Ressalva: a janela da fixture (`inicio=2026-10-12, fim=2026-10-15, dias_maduros=16`) é inconsistente (4 dias de intervalo, 16 maduros) desde a V1 — o gerador usa `corte_maturidade..as_of` como intervalo. O kernel não usa `inicio/fim` em nenhuma decisão (grep em gate/economia/teto/invariantes), então não altera veredito; é defeito de proveniência da fixture (ver risco R5).

**(c) Achados extras do RED-TEAM-V1.md — estado na V2 (todos executados):**

| Achado extra | V2 | Evidência executada |
|---|---|---|
| Moeda do custo não checada | **Parcial.** Invariante checa; o GATE não (`moeda_provada` só olha a receita) | custo `moeda_evidencia=ATTESTED`, resto favorável → `avaliar` devolve `already_profitable · high`; `verificar_invariantes` levanta; CLI `evaluate` sai **4** sem gravar resultado. Pela biblioteca (`avaliar` direto) o falso positivo sai. |
| Cliques ausentes viram zero no adapter | **Corrigido** — `cliques_unknown` + flag | código `adaptadores.py` 163–167 |
| Moeda padrão silenciosa no adapter | **Permanece** — linhas sem moeda recebem BRL/USD sem flag | `moedas por default: BRL USD flags: ()`; mitigação: `moeda_evidencia=unknown` para ambas, o que bloqueia positivos |
| `JanelaObservada` sem cross-check de dias × intervalo | **Permanece** | `JanelaObservada("2026-10-14","2026-10-15",16)` aceita |
| `janela.fim` depois do `as_of` | **Permanece** | `fim=2026-12-31` com `as_of=2026-10-15` aceita na entrada |
| `codigo_sha256` só sobre `viability/*.py` | **Parcial** — inclui a CLI e `source_commit`; `contracts/money.py` continua fora | `MODULOS = … + [Path(__file__)]` |
| `verify` confia na `entrada` do recibo | **Permanece por desenho**, agora declarado na saída ("integridade/reprodutibilidade, não autoria") | `cmd_verify` |
| Revshare ESTIMATED ao valor de face | **Permanece** | revshare `0.95 estimated`, resto favorável → `already_profitable · high`, invariantes ok |
| Stop-loss só com receita realizada | **Permanece** | custo 1.000 obs, receita 100 PROJECTED, tolerância 100 → `test_with_cap · low` com teto, sem parada |
| `zero_confirmed` com `receita_micros=None` → TypeError | **Corrigido** — vira `absent` + flag | executado |
| Invariante só protegia a receita | **Corrigido** — custo/cliques/stale/invalid/cobertura/moeda do custo | `invariantes.py` V2 |

**Regra de `issuer` (4950fbe6).** Aceita `<papel>:<identidade>` com ambos não vazios ou identidade nua com `@`. Executado: `tarcisio@agenciavolc.com.br`, `bia@volc`, `owner:bia`, `agente:x`, `owner:lab-fixture` são todos aceitos; `owner`, `bia`, `""` recusados (RED 11c). Ou seja: a regra valida FORMATO de identidade, não identidade. O hash da `Autorizacao` prova integridade do conteúdo, não autoria (docstring do contrato diz isso). Quem monta o dict pode cunhar uma autorização válida com qualquer issuer formatado. Aceitável para um kernel offline/shadow sem autoridade de gasto, **desde que** nenhum consumidor trate `Autorizacao` como prova de consentimento do owner sem um registro externo (assinatura ou tabela de autorizações do lado VOLC).

## 4. Riscos remanescentes

| ID | Risco | Severidade | Onde | Ação recomendada |
|---|---|---|---|---|
| R1 | Gate e invariante discordam sobre a moeda do custo: `avaliar` produz `already_profitable · high` com `custo.moeda_evidencia` não observada; a CLI aborta com exit 4 (sem resultado), a biblioteca devolve o falso positivo. O adapter deixa `moeda_evidencia` do custo em `unknown` quando a linha não traz `custo_moeda_evidencia`, o que torna o caminho fácil de atingir por um ledger incompleto. | **Média** (contida pela invariante na CLI; aberta para consumidores de biblioteca, que hoje não existem) | `gate.py` `moeda_provada`; `adaptadores.py` `_moeda_unica`/evidência do custo | Uma linha: `moeda_provada` exigir `e.custo.moeda_evidencia is OBSERVED`; teste de gate correspondente. Fazer antes de qualquer consumidor chamar `avaliar` sem `verificar_invariantes`. |
| R2 | `VERSAO_KERNEL` continua `viability-kernel@1.0.0` na V2: recibos, replay e resultado rotulam o código V2 como V1. `codigo_sha256`/`source_commit` distinguem, o rótulo humano não. | **Baixa** (proveniência), correção trivial | `viability/__init__.py` | Subir para `2.0.0` e regenerar replay/recibo (muda `result_hash` de tudo — fazer antes do merge, não depois). |
| R3 | `Autorizacao` prova integridade, não autoria; issuer é formato, não identidade. | **Média** como primitiva de autoridade; **baixa** no estado shadow atual | `contrato.Autorizacao` | Documentar como "referência a autorização externa"; antes do primeiro consumidor, registro de autorizações do lado VOLC (ou assinatura) e checagem do `authorization_id` contra ele. |
| R4 | Parâmetros `revshare`/`imposto` com evidência ESTIMATED/ATTESTED entram ao valor de face e não impedem `already_profitable · high`. | **Baixa-média** | `economia.receita_liquida_comparavel`, `gate._confianca` | Incluir evidência dos parâmetros na governança (`impede_alta`) ou aplicar desconto de premissa como já se faz com câmbio. |
| R5 | `JanelaObservada` não cruza `dias_maduros` com o intervalo nem `fim` com `as_of`; a fixture Senac carrega janela inconsistente desde a V1. | **Baixa** (nenhuma decisão usa `inicio/fim`) | `contrato.JanelaObservada`, `viability_gerar_fixtures.py` | Validar `dias_maduros + dias_imaturos <= dias(inicio..fim)` e `fim <= as_of.date()`; corrigir o intervalo da fixture Senac no gerador. |
| R6 | Receita PROJECTED com gasto muito acima da tolerância recebe `test_with_cap` com teto, não parada (stop-loss exige receita realizada). | **Baixa** (confiança `low`, teto limitado pela tolerância) | `gate.py` ramo 2 | Opcional: quando `custo` realizado > tolerância e receita não realizada, degradar para `insufficient_evidence` sem teto. |
| R7 | Moeda padrão (BRL/USD) silenciosa no adapter para linhas sem moeda. | **Baixa** (mitigado por `moeda_evidencia=unknown`) | `adaptadores._moeda_unica` | Emitir flag `moeda_assumida_*` ou recusar. |
| R8 | `codigo_sha256` não cobre `contracts/money.py`. | **Baixa** (`source_commit` cobre o repositório) | `viability_cli.MODULOS` | Incluir o módulo de dinheiro no hash. |

Nenhum dos riscos reabre um achado da suíte RED; R1 é a única inconsistência interna nova que encontrei na V2 e está na família dos falsos positivos que a missão atacou — por isso a condição abaixo.

## 5. Veredito

**APPROVE_WITH_LOW_RISKS** — para o estado declarado do kernel (offline/shadow, sem autoridade de gasto, consumido só pela CLI com invariantes em runtime).

Razões:
1. Os 44 falsos positivos e lacunas de contrato provados na V1 estão corrigidos na V2 e verificados pela mesma suíte, sem alteração entre as rodadas além dos dois ajustes de nome pedidos pelo integrador (`055ca6b4`); os 14 controles não regrediram; a suíte completa do kernel passa (262).
2. O critério do owner para stop-loss (1.000/950/100 não aciona) foi executado e atendido com os dois números de perda (realizada e conservadora) visíveis no resultado.
3. A governança de evidência (custo/cliques projetados, stale, `invalid*`, cobertura, moeda do custo) está na invariante de runtime, que a CLI aplica em `evaluate`, `replay` e `verify`.

Condições para que o "low risks" continue verdadeiro (não autoaprovo nenhuma delas; cabe ao integrador fechar e a mim reexecutar se pedido):
- **R1 antes de qualquer consumidor de biblioteca** (Pautador, Bia, Hub) chamar `avaliar` sem `verificar_invariantes`; a correção é de uma linha e cabe num commit do integrador com teste de gate. Sem isso, para consumidores de biblioteca o veredito seria REJECT.
- **R2 antes do merge** (rótulo de versão), porque muda todos os hashes e o replay — depois do merge vira uma mudança de proveniência difícil de explicar.
- **R3 documentado** no README (seção V2) como "referência de autorização; integridade, não autoria".
