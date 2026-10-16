# HANDOFF-D — Replay `as_of` e shadow engine (thread D)

Branch `lab/dil-fundacao-20261016-d` (worktree esparso `worktrees/dil-fundacao-20261016-d`), base `d4475d30`.
Documento principal: `docs/data-intelligence/fundacao-20261016/06-REPLAY-E-SHADOW.md`.
Nada foi lido de produção, nenhuma rede, nenhum segredo, nenhum roadmap/curadoria/grafo tocado, nenhuma
mutação possível no código (provado por teste).

## 1. Arquivos

| Caminho | O quê |
|---|---|
| `experiments/data-intelligence-lab/src/volc_dil/fundacao/shadow/__init__.py` | docstring do pacote |
| `.../shadow/tipos.py` | `PropostaShadow` (`executavel=False` imposto), `Diagnostico`, `DecisaoShadow`, `Acao`, `Confianca`, `EntidadeCampanha`, `DictCongelado` |
| `.../shadow/versao.py` | `versao_codigo()` (sha256 do conteúdo do código que decide) |
| `.../shadow/fluxo.py` | `FluxoIndexado` (as_of da A sobre prefixo, hash encadeado, quarentena), `cortes_regulares` |
| `.../shadow/snapshot.py` | `construir_snapshot`, `SnapshotShadow`, `FatoCampanhaDia`, `CoberturaDia`, `ConfigCorte`, `CambioDeclarado`; compatível com as duas APIs de `juntar_campanha_dia` |
| `.../shadow/politicas.py` | `Manter`, `RegraMargem`, `Guardiao72h`, `BaselineHerdada` (`equal`, `greedy_conservador`), `regra_margem_imatura`, `regra_margem_null_zero`, `catalogo_padrao` |
| `.../shadow/kernel.py` | `aplicar_kernel`, `ConfigKernel`, bloqueios |
| `.../shadow/motor.py` | `executar_replay` (serial/processo/thread), `detectar_vazamento`, `auditar_null_zero`, `ConfigShadow` |
| `.../shadow/ledger.py` | `LedgerShadow`, `SinkJsonl`, `verificar_cadeia` |
| `.../shadow/avaliacao.py` | `avaliar`, `registrar_resultados_maduros`, `FluxoSintetico`, protocolo `Verdade` |
| `.../shadow/real.py` | `observacoes_de_linhas_reais`, `deduplicar`, `replay_de_linhas_reais`, `carregar_jsonl` |
| `.../shadow/linhas_formato_real.py` | construtores de linhas v21/JoinAds v2 sintéticas; `fixture_padroes_reais()` |
| `.../shadow/fonte_simulador.py` | `registro_para_observacao`, `observacoes_do_simulador`, `VerdadeSimulador`, `fluxo_do_simulador` |
| `.../shadow/_gerador_provisorio.py` | gerador mínimo isolado (`gerar`, `cenarios_provisorios`, `preparar`) |
| `.../shadow/controles.py` | `PoliticaTrapaceira`, `cortar_por_observed_at` (controles negativos) |
| `experiments/data-intelligence-lab/scripts/fundacao_shadow.py` | `--sintetico`, `--simulador`, `--verificar`, modo real |
| `experiments/data-intelligence-lab/results/fundacao/shadow/shadow_resultados.json`, `SHADOW-RESULTS.md` | resultados gerados (sha determinístico `6928cdd3…` total; provisório+gates `b1f2b2df…`, conferido por `--verificar`) |
| `tests/data-intelligence/fundacao/test_shadow_{corte,politicas,gates,ledger,sem_escrita_externa,real,avaliacao,simulador}.py` | 65 testes |
| `docs/.../06-REPLAY-E-SHADOW.md`, este arquivo | docs |

## 2. Provas

```bash
cd /Users/mac/Desktop/VOLC-OS-CAMPAIGN/worktrees/dil-fundacao-20261016-d
OMP_NUM_THREADS=2 /Users/mac/Desktop/VOLC-OS-CAMPAIGN/worktrees/data-intelligence-overnight-20261015/experiments/data-intelligence-lab/.venv/bin/python -m pytest tests/data-intelligence -q
# 528 passed, 1 skipped (test_shadow_simulador: simulador ausente neste worktree) em ~129 s
cd experiments/data-intelligence-lab && .venv/bin/python -I scripts/fundacao_shadow.py --verificar   # sha igual
```

Na árvore combinada (src do integrador em `55fe6bb5`, com simulador da E e junção endurecida da C, + este
pacote): `pytest -k shadow` → **65 passed** (inclui os 8 do simulador). O merge da branch da missão neste
worktree foi pedido pelo integrador e **negado pelo classificador de permissões** (a missão também proíbe
merge); por isso a validação com o simulador e com a API nova da C foi feita numa cópia no scratchpad.

| Arquivo | Testes | Gate |
|---|---|---|
| `test_shadow_corte.py` | 8 | as_of do índice = as_of da A em todos os cortes; fingerprint independe de ordem/reentrega; futuro não muda o snapshot; imutável, sem `Observacao`, integridade; política recusa o fluxo; junção por dia com cobertura e `nao_atribuivel`; quarentena de ambíguas |
| `test_shadow_politicas.py` | 9 | `executavel=True` levanta; catálogo inteiro passa pelo kernel; regra madura corta o que deve; imaturo → `insuficiente`; guardião rebaixa corte de campanha nova a `alerta` (e nunca corta campanha nova em nenhum corte); baselines herdadas fecham orçamento |
| `test_shadow_gates.py` | 11 | trapaceira detectada / honestas intactas antes do futuro; restatement tardio não reescreve o ledger; auditoria null→0; R3 não vira campanha morta; custom_key trocada, colisão de identidade, moeda misturada, sem câmbio e grão misto bloqueiam; retrodatado não vaza; bytes idênticos; serial = processo = thread |
| `test_shadow_ledger.py` | 4 | cadeia, retomada, adulteração, sink restrito, resultado maduro com referência |
| `test_shadow_sem_escrita_externa.py` | 4 (+7 contraprovas parametrizadas) | varredura AST sem rede/banco/subprocess/mutate; só `ledger.jsonl` é escrito em execução; nenhuma proposta executável |
| `test_shadow_real.py` | 6 | padrões do recibo (5 campanhas, 1 muda/h, ~80% repetição, zeros sintetizados → missing, 3 runs presos, re-execução do slot deduplicada por payload, A→B→A preservado), replay ponta a ponta, JSONL com Decimal |
| `test_shadow_avaliacao.py` | 7 (+2 param.) | métricas, determinismo, null→0 erra onde a madura não erra, guardião reduz corte errado imaturo |
| `test_shadow_simulador.py` | 8 | adaptador `RegistroObservacao`→`Observacao`, snapshot = `visao_as_of` da E, R3 do coletor, identidade trocada, retrodatado, moeda/câmbio, verdade pareada, replay+avaliação |

Tempos: suíte da thread ~19 s; `--sintetico` ~35 s (6 cenários × 241 cortes × 8 políticas, ~27 ms/corte);
`--simulador` ~4,5 min (13 cenários, 35–195 ms/corte).

## 3. API pública

```python
from volc_dil.fundacao.shadow.fluxo import FluxoIndexado, cortes_regulares
from volc_dil.fundacao.shadow.snapshot import construir_snapshot, SnapshotShadow, ConfigCorte, CambioDeclarado
from volc_dil.fundacao.shadow.politicas import (PoliticaShadow, Manter, RegraMargem, Guardiao72h, BaselineHerdada,
    equal, greedy_conservador, regra_margem_imatura, regra_margem_null_zero, catalogo_padrao)
from volc_dil.fundacao.shadow.motor import ConfigShadow, executar_replay, detectar_vazamento, auditar_null_zero, decidir_no_corte
from volc_dil.fundacao.shadow.kernel import ConfigKernel, aplicar_kernel
from volc_dil.fundacao.shadow.ledger import LedgerShadow, SinkJsonl, verificar_cadeia
from volc_dil.fundacao.shadow.avaliacao import avaliar, registrar_resultados_maduros, FluxoSintetico, Verdade
from volc_dil.fundacao.shadow.real import observacoes_de_linhas_reais, deduplicar, replay_de_linhas_reais, carregar_jsonl
from volc_dil.fundacao.shadow.fonte_simulador import fluxo_do_simulador, registro_para_observacao, VerdadeSimulador

FluxoIndexado(observacoes, *, ambiguidade="falhar"|"quarentena")   .as_of(t) .fingerprint_visiveis(t) .quarentena_visivel(t)
construir_snapshot(fluxo_indexado, t, ConfigCorte(janela_dias=14, revenue_basis="client", cambios=(...), registro=None)) -> SnapshotShadow
PoliticaShadow.decidir(snapshot: SnapshotShadow) -> DecisaoShadow(propostas: PropostaShadow..., diagnosticos: Diagnostico...)
executar_replay(fluxo, cortes, politicas, *, config, seed, ledger, paralelismo=1, executor="processo"|"thread") -> ResultadoReplay
avaliar(resultado, verdade, *, hora_decisao=7) -> dict   # natureza "testado_com_sintetico"
replay_de_linhas_reais(linhas_v21, linhas_joinads, *, politicas, config, diretorio_ledger) -> (adaptacao, resultado, ledger)
```

Para F (Model Lab): uma política nova é qualquer objeto com `nome`, `versao` e `decidir(SnapshotShadow)`;
o motor, o kernel, o ledger e a avaliação valem sem mudança. Para G: os `Diagnostico` e `CoberturaDia.bloqueios`
são insumos de DQ por corte.

## 4. Falhas encontradas no caminho (e o que mudou)

- Baselines herdadas: o piso do `validar_decisao` ficava acima da verba vigente de campanhas pequenas → piso limitado à menor verba vigente.
- Fixture de futuro com payload repetido gerou `ConflitoIdempotencia`/`VersaoAmbigua` no próprio teste — corrigido (uma versão futura por fato).
- Simulador `identidade_trocada` produz versões ambíguas → `VersaoAmbigua` derrubava o replay → quarentena no índice.
- Guardião só por horas não pegava a campanha nova (o 1º corte com 3 dias de dado já tinha > 72 h) → "nova" passou a ser < 72 h **ou** < 3 dias com dado maduro.
- API nova da junção (R1-F5): grão misto e identidade de linha → camada de compatibilidade + bloqueio `receita_recusada_pela_juncao`; teste de moeda misturada passou a usar outro domínio (no mesmo grão uma campanha tem uma linha só).
- Heredoc do shell comeu crases de uma docstring (`fluxo.py`) — restaurado.

## 5. Riscos e limitações

1. **Merge negado:** a integração com simulador e junção nova está provada só na árvore combinada; o integrador deve rodar `pytest -k shadow` (65) e `fundacao_shadow.py --verificar` depois do merge.
2. **Divergência de ordem de versão A × E** (06 §10.1): entrega atrasada de leitura antiga volta o `as_of` para o valor antigo (10/7.689 em `atraso_receita_longo`). Decisão da A.
3. **`Registro`/`dil_obs` × v21 D0** (06 §10.2): mesma `chave_base` com cobertura diferente → `ConflitoIdempotencia` se alguém gravar v21 em `dil_obs`.
4. A thread A ainda vai mudar o contrato (R1 F1, F3, F4, F9, F16, F17). Impacto esperado no shadow: baixo — o shadow só lê `Observacao`; F4 (moeda só com prova) e F17 (cobertura desconhecida) podem mudar status de leituras e, portanto, o que é "maduro". Re-rodar a suíte e o `--verificar` (o fingerprint inclui a versão do código, então o sha determinístico MUDA de propósito).
5. Gerador provisório mínimo; resultados provisórios são de um mundo com campanhas obviamente ruins.
6. Proxy de verba (custo de D-1) nas baselines herdadas; câmbio declarado, não observado.
7. Ledger grande (~9 MB por 10 dias × 24 cortes × 8 políticas); persistência em banco não construída.
8. Desempenho O(visíveis) por corte; para histórico longo, `as_of` incremental.

## 6. Delta de curadoria proposto (só proposta; integrador decide e aplica)

| Tarefa | Estado atual | Proposta | Evidência |
|---|---|---|---|
| **P14-T02** "Provar replay e shadow antes de qualquer autonomia" | partial | **manter partial**; acrescentar: "motor só enxerga dados disponíveis na data simulada" (isolamento por tipo + detector de vazamento com controle trapaceiro), "persiste ledger/recibos" (ledger JSONL com hash encadeado, resultado maduro D+1+k), "mede falsos positivos e drawdown" (cortes errados, por sinal imaturo, drawdown, regret) — tudo **testado com sintético**; faltam GoogleAdsRow/linha v21 real, shadow por janela declarada e ADR T2 | `06-REPLAY-E-SHADOW.md` §3, §7; `test_shadow_gates.py`, `test_shadow_ledger.py`; `results/fundacao/shadow/` |
| **P09-T09** "Provar ORAKUL em shadow antes do primeiro canário" | todo | **sem mudança de estado**; registrar que o motor shadow (proposta tipada, kernel de bloqueio, ledger, métricas de falso positivo/drawdown) existe e está testado com sintético, e que o adaptador para linha real está pronto mas não executado (exportação depende do operador) | `real.py`, `test_shadow_real.py`, 06 §9 |
| **P09-T11** "Provar o Budget-ROI Allocator em replay offline" | todo | **sem mudança de estado**; dependência satisfeita em parte: replay as-of sem futuro e baselines atual/igual/greedy lado a lado existem (sintético); o allocator SGD-UCB não foi implementado; resultado negativo a registrar: no simulador nenhuma regra supera `equal` | `politicas.py` (`BaselineHerdada`), 06 §7.2 |
| **P09-T13** "Rodar o Budget-ROI Allocator em shadow com propostas T1" | todo | **sem mudança**; registrar que `PropostaShadow` tipada com `executavel=False`, kernel que bloqueia e ledger existem para receber o allocator | `tipos.py`, `kernel.py`, `ledger.py` |
| **P05-T09** "Criar o guardião canônico das primeiras 72 horas" | partial | **manter partial**; acrescentar evidência: `Guardiao72h` versionado no shadow (nova = < 72 h desde o 1º custo observado ou < 3 dias com dado maduro; só diagnóstico/alerta, nunca corte; cita evidência e frescor), com replay sintético mostrando corte errado imaturo eliminado (provisório 1 → 0) e trade-off de atraso; ainda não substitui a política v3/v4.9 nem roda em produção | `politicas.py::Guardiao72h`, `test_shadow_politicas.py::test_guardiao_*`, `test_shadow_avaliacao.py::test_guardiao_reduz_*` |

Nós/arestas sugeridos para o Mapa Vivo (após merge): nó `volc_dil.fundacao.shadow` (domínio decisão/atuação,
estado `testado com sintético`); arestas `volc_dil.fundacao.shadow —lê→ volc_dil.fundacao.observacao`,
`—compõe→ volc_dil.fundacao.identidade.juntar_campanha_dia`, `—reusa→ volc_dil.replay.politicas`,
`—avalia_com→ volc_dil.fundacao.simulador`, `google_ads_observation (v21)/joinads_observation (v2) —replay_pronto_não_executado→ shadow.real`.
