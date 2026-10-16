# HANDOFF-E — Simulator Lab (worker E → integrador I)

Branch `lab/dil-fundacao-20261016-e` (worktree esparso `worktrees/dil-fundacao-20261016-e`), base `b6e85974`.
Estado: **construído · testado hermeticamente · testado com sintético**. Nada calibrado com dado real.
Documento técnico: `docs/data-intelligence/fundacao-20261016/07-SIMULATOR-LAB.md`.

## 1. Arquivos

| Caminho | Conteúdo |
|---|---|
| `experiments/data-intelligence-lab/src/volc_dil/fundacao/simulador/__init__.py` | API pública, `simular`, `VERSAO_SIMULADOR=1.0.0` |
| `…/simulador/parametros.py` | `ParametrosMundo`, `ParametrosObservador`, `EspecCenario`, `MudancaOrcamento`, `QuebraRegime`, `JanelaForaDoAr` |
| `…/simulador/mundo.py` | processo verdadeiro (campanha × hora × dispositivo), CRN, contrafactual de orçamento |
| `…/simulador/observador.py` | processo de observação por fonte, gabarito, livro de runs |
| `…/simulador/registro.py` | `RegistroObservacao` (17 campos do contrato + extras), `Gabarito`, vocabulário de status |
| `…/simulador/cenarios.py` | catálogo versionado (20 cenários, `VERSAO_CATALOGO=1.0.0`) |
| `…/simulador/consumidor.py` | consumidor de referência `visao_as_of` e anti-referência `soma_ingenua` |
| `…/simulador/adaptador_contrato.py` | registro → `volc_dil.contracts.Observacao` (contrato herdado) |
| `…/simulador/calibracao.py` | origem declarada de cada parâmetro e faixas de forma |
| `…/simulador/pacote.py` | gerador determinístico do pacote de datasets |
| `experiments/data-intelligence-lab/scripts/fundacao_simulador_pacote.py` | script reprodutível (`--verificar`, performance) |
| `experiments/data-intelligence-lab/results/fundacao/simulador/` | `MANIFEST.json`, `PERFORMANCE.json`, 20 pastas de cenário (32,2 MB) |
| `tests/data-intelligence/fundacao/test_simulador_{determinismo,conservacao,tempo,status,cenarios,estatistica,performance,pacote}.py` | 113 testes |
| `docs/data-intelligence/fundacao-20261016/07-SIMULATOR-LAB.md`, este handoff | documentação |

Não criei `fundacao/__init__.py` (namespace package funciona; é de outro worker) nem `tests/.../fundacao/conftest.py`.

## 2. Provas

- Suíte: `OMP_NUM_THREADS=2 <python> -m pytest tests/data-intelligence -q` → **285 passed** (172 herdados + 113 novos), ~48 s; só os novos: 113 em ~18 s.
- Pacote: `fundacao_simulador_pacote.py --verificar` → `{"verificado": true, "divergentes": []}`; manifesto `fingerprint 6898d28a4ecb5f6a9194f950378e402ebf12df234319cfd7bcdce24717bfac8e`, `codigo_sha256 a1e5cfde26c9816125ddb8ee72cf5cfb5a1406165dd2bcd0806c264730cc4fd1`, `catalogo_sha256 d449d43f12ee20fdff245663329e8779aaa96faa39a4e71617cf746ec8601600`, seed 20261016, numpy 2.5.3, scipy 1.18.1, Python 3.13.0. O teste `test_pacote_versionado_completo_pequeno_e_em_sincronia_com_o_codigo` regenera `zero_falso` e exige o mesmo sha256.
- Performance: 50 campanhas × 30 dias × 24 h × 3 dispositivos = 1,2 s (mundo 0,24 + observador 0,96; 53.217 registros); `escala_10x` (500 campanhas) = 16,6 s, 505.464 registros. Orçamento de teste: 15 s.
- Robustez a seed: testes de cenário, conservação, tempo, status e determinismo passam em 5 seeds (20261016, 1, 777, 424242, 99); a propriedade de mudança de orçamento vale em 7 de 8 seeds conferidas.
- Isolamento: teste AST sem `socket/urllib/http/requests/subprocess/eval/exec/importlib`, sem `.env`/`os.environ`; conftest bloqueia rede.
- Nenhuma escrita fora das pastas autorizadas; nada de roadmap, curadoria, grafo, rede, produção ou segredo.

## 3. API pública (resumo; completo em 07 §6)

```python
simular(espec: str | EspecCenario, seed: int, *, n_campanhas=None, n_dias=None, orcamento_diario_micros=None) -> Simulacao
gerar_mundo(params: ParametrosMundo, seed: int, orcamento_diario_micros=None) -> Mundo
observar(mundo: Mundo, po: ParametrosObservador, *, cenario="ad_hoc") -> Leituras  # registros, gabarito, execucoes
cenario(nome) -> EspecCenario; CATALOGO; NOMES; ADVERSARIAIS; catalogo_sha256()
visao_as_of(registros, as_of, *, relogio="available_at", exigir_custom_key=True)
para_observacao_contrato(registro) -> volc_dil.contracts.Observacao | None
RegistroObservacao.contrato() -> dict com os 17 campos
pacote.gerar_pacote(destino, seed, nomes=None); pacote.conteudo_cenario(nome, seed, tamanho=None)
```

Ligação com o worker A (`volc_dil.fundacao.observacao`): mapear `RegistroObservacao.contrato()`
campo a campo (tabela em 07 §3.4). Divergências prováveis a decidir pelo integrador: `grao` (ASCII,
tupla) vs `grão`; `valor` + `unidade` vs `valor_micros` (contagens também são observadas); `moeda`
`None` em contagem; extras (`tipo_leitura`, `maturidade`, `custom_key_*`, `available_previsto`)
sem campo no contrato podem virar colunas ou `motivo`.

## 4. Cenários

Base/mundo/observação: `estavel`, `campanha_nova_aprendendo`, `atraso_receita_longo`, `restatement_custo`,
`fonte_fora_do_ar`, `outlier_bot`, `quebra_regime_rpm`, `mudanca_orcamento`, `sazonal_fim_de_semana`, `escala_10x`.
Adversariais: `vazamento_tentado`, `zero_falso`, `moeda_misturada`, `identidade_trocada`.
Confirmados em produção (pedido do integrador; recibo `RECIBO-LEITURAS-20261016` + inventário §10):
`sensor_sem_campanha` (R2), `zero_sintetizado_coletor` (R3), `dedup_por_segundo` (R4),
`gatilho_legado_joinads` (R5), `custo_d0_multiversao` (L10), `execucao_presa` (L9).

## 5. Falhas e correções durante o trabalho

- `run_id` colidia entre releituras de dias diferentes no mesmo horário (livro de runs inconsistente) → `run_id` inclui o dia de referência.
- O pacing só em expectativa deixava o gasto diário passar de 2× o orçamento (o Google não permite) → corte rígido `limite_diario_x_orcamento=2.0`.
- Preliminar atrasada chegando depois da final virava "última versão" no consumidor de referência → versão escolhida por `observed_at` (empate: chegada).
- Testes que dependiam da seed (quebra de RPM, mudança de orçamento, pareamento `estavel`×`outlier_bot`, que diferem em `frac_novas`) → reescritos com contraste contra controle e pareamento correto.
- Primeira versão do pacote tinha 92 MB → reduzido para 4 × 7 (escala 40 × 3), 32 MB.
- Tentei apagar o conteúdo antigo de `results/fundacao/simulador/` antes de regenerar; a remoção foi bloqueada pela checagem de segurança e era desnecessária (o gerador sobrescreve o mesmo conjunto de arquivos). Nada ficou órfão: o manifesto lista exatamente os arquivos presentes.

## 6. Riscos

1. **Leitura de simulação como evidência.** Qualquer número de política/modelo medido aqui é "testado com sintético"; promover para "eficaz" é erro de categoria.
2. **Parâmetros arbitrários dominam** (RPM, funil, maturação, defeitos). Conclusões sensíveis a eles precisam de varredura (o catálogo permite `replace`).
3. **Pacote pequeno (4 × 7):** alguns fenômenos aparecem pouco (ex.: 1 hora de bot em `outlier_bot`). Para estatística, gerar pela API.
4. **Determinismo entre plataformas não testado:** bytes dependem de numpy/scipy (versões gravadas no manifesto).
5. **Mapeamento com o contrato do worker A** ainda não exercitado (só com o herdado).
6. **Tamanho no repositório:** 32 MB de JSONL/CSV versionados; se o integrador preferir, versionar só `MANIFEST.json` + `--verificar` e regenerar sob demanda.
7. **Curva real de maturação** (recibo L10) não usada ainda: o default de cadência D0/D-1 é forma documentada, não medida.

## 7. Delta de curadoria proposto (NÃO aplicado; decisão do integrador)

| Tarefa | Estado atual | Proposta | Evidência | Lacuna honesta |
|---|---|---|---|---|
| P14-T09 "Expor simulador read-only de planned_spend" | `todo` | manter `todo`; registrar **insumo pronto em laboratório**: `gerar_mundo(..., orcamento_diario_micros)` dá grid gasto→receita contrafactual pareado (CRN) num mundo sintético | `07-SIMULATOR-LAB.md` §2/§6; `test_contrafactual_orcamento_reproduz_e_responde` | não é o simulador do cockpit: falta modelo calibrado em dado real, intervalo, premissas por campanha real, exposição read-only no QG e dependências P14-T08/P05-T02 |
| P15-T08 "Expor cenários no QG e na Bia em shadow mode" | `todo` | manter `todo`; anotar que existe catálogo versionado de cenários sintéticos com gabarito para testar o shadow antes de exposição | `cenarios.py`, pacote `results/fundacao/simulador/` | depende de modelo aceito; nada exposto; cenário sintético ≠ cenário de negócio |
| P14-T07 "Baseline preditivo sem vazamento de futuro" | `todo` | manter `todo`; registrar bancada de teste de vazamento: `vazamento_tentado` (retrodatado), `visao_as_of` por `available_at`, `zero_falso`/`zero_sintetizado` (null ≠ 0) | `test_vazamento_tentado_observed_at_ve_o_futuro`, `test_zero_falso_*`, `test_zero_sintetizado_*` | baseline preditivo em si (features as-of, time split, amanhã=hoje, previsão imutável) é do worker F; nada rodou sobre dado real |

Nós do grafo sugeridos (para o integrador decidir): `volc_dil.fundacao.simulador` (cluster dados/plataforma,
estado `experimento`), arestas `simulador → contrato de observação (A)`, `simulador → shadow (D)`,
`simulador → Model Lab (F)`, `simulador → qualidade (G)`, e `simulador ← recibo leituras externas (R2–R5)`.
