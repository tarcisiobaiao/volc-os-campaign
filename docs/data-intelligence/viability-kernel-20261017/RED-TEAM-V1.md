# RED TEAM V1 — suíte adversarial do kernel de viabilidade (17/10/2026)

Alvo: `2e982a82` (V1, `viability-kernel@1.0.0`). Branch desta suíte: `lab/fable-viability-kernel-v2-C-20261017`.
Suíte: `tests/data-intelligence/viability/adversarial/` (9 módulos `test_red_*.py`, `conftest.py` com `sobrescrever` e `autorizacao_v2`).
Nenhum arquivo de produto foi tocado. Os testes foram escritos contra a interface V2 fixada pelo integrador; a mesma suíte será reexecutada, sem alteração, contra a V2 integrada.

Comando (raiz do worktree, Python 3.13 do lab):

```bash
$PY -m pytest tests/data-intelligence/viability/adversarial -q -p no:cacheprovider
```

## Resultado na V1

**58 testes: 44 FAIL, 14 PASS.** Os 14 que passam são controles declarados (comportamento que a V1 já acerta e a V2 precisa manter) ou subcasos que a V1 já cobre (hashes adulterados no recibo). Nenhum ERROR: toda falha por construção é convertida em `pytest.fail` com a mensagem `falha por construção: …`, para que o relatório distinga "a V1 decide errado" (asserção) de "a V1 não tem o campo" (construção).

Classificação das 44 falhas: **31 por asserção econômica/contratual** (a V1 roda e decide errado) · **13 por construção** (campo/classe V2 inexistente na V1: `observado_em`, `flags_qualidade` por medida, datas em `Cambio`/`Taxa`, `Autorizacao`).

Suíte V1 original com o pacote adversarial ao lado: 106 passed (inalterada).

## Matriz achado → teste → V1 → V2 esperado

| # | Achado | Teste | V1 (2e982a82) | Tipo de falha | V2 esperada |
|---|---|---|---|---|---|
| 1 | Dia maduro com custo alto e receita ausente some do custo | `test_red_adaptador_ledger::test_red01…` | `already_profitable`, contribuição +150 BRL (custo real 900, somado 300) | asserção | custo soma todos os dias maduros; cobertura de receita 3/4 é lacuna própria; nunca `already_profitable` |
| 2 | Break-even por visita em vez de por clique | `test_red_economia::test_red02…` | contribuição −25 correta, mas `break_even_cpc` = 1,50 (receita/visita) > CPC 1,00 → "favorável" | asserção | `rpc_por_clique` = 0,75 decide; `rpc_por_visita` só reportada |
| 2b | `visitas=0` cai para cliques | `test_red_economia::test_red02b…` | `visitas_elegiveis=100` (0 tratado como não informado) | asserção | visitas=0 válido; receita/visita indisponível; nunca fallback |
| 3a | Custo PROJECTED decide lucro | `test_red_evidencia::test_red03a…` | `already_profitable`, confiança `high` | asserção | custo e cliques realizados obrigatórios; nunca `high` |
| 3b | Cliques PROJECTED decidem lucro | `test_red_evidencia::test_red03b…` | `already_profitable`, confiança `high` | asserção | idem |
| 3c | Receita observada há 10 dias (SLA 7) | `test_red_evidencia::test_red03c…` | `MedidaMonetaria` sem `observado_em` | construção | `observado_em` + `freshness_sla_dias=7`; sem `already_profitable`/`high` |
| 3d | Flag `invalid_*` na entrada ignorada | `test_red_evidencia::test_red03d…` | `already_profitable`, confiança `high` (flag hasheada, nunca lida) | asserção | flag `invalid_*` = evidência inválida |
| 3e | Flag `invalid_*` na medida | `test_red_evidencia::test_red03e…` | `MedidaMonetaria` sem `flags_qualidade` | construção | flags por medida honradas |
| 4 | Intervalos CPC/RPC em USD, perda em BRL, sem câmbio | `test_red_moeda::test_red04…` | `TetoExperimento` em "BRL" com micros de USD; `test_with_cap` | asserção | `Indisponivel(moeda_incompativel)`; `insufficient_evidence`; sem teto |
| 5 | Simulação em USD contra economia em BRL | `test_red_moeda::test_red05…` | curva analisada, "último sustentável 100000" | asserção | `CurvaIndisponivel(moeda_incompativel)`; nenhuma razão de expansão |
| 6 | Stop-loss compara gasto bruto | `test_red_stop_loss::test_red06…` (1000/999/200) | `parar_por_stop_loss` ("custo 1000 > tolerância 200") com perda líquida de 1 BRL | asserção | `max(0, custo − receita)` vs tolerância; sem stop-loss |
| 7 | Custo/receita bruta negativa aceita | `test_red_economia::test_red07…[custo|receita]` | `MedidaMonetaria(Dinheiro(−1…))` aceito | asserção (DID NOT RAISE) | `ContratoViabilidadeViolado`; contribuição pode ser negativa (controle passa) |
| 8a | Câmbio do futuro no replay | `test_red_lookahead::test_red08a…[disponivel_em|effective_at]` | `Cambio` sem data nenhuma | construção | datado e recusado se > as_of |
| 8b | Taxa do futuro | `test_red_lookahead::test_red08b…` | `Taxa` sem data | construção | idem |
| 8c | Autorização do futuro | `test_red_lookahead::test_red08c…` | sem `Autorizacao` | construção | recusada se vigência/disponibilidade > as_of |
| 8d | Simulação do futuro (controle) | `test_red_lookahead::test_red08d…` | já recusa | PASS | manter |
| 9 | Datas duplicadas inflam `dias_maduros` | `test_red_adaptador_ledger::test_red09…` | `dias_maduros=4` para 3 datas; custo/cliques em dobro | asserção | dedup por data + flag `duplic…` |
| 10a | `resultado.json` apagado | `test_red_cli_verify::test_red10a…` | `verify` exit 0 | asserção | exit 4 |
| 10b | `external_actions` adulterado | `test_red_cli_verify::test_red10b…` | exit 0 (campo nunca lido) | asserção | exit 4 |
| 10c | `relatorio.md` editado | `test_red_cli_verify::test_red10c…` | exit 0 (sem `relatorio_sha256`) | asserção | exit 4 |
| 10d | Campo removido do recibo | `test_red_cli_verify::test_red10d…[6]` | `external_actions` → 0; `entrada` → 2; os outros 4 → 4 | asserção (2 de 6) | exit 4 em todos |
| 10e | Hash adulterado (controle parcial) | `test_red_cli_verify::test_red10e…[4]` | exit 4 | PASS | manter |
| 10f | Recibo V2 completo | `test_red_cli_verify::test_red10f…` | faltam `source_commit`, `ambiente`, `relatorio_sha256` | asserção | campos presentes; `ambiente{python, plataforma, uv_lock_sha256}` |
| 11 (adapter) | `perda_maxima` por texto ou sem proveniência | `test_red_adaptador_ledger::test_red11…[3]` | aceita "owner", "bia" e INVENTA "owner" quando falta | asserção (DID NOT RAISE) | só via dict `autorizacao` |
| 11a | `PerdaMaxima.de_json` com proveniência textual | `test_red_autorizacao::test_red11a…[5]` | aceita "owner"/"bia"/"agente"/"chat"/"" | asserção | `ContratoViabilidadeViolado` |
| 11b | Construtor com valor e sem autorização | `test_red_autorizacao::test_red11b…` | aceita (`proveniencia=None`) | asserção | levanta |
| 11c | `Autorizacao` com issuer genérico | `test_red_autorizacao::test_red11c…[5]` | sem `Autorizacao` | construção | levanta |
| 11d | `Autorizacao` com hash adulterado | `test_red_autorizacao::test_red11d…` | sem `Autorizacao` | construção | levanta |
| 11e | `valor=None` continua válido (controle) | `test_red_autorizacao::test_red11e…` | ok | PASS | manter |
| 12 | Moedas heterogêneas no custo do ledger | `test_red_adaptador_ledger::test_red12…` | soma USD como BRL (pega a primeira moeda) | asserção (DID NOT RAISE) | levanta |
| 13a | Vocabulário de vereditos | `test_red_vereditos::test_red13a…` | tem `structurally_unviable`, não tem `unviable_under_declared_scenarios` | asserção | enum V2 com 5 valores |
| 13b | `viable_candidate` alcançável (< 500 cliques) | `test_red_vereditos::test_red13b…` | 300 cliques favoráveis → `already_profitable`; nenhum ramo produz `viable_candidate` | asserção | `viable_candidate` |
| 13c | `already_profitable` com 634 cliques (controle) | `test_red_vereditos::test_red13c…` | ok | PASS | manter |
| 6-ctrl | Stop-loss legítimo (1000/500/100) | `test_red_stop_loss::test_red06_controle…` | dispara | PASS | manter |
| 7-ctrl | Contribuição negativa permitida | `test_red_economia::test_red07_controle…` | ok | PASS | manter |
| 10-ctrl | Recibo íntegro → exit 0 | `test_red_cli_verify::test_red10_controle…` | ok | PASS | manter |

### Nota sobre o achado 6 (números)

O briefing cita gasto 1000 / receita 950 / tolerância 100. Com as premissas conservadoras declaradas (custo ×1,05, receita ×0,9) a perda conservadora é 1050 − 855 = 195 > 100, e um stop-loss conservador legítimo dispararia na V2. O teste usa 1000 / 999 / 200 (perda observada 1, conservadora 150,9, ambas < 200; gasto bruto 1000 > 200) para provar só o erro de comparar gasto bruto. O controle usa 1000 / 500 / 100.

### Dependências da suíte sobre a V2 (ajustes de nome que o integrador pode pedir)

- `_entradas.entrada(...)` do diretório pai é a fábrica base; a V2 deve mantê-la construindo entradas válidas (inclusive `perda="300", horizonte=14` → `PerdaMaxima` com `Autorizacao`).
- `autorizacao_v2` assume `Autorizacao(authorization_id, version:int, hash, issuer, effective_at, expires_at, disponivel_em)` e hash = sha256 do `json_canonico({authorization_id, version, issuer, effective_at: iso, expires_at: iso|None})`.
- `sobrescrever(obj, **campos)` reconstrói dataclasses congeladas via `__dict__`; se a V2 validar o hash de `Cambio`/`Taxa` sobre `disponivel_em`, os testes 8a/8b levantam pela razão "hash" e não "lookahead" — ainda `ContratoViabilidadeViolado`, mas registro aqui.
- `test_red_cli_verify` usa a fixture versionada `campanha_favoravel.json`; a V2 deve regenerá-la com o mesmo nome. O `evaluate` pode sair 0 ou 3; o que importa é o recibo.
- `test_red02b` lê `rpc_por_visita` e `visitas_elegiveis` por `getattr` com tolerância a renome.

## Falsos positivos adicionais encontrados na leitura (sem teste nesta suíte)

Listados para o integrador; não entraram na suíte porque a especificação V2 não os fixa e um teste poderia reprovar a V2 por algo que ninguém se comprometeu a fazer.

1. **Moeda do custo nunca é checada.** `moeda_provada` olha só `receita.moeda_evidencia`; `custo.moeda_evidencia=UNKNOWN/ATTESTED` com receita observada ainda dá `already_profitable`. (`gate.py` linha `moeda_provada = …`)
2. **Cliques ausentes viram zero no adapter.** `sum(int(l.get("cliques") or 0) …)` — ausência de cliques num dia maduro é tratada como 0 cliques: o custo do dia entra, os cliques não, e o CPC aparente sobe sem que nenhuma fonte tenha dito isso — ausência virando número. (`adaptadores.py` `de_ledger_campanha_dia`)
3. **Moeda padrão silenciosa no adapter.** Linhas sem `custo_moeda`/`receita_moeda` recebem "BRL"/"USD" por default — um "literal assumido" que o contrato proíbe em outros lugares.
4. **`JanelaObservada` não confere `dias_maduros` com o intervalo.** `inicio=2026-10-10, fim=2026-10-11, dias_maduros=16` é aceito; `dias_maduros + dias_imaturos` pode exceder o número de dias da janela.
5. **Janela no futuro.** `janela.fim` posterior ao `as_of` não é recusado (só `disponivel_em` das medidas é); `dias_maduros` pode contar dias que ainda não aconteceram.
6. **`codigo_sha256` do recibo cobre só `viability/*.py`.** Nem `contracts/money.py` (a aritmética de dinheiro) nem a própria `viability_cli.py` (o `verify`) entram no hash: adulterar o verificador não muda o hash que o verificador confere. A V2 adiciona `source_commit`, que fecha parte disso.
7. **`verify` confia na `entrada` do recibo.** Entrada e `input_hash` trocados de forma consistente verificam; o recibo prova reprodutibilidade, não autenticidade da entrada (não há assinatura). Aceitável se documentado.
8. **`Cambio`/`Taxa` com evidência PROJECTED/ESTIMATED aplicam o número integralmente.** Revshare "estimated 0.95" entra como 0.95 sem desconto; só o câmbio recebe desconto de premissa.
9. **`_confianca` tem um ramo morto**: `c = Confianca.LOW if c is Confianca.HIGH else Confianca.LOW` — sempre LOW; inofensivo, mas indica que a lógica de confiança não foi lida depois de escrita.
10. **`receita_status="zero_confirmed"` com `receita_micros=None`** quebra com `TypeError` (`int(None)`) em vez de `ContratoViabilidadeViolado`: a CLI devolveria traceback, não exit 2.
11. **Stop-loss só com receita realizada.** Campanha com receita PROJECTED e gasto muito acima da tolerância nunca recebe `parar_por_stop_loss` (o ramo exige `realizada`); recebe `test_with_cap` com teto. Discutível, mas é um caminho em que gasto excessivo não gera parada.
12. **Invariante de runtime só protege a receita.** `verificar_invariantes` verifica `receita.evidencia not in REALIZADA` mas não custo/cliques — a rede de segurança deixa passar o achado 3a/3b. A V2 deve estender a invariante, senão a correção fica só no gate.

## Como a suíte será usada na V2

Reexecutar exatamente o mesmo comando contra a V2 integrada. Veredito independente (APPROVE / APPROVE_WITH_LOW_RISKS / REJECT) só depois dessa segunda execução; nada aqui é autoaprovação. Alterações na suíte entre as duas rodadas: somente correções puras de nome de API pedidas explicitamente pelo integrador, registradas no commit.
