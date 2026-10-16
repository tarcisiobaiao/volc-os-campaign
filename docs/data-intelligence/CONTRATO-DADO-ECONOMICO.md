# Contrato mínimo de dado econômico confiável (Lab v1)

**Estado:** implementado e testado no laboratório (`experiments/data-intelligence-lab/src/volc_dil/contracts/`, stdlib apenas).
**Não é:** schema de produção, migration ou substituto do núcleo `volc_ads/economia/` (que hoje só existe em `wip/*`).
**Prova:** `tests/data-intelligence/test_contracts.py` (contraprovas + reprodução da fixture; contagem atual na suíte).

## 1. A unidade de fato: `Observacao`

Uma observação é *identidade × métrica × janela de evento × versão de conhecimento*. Campos obrigatórios e por quê:

| Campo | Regra | Invariante protegido |
|---|---|---|
| `unidade: ChaveUnidade(conta, tipo_entidade, entidade_id, grao, dimensoes)` | ids não vazios, grão de vocabulário fechado, dimensões ordenadas | identidade não se casa por nome; conta faz parte da chave (X08) |
| `metrica` | `cost`, `revenue`, `clicks`, `impressions`, `sessions`, `conversions`, `signal` | — |
| `valor` + `estado` | `medido`/`zero_confirmado` exigem valor; os demais (`ausente`, `nao_coletado`, `falha`, `nao_atribuivel`, `nao_aplicavel`) exigem `valor=None` **e** `motivo` | `null != 0` |
| tipos de valor | dinheiro = `Dinheiro(micros:int, moeda:ISO-4217)`; contagens = `int >= 0`; float é recusado em todo lugar | micros, sem float |
| `janela_inicio`, `janela_fim`, `timezone` | instantes com tz; janela não vazia; IANA válido | todo instante tem timezone |
| `observado_em`, `disponivel_em` | `janela_inicio <= observado_em <= disponivel_em` | separa event time de knowledge time |
| `fonte`, `versao_fonte`, `coleta_id`, `linhagem` | obrigatórios | linhagem |
| `cobertura` | `complete`/`partial`/`unknown` | cobertura explícita |
| `maturidade` | `preliminary`/`mature`/`revised` | preliminar × fechado |
| `metodo` | vocabulário do núcleo (`deterministic_click_id` … `not_identifiable`, `nao_aplicavel`) | atribuição não é causalidade e não se esconde |
| `value_kind` | obrigatório em `revenue`; obrigatório e igual a `observed_auction_signal` em `signal` monetário; proibido em custo/contagens | sinal ≠ receita |

Regras cruzadas que o construtor recusa:

- `revenue` com `observed_auction_signal` (X02 do catálogo);
- `reconciled_revenue` com método `inferred`/`unreconciled`/`not_identifiable`;
- `reconciled_revenue` em grão `session` com método `aggregate_campaign_date` (receita agregada não vira receita por sessão).

## 2. Snapshot `as_of`

`Snapshot.construir(observacoes, as_of, politica_futuro="excluir"|"falhar")`:

1. só entra o que tem `disponivel_em <= as_of`; o resto é contado em `n_futuras_excluidas` (ou levanta `VazamentoDeFuturo` na política `falhar`, usada por quem já devia receber dados cortados: replay, features);
2. revisões compartilham a `chave_logica` (unidade, métrica, janela, tz, fonte, value_kind); o snapshot usa **a versão mais recente conhecida no corte**, não a final do mundo; duas versões diferentes no mesmo instante → `VersaoAmbigua`;
3. cobertura `complete` numa janela que ainda não terminou no `as_of` é recusada como indício de dado do futuro;
4. manifesto com contagens por fonte, moeda, value_kind, cobertura, maturidade e estado, e `fingerprint` = sha256 do JSON canônico ordenado (independe da ordem de entrada).

## 3. Agregação, identidade e lucro

- `agregar([])` → `ausente`, nunca zero; membro sem valor anula o total (pior estado vence) salvo `aceitar_parcial=True`, que devolve cobertura `partial`.
- Soma de moedas diferentes → `MoedasDiferentes`; de value_kinds diferentes → `ValueKindsMisturados`.
- `contribuicao(custo, receita)` exige a mesma `ChaveUnidade`, janela e timezone (`IdentidadeIncompativel` caso contrário, inclusive mesmo `entidade_id` em outra conta) e só calcula com receita contábil (`reported_revenue`/`reconciled_revenue`) com valor; estimativa não vira lucro.

## 4. Features, rótulos e circularidade

- `rotulo_economico(obs)` só aceita `reconciled_revenue` + maturidade `mature`/`revised` + cobertura `complete` + valor. `reported_revenue` preliminar não é rótulo.
- `verificar_nao_circular(features, rotulo)` recusa feature que compartilhe `coleta_id`/linhagem com o rótulo, ou receita da mesma unidade sobrepondo a janela do rótulo.

## 5. Fingerprint, seed e versões

`manifesto_execucao(nome, seed, entradas, parametros)` registra seed, sha256 das entradas, parâmetros e versões (Python, numpy, scipy, statsmodels, scikit-learn, duckdb, polars, pandas). Resultado sem esse manifesto é inválido para o laboratório.

## 6. Fixture

`experiments/data-intelligence-lab/fixtures/contract/observacoes_exemplo.json` (**sintética**, 8 observações: custo, cliques, receita preliminar e revisada, zero confirmado, não coletado, falha de coleta, sinal Prebid em USD) + `MANIFEST.json` com sha256 do arquivo e o manifesto de dois snapshots (`d+1_04h`: 7 incluídas, 1 futura excluída; `d+4`: 7 incluídas, 1 versão substituída). Gerada por `scripts/gerar_fixture_contrato.py`; o teste refaz os snapshots e exige igualdade byte a byte do manifesto.

## 7. Encaixe com o que existe (handoff, não aplicado)

- Vocabulário (`EstadoMedida`, `MetodoAtribuicao`) é 1:1 com `volc_ads/economia/nucleo.py` em `wip/original-worktree-pre-qg-real-20261007` (commit 043c77f5). Diferenças: o lab acrescenta `value_kind`, `disponivel_em`, `maturidade`, `cobertura` categórica e `MetodoAtribuicao.NAO_APLICAVEL`.
- Quando o núcleo for integrado à linha principal, o caminho é: núcleo importa/define `ValueKind` e `disponivel_em`; o lab passa a importar o núcleo e apaga sua cópia. Até lá, nada aqui é autoridade de produção.

## 8. Endurecimento após a revisão adversarial F1 (2026-10-16)

| Achado | Mudança no contrato |
|---|---|
| F1-02 | `chave_logica`, `para_json` e fingerprint usam instantes em **UTC**; o grão é um conjunto (ordenado/deduplicado). Preliminar em −03:00 e revisada em UTC agora são o mesmo fato. `agregar` recusa chave lógica repetida (reentrega/duplicata não soma). |
| F1-08 | `contribuicao` devolve `None` para método `inferred`/`unreconciled`/`not_identifiable` e para cobertura não completa (salvo `aceitar_parcial=True`); o resultado carrega `preliminar`, `cobertura_completa`, maturidades, método e `value_kind`. |
| F1-14 | Enums são coagidos no construtor (`"revenue"` como str não escapa das regras); valor precisa ser `Dinheiro`, `int` ou `Decimal` finito; `complete` exige `observado_em >= janela_fim`; `politica_futuro` desconhecida levanta; `Snapshot.filtrar` filtra por `ChaveUnidade` completa. |
| F1-15 | `Snapshot.manifesto` é somente leitura (`MappingProxyType`, listas viram tuplas) e o fingerprint é fixado na construção; `manifesto_json()` devolve a cópia serializável; `verificar_integridade` confere também as contagens. |
| F1-04 | Regra única de circularidade: `origens_circulares` (vocabulário fechado `FAMILIAS_DE_FONTE`; famílias que medem a mesma receita publisher contam como iguais) usada pelo contrato e pelo portão do surrogate; `verificar_nao_circular` checa entidade (conta, tipo, id) e interseção temporal independente de grão/dimensão. |
| F1-16 | Testes para as oito guardas que sobreviviam a mutação. |

Efeito: fingerprints mudaram (UTC); fixtures regeneradas e conferidas.
