# Time vermelho, rodada 2 — R4, R5, R7, R8 contra o candidato V2 (34a5f960)

Subagente C (red team). Nenhum arquivo de produto foi tocado. A suíte foi escrita contra o comportamento-alvo fixado
pelo integrador e executada, sem alteração, contra `34a5f960`. Ela será reexecutada, idêntica, contra o SHA corrigido;
o veredito independente só nasce dessa segunda execução. Nada aqui é autoaprovação.

- Suíte: `tests/data-intelligence/viability/adversarial/test_red_r4_r5_r7_r8.py` (commit `bd5b1380`).
- R6 fora de escopo (escolha de política documentada). R3 inalterado.

Comando (raiz do worktree, Python 3.13 do lab):

```bash
PYTHONPATH=experiments/data-intelligence-lab/src $PY -m pytest tests/data-intelligence/viability/adversarial/test_red_r4_r5_r7_r8.py -q -p no:cacheprovider
```

## Resultado em 34a5f960

**46 testes: 38 FAIL, 8 PASS.** Os 8 que passam são controles declarados (comportamento que a V2 já acerta e a correção
tem de manter). Todas as 38 falhas são **de asserção** (o contrato/adapter aceita a forma pedida e devolve o valor errado,
ou "DID NOT RAISE"); nenhuma é por construção, nenhum ERROR. A suíte anterior (58 testes, `RED-TEAM-V2-VERDICT.md`)
continua 58/58 no mesmo SHA; a suíte de viabilidade inteira dá 271 PASS + estes 38 FAIL.

| Achado | Teste | V2 (34a5f960) | Esperado depois da correção |
|---|---|---|---|
| R4 controle | `r4_controle_revshare_e_imposto_observados_permitem_high` | PASS: revshare OBSERVED (contrato) + imposto 0,05 OBSERVED (nota fiscal), resto forte → `already_profitable` / HIGH | Continua PASS (a cap não pode matar o HIGH) |
| R4a | `r4a_revshare_nao_observado_nunca_permite_high[attested\|estimated]` | FAIL: HIGH. `_confianca` nunca olha revshare; a razão `revshare_attested` já existe (limitação do envelope) mas não cala a confiança | ≤ MEDIUM; razão `revshare_<evidencia>` |
| R4a | `r4a_revshare_unknown_sem_valor_nunca_permite_high` | FAIL: HIGH com receita bruta = líquida; razão hoje é `revshare_desconhecido_nao_aplicado` | ≤ MEDIUM; razão tipada `revshare_unknown` |
| R4b | `r4b_imposto_nao_observado_nunca_permite_high[attested\|estimated]` | FAIL: HIGH **e nenhuma razão** sobre o imposto (a economia só registra `imposto_desconhecido_nao_aplicado` quando falta valor; evidência fraca com valor passa em silêncio) | ≤ MEDIUM; razão `imposto_<evidencia>` |
| R4b | `r4b_imposto_unknown_sem_valor_nunca_permite_high` | FAIL: HIGH; razão `imposto_desconhecido_nao_aplicado` | ≤ MEDIUM; razão tipada `imposto_unknown` |
| R4c guarda | `r4c_valor_declarado_continua_aplicado_sem_desconto_inventado` | PASS: revshare 0,7 ATTESTED e 0,7 OBSERVED dão números idênticos (contribuição, RPC, break-even, cenários); 0,7 ≠ 1 | Continua PASS: cap de confiança ≠ desconto |
| R4d | `r4d_cap_vale_tambem_no_veredito_inviavel` | FAIL: no ramo `unviable_under_declared_scenarios`, `c2 = HIGH if moeda_provada and conf is HIGH` devolve HIGH com revshare atestado | ≤ MEDIUM também nesse ramo |
| R5 controle | `r5_controle_janela_consistente_e_fim_igual_ao_as_of_constroem` | PASS: 16 maduros em 16 dias; `fim` == data do `as_of` | Continua PASS (`fim` = as_of.date() é permitido) |
| R5a | `r5a_fim_posterior_ao_as_of_e_lookahead_por_construcao` | FAIL (DID NOT RAISE): `fim` 16/10 com `as_of` 15/10 constrói | `ContratoViabilidadeViolado` em `EntradaViabilidade` |
| R5b | `r5b_dias_maduros_acima_do_intervalo_e_recusado` | FAIL (DID NOT RAISE): 16 maduros em 12..15/10 (4 dias) — a forma exata da Senac hoje | Recusa em `JanelaObservada` ou `EntradaViabilidade` |
| R5c | `r5c_maduros_mais_imaturos_acima_do_intervalo_e_recusado` | FAIL (DID NOT RAISE): 7 + 4 em 10 dias | Recusa |
| R5d | `r5d_dias_receita_madura_acima_do_intervalo_e_recusado` | FAIL (DID NOT RAISE): `dias_receita_madura` 12 em 10 dias | Recusa (também `dias_custo_maduro`) |
| R5e | `r5e_ledger_com_dia_posterior_ao_as_of_e_recusado` | FAIL (DID NOT RAISE): linha do ledger datada 20/10 com `as_of` 15/10 vira janela que termina no futuro | Recusa pelo contrato (o adapter monta a janela com `dias[-1]`) |
| R5f | `r5f_fixture_senac_respeita_a_janela` | FAIL: `dias_maduros 16 + dias_imaturos 3 > intervalo 4 (2026-10-12..2026-10-15)` | Aritmética fecha e `EntradaViabilidade.de_json` carrega |
| R5g | `r5g_toda_fixture_versionada_respeita_a_janela[18 fixtures]` | 16 FAIL / 2 PASS. **Não é só a Senac**: todas as fixtures do `base()` do gerador declaram 26/09..11/10 (16 dias) com 16 maduros + 3 imaturos = 19. Passam só `campanha_nova_sem_historico` (0/0) e `dados_imaturos` (1+2 em 3 dias) | 18/18: o gerador precisa corrigir `base()` (fim 14/10 ou `dias_imaturos` 0) e a Senac (`inicio` = início da janela madura, não `corte_maturidade`); senão, assim que o contrato impuser a regra, 16 fixtures e o replay param de carregar |
| R7 controle | `r7_controle_ledger_com_moedas_declaradas_constroi_dinheiro` | PASS | Continua PASS |
| R7a | `r7a_ledger_sem_custo_moeda_nao_inventa_brl` | FAIL: `custo.valor = Dinheiro(300000000, 'BRL')` sem nenhuma linha declarar moeda (`_moeda_unica(..., padrao="BRL")`) | `custo` = valor None / UNKNOWN / moeda UNKNOWN + flag `moeda_ausente` e veredito `insufficient_evidence`; OU `ContratoViabilidadeViolado("moeda_ausente")` |
| R7b | `r7b_ledger_sem_receita_moeda_nao_inventa_usd` | FAIL: `receita.valor = Dinheiro(450000000, 'USD')` — literal do código, moeda JoinAds promovida | Idem, no lado da receita; custo declarado continua real |
| R7c | `r7c_ledger_sem_nenhuma_moeda_nao_inventa_par_de_cambio` | FAIL: `Cambio(taxa=None, de="USD", para="BRL")` sem nenhuma moeda declarada | Nenhum par inventado, ou recusa tipada |
| R7d | `r7d_cambio_com_taxa_sem_par_declarado_e_recusado` | FAIL: dict de câmbio com taxa 5,25 e sem `de`/`para` vira `Cambio(5.25, USD→BRL)` por `d.get("de", de)` | Recusa, ou taxa descartada (`taxa=None`); nunca taxa com par inferido |
| R7e | `r7e_de_pautador_card_exige_moeda_explicita` | FAIL: `moeda: str = "BRL"` na assinatura; card nasce com `Cambio(None, "BRL", "BRL")` | `moeda` sem default (TypeError) ou recusa |
| R7f controle | `r7f_de_pautador_card_com_moeda_explicita_constroi` | PASS | Continua PASS |
| R8 controle | `r8_controle_copia_integra_verifica_exit_0` | PASS: cópia isolada de `src/`, `scripts/`, `fixtures/viability` e `uv.lock` reproduz o recibo (exit 0) | Continua PASS |
| R8a | `r8a_adulterar_contracts_invalida_verify_exit_4[money.py\|vocab.py]` | FAIL: comentário acrescentado a `contracts/money.py` (ou `vocab.py`) da cópia → `verify` exit **0**, "recibo verificado". `MODULOS` cobre só `viability/*.py` + a CLI | exit 4 com "codigo_sha256 difere" |
| R8b | `r8b_codigo_sha256_do_recibo_muda_quando_money_muda` | FAIL: `codigo_sha256` idêntico antes e depois de alterar `money.py` | Hash muda |
| R8c | `r8c_modulos_do_recibo_incluem_money_e_vocab` | FAIL: `MODULOS` sem `contracts/money.py` e `contracts/vocab.py` (falha por construção se a CLI deixar de expor `MODULOS`) | Os dois no conjunto |

## Observações para o integrador

1. **R5g é maior do que o enunciado.** A regra `dias_maduros + dias_imaturos <= intervalo` derruba 16 das 18 fixtures
   versionadas, não só a Senac. Quem corrigir o contrato sem regenerar as fixtures quebra `replay` e `test_cli_replay`.
2. **R4b com valor presente hoje é silencioso.** Imposto ATTESTED/ESTIMATED com valor não gera limitação nenhuma em
   `receita_liquida_comparavel` (só `imposto_desconhecido_nao_aplicado` quando falta valor). A razão `imposto_<evidencia>`
   é comportamento novo, não só uma cap.
3. **R7 admite duas correções**; a suíte aceita as duas (medida degradada com flag `moeda_ausente`, ou recusa tipada com
   `moeda_ausente` na mensagem). O que ela não aceita é `Dinheiro` em moeda que ninguém declarou.
4. **R8 é ponta a ponta em cópia isolada** (`shutil.copytree`), com `sys.executable -I`; o worktree nunca é adulterado.
   `uv.lock` é copiado para que `ambiente.uv_lock_sha256` seja comparável dos dois lados.

## Próximo passo

Reexecutar exatamente o mesmo comando contra o SHA corrigido. Alterações na suíte entre as duas rodadas: somente
correções puras de nome de API pedidas explicitamente pelo integrador, registradas no commit.

## Resultado após as correções

A suíte da rodada 2 foi preservada e reexecutada contra a candidata integrada. Os 46 testes passaram. A suíte
adversarial completa passou em **104/104**, e a suíte inteira do kernel passou em **332/332**.

Na revisão final apareceu uma inconsistência que o merge dos subagentes não havia fechado: uma taxa de câmbio sem
`de`/`para` ainda herdava o par das moedas do ledger. O teste R7d a detectou. O adapter foi corrigido para descartar a
taxa ambígua e devolver câmbio ausente, mesmo quando o ledger conhece as duas moedas; o teste de compatibilidade antigo
foi alinhado ao contrato fail-closed. Correção em `127d9670`.

Estado dos riscos desta rodada:

- **R4, R5, R7 e R8:** fechados por código e testes.
- **R6:** permanece uma escolha de política explícita, fora do escopo desta correção.
- **R3:** permanece como limite de arquitetura: o hash prova integridade da referência de autorização, não autoria.
