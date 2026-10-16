# HANDOFF-A — Contrato de dados e schema (thread A)

Branch `lab/dil-fundacao-20261016-a` (worktree esparso `worktrees/dil-fundacao-20261016-a`), criada de `b6e85974`.
Contrato completo: `docs/data-intelligence/fundacao-20261016/02-CONTRATO-DE-DADOS.md`.
Nada foi aplicado fora de PostgreSQL descartável; nenhuma rede, nenhum segredo lido, nenhum roadmap/curadoria/grafo tocado.

## 1. Arquivos

| Caminho | O quê |
|---|---|
| `experiments/data-intelligence-lab/src/volc_dil/fundacao/__init__.py` | docstring do pacote (outros workers criam o mesmo arquivo: conflito trivial no merge) |
| `.../fundacao/observacao/vocab.py` | `StatusObservacao`, `Unidade`, `MAPA_ESTADO_HERDADO` |
| `.../fundacao/observacao/modelo.py` | `Observacao`, `EntidadeRef`, `Coletor`, `ObservacaoInvalida` |
| `.../fundacao/observacao/chaves.py` | chave natural e de idempotência (espelho SQL; v2 com `observed_at`) |
| `.../fundacao/observacao/registro.py` | `Registro` append-only (oráculo do SQL) |
| `.../fundacao/observacao/asof.py` | `as_of`, `latest`, `para_contrato_economico`, `agregar_observacoes` |
| `.../fundacao/observacao/normalizador.py` | normalizador tolerante a schema drift |
| `.../fundacao/observacao/adaptadores.py` | `adaptar_google_ads_v21`, `adaptar_joinads_v2` (pedido do integrador) |
| `experiments/data-intelligence-lab/migrations_candidatas/dil_obs_0001_schema_observacao.sql` + `.down.sql` | schema `dil_obs` |
| `.../migrations_candidatas/dil_obs_0002_observacao_particionada.OPCIONAL.sql` + `.down.sql` | particionamento mensal opcional |
| `tests/data-intelligence/fundacao/conftest.py` | fábrica de observações + PostgreSQL 16 descartável (indispensável: compartilhado por 3 arquivos PG) |
| `tests/data-intelligence/fundacao/test_observacao_{contrato,registro_asof,normalizador,adaptadores,sem_segredos}.py` | domínio |
| `tests/data-intelligence/fundacao/test_schema_pg_{observacao,rollback,particionamento}.py` | banco |
| `docs/data-intelligence/fundacao-20261016/02-CONTRATO-DE-DADOS.md`, este arquivo | docs |

## 2. Provas

Comando (do worktree A):

```bash
cd /Users/mac/Desktop/VOLC-OS-CAMPAIGN/worktrees/dil-fundacao-20261016-a
OMP_NUM_THREADS=2 /Users/mac/Desktop/VOLC-OS-CAMPAIGN/worktrees/data-intelligence-overnight-20261015/experiments/data-intelligence-lab/.venv/bin/python -m pytest tests/data-intelligence -q
```

Resultado: **343 passed** (172 herdados + **171 novos**) em ~45 s; só a pasta da fundação: 171 em ~17 s.
Nenhum skip (o PostgreSQL 16.11 do Homebrew subiu em todas as execuções).

| Arquivo | Testes | Gate provado |
|---|---|---|
| `test_observacao_contrato.py` | 62 | status × valor (null ≠ 0), relógios, unidade/moeda/value_kind, identidade, chaves, JSON ida-e-volta |
| `test_observacao_registro_asof.py` | 15 | idempotência, restatement, conflito, versão ambígua, A→B→A, fora de ordem, as_of/latest, agregação sem zero, ponte herdada, **propriedade** (seed 20261016, 150 sequências; exige os 3 caminhos) |
| `test_observacao_normalizador.py` | 17 | schema drift, aliases, extras, chave substituída, float/precisão, nulo → missing, partial, missing × unavailable × late ponta a ponta |
| `test_observacao_adaptadores.py` | 28 | v21 (zero sintetizado → missing; prova de linha; partial intradiário; relógios; keyword; maturação → versões) e JoinAds v2 (client × gross, chave substituída, data_status, hash zerado, entidades) |
| `test_observacao_sem_segredos.py` | 3 | nenhum host hosted, JWT, chave, token, senha, caminho de credencial ou IP do servidor nos arquivos da thread; contraprova de que cada padrão detecta |
| `test_schema_pg_observacao.py` | 43 | chaves Python = SQL; reinserção = no-op; restatement no as_of; A→B→A/conflito/ambígua; append-only (12 casos, superusuário); 18 CHECKs; 25 mutações com Python e SQL concordando; retroativo/futuro; hash do payload; missing/unavailable/late no banco; dead letter; RLS/grants; **equivalência as_of SQL × Python** (seed 1610, 8 sequências, 9 cortes cada) |
| `test_schema_pg_rollback.py` | 2 | up → down → up com catálogo idêntico; down idempotente; up repetido falha atômico; papéis preservados se usados em outro banco |
| `test_schema_pg_particionamento.py` | 1 | 0002: as_of idêntico antes/depois, no-op e inserção roteados, append-only pelo pai/partição/TRUNCATE, sem DEFAULT, rollback com catálogo idêntico a 0001 |

Commits: `7a4f41f2` (domínio), `7d2bf7e5` (migration 0001 + testes PG), `ba24302b` (adaptadores + varredura),
`7330ad5c` (particionamento 0002), e o commit final de docs.

## 3. API pública (`from volc_dil.fundacao.observacao import ...`) — o que D e G importam

```python
class StatusObservacao(str, Enum): OBSERVED, ZERO_CONFIRMED, MISSING, LATE, UNAVAILABLE, UNSUPPORTED, INVALID, PARTIAL
class Unidade(str, Enum): MICROS, CONTAGEM
@dataclass(frozen=True) class EntidadeRef: tipo: str; id: str
@dataclass(frozen=True) class Coletor: nome: str; versao: str
@dataclass(frozen=True) class Observacao:
    fonte, conta, entidade, grao, metrica, valor, unidade, moeda, janela_inicio, janela_fim, timezone,
    observed_at, available_at, ingested_at, run_id, lote_id, payload_sha256, payload_ref, schema_version,
    coletor, status, motivo=None, value_kind=None, dimensoes=(), source_updated_at=None, request_id=None,
    cobertura_ppm=None
    # propriedades: chave_natural, chave_base, conteudo, tem_valor; para_json(); Observacao.de_json(d)
class ObservacaoInvalida(ContratoViolado); class ConflitoIdempotencia(ContratoViolado); class AdaptacaoImpossivel(ObservacaoInvalida)

class Registro:
    def __init__(self, observacoes=()): ...
    def registrar(self, obs) -> ResultadoRegistro          # INSERIDO | NOOP | CONFIRMADO (D2')
    confirmacoes: tuple[Confirmacao, ...]; def ultima_confirmacao(self, chave_natural) -> datetime | None
# Observacao.estado_negocio -> (status, valor, unidade, moeda, cobertura_ppm, motivo)   # D2': o que precisa mudar para virar versão
    def registrar_todas(self, obs) -> list[ResultadoRegistro]
    versoes: tuple[VersaoRegistrada, ...]; observacoes: tuple[Observacao, ...]
    def vigente(self, chave_natural) -> VersaoRegistrada | None
    def historico(self, chave_natural) -> tuple[VersaoRegistrada, ...]
    def as_of(self, t) -> Mapping[str, Observacao]

def as_of(observacoes, t: datetime) -> Mapping[str, Observacao]      # {chave_natural: versão vigente}
def latest(observacoes, agora: datetime) -> Mapping[str, Observacao]
def para_contrato_economico(o, *, maturidade=PRELIMINAR, metodo=NAO_APLICAVEL) -> volc_dil.contracts.Observacao
def agregar_observacoes(obs, *, aceitar_parcial=False, maturidade=..., metodo=...) -> AgregadoObservacao  # .agregado, .por_status, .valor

def normalizar(payload: PayloadBruto, esquemas: Mapping[str, EsquemaPayload], ctx: ContextoLeitura) -> ResultadoNormalizacao
def observacoes_sem_dado(ctx, payload, campos, status, motivo) -> tuple[Observacao, ...]
# PayloadBruto(schema_version, corpo: bytes) .sha256 .ref; EsquemaPayload(schema_version, campo_entidade, campos_metrica,
# campo_chave=None, campos_obrigatorios=(), campo_linhas=None, validador=None); CampoMetrica(nomes, metrica, unidade, value_kind=None)
# ResultadoNormalizacao(schema_version, payload_sha256, observacoes, rejeicoes, campos_extras); Rejeicao(motivo, indice, detalhe)

def adaptar_google_ads_v21(linha: Mapping, *, moeda_atestada: str | None = None) -> tuple[Observacao, ...]  # 02 §9
def adaptar_joinads_v2(linha: Mapping, *, moeda_atestada: str | None = None) -> tuple[Observacao, ...]
Observacao.de_json_texto(texto: str) -> Observacao        # R1: lê como o banco (chave repetida, NaN, float recusados)
AgregadoObservacao.cobertura_minima_ppm, .n_cobertura_desconhecida   # R1-F16
ContextoLeitura(..., cobertura_ppm: int | None = None)    # R1-F17: cobertura declarada pela fonte
def chave_natural(...), chave_base(..., observed_at), instante_canonico(t)   # chave_reafirmacao e TipoRegistro removidos
def ordem_versao(o) -> tuple                                # D1: (observed_at, available_at)
def vigente_entre(itens, *, obs=..., base=...)              # D1/D3: regra única de versão vigente (FluxoIndexado da D usa)
```

- **Thread D (replay/shadow):** use `Registro` + `as_of(t)` como fonte do estado em cada corte; para dado
  vivo, leia v21/v2 pela junção de 02 §9 e passe pelos adaptadores (nunca `google_ads_campaign_day_latest`,
  que ordena por relógio do n8n e mantém o zero sintetizado). `para_contrato_economico` liga ao `Snapshot` herdado.
- **Thread G (qualidade):** os insumos de DQ são `status`/`motivo` por observação, `AgregadoObservacao.por_status`,
  `dead_letter`, `run_coleta` (status/contagens) e `ingested_at − available_at` (atraso de escrita).
  Views em `migrations_candidatas/views_qualidade/` podem ler `dil_obs.observacao` e `observacao_as_of(t)`.
  O conftest de `tests/data-intelligence/fundacao/` já oferece `cluster_pg`, `banco_obs` e `cluster_pg_dedicado`.

## 4. Falhas encontradas no caminho (e o que mudou)

- macOS: o postmaster aborta com "postmaster became multithreaded during startup" sem `LC_ALL`; o harness
  força `LC_ALL=C` em todo subprocesso (documentado no conftest).
- Paridade Python × SQL de espaço: `str.strip()` remove espaços Unicode, `btrim` só o ASCII; o Python passou a
  usar `strip(" ")` para bater com o CHECK.
- Gerador de propriedade inicial dava conteúdo diferente para a mesma leitura (status aleatório) e caiu em
  `ConflitoIdempotencia` — corrigido para conteúdo função do payload (como um coletor determinístico).
- `0002.down` recriava a sequência sem a ACL materializada que 0001 tinha; o teste de catálogo pegou e o down
  passou a revogar PUBLIC das sequências como 0001.

## 5. Limitações e riscos

1. **Redundância com v21/v2 (decisão em 02 §9.3):** `dil_obs` não deve receber Google Ads/JoinAds; para essas
   fontes a observação canônica é modelo de leitura via adaptadores. Risco se alguém escrever nos dois.
2. Adaptadores testados só com linhas sintéticas; a forma real de `raw_source.metrics` (v21) não foi conferida.
3. `conversions` fracionária vira `invalid` (vocabulário herdado só tem contagem inteira) — decisão de
   vocabulário pendente (micro-conversões? `Decimal`?).
4. Vocabulário de grão herdado sem `search_term`/`post` (02 §2); proposta de extensão em `volc_dil.contracts`.
5. JoinAds `currency_code DEFAULT 'USD'` pode inventar moeda — indetectável no adaptador; endurecer na origem.
6. Append-only cede a superusuário que desligue triggers; aceito e documentado.
7. Concorrência: lock consultivo por chave natural sem teste multi-sessão.
8. `ingested_at` do Python é declarado pelo chamador; no SQL é `now()` — o teste de concordância exclui esse campo de propósito.
9. `as_of` SQL global (`DISTINCT ON` sobre a tabela inteira) não foi medido em volume (thread B).
10. O down de 0001 apaga o histórico; o de 0002 copia os dados de volta.

## 6. Delta de curadoria proposto (só proposta; integrador decide e aplica)

| Tarefa | Estado atual | Proposta | Evidência |
|---|---|---|---|
| P06-T08 "Criar ledger canônico de coleta Google Ads por conta e data" | partial | **manter partial**; acrescentar evidência: contrato de leitura v21 → `Observacao` com regra zero-sem-linha → `missing` e `available_at = max(collected_at, created_at)` | `adaptadores.py`, `test_observacao_adaptadores.py` (28), 02 §9.1 |
| P14-T02 "Provar replay e shadow antes de qualquer autonomia" | partial | manter partial; evidência: `as_of` puro e SQL equivalentes, append-only provado no banco, restatement e ordem de versão por observed_at (D1) | `test_schema_pg_observacao.py::test_equivalencia_as_of_sql_python`, `test_observacao_registro_asof.py::test_propriedade_idempotencia_e_as_of` |
| P14-T06 "Criar o ledger e registry do preditivo" | todo | **todo → partial** só se o integrador aceitar `dil_obs`/`Registro` como base do ledger de observações do preditivo; registry de modelos não foi tocado | `dil_obs_0001_*.sql`, 02 §10 |
| P14-T07 "Construir baseline preditivo sem vazamento de futuro" | todo | sem mudança de estado; registrar dependência: features devem vir de `as_of(t)` | 02 §7 |

Nós/arestas sugeridos para o Mapa Vivo (após merge): nó `volc_dil.fundacao.observacao` (domínio dados,
estado `testado hermeticamente`); nó `dil_obs` (migration candidata, não aplicada); arestas
`google_ads_observation (v21) —adaptada_por→ adaptar_google_ads_v21`, `joinads_observation (v2) —adaptada_por→
adaptar_joinads_v2`, `volc_dil.fundacao.observacao —compõe→ volc_dil.contracts`.

## 7. Resposta à R1 (revisão adversarial, 2026-10-16)

Base: `git merge --no-ff lab/data-foundation-20261016` (HEAD `413395a5`) no worktree A → `d550b445`.
Correções em `f8de6875`; ajuste mínimo em 2 testes da thread G em `6f7014dc` (marcado `[thread A, R1-*]`).
Suíte: **692 passed** (650 após o merge + 44 testes novos − 2 substituídos), ~95 s. Dos 44 testes novos,
**43 falham no código anterior** (`d550b445`, rodado numa cópia com os testes novos); o 44º
(`test_r1_m7_...` em Python) passa no código correto e existe para matar a mutação M7. Mutações reaplicadas
numa cópia (script `mutar.py` no scratchpad): **M1, M2, M3, M4, M5, M6, M7 (Python e SQL), M11, M13 e M18 mortas**. (Depois, em D2, o trecho de M7 — `<=` na regra de reafirmação — deixou de existir; o teste continua cobrindo a reentrega no instante de outra versão.)

| Achado | Correção | Teste (falha antes, passa depois) |
|---|---|---|
| F1 bloqueante: `recebido_em` declarado pelo escritor; `as_of` mostrava no passado o recebido hoje | relógio do banco `dil_obs._agora()`; `payload_bruto.recebido_em` e `lote.recebido_em` := relógio do banco; `p_recebido_em` só conferido (≤ 5 min no passado, nunca futuro); `available_at` ≥ primeiro recebimento dos bytes e ≥ lote | `test_schema_pg_observacao.py::test_r1_f1_nunca_retroativo_pelo_relogio_do_banco` (cenário `t_retro.py` + lote passado + M3 futuro + bytes posteriores + futuro) |
| F2 aplicador continuava dono | membresia temporária: superusuário não se concede; não-superusuário se concede e revoga no fim; membro permanente → WARNING | `test_schema_pg_r1.py::test_r1_f2_aplicador_nao_superusuario_nao_continua_dono` (papel NOSUPERUSER CREATEROLE aplica; depois `SET ROLE`, UPDATE, TRUNCATE e DISABLE TRIGGER negados; down pelo mesmo aplicador), `test_r1_f2_membro_permanente_recebe_aviso` |
| F3 linhagem solta | run da obs = run do lote, em andamento (FOR SHARE); fonte/coletor = run; schema = lote | `test_r1_f3_linhagem_conferida` (5 casos), `test_r1_f3_lote_de_run_finalizado_nao_recebe` (cenário `t_linhagem.py`) |
| F4 moeda inventada a montante | moeda só com prova no payload ou `moeda_atestada`; senão `invalid` `moeda_nao_provada`/`moeda_divergente`; moeda sem prova não é gravada nem em linha sem valor. Documentado: v21 campanha-dia grava 'BRL' fixo, JoinAds `cfg.CURRENCY \|\| 'USD'` + DEFAULT 'USD' | `test_observacao_adaptadores.py::test_r1_f4_*` (2) |
| F8 run fechado com contagens NULL/incoerentes; retry erra | `finalizar_run` conta inseridas/dead letter, exige `n_lidas`/`n_noop`, coerência e é idempotente; CHECK com `IS NOT NULL` | `test_schema_pg_r1.py::test_r1_f8_*` (cenário `t_run.py`), `test_r1_m4_check_de_contagens_no_banco` |
| F9 SQL aceitava o que o Python recusa | entrada `json`; inteiro literal; tipos JSON; offset ISO obrigatório (SQL e `de_json`); `_texto_ok` em toda identidade (CHECK e função); `ingested_at` declarado ≥ `available_at`; Python com `available_timezones()` (caixa exata); `Observacao.de_json_texto` | `test_validacao_python_e_sql_concordam` (37 mutações, todos os casos de `t_div.py`), `test_r1_m18_*` (4), `test_observacao_contrato.py::test_r1_f9_*` (7), novos casos de CHECK |
| F15 chave JoinAds mascarada a montante | `custom_key_ausente:<pedida>` (pedido do request ou do endpoint); `custom_key_forcado_upstream` em `key_value_country_adunit`/`pageviews_campaign_batch`; limite documentado (linhas substituídas são descartadas antes da tabela) | `test_r1_f15_custom_key_ausente_forcado_e_com_espaco` (casos (j), (k) e M13) |
| F16 partial somado num total `medido` | `partial` fora do total por padrão; `cobertura_minima_ppm`, `n_cobertura_desconhecida` | `test_observacao_registro_asof.py::test_r1_f16_*` (cenário `t_agreg.py`) |
| F17 cobertura fabricada linearmente; "desconhecida" impossível | `partial` com `cobertura_ppm` nulo + marcador `cobertura_desconhecida` (Python e CHECK); normalizador usa só cobertura declarada pela fonte; adaptadores gravam desconhecida | `test_r1_f17_*`, `test_v21_intradiario_vira_partial_sem_cobertura_fabricada`, `test_janela_aberta_vira_partial_com_cobertura` (mata M11), `test_checks_aceitam_partial_com_cobertura_desconhecida` |
| F20 mutações sobreviventes | testes dirigidos: M1 (`ck_obs_janela_fechada`), M2 (`source_updated_at`), M3, M4, M5, M6 (cluster `en_US.UTF-8`, `C.UTF-8` como reserva), M7 (Python e SQL), M11, M13, M18 (mensagem própria da guarda) | casos novos em `test_checks_do_banco_rejeitam_insercao_direta`, `test_schema_pg_r1.py::test_r1_m*`, `test_r1_m7_*` |
| F21 down com CASCADE cego | down procura dependentes fora de `dil_obs` em `pg_depend` e para listando-os | `test_r1_f21_down_recusa_dependente_fora_do_schema` (view `public.painel_receita` sobrevive) |
| F22 não reaplicável por não-superusuário com papéis existentes | sem ADMIN OPTION: erro claro com o GRANT a pedir, nada pela metade; com `WITH ADMIN OPTION, INHERIT FALSE, SET FALSE`: reaplica sem membresia residual | `test_r1_f22_papeis_existentes_reaplicacao_por_nao_superusuario` |
| H3 retry concorrente sob REPEATABLE READ | READ COMMITTED obrigatório (erro `isolamento`); em RC o retry concorrente espera a trava e vira `noop` | `test_r1_h3_*` (duas sessões psql) |
| H4 `finalizar_run` concorrente | `FOR SHARE` no registro, `FOR UPDATE` + contagem em comando novo no fechamento | `test_r1_h4_*` (fechamento espera a observação em voo e a conta; depois recusa nova) |

Achados contestados: **nenhum**. Duas ressalvas de escopo:
- F22 pedia "reaplicável por não-superusuário quando papéis já existem". No PostgreSQL 16 um CREATEROLE só
  administra papéis em que tem ADMIN OPTION; a migration não pode (nem deve) contornar isso. O que entreguei:
  com ADMIN OPTION reaplica; sem ela, para cedo com o GRANT exato a pedir.
- F1 vale no banco; o `Registro` em Python continua sem conhecer o recebimento dos bytes (documentado em 02 §3).

Mudanças que afetam outras threads:
- `registrar_observacao` agora recebe `json` (chamadas com `::jsonb` não resolvem). Linhagem conferida:
  `schema_version` da observação = a do lote. `finalizar_run`: passe `NULL` nas contagens que o banco calcula.
- Para dados com `available_at` no passado em teste, troque o relógio do banco: `ClusterPG.sql_relogio(t, papel)`
  no conftest (só no cluster descartável).
- Ajustei `test_qualidade_pg_views.py::_carga_dil_obs` e `test_qualidade_checagens.py::test_zero_sintetizado_caminho_contrato_a_igual_ao_direto`
  da thread G para essas regras (sem mudar a lógica de G). `agregar_observacoes` deixa `partial` fora do total por padrão.
- O down de 0001 agora recusa rodar com as views `dil_qualidade.*` (dq_02) aplicadas: rode o down de dq_02 antes.

Delta de curadoria adicional (proposta): P06-T08 e P14-T02 continuam `partial`; anotar que a regra "nunca
retroativo" agora é do relógio do banco e que adaptadores v21/v2 marcam moeda sem prova como `invalid` — o
coletor v21 precisaria pedir `customer.currency_code` no GAQL para o custo deixar de ser `invalid`.

### 7.1 Achados D1–D3 da thread D (tratados junto com a R1)

Base: merge local de `lab/data-foundation-20261016` em `62df98be` (com D) → `ced64b37`.
Suíte: **786 passed** (~150 s). Os 8 testes novos de D1–D3 falham todos no código anterior (`ced64b37`).

| Achado | Decisão / correção | Teste |
|---|---|---|
| D1 ordem de versão: leitura antiga entregue atrasada voltava o `as_of` ao valor antigo (10/7.689 contra o `visao_as_of` da E em `atraso_receita_longo`) | regra única `ordem_versao = (observed_at, available_at)`: vence a medição mais recente; empate → conhecida por último; depois `chave_idempotencia` (inalcançável pelo UNIQUE). Igual em `as_of`, `Registro.vigente`, `observacao_as_of` (SQL, índice `ix_obs_asof`) e no `FluxoIndexado` da D (que agora delega a `vigente_entre`) | `test_observacao_ordem_versao.py::test_d1_*` (2; contra o simulador: 0 divergências com a regra nova, >0 com a antiga), `test_schema_pg_r1.py::test_d1_*`, geradores de propriedade e de equivalência SQL×Python agora com `observed_at` fora da ordem de chegada |
| D2 releitura D0 com a mesma `chave_base` e outra cobertura → `ConflitoIdempotencia` | `observed_at` entra na chave da leitura (`dil_obs.chave_idempotencia.v2`): retry/reentrega = no-op; releitura em outra hora (inclusive a de D+1 com o MESMO payload e janela fechada) = versão nova. A "reafirmação" deixou de existir (removidos `TipoRegistro`, `REAFIRMADO`, `chave_reafirmacao`, colunas `chave_base`/`tipo_registro` e `n_reafirmadas`; `finalizar_run` tem 7 parâmetros). Alternativas rejeitadas e custo no 02 §6 | `test_d2_releitura_d0_do_padrao_real_*` (5 campanhas, 1 muda por hora, ≥75% de repetição: tudo `inserido`, retry `noop`, janela fecha), `test_d2_cobertura_declarada_*` (cobertura que muda = versão; mesma leitura com outra cobertura = conflito), `test_schema_pg_r1.py::test_d2_releitura_d0_no_banco_igual_ao_registro` |
| D3 erro de ambiguidade já superada dependia da ordem de entrada | `vigente_entre` agrupa e decide pelo topo: ambiguidade só quando leituras diferentes empatam no topo; superadas não levantam; resultado e erro independem da ordem | `test_d3_*` (todas as permutações de um caso e propriedade com 200 conjuntos × 10 embaralhamentos) |

Efeitos em outras threads (mudança mínima, marcada `[thread A, D*]`/`[thread A, R1-*]`):
- D: `shadow/fluxo.py::FluxoIndexado.as_of` delega a `vigente_entre`; `shadow/linhas_formato_real.py` passa a
  provar a moeda no payload (`customer.currencyCode` no v21; `batch_payload` com `currency` na JoinAds) — sem isso
  o R1-F4 deixava custo e receita `invalid`; `test_shadow_real.py::test_replay_de_linhas_reais_ponta_a_ponta`:
  com D2 a leitura de D+1 06h (mesmo payload, janela fechada) não é mais descartada como duplicata, o custo de
  D-1 chega fechado e as baselines `equal`/`greedy` (sem portão de maturidade, 06 §11) realocam por construção —
  saíram do conjunto "não corta" e ganharam uma asserção de que recebem o custo.
- G: `finalizar_run` com 7 argumentos em `test_qualidade_pg_views.py`.
- Contagem de "repetição" muda de natureza: quem precisa de pontos de mudança deduplica por conteúdo na leitura.

### 7.2 Medições da frente B: `as_of` inlinável, chaves compactas e D2' (versão só quando o estado muda)

Base: merges locais de `lab/data-foundation-20261016` em `d62bf0c0` e `7b3e9834`. Commits: `cb47ecac`
(as_of inlinável + bytea + 0002 corrigido), `a5b6e4fb` (D2'), e o commit de docs.
Suíte: **878 passed, 1 skipped** (o skip é a medição grande, com motivo explícito; roda com `DIL_BENCH_N`).

**(1) `observacao_as_of` não era inlinada.** A função tinha `SET search_path` e `STRICT` — qualquer um dos dois
impede o planejador de expandir uma função SQL de conjunto. Agora: sem `SET`, sem `STRICT`, nomes e o operador
qualificados (`OPERATOR(pg_catalog.<=)`), SECURITY INVOKER; `t` nulo → conjunto vazio como antes. A ordem do D1
ficou com 3 colunas (o UNIQUE `(chave_natural, available_at)` torna o desempate extra inalcançável), coberta
pelo índice `ix_obs_asof`. Prova na suíte: `test_schema_pg_desempenho.py::test_as_of_e_latest_sao_inlinados_e_chaves_compactas`
(nenhum "Function Scan" para função, ponto e view; resultado = consulta escrita à mão).

Medição (cluster descartável, `test_medicao_grande`, tempo no servidor = Planning + Execution do
`EXPLAIN ANALYZE`, 3 repetições; máquina compartilhada com outros workers, há ruído):

| 1e6 linhas (10 contas × 100 entidades × 250 dias × 4 versões) | antes (`HEAD` de então) | depois |
|---|---|---|
| inlinada? | não | **sim** |
| `as_of` de um ponto (uma chave) | 1,51–1,58 s | **0,001 s** |
| `as_of` global no meio do histórico | 0,72–3,41 s | **0,30–0,41 s** |
| `as_of` global no fim (1e6 versões visíveis) | 1,52–2,12 s | 1,23–3,70 s |
| `observacao_latest` | 1,68–2,44 s | 1,48–2,17 s |
| 1e5: ponto / meio / fim / latest | 0,97–2,31 / 0,41–0,51 / 0,71–0,98 / 0,71–0,91 s | 0,001 / 0,026–0,044 / 0,05–0,10 / 0,045–0,10 s |

Leitura honesta: o ganho grande é em toda consulta seletiva (ponto, filtro por conta, corte no meio), que agora
empurra o predicado para dentro do `as_of`. O `as_of` global no fim do histórico continua custando ~1–4 s em 1e6
porque percorre todas as versões (DISTINCT ON sobre 1e6 linhas com acesso ao heap). Não reproduzi os 8,5–17,5 s
que a B mediu para a função não inlinada (aqui: 1,5–3,4 s); a diferença provável é a forma de medir (B: cliente,
EXECUTE e outra carga). Disco: pico do cluster 2,1 GiB; todos os clusters apagados.

**(2) Formato longo caro.** `ix_obs_chave_base` já não existia (saiu com o D2). Mudanças: `chave_natural` e
`chave_idempotencia` como **digest bytea de 32 bytes** (paridade Python × SQL = `encode(chave, 'hex')`, provada no
teste de chaves) e sem índice em `lote_id`.

| 1e6 linhas | antes | depois |
|---|---|---|
| heap B/linha | 512 | **455** |
| índices B/linha | 483 | **332** |
| total B/valor | 995 | **787** (−21%) |
| `uq_obs_chave_idempotencia` / `uq_obs_versao` / `ix_obs_asof` (MB) | 124 / 141 / 148 | **77 / 90 / 102** |

**Achado colateral (corrigido):** o `0002` (particionamento opcional) tinha o corpo do `as_of` congelado na
1ª geração — com a ordem pré-D1 (maior `available_at`). Aplicar o 0002 desfaria o D1 em silêncio. O gerador agora
copia também esse bloco de 0001, e `test_schema_pg_particionamento.py` compara o corpo da função depois do 0002 com
o de 0001 e inclui uma leitura antiga entregue atrasada.

**(3) D2' — decisão do integrador sobre o custo do D2.** Uma leitura só vira **versão** quando o `estado_negocio`
(status — inclui o fechamento da janela —, valor, unidade, moeda, cobertura, motivo) difere do vigente no instante
dela. Releitura igual → **confirmação** estreita em `dil_obs.confirmacao`. Retry (mesmo fato, mesmo
`observed_at`, já conhecido) → `noop`. Para ser independente da ordem de chegada:

- a redundância compara com a versão vigente no instante da leitura **e** com toda versão de ordem menor que,
  conhecida depois, venceria antes dela;
- ao inserir uma versão, todo corte posterior é conferido; a confirmação que passaria a vencer com outro estado
  é **materializada** como versão (a própria leitura, com seus relógios; no banco a linha é reconstruída da versão
  confirmada + lote + run, e a chave é recalculada).

Escolha da forma da confirmação (bytes medidos, 1e6): **tabela estreita, 211 B por confirmação** contra 787 B por
observação (3,7×). A alternativa "só contagem no recibo do run" custaria 0 B por leitura, mas foi rejeitada:
perde o frescor e, principalmente, impede o reparo — sem a confirmação guardada, uma leitura antiga e diferente
chegando atrasada passaria à frente de uma confirmação mais nova, e o estado ficaria dependente da ordem
(a propriedade com permutações falharia). Estimativa sobre o modelo da B (HANDOFF-B §8.6: D2 = 70,7 MB/dia e
7,9 TB em 3 anos a ×100, com 1.043 B/valor e ~94% de releituras iguais): com D2' e o DDL novo, cada leitura custa
~0,06 × 787 + 0,94 × 211 ≈ 245 B (contra 1.043) → **~17 MB/dia e ~1,9 TB em 3 anos a ×100** (estimativa
proporcional, não remedida pelo modelo da B; a confirmação passa a dominar o custo — trocar `run_id`/`lote_id`
textuais por referências inteiras a reduziria mais).

| Prova | Teste |
|---|---|
| releitura igual atrasada vira confirmação; A→B→A preservado | `test_observacao_ordem_versao.py::test_d2_linha_igual_atrasada_nao_cria_versao_e_aba_continua` |
| leitura diferente atrasada materializa a confirmação mais nova (todas as permutações) | `test_d2_leitura_diferente_atrasada_materializa_a_confirmacao_mais_nova` |
| estado do `as_of` em todo corte independe da ordem (400 conjuntos × 8 permutações) | `test_d2_propriedade_estado_independe_da_ordem_de_chegada` |
| padrão real D0 (5 campanhas, 1 muda por hora): 32 versões, 88 confirmações, retry `noop`, janela fecha (D+1 com o mesmo payload vira versão) | `test_d2_releitura_d0_do_padrao_real_nao_conflita_e_fecha_a_janela` |
| banco = Registro em 8 permutações e estado = dado bruto em 6 cortes | `test_schema_pg_r1.py::test_d2_linha_banco_igual_ao_registro_em_permutacoes_e_estado_independe_da_ordem` |
| banco: releitura D0 confirma, fechamento é versão | `test_schema_pg_r1.py::test_d2_releitura_d0_no_banco_igual_ao_registro` |
| bytes da confirmação < metade da observação | `test_schema_pg_desempenho.py` |

Os testes novos de D2' falham no código anterior (`cb47ecac`). A exceção é o de permutações no banco, que é uma
propriedade (Registro = banco e estado = bruto) e também valia sob D2; ganhou a asserção de que a confirmação foi
exercitada, que falha antes.

Mudanças fora da A (mínimas e marcadas `[thread A, D2']`):
- `capacidade/coletor.py`: `ReciboRun.confirmadas`, preenchido com o resultado CONFIRMADO do `Registro`.
- `test_capacidade_coletor.py`:
  - releitura igual às 07h agora é 0 inseridas e 9 confirmadas;
  - no A→B→A, cada leitura gera 1 versão (custo) e 2 confirmações (métricas que não mudam);
  - serial × paralelo passa a contar versões + confirmações;
  - fora de ordem passa a comparar os ESTADOS registrados — as linhas dependem da ordem de chegada, e devem.

Limites: confirmações não entram no `as_of` (só frescor e reparo). Uma reentrega que chegue com `available_at`
anterior ao de uma confirmação já registrada vira outra confirmação (não `noop`), para não descartar conhecimento
mais cedo. Uma confirmação a materializar com o mesmo `available_at` de outra versão do fato levanta
`versao_ambigua`.
