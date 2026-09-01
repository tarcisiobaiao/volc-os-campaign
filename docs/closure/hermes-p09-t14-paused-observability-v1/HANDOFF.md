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
sido a resposta errada. Ampliaria a agenda que o n8n comanda e gastaria cota da
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
| `backend/tests/test_google_inteligencia_persistente.py` | 30 contraprovas novas |

`git diff --stat c3c820b..HEAD` → **6 arquivos, 1316 inserções, 12 remoções.**

Commits atômicos: `55bd74c` (domínio + persistência) · `fa2b0f5` (coletor) ·
`5daebf5` (CLI) · `675fdf2` (contraprovas).

Nenhum arquivo fora do ownership foi tocado. `backend/app/**`, `src/**`,
`supabase/migrations/**`, `volc-os-workbook/ROADMAP-VIVO.json`,
`docs/volc-os-graph/**` e `graphify-out/**` permanecem intocados.

---

## 3. Comandos e contagens de gates

```bash
# suíte das duas famílias sob ownership
python3 -m pytest backend/tests/test_google_inteligencia_persistente.py \
                  backend/tests/test_google_inteligencia_saude.py -q
# 83 passed        (baseline no commit base: 53 passed → +30 contraprovas)

# suíte completa python
python3 -m pytest backend/tests volc_ads -q \
  --ignore=backend/tests/test_admin_fields_separation.py \
  --ignore=backend/tests/test_docx_intro_closing.py
# 2501 passed, 20 failed, 98 skipped

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

Execução hermética com a identidade nomeada do canário (`modo=completa`), com
protos Google Ads v25 reais e zero rede:

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
  "veiculou_na_janela": false,
  "volc_campaign_id": "a7f1c0de-0000-4000-8000-000000000001",
  "total": 4
}
  DIAGNOSTICO_ENTREGA        com_dados          coleta-001
  SIMULACOES_CAMPANHA        inelegivel         coleta-002
  RECOMENDACOES_GERADAS      inelegivel         coleta-003
  FORECAST_KEYWORDS          inelegivel         coleta-004
```

O recibo carrega as **duas** identidades (`campaign_id` e `volc_campaign_id`) e a
marca de procedência `origem: alvo_explicito` no payload.

Contraprovas: `test_campanha_pausada_explicita_entra_na_coleta`,
`test_alvo_e_read_only_de_ponta_a_ponta`.

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

`test_caminho_do_alvo_nao_cria_segundo_scheduler` varre `alvo.py`, `coletor.py`,
`persistencia.py` e o CLI procurando `while true`, `time.sleep`, `threading`,
`schedule.every`, `crontab`, `apscheduler`, `asyncio.sleep`, `systemd`,
`signal.alarm`. Nenhum aparece. A autoridade de frequência continua sendo o n8n;
o alvo é invocação humana ou de um caller já existente.

---

## 6. Prova de idempotência

`test_retry_do_alvo_e_idempotente` roda `executar_alvo` **duas vezes** e confere:

- as chaves de idempotência da segunda rodada são **idênticas** às da primeira;
- os `coleta_id` devolvidos são os mesmos;
- o número de recibos distintos é igual ao número de famílias.

Medido na execução nominal do §4: **8 documentos enviados, 4 recibos distintos.**

A procedência (`origem`) mora no **payload**, nunca na chave de idempotência —
o recibo diz de onde veio sem que repetir a coleta crie outro.

E o inverso continua valendo: `test_falha_e_sucesso_do_mesmo_alvo_nao_se_apagam`
prova que uma falha e um retry bem-sucedido no mesmo bucket geram chaves
distintas, então a falha antiga não esconde o sucesso posterior.

---

## 7. Prova dos seis estados semânticos

`test_seis_estados_semanticos_permanecem_distintos` acumula os estados de quatro
cenários e exige o conjunto completo. Cada estado tem, além disso, contraprova
própria:

| Estado | Contraprova | O fato que ele representa |
|---|---|---|
| `com_dados` | `test_campanha_pausada_explicita_entra_na_coleta` | a API respondeu com itens |
| `vazio_confirmado` | `test_campanha_antiga_sem_simulacao_permanece_vazio_confirmado` | perguntamos, não havia nada, `quantidade = 0` |
| `parcial` | `test_falha_de_uma_familia_nao_contamina_a_outra` + modelo | parte respondeu, parte falhou |
| `inelegivel` | `test_ausencia_de_simulacao_em_campanha_nova_e_inelegivel` | a pergunta não se aplica a esta campanha |
| `nao_suportado` | `test_familia_de_plano_de_palavras_fora_de_search_e_nao_suportada` | a pergunta não existe neste canal |
| `falhou` | `test_erro_de_rede_vira_falhou_e_nunca_vazio` | não sabemos; `quantidade = None`, código e classe presentes |

### Os três pares que mais se confundem, separados com prova

- **`inelegivel` vs `vazio_confirmado`.** Campanha nova sem simulação →
  `inelegivel`. Campanha antiga sem simulação → `vazio_confirmado`. O rebaixamento
  só acontece quando é **demonstrável**: a janela precisa cobrir a vida inteira da
  campanha e não ter veiculação. Começou antes da janela → não se afirma nada.
  Doutrina: `docs/architecture/evidence/GOOGLE-ADS-DOCS-2026-09-01.md` §4.
- **`inelegivel` vs `nao_suportado`.** Search sem keywords habilitadas →
  `inelegivel` (`test_search_sem_keywords_habilitadas_e_inelegivel_nao_nao_suportado`).
  PMax → `nao_suportado`, e sem gastar chamada.
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
3. **Varredura de fonte de todo o pacote** —
   `test_pacote_de_inteligencia_nao_contem_mutacao_google` varre os **cinco**
   arquivos de `volc_ads/inteligencia_google/` mais o CLI procurando `.mutate_`,
   `apply_recommendation`, `dismiss_recommendation`, `mutate_operation` e
   `forge_permitir_escrita=1`. (O teste anterior olhava só `coletor.py`.)
4. **Prova em execução, não só em texto** — o dublê do Google Ads registra em
   `atributos_desconhecidos` **toda** superfície fora das três previstas. Na
   execução nominal:
   ```
   servicos google tocados: ['GoogleAdsService']
   tipos google pedidos:    []
   atributos desconhecidos: []
   ```
   Um `.mutate` hipotético ficaria gravado e levantaria `AttributeError`, em vez
   de passar em silêncio.

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
5. **`except Exception` na sonda é deliberado e estreito.** Se a sonda não puder
   rodar, ela devolve "não sei" e **nada é rebaixado**; quem falha alto é a
   consulta da própria família, que roda em seguida e vira `FALHOU` pelo caminho
   normal. A sonda nunca pode transformar falha em ausência.
6. **`NAO_SUPORTADO` só é emitido no caminho one-shot.** A varredura contínua só
   alcança SEARCH, então lá o estado nunca se aplicaria — mas isso significa que
   o dashboard só verá esse estado quando alguém coletar um alvo não-SEARCH.
7. **Colisão de bucket entre os dois caminhos.** Se a coleta contínua e o
   one-shot rodarem na mesma campanha, no mesmo bucket e com o mesmo desfecho, a
   chave de idempotência é a mesma e o segundo recibo é deduplicado — inclusive
   o `origem` do payload. É o comportamento correto (não duplicar observação),
   mas significa que a marca de procedência pode não aparecer. Para uma PAUSED
   não acontece, porque a contínua nunca a alcança.
8. **Duplicação deliberada de normalização** entre `alvo.py` e `saude.py`.
   Unificar exigiria mexer em `saude.py` e suas 45 provas, misturando
   reorganização estrutural com mudança funcional no mesmo lote — o que o
   protocolo do projeto proíbe. Em vez disso,
   `test_normalizacao_de_identidade_nao_divergiu_da_saude` trava as duas
   implementações juntas: se divergirem, a suíte quebra.
9. **O Mapa Vivo não pôde ser consultado nesta worktree.**
   `python3 scripts/atualizar_grafo_volc_os.py --check` devolveu
   `{"current": false, "reason": "UPDATE_STATUS.json ausente"}` — `graphify-out/`
   e `.graphify-cache/` não existem aqui e não há `.venv-graphify`. A arqueologia
   foi feita pela curadoria humana (`docs/volc-os-graph/curadoria-operacional.json`,
   nível 1 da cadeia), pelo ROADMAP-VIVO, pelo código, pelo SQL e pela doutrina
   oficial. **Declarado, não contornado.**
10. **A decisão de autoridade de agenda continua pendente.** O critério de aceite
    de P09-T14 pede agenda única decidida (n8n **ou** worker), frequência ativa,
    heartbeat, alerta por atraso e dashboard mostrando os seis estados. Esta lane
    não decide nada disso — ela só garante que a PAUSED **pode** ser observada
    quando alguém pedir.

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
> própria. 30 contraprovas novas, 83 verdes nas duas famílias, 2501 na suíte
> completa, zero mutação em quatro camadas de prova. SEGUE PARTIAL: nenhuma
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
python3 scripts/coletar_google_inteligencia.py \
  --modo completa \
  --customer-id <conta> \
  --volc-campaign-id <id interno> \
  --campaign-id <id externo>
```

É read-only e idempotente. Depois disso, reconciliar os recibos gravados contra
`trafego_google_inteligencia_coleta` e só então revisitar o status de P09-T14.
