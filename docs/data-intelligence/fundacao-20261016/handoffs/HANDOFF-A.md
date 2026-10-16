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
| `.../fundacao/observacao/chaves.py` | chave natural, de idempotência e de reafirmação (espelho SQL) |
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
| `test_schema_pg_observacao.py` | 43 | chaves Python = SQL; reinserção = no-op; restatement no as_of; reafirmação/conflito/ambígua; append-only (12 casos, superusuário); 18 CHECKs; 25 mutações com Python e SQL concordando; retroativo/futuro; hash do payload; missing/unavailable/late no banco; dead letter; RLS/grants; **equivalência as_of SQL × Python** (seed 1610, 8 sequências, 9 cortes cada) |
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
    def registrar(self, obs) -> ResultadoRegistro          # INSERIDO | NOOP | REAFIRMADO
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

def adaptar_google_ads_v21(linha: Mapping) -> tuple[Observacao, ...]   # linha = observação ⋈ lote ⋈ execução (02 §9)
def adaptar_joinads_v2(linha: Mapping) -> tuple[Observacao, ...]
def chave_natural(...), chave_base(...), chave_reafirmacao(...), instante_canonico(t)
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
| P14-T02 "Provar replay e shadow antes de qualquer autonomia" | partial | manter partial; evidência: `as_of` puro e SQL equivalentes, append-only provado no banco, restatement/reafirmação | `test_schema_pg_observacao.py::test_equivalencia_as_of_sql_python`, `test_observacao_registro_asof.py::test_propriedade_idempotencia_e_as_of` |
| P14-T06 "Criar o ledger e registry do preditivo" | todo | **todo → partial** só se o integrador aceitar `dil_obs`/`Registro` como base do ledger de observações do preditivo; registry de modelos não foi tocado | `dil_obs_0001_*.sql`, 02 §10 |
| P14-T07 "Construir baseline preditivo sem vazamento de futuro" | todo | sem mudança de estado; registrar dependência: features devem vir de `as_of(t)` | 02 §7 |

Nós/arestas sugeridos para o Mapa Vivo (após merge): nó `volc_dil.fundacao.observacao` (domínio dados,
estado `testado hermeticamente`); nó `dil_obs` (migration candidata, não aplicada); arestas
`google_ads_observation (v21) —adaptada_por→ adaptar_google_ads_v21`, `joinads_observation (v2) —adaptada_por→
adaptar_joinads_v2`, `volc_dil.fundacao.observacao —compõe→ volc_dil.contracts`.
