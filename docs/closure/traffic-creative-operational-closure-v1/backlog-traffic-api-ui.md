# Backlog — traffic-api-ui

Dívida encontrada durante a entrega e **deliberadamente não fechada**, com o
motivo. Nada aqui bloqueia o que foi entregue; tudo aqui tem consumidor real e
custo se ficar.

---

## 1. Dois registros de canal defasados, e nenhum deles é meu

### 1.1 `volc_ads/campanha/perfil.py:297` — PMax declara ausência que deixou de existir

`PERFORMANCE_MAX` ainda diz `campos_operados=()`, `recursos_criativos=()` e
*"não há construtor de campanha para Performance Max — o engine levanta
exceção"*. `volc_ads/campanha/pmax.py` existe desde 01/09/2026 com `planejar()`
e `construir()`.

**Impacto medido:** o contrato dos canais teve de ler os papéis de asset de
`brief.PAPEIS_DE_ASSET_PMAX` em vez do registro. Ler do registro devolveria
*"este canal não declara recursos criativos próprios"* — falso, com a
autoridade de um registro.

**Onde está o desvio:** `backend/app/trafego/contrato_canais.py:_assets_de_pmax`,
com o motivo escrito no docstring.

**Dono:** channel-builders. Não toquei porque o arquivo é dele e porque
`perfil.PERFIS` participa da guarda de import de `volc_ads/subir.py`.

### 1.2 `backend/app/trafego/dominio.py:161` — `CANAIS_COM_CONSTRUTOR = {"SEARCH"}`

Defasado desde 26/08/2026, quando Display ganhou construtor. O comentário acima
dele ainda descreve a medição de 24/08.

**Por que não é urgente:** zero consumidores de produção. As únicas referências
são o próprio módulo e `backend/tests/test_trafego_dominio.py:119`, que fixa o
conjunto exato. A autoridade real de "quem sabe criar" é
`volc_ads/subir.py:CONSTRUTORES_POR_CANAL`, e `plataforma.py` já é comparado
com ela por teste.

**Por que ainda assim precisa sair:** é uma constante pública, com nome que
promete ser a resposta, e a primeira pessoa que a usar vai esconder Display.
Classificação: **duplicado comprovado** — remover, e ajustar o teste que a fixa.

---

## 2. O contrato dos canais não lê a conta, e isso tem um preço declarado

`GET /api/trafego/canais` nunca chama o Google. A consequência é que
`mensuracao.lida` é **sempre `false`** nessa rota: quem lê a conta é
`POST /provar`, e o cockpit não guarda essa leitura.

O contrato já aceita a leitura injetada (`contrato(..., prontidao=...)`) e há
prova dos dois ramos. O que falta é **persistir a última prontidão observada por
conta/canal** para o cockpit poder mostrá-la com data, em vez de dizer sempre
"não lida".

**Não é defeito, é fatia seguinte.** Mostrar "não lida" é honesto; mostrar uma
leitura velha sem data não seria.

---

## 3. A observabilidade de PMax chega ao cockpit sem coletor ligado

`backend/app/trafego/pmax_cockpit.py` projeta um `PMaxCampaignCoverageReport`
inteiro e devolve `NOT_COLLECTED` quando não recebe nenhum — que é sempre, hoje.

O que falta é o **coletor**: `PMaxObservabilityKernel.inspect_and_diagnose`
precisa de um snapshot GAQL, e ninguém o produz num caminho persistido. Ligar
isso no cockpit exigiria ou uma coleta viva (gasta quota a cada navegação, e foi
recusada por desenho) ou uma tabela de snapshot que ainda não existe.

**Fatia seguinte:** um job que colete e grave; o projetor já está pronto e
provado (`backend/tests/test_trafego_pmax_cockpit.py`, 17 provas).

---

## 4. A contagem do espelho tem teto, e o teto é um piso disfarçado

`contar_espelho_por_canal` conta até `TETO_DE_CONTAGEM = 500` por canal, porque
`SupabaseService.select` não expõe o `count=exact` do PostgREST e
`supabase_service.py` está fora do meu ownership.

Ao bater no teto, a resposta marca `contagem_truncada=true` e o número passa a
significar "ao menos isto" — a tela mostra `500+`. Correto, e mais caro que
precisa ser: uma linha em `SupabaseService` (`Prefer: count=exact` +
`Content-Range`) devolveria o total real com uma consulta menor.

---

## 5. `/criativos` ficou sem porta HTTP para o contrato novo

As cinco funções do contrato do motor criativo existem
(`backend/app/criativo/bancada/servico.py`: `receitas_locais`, `produzir_local`,
`estado_da_producao`, `ambiente_da_bancada`, `motores_disponiveis`) e **nenhuma
rota HTTP as alcança**. `backend/app/routers/criativos_execucao.py` só expõe a
bancada antiga.

Sem elas a tela não tem de onde ler `entrega.recusas` — e sem `recusas` ela diz
"aprovado" sobre um lote que a ponte descartou, que é o defeito nominalmente
proibido pela missão. Também não sabe se pode oferecer o botão de produzir
(`ambiente_da_bancada.pode_produzir`).

**Não invadi o arquivo:** ele é do dono do motor criativo, e a questão foi
levantada com o lead. O esboço das três rotas está no §6 do
`CONTRATO-CRIATIVO-PARA-UI.md`.

---

## 6. O que NÃO é dívida, e está registrado para ninguém "consertar"

- **`ativavel` fechado em todos os canais** não é bug. Não existe rota de
  ativação, a política declara `inclui_ativacao=False`, e os anúncios do canário
  estão em revisão. Três razões independentes, todas nomeadas.
- **`mensuracao.lida=false`** não é falha de leitura: é a declaração de que esta
  rota não gasta quota da conta para pintar um cockpit.
- **`campanhas_no_espelho: null`** não é zero. Trocar por `0` "para a tela ficar
  mais limpa" reintroduz exatamente a mentira que o contrato inteiro evita.
