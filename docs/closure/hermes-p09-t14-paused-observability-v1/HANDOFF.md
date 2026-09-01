# P09-T14 — observabilidade de campanha PAUSED · handoff da lane

**Branch:** `sprint/hermes-p09-t14-paused-observability-v1`
**Base:** `c3c820bdc1242f29cdba8c336d97302597098f86` (= `origin/volc-os-v2` na abertura)
**Data:** 01/09/2026
**Estado proposto para P09-T14:** continua **`partial`**. Esta lane NÃO promove nada.

---

## 1. Resumo

A auditoria de 01/09/2026 registrada no ROADMAP-VIVO apontou o defeito com
precisão: o coletor lê apenas campanhas ENABLED (`persistencia.py:64-65`,
`estado_externo=eq.ENABLED`), então uma campanha PAUSED — que é exatamente o que
o canário é — desaparece da observabilidade, e não existia caminho one-shot por
identidade explícita porque todo caminho passava por `campanhas_search_ativas()`.

A lane fecha essa lacuna sem tocar a coleta contínua:

- **`executar_alvo(alvo)`** coleta UMA campanha nomeada, em qualquer estado
  externo, reaproveitando as famílias, o bucket, a persistência e os recibos que
  já existiam. Uma execução, um alvo, sem agenda própria.
- A proteção que o filtro `ENABLED` dava é substituída por algo mais forte:
  **identidade canônica completa** (conta + `volc_campaign_id` + `campaign_id`,
  os três obrigatórios) mais **reconferência do que o inventário devolveu**. Um
  filtro remoto ignorado devolveria a campanha errada com a mesma cara; a única
  defesa real é conferir a identidade recebida contra a pedida.
- Dois estados semânticos que o modelo previa e o coletor nunca emitia passam a
  existir com prova: **`NAO_SUPORTADO`** (fora de SEARCH não há plano de
  palavras-chave, então a pergunta não existe) e **`INELEGIVEL` na simulação**
  (doutrina oficial: bid simulation exige desempenho passado).

`campanhas_search_ativas` fica intacta, com o filtro `ENABLED` e um comentário
explicando por que ele não deve ser afrouxado.

### Decisão de projeto que vale registrar

Ampliar o filtro do scan contínuo teria fechado a lacuna em uma linha — e teria
sido a resposta errada. Ampliaria a agenda contínua e gastaria cota da
carteira inteira para observar uma campanha. O caminho é **nomear o alvo**, não
alargar a varredura.

---

## 2. Arquivos alterados

| Arquivo | Natureza |
|---|---|
| `volc_ads/inteligencia_google/alvo.py` | **NOVO.** Camada de domínio: identidade, canal, elegibilidade de simulação. Sem HTTP, sem Google Ads, sem relógio |
| `volc_ads/inteligencia_google/persistencia.py` | `campanha_por_identidade`; `estado_externo` em `CampanhaAtiva`; `campanhas_search_ativas` inalterada |
| `volc_ads/inteligencia_google/coletor.py` | `executar_alvo`, `_nao_suportado`, `_veiculacao_na_janela`, `_data_de_inicio`; seam `elegivel` em `_simulacoes`; `origem` em `_persistir_familia`; injeção `cliente_google` |
| `volc_ads/inteligencia_google/__init__.py` | Exports do caminho por alvo |
| `scripts/coletar_google_inteligencia.py` | `--volc-campaign-id` / `--campaign-id`; `sys.path` da raiz |
| `backend/tests/test_google_inteligencia_persistente.py` | 43 contraprovas novas |

Commits atômicos: `55bd74c` (domínio + persistência) · `fa2b0f5` (coletor) ·
`5daebf5` (CLI) · `675fdf2` (contraprovas) · `78695b4` (handoff) · mais o commit
de correções da revisão focal (§9-bis).

Nenhum arquivo fora do ownership foi tocado. `backend/app/**`, `src/**`,
`supabase/migrations/**`, `volc-os-workbook/ROADMAP-VIVO.json`,
`docs/volc-os-graph/**` e `graphify-out/**` permanecem intocados.

---

## 3. Comandos e contagens de gates

```bash
# suíte das duas famílias sob ownership
python3 -m pytest backend/tests/test_google_inteligencia_persistente.py \
                  backend/tests/test_google_inteligencia_saude.py -q
# 96 passed        (baseline no commit base: 53 passed → +43 contraprovas)

# suíte completa python
python3 -m pytest backend/tests volc_ads -q \
  --ignore=backend/tests/test_admin_fields_separation.py \
  --ignore=backend/tests/test_docx_intro_closing.py
# 2515 passed, 20 failed, 98 skipped

# cobertura do pacote sob ownership
python3 -m coverage run --source=volc_ads/inteligencia_google \
  -m pytest backend/tests/test_google_inteligencia_persistente.py -q
python3 -m coverage report -m
# alvo.py 89% · coletor.py 91% · persistencia.py 74% · modelo.py 86%

# gate oficial de mutação
python3 scripts/gate_sem_mutacao_google.py
# ok · 1/3 FORGE_PERMITIR_ESCRITA não está armada
# ok · 2/3 a trava de escrita está fechada
# ok · 3/3 as 5 contraprovas focais da rota passaram

# autoridade Supabase
python3 scripts/verificar_autoridade_supabase.py
# ✓ Supabase oficial: https://database.agenciavolc.com.br
```

### As 20 falhas são herdadas, e isso foi provado, não suposto

`test_criativo_execucao.py` (18) e `test_criativo_rotas_equivalentes.py` (2)
falham por falta de `pytest-asyncio` no ambiente. Rodadas em worktree limpa no
commit base `c3c820b`: **as mesmas 20 falham lá**. Nenhum desses módulos importa
`inteligencia_google` nem o CLI. Os dois erros de coleta
(`test_admin_fields_separation.py`, `test_docx_intro_closing.py`) são
`ModuleNotFoundError: No module named 'docx'`, também herdados.

---

## 4. Prova nominal — campanha PAUSED explícita

Execução hermética com a identidade nomeada do canário (`modo=completa`, que é o
default do CLI), com protos Google Ads v25 reais e zero rede:

```
{
  "bucket": "daily:2026-09-01",
  "campaign_id": "24156373085",
  "canal": "SEARCH",
  "customer_id": "8017851692",
  "estado_externo": "PAUSED",          <-- a PAUSED entrou na coleta
  "modo": "completa",
  "origem": "alvo_explicito",
  "simulacao_elegivel": false,
  "sonda": {
    "estado": "medido",
    "inicio_da_campanha": "2026-09-01",
    "janela": ["2026-08-19", "2026-09-01"],
    "veiculou_na_janela": false
  },
  "volc_campaign_id": "a7f1c0de-0000-4000-8000-000000000001",
  "total": 4
}
  DIAGNOSTICO_ENTREGA      com_dados        coleta-001
  SIMULACOES_CAMPANHA      inelegivel       coleta-002
  RECOMENDACOES_GERADAS    com_dados        coleta-003
  FORECAST_KEYWORDS        parcial          coleta-004
```

O recibo carrega as **duas** identidades (`campaign_id` e `volc_campaign_id`), a
marca de procedência `origem: alvo_explicito` e — no recibo da simulação — o
retrato da sonda que justificou o `inelegivel`.

Contraprovas: `test_campanha_pausada_explicita_entra_na_coleta`,
`test_modo_completa_e_read_only_com_lista_branca_de_superficie`,
`test_inelegivel_carrega_o_retrato_da_sonda_que_o_justificou`.

⚠️ **Isto é prova hermética, não execução contra a conta real.** Ver §9.

---

## 5. Prova de que o scan contínuo NÃO foi ampliado

Quatro ângulos independentes:

1. **A consulta PostgREST real continua filtrando.**
   `test_scan_continuo_consulta_apenas_enabled_no_postgrest` monta a URL de
   verdade e confere `estado_externo=eq.ENABLED` e `canal=eq.SEARCH`.
2. **A PAUSED não aparece na varredura.**
   `test_scan_continuo_nao_alcanca_campanha_pausada`: com canário PAUSED, campanha
   ENABLED e PMax no inventário, a varredura devolve só a ENABLED.
3. **A ENABLED continua funcionando igual.**
   `test_coleta_continua_de_enabled_continua_funcionando`: `executar()` produz
   `com_dados`/`vazio_confirmado` nas mesmas famílias, e as campanhas tocadas são
   exatamente `{ENABLED}`.
4. **O one-shot não herdou agenda.**
   `test_scan_continuo_nao_ganhou_agenda_nova_no_caminho_do_alvo`: `executar_alvo`
   **não** dispara `RECOMENDACOES_ARMAZENADAS` nem `EXPERIMENTOS` (famílias de
   conta) e toca uma única campanha.

E o caminho do alvo não pode herdar o filtro por acidente:
`test_persistencia_filtra_pelos_tres_identificadores` confere que
`estado_externo=eq.ENABLED` **não** está na URL de `campanha_por_identidade`.

### Nenhum segundo scheduler

`test_caminho_do_alvo_nao_cria_segundo_scheduler` verifica a **AST** de
`alvo.py`, `coletor.py`, `persistencia.py`, `modelo.py` e do CLI: nenhum import
de `threading`/`sched`/`schedule`/`apscheduler`/`croniter`/`signal`/`asyncio`/
`time`/`multiprocessing`/`subprocess`, nenhuma chamada de espera
(`sleep`/`every`/`enter`/`alarm`) e nenhum laço `while`. O CLI também não ganhou
`--intervalo`/`--repetir`/`--loop`/`--daemon`/`--watch`.

Grep de substring não serviria aqui — reprovaria um comentário que *explica* por
que não há scheduler e aprovaria `getattr(time, "sl" + "eep")()`. O que decide é
a estrutura.

⚠️ **Correção de fato sobre a agenda contínua.** Uma versão anterior deste
handoff (e comentários no código) afirmavam que "a autoridade de frequência
continua sendo o n8n". Isso afirma mais do que se sabe. O que existe hoje:
`deploy/google-intelligence/` versiona um pacote **systemd** com dois timers
(`…-completa.timer`, `OnCalendar=*-*-* 06:15:00 America/Sao_Paulo`, e
`…-frequente.timer`, a cada 4h UTC), que o ROADMAP registra como **não
instalado**; e os workflows n8n, onde a ingestão operacional de fato vive.
**Escolher UMA dessas autoridades é justamente o que falta em P09-T14.** O
caminho por alvo não entra nessa disputa — mas dizer que a disputa já está
resolvida era falso, e o texto foi corrigido em `alvo.py`, `persistencia.py` e
`coletor.py`.

---

## 6. Prova de idempotência

`test_retry_do_alvo_e_idempotente` roda `executar_alvo` **duas vezes** e confere:

- as chaves de idempotência da segunda rodada são **idênticas** às da primeira;
- os `coleta_id` devolvidos são os mesmos;
- o coletor **enviou** 8 documentos e o banco **gravou** 4.

Medido na execução nominal do §4: `enviados: 8 | gravados: 4`.

A procedência (`origem`) mora no **payload**, nunca na chave de idempotência —
repetir a coleta não cria recibo novo.

E o inverso continua valendo: `test_falha_e_sucesso_do_mesmo_alvo_nao_se_apagam`
prova que uma falha e um retry bem-sucedido no mesmo bucket geram chaves
distintas, então a falha antiga não esconde o sucesso posterior.

### O custo da idempotência por bucket, medido em vez de prometido

`test_leitura_nova_no_mesmo_bucket_e_descartada_e_isso_esta_provado` monta o caso
desconfortável: primeira coleta com 0 keywords, o operador sobe 2 keywords, e a
segunda coleta roda no mesmo bucket. O coletor **lê** as 2 (`enviados[1]` traz
`keywords: 2`), mas a chave é a mesma e a RPC devolve o id antigo sem regravar —
a linha do banco continua com `keywords: 0`, e nada acusa isso.

É o comportamento pedido pelo contrato (não duplicar observação), mas o alcance
disso não é o que a versão anterior deste handoff dizia. Quem precisa da leitura
nova precisa de **outro bucket**, não de outra chamada. Fica registrado como
comportamento conhecido e testado, não como surpresa.

O dublê de persistência imita a RPC nesse ponto exato (`enviados` × `documentos`
são listas separadas), justamente para que nenhum teste afirme conteúdo que
nunca chegou ao banco.

---

## 7. Prova dos seis estados semânticos

`test_seis_estados_semanticos_permanecem_distintos` acumula os estados de quatro
cenários e exige o conjunto completo. Cada estado tem, além disso, contraprova
própria:

| Estado | Contraprova | O fato que ele representa |
|---|---|---|
| `com_dados` | `test_campanha_pausada_explicita_entra_na_coleta` | a API respondeu com itens |
| `vazio_confirmado` | `test_campanha_antiga_sem_simulacao_permanece_vazio_confirmado` | perguntamos, não havia nada, `quantidade = 0` |
| `parcial` | `test_forecast_com_cenario_recusado_e_parcial_de_verdade` | parte respondeu, parte falhou |
| `inelegivel` | `test_ausencia_de_simulacao_em_campanha_nova_e_inelegivel` | a pergunta não se aplica a esta campanha |
| `nao_suportado` | `test_familia_de_plano_de_palavras_fora_de_search_e_nao_suportada` | a pergunta não existe neste canal |
| `falhou` | `test_erro_de_rede_vira_falhou_e_nunca_vazio` | não sabemos; `quantidade = None`, código e classe presentes |

`parcial` é produzido pelo `_forecast` **real** — um cenário responde, os
seguintes são recusados — e não por um documento montado à mão no teste.
Cobertura de `coletor.py`: **91%**, com os corpos de `_forecast` e
`_recomendacoes_geradas` exercitados.

### Os quatro pares que mais se confundem, separados com prova

- **`inelegivel` vs `vazio_confirmado`.** Campanha nova sem simulação →
  `inelegivel`. Campanha antiga sem simulação → `vazio_confirmado`. O rebaixamento
  só acontece quando é **demonstrável**: a janela precisa cobrir a vida inteira da
  campanha e não ter veiculação. Começou antes da janela → não se afirma nada.
  Doutrina: `docs/architecture/evidence/GOOGLE-ADS-DOCS-2026-09-01.md` §4.
- **`vazio_confirmado` observado vs `vazio_confirmado` de sonda cega.** A sonda lê
  `campaign`; a família lê `campaign_simulation`. São recursos diferentes, então a
  sonda **pode falhar sozinha** — e nesse caso o `inelegivel` degradaria para
  `vazio_confirmado` em silêncio. Por isso o retrato da sonda (`estado`,
  `veiculou_na_janela`, `erro_codigo`) viaja dentro do payload:
  `test_sonda_cega_nao_produz_vazio_indistinguivel_de_vazio_observado` prova que
  os dois recibos diferem até no `payload_sha256`.
- **`inelegivel` vs `nao_suportado` vs "não sei".** Search sem keywords habilitadas
  → `inelegivel`. PMax → `nao_suportado`, sem gastar chamada. E canal `UNKNOWN` ou
  `UNSPECIFIED` — que no vocabulário canônico (ADR-18) significam *"a conta não
  disse"* — **não** viram `nao_suportado`: o alvo inteiro falha fechado
  (`test_canal_desconhecido_nao_vira_nao_suportado`). Ignorância não é conclusão
  de domínio, e o vocabulário não tem estado para "não sei".
- **`falhou` vs `vazio_confirmado`.** Erro de rede → `falhou`, `quantidade` nula,
  `erro_codigo`/`erro_classe` presentes. Nunca vira zero.

### Zero medido permanece zero

`test_zero_medido_atravessa_o_coletor_como_zero`: `impressions` medida em 0
atravessa como `estado_valor: medido`, `valor_numerico: "0"`; e
`search_impression_share`, que não veio na resposta, permanece
`estado_valor: ausente` com `valor_numerico: null`. Ausência e zero não se
tocam.

E `test_simulacao_presente_vence_a_heuristica_de_elegibilidade`: se a API
devolve simulação, o dado vence a heurística — `com_dados`, não `inelegivel`.

---

## 8. Prova de zero mutação

Quatro camadas:

1. **A trava do FORGE** continua conferida antes da primeira chamada
   (`coletor.py`, `estado_escrita()`), inalterada.
2. **Somente `SELECT`** — `_query` recusa qualquer GAQL que não comece com
   `SELECT`, e o dublê de teste recusa de novo, do outro lado.
3. **Lista branca de superfície, exercitada no modo default** — o dublê declara
   os serviços e tipos previstos e **recusa qualquer outro**; qualquer coisa fora
   disso cai em `atributos_desconhecidos` e levanta `AttributeError`. Rodado em
   `modo=completa` (o default do CLI), que é onde `RecommendationService` e
   `KeywordPlanIdeaService` realmente são chamados:
   ```
   servicos: ['GoogleAdsService', 'KeywordPlanIdeaService', 'RecommendationService']
   tipos:    ['GenerateKeywordForecastMetricsRequest', 'GenerateRecommendationsRequest']
   atributos desconhecidos: []
   ```
   Uma superfície nova precisa ser adicionada à lista **à mão**. É essa fricção,
   e não o grep, que torna difícil um caminho de escrita entrar sem alguém
   decidir que ele entra.
4. **Varredura de fonte** —
   `test_pacote_de_inteligencia_nao_contem_mutacao_google` varre os arquivos do
   pacote mais o CLI procurando `.mutate_`, `apply_recommendation`,
   `dismiss_recommendation`, `mutate_operation` e `forge_permitir_escrita=1`.
   ⚠️ **Isto é defesa em profundidade barata, não prova.** Uma fonte que
   escrevesse via `getattr(svc, "mutate" + "_campaigns")` passaria nesse grep. É
   por isso que ele vem em quarto lugar e não é citado como a prova: quem prova
   são a trava do FORGE, o `SELECT`-only e a lista branca acima. O teste
   estrutural `test_caminho_do_alvo_nao_cria_segundo_scheduler` fecha
   parcialmente essa brecha proibindo, **na AST do `coletor.py`**, `getattr` com
   nome de atributo computado.

`scripts/gate_sem_mutacao_google.py` continua verde (3/3).

---

## 9. Limitações honestas

Nenhuma destas é hipótese: são o que a lane **não** provou.

1. **Não houve execução real.** Zero chamadas ao Google Ads, zero chamadas ao
   Supabase real, zero recibos no banco. Toda prova é hermética. Enquanto o
   comando não rodar contra a Crédito Up com o canário real, P09-T14 continua
   `partial` — e é por isso que esta lane não promove nada.
2. **`campaign.start_date_time` foi verificado contra os protos v25 instalados
   (`google-ads 31.4.0`), não contra a conta.** Em v25 o campo é
   `start_date_time`, não `start_date`. `_data_de_inicio` lê os 10 primeiros
   caracteres, o que aguenta `2026-09-01` e `2026-09-01 00:00:00`; formato
   diferente devolve `None` e nada é rebaixado.
3. **`start_date_time` vem no fuso do cliente; a janela é em UTC.** Na fronteira
   de um dia, uma campanha que nasceu um dia antes da janela pode ser lida como
   nascida dentro dela. O efeito máximo é marcar `inelegivel` uma simulação de
   campanha que não veiculou em 14 dias — conclusão que continua defensável, mas
   é uma aproximação e está declarada.
4. **A sonda `_veiculacao_na_janela` custa duas consultas a mais por execução do
   alvo**, e uma delas repete a janela de desempenho que o `DIAGNOSTICO_ENTREGA`
   já consulta. Foi mantida separada de propósito: acoplar a elegibilidade da
   simulação ao resultado do diagnóstico criaria dependência entre famílias, e
   "falha de uma família não contamina a outra" é uma propriedade que a lane
   queria preservar. É custo de cota, não de correção, e só no caminho one-shot.
5. **A sonda pode falhar sozinha — e agora isso aparece no recibo.** A versão
   anterior deste handoff afirmava que "quem falha alto é a consulta da própria
   família". **Era falso**: a sonda lê `campaign` e a família lê
   `campaign_simulation`, recursos diferentes. Uma sonda cega produzia
   `vazio_confirmado` byte a byte idêntico a um vazio observado, inclusive no
   `payload_sha256` — a degradação de `INELEGIVEL` era invisível no banco.
   Corrigido: o retrato da sonda viaja no payload
   (`test_sonda_cega_nao_produz_vazio_indistinguivel_de_vazio_observado`). O
   `except` continua estreito e nunca rebaixa por suposição, mas agora ele
   **declara** que não enxergou.
6. **`NAO_SUPORTADO` só é emitido no caminho one-shot.** A varredura contínua só
   alcança SEARCH, então lá o estado nunca se aplicaria — mas isso significa que
   o dashboard só verá esse estado quando alguém coletar um alvo não-SEARCH.
7. **Idempotência por bucket descarta leitura nova, não só retry.** Ver §6: se a
   campanha mudar entre duas execuções do mesmo bucket, a segunda leitura é
   deduplicada e o recibo antigo prevalece. A versão anterior deste handoff dizia
   que isso "não acontece para uma PAUSED" — errado; ela falava só da colisão
   *entre* os dois caminhos. Quem precisa da leitura nova precisa de outro
   bucket. Comportamento agora testado, não prometido.
8. **Divergência deliberada de normalização** entre `alvo.py` e `saude.py`, e a
   razão mudou depois da revisão. `saude._normalizar_id_interno` rebaixa a caixa;
   `alvo.normalizar_id_interno` **preserva**, porque a coluna
   `trafego_campanha.volc_campaign_id` é PK textual case-sensitive
   (`CHECK ... '^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$'`) e o valor vira filtro
   PostgREST. Com `.lower()`, um id em caixa alta produziria zero linhas e a
   resposta seria *"nenhuma campanha no inventário"* — afirmação de ausência
   sobre algo que existe. O gerador de produção hoje é `uuid5` (minúsculo), então
   era latente; o contrato do banco permite. O teste anterior comparava as duas
   implementações Python e não podia pegar isso — as duas estavam erradas juntas.
   Trocado por `test_identidade_interna_obedece_o_contrato_do_banco_e_preserva_caixa`,
   que extrai o CHECK **da própria migration** e valida contra ele.
9. **O one-shot roda fora do `flock` da coleta contínua.**
   `deploy/google-intelligence/run.sh` toma `/run/lock/volc-google-intelligence.lock`
   com `flock -n` antes de rodar; a invocação direta do CLI (§10.4) não passa por
   lá. Se um timer e um one-shot coincidirem no mesmo bucket e na mesma campanha,
   vale quem gravar primeiro (limitação 7). **Recomendação para o integrador:**
   invocar o one-shot sob o mesmo lock (`flock /run/lock/volc-google-intelligence.lock -c …`)
   enquanto a autoridade de agenda não for decidida. Não foi implementado aqui
   porque `run.sh`/`deploy/` estão fora do ownership desta lane.
10. **O Mapa Vivo não pôde ser consultado nesta worktree.**
   `python3 scripts/atualizar_grafo_volc_os.py --check` devolveu
   `{"current": false, "reason": "UPDATE_STATUS.json ausente"}` — `graphify-out/`
   e `.graphify-cache/` não existem aqui e não há `.venv-graphify`. A arqueologia
   foi feita pela curadoria humana (`docs/volc-os-graph/curadoria-operacional.json`,
   nível 1 da cadeia), pelo ROADMAP-VIVO, pelo código, pelo SQL e pela doutrina
   oficial. **Declarado, não contornado.**
11. **A decisão de autoridade de agenda continua pendente.** O critério de aceite
    de P09-T14 pede agenda única decidida (n8n **ou** worker), frequência ativa,
    heartbeat, alerta por atraso e dashboard mostrando os seis estados. Esta lane
    não decide nada disso — ela só garante que a PAUSED **pode** ser observada
    quando alguém pedir.

---

## 9-bis. Revisão focal adversarial — o que ela derrubou

Uma única revisão adversarial interna (read-only, sem editar nada) atacou a
entrega tentando **refutá-la**. Ela devolveu 9 achados confirmados; **todos os
reproduzíveis foram corrigidos** nesta mesma lane, com contraprova nova para
cada um. Vale registrar os que derrubaram afirmações minhas, não só código:

| # | Achado | Desfecho |
|---|---|---|
| C1 | Sonda cega produzia `vazio_confirmado` **byte a byte idêntico** a um vazio observado — mesmo `payload_sha256`, mesma `chave_idempotencia`. A afirmação de que "a família falha alto em seguida" era falsa: são recursos diferentes | **Corrigido.** Retrato da sonda no payload + `test_sonda_cega_nao_produz_vazio_indistinguivel_de_vazio_observado` |
| C2 | Repetir o one-shot no mesmo bucket depois da campanha mudar descarta a leitura nova em silêncio; e o dublê guardava o documento descartado, então um teste afirmava conteúdo que nunca chegaria ao banco | **Corrigido.** Dublê fiel à RPC (`enviados` × `documentos`) + `test_leitura_nova_no_mesmo_bucket_e_descartada_e_isso_esta_provado` + §6 reescrita |
| C3 | Canal `UNKNOWN`/`UNSPECIFIED` — que significam "a conta não disse" — virava `NAO_SUPORTADO`: ignorância como conclusão de domínio, com quantidade nula e sem erro | **Corrigido.** Fail-closed + `test_canal_desconhecido_nao_vira_nao_suportado` |
| C4 | `.lower()` no `volc_campaign_id` contra PK case-sensitive: id em caixa alta daria zero linhas e a resposta seria "nenhuma campanha no inventário" | **Corrigido.** Caixa preservada, regex igual ao CHECK do banco |
| C5 | `test_seis_estados…` provava `parcial` com `vistos.add("parcial")` disfarçado; `_forecast` e `_recomendacoes_geradas` **nunca executavam** (coverage: `354-378`, `419-498` ausentes) | **Corrigido.** PARCIAL vem do `_forecast` real; `coletor.py` de ~0% nesses trechos para **91%** no arquivo |
| C6 | O teste de "não divergiu da saúde" travava consistência, não correção — as duas implementações podiam estar erradas juntas, e estavam (C4) | **Corrigido.** Trocado por teste que extrai o CHECK da migration |
| C7 | "read-only de ponta a ponta" só cobria `modo=frequente`; as famílias que chamam `RecommendationService`/`KeywordPlanIdeaService` só existem em `completa`, o **default do CLI** | **Corrigido.** `test_modo_completa_e_read_only_com_lista_branca_de_superficie` |
| C8 | As provas de "zero mutação" eram grep de substring, deriváveis por concatenação | **Corrigido parcialmente + reclassificado.** Lista branca de superfície virou a prova; o grep foi rebaixado a defesa em profundidade e o handoff parou de citá-lo como prova (§8) |
| C9 | O código e o handoff afirmavam "a agenda é do n8n"; o repo versiona timers **systemd**, e a escolha é justamente o que falta em P09-T14. O teste de scheduler era grep e reprovava o próprio comentário | **Corrigido.** Texto corrigido em três módulos + teste de scheduler agora estrutural (AST) |

Três hipóteses ficaram **abertas** e estão declaradas em vez de fechadas:

- **H1 — canário recém-criado pode ser inalcançável.** `trafego_inventario_campanha`
  traz `canal` por LEFT JOIN com o espelho; campanha declarada pela porta de
  criação e ainda não varrida teria `canal = NULL` → o alvo falha fechado. É
  fail-closed, mas é exatamente a janela que a lane quer atacar. Verificação:
  `SELECT c.volc_campaign_id FROM trafego_campanha c LEFT JOIN trafego_campanha_espelho e USING (volc_campaign_id) WHERE e.canal IS NULL;`
- **H2 — `estado_externo` não é observável no banco.** Ele viaja no retorno do
  comando, não no recibo persistido. Um analista lendo
  `trafego_google_inteligencia_coleta` não distingue coleta de PAUSED de coleta
  de ENABLED. Depende do consumidor (o dashboard dos seis estados) para virar
  achado ou não.
- **H3 — a inferência "zero linhas ⇒ não veiculou"** só pode ser confirmada numa
  execução real contra a conta.

A revisão **não conseguiu refutar**: a preservação byte a byte da coleta contínua
(`_sondar_veiculacao` chamada 0 vezes, nenhum payload com `origem`, mesmas 11
consultas, mesmos estados — hoje travado por
`test_coleta_continua_nao_ganhou_sonda_nem_marca_de_origem`); o fuzz de
identidade com 17 entradas hostis; a ausência de qualquer caminho de escrita
novo; e o uso correto de `campaign.start_date_time` em v25.

---

## 10. Curation handoff — para o integrador aplicar UMA vez

Esta lane **não** editou `ROADMAP-VIVO.json`, **não** editou
`curadoria-operacional.json`, **não** reconstruiu o grafo e **não** fez merge.
Abaixo o delta proposto, com a evidência já redigida.

### 10.1 Roadmap — `volc-os-workbook/ROADMAP-VIVO.json`

**Tarefa `P09-T14` — manter `status: "partial"`.** Não promover.

Sugestão de acréscimo ao campo `proof` (o texto atual permanece; isto vem depois
do trecho de 01/09/2026):

> 01/09/2026, lane `hermes-p09-t14-paused-observability-v1` (branch não
> integrada, nada executado contra conta ou banco reais): a lacuna do caminho
> one-shot foi fechada em código. `executar_alvo` coleta uma campanha nomeada
> por identidade canônica completa (conta + `volc_campaign_id` + `campaign_id`)
> em qualquer estado externo, inclusive PAUSED, reaproveitando famílias, bucket,
> persistência e recibos da coleta contínua — repetir o comando devolve o mesmo
> recibo. `campanhas_search_ativas` permanece com `estado_externo=eq.ENABLED` e
> quatro contraprovas independentes atestam que a agenda contínua não foi
> ampliada. `NAO_SUPORTADO`, que o modelo previa e o coletor nunca emitia, passa
> a ser emitido fora de SEARCH; e a ausência de simulação em campanha nova vira
> `INELEGIVEL` apenas quando demonstrável — a janela precisa cobrir a vida
> inteira da campanha e não ter veiculação —, mantendo `VAZIO_CONFIRMADO` para
> campanha antiga. Identidade malformada, campanha inexistente, conta divergente
> e ID externo trocado falham fechado antes da primeira chamada ao Google,
> inclusive quando a persistência mente, porque o coletor reconfere por conta
> própria. Uma revisão adversarial interna derrubou nove pontos e todos os
> reproduzíveis foram corrigidos na mesma lane — o mais grave era uma sonda cega
> produzindo `vazio_confirmado` byte a byte idêntico a um vazio observado, o que
> apagava em silêncio a distinção `INELEGIVEL`×`VAZIO_CONFIRMADO` que é a entrega
> principal; hoje o retrato da sonda viaja no recibo. Também: canal
> `UNKNOWN`/`UNSPECIFIED` deixou de virar `NAO_SUPORTADO` (ignorância não é
> conclusão), `volc_campaign_id` parou de ser rebaixado para minúsculo contra uma
> PK case-sensitive, e `PARCIAL` passou a ser provado pelo `_forecast` real em vez
> de um documento montado à mão. 43 contraprovas novas, 96 verdes nas duas
> famílias, 2515 na suíte completa, `coletor.py` a 91% de cobertura, zero mutação
> provada por lista branca de superfície exercitada no modo default. SEGUE
> PARTIAL: nenhuma
> execução real, nenhum recibo no banco, e a decisão de autoridade única de
> agenda (n8n × worker), heartbeat, alerta e dashboard dos seis estados continua
> aberta.

### 10.2 Curadoria — `docs/volc-os-graph/curadoria-operacional.json`

**Nó a atualizar: `concept:google_ads_collection_ledger`** (cluster
`measurement`). Manter `state: "partial"`. Acrescentar ao `evidence`:

> Em 01/09/2026 o ledger deixou de depender do estado externo da campanha para
> observá-la: existe caminho one-shot por identidade canônica explícita, que
> alcança campanha PAUSED sem ampliar a varredura contínua nem criar segunda
> agenda. Os seis estados passaram a ser todos emissíveis — `NAO_SUPORTADO`
> nunca havia saído do modelo. Em branch não integrada, sem execução real.

**Aresta nova proposta** (a lane não a criou):

```json
{
  "source": "concept:google_ads_collection_ledger",
  "target": "concept:search_paused_canary",
  "relation": "torna_observavel"
}
```

Justificativa: `concept:search_paused_canary` descreve um canário deliberadamente
PAUSED, e `concept:google_ads_collection_ledger` é o ledger que até agora não
conseguia enxergá-lo. A aresta registra que a dependência passou a existir.

**Nada a mudar em `concept:search_paused_canary`** — o estado dele depende de
mutate, recibo e reconciliação reais, que esta lane não tocou.

### 10.3 Grafo

Reconstruir **uma vez**, depois do merge, pelo pipeline oficial:

```bash
python3 scripts/atualizar_grafo_volc_os.py
python3 scripts/atualizar_grafo_volc_os.py --check
```

Nunca `graphify update .`. Citar no handoff final o resultado de frescor —
que esta lane, por não ter `graphify-out/` na worktree, não pôde produzir.

### 10.4 Próximo passo real (fora desta lane)

O comando que fecha a prova de produção, quando houver autorização e a
identidade real do canário:

```bash
# sob o MESMO lock da coleta contínua, enquanto a autoridade de agenda não for
# decidida — ver limitação 9
flock /run/lock/volc-google-intelligence.lock \
  python3 scripts/coletar_google_inteligencia.py \
    --modo completa \
    --customer-id <conta> \
    --volc-campaign-id <id interno> \
    --campaign-id <id externo>
```

É read-only e idempotente. Antes de rodar, conferir H1 (§9-bis): se o espelho da
campanha ainda não tiver `canal`, o alvo falha fechado — o que é correto, mas
significa esperar a varredura passar uma vez.

Depois disso, reconciliar os recibos gravados contra
`trafego_google_inteligencia_coleta` e só então revisitar o status de P09-T14.
