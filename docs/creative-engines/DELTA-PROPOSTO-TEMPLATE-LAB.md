# Delta proposto para o Mapa Vivo — Laboratório de Templates do Estúdio Criativo

**Status:** proposta factual, **não aplicada**
**Data:** 28/08/2026
**Branch:** `feat/estudio-template-lab` — commits `bf7062f`, `870b9df`, `f6c7ff1`
**Worktree:** `/private/tmp/volc-template-lab`
**Autor:** delta agent (curador de rodada) — não edito curadoria, Roadmap nem grafo gerado.

## 0. Isto é a terceira camada, não a primeira — e há um conflito a resolver antes de aplicar

Já existe `docs/creative-engines/DELTA-PROPOSTO-ESTUDIO-C0-C1-C3.md`, proposto em
27–28/08/2026 e **ainda não aplicado** pelo integrador. Este documento não o repete
nem o descarta: acrescenta a evidência de uma terceira rodada (`f6c7ff1`) e **corrige
duas coisas nele antes que a aplicação em lote propague o erro**.

### 0.1 — A promoção de `concept:creative-engine-registry` para `implemented` estava prematura quando foi escrita

O adendo de 28/08 no delta anterior (`870b9df`, 14:03) afirma que "leitura runtime...
passou a existir". Conferido no diff: `870b9df` é um commit **só de doc** — nenhum
arquivo Python mudou. O módulo que efetivamente lê o banco (`backend/app/criativo/parque.py`,
`GET /api/criativos/parque`) só nasce em `f6c7ff1` (16:13), **duas horas e treze
minutos depois**. Na hora em que o delta anterior foi escrito, a leitura runtime
**não existia** — a frase era aspiracional, não factual.

Isso muda a recomendação: ver §3.1 abaixo. Recomendo manter `partial`, e não
`implemented`, mesmo agora que a leitura já existe de fato.

### 0.2 — Colisão de `id`: `concept:creative-job-contract` já existe, e é outra coisa

O delta anterior propõe `concept:creative-job-contract` como **nó novo**, estado
`implemented`, evidência `src/types/criativos.ts` + `v11_01`. Mas esse `id` **já
está ocupado** em `docs/volc-os-graph/curadoria-operacional.json`:

```json
{
  "id": "concept:creative-job-contract",
  "label": "Contrato de job criativo",
  "cluster": "production",
  "state": "partial",
  "summary": "Envelope versionado de briefing, brand pack, assets, destinos, variantes, gates, custo, aprovação e vínculo com campanha ou publicação.",
  "evidence": "O núcleo Asset/Procedencia/Exigencia/Violacao/Falha/Lote e a porta MotorDeCriativo foram implementados em volc_ads/criativo no commit 6eed77f. Briefing, brand pack, gates PRENSA, aprovação humana e vínculo posterior ainda não fecham o envelope completo."
}
```

Esse nó documenta o contrato **`volc_ads/criativo`** (o Protocol `MotorDeCriativo`,
`Asset`, `Procedencia`) — a Fronteira criativo→canal do domínio Ads/Display. O
delta anterior queria usar o mesmo `id` para o envelope **do Estúdio**
(`criativo_briefing` → `criativo_job` → `criativo_master`, 7 estados em
`src/types/criativos.ts`). São contratos parecidos de propósito e **diferentes de
fato** — o segundo não substitui nem versiona o primeiro, e aplicar a proposta
como está sobrescreveria a evidência do domínio Ads/Display com a evidência do
Estúdio sob o mesmo rótulo. Recomendo ao integrador: dar ao envelope do Estúdio um
`id` próprio (`concept:estudio-job-envelope`, por exemplo) antes de aplicar
qualquer coisa do delta anterior. Não decido o nome — só sinalizo a colisão.

## 1. Gate técnico desta rodada

| Gate | Resultado declarado | Onde consultar | Reproduzir |
|---|---|---|---|
| Backend (suíte completa) | 1592 passando | trailer de `f6c7ff1` | `cd backend && python -m pytest -q` |
| Backend (`criativos`) | 95/95 | trailer de `f6c7ff1`; `backend/tests/test_criativo_estudio.py`, `backend/tests/test_criativo_parque.py` (258 linhas, 14 funções `test_`) | `cd backend && python -m pytest tests/test_criativo_estudio.py tests/test_criativo_parque.py -q` |
| `tsc` | 77 erros, todos herdados, **zero em `criativos`** | trailer de `f6c7ff1`; herança já documentada em `CLAUDE.md` (76→77, mesma lista) | `npx tsc --noEmit -p tsconfig.app.json` |
| Build | ok | trailer de `f6c7ff1` | `npm run build` |
| Teste de catálogo endurecido, provado por mutação | de `assert substring solta` para comparação estruturada; troca deliberada de `4x5`↔`9x16` faz o teste NOVO falhar e o ANTIGO passar | `backend/tests/test_criativo_estudio.py` (ver G10 na Matriz) | inspeção do diff de `f6c7ff1` no arquivo |
| Front (`receita-do-laboratorio`) | 17 asserções (`it`/`test`) | `src/components/criativos/__tests__/receita-do-laboratorio.test.ts` | `npm test -- receita-do-laboratorio` |

⚠️ Os números de gate acima são **auto-reportados no trailer do commit**, não
re-executados por este agente nesta sessão (sem venv Python 3.11/3.12 disponível
na worktree no momento da checagem). Ficam como evidência **consultável e
reproduzível pelo dono**, não como fato reconferido por mim. Recomendo ao
integrador rodar os comandos da coluna 4 antes de aplicar qualquer promoção de
estado que dependa deles.

**Achados abertos (G1–G15, `docs/design/MATRIZ-ESTUDIO-LEGADO-SCHEMA-RUNTIME-FRONTEND.md`):**
nenhum é classificado como bloqueante para esta fatia — o próprio documento diz,
em §5: "Isso não bloqueia a Fase B, porque a fatia vertical pedida... não depende
do caminho de execução em produção." G4 (estrutural) é registrado como risco para
a **próxima** fase (execução em produção / v11_03), não como achado alto aberto
contra o que foi entregue agora. Por isso este handoff prossegue.

## 2. Delta de tarefa (Roadmap Vivo)

| id | status atual | status proposto | evidência |
|---|---|---|---|
| `P04-T05` | `partial` | **sem mudança** | Nenhum arquivo desta rodada toca `volc_ads/criativo`, `volc_ads/criativo_ponte.py` ou `backend/app/routers/trafego.py` — domínio do `proof` atual. `git diff --stat main...f6c7ff1` (ver `docs/design/RECONCILIACAO-ESTUDIO-2026-08-28.md §2`) lista 9+22 arquivos, nenhum nesse caminho. |
| `P11-T02` | `partial` | **sem mudança** | Meta Ads/Co-Piloto não aparece em nenhum arquivo tocado por `bf7062f`/`870b9df`/`f6c7ff1`. |
| `P16-T03` | `reserved` | **sem mudança** | Site Factory (logo/cores/tema→motores) não aparece em nenhum arquivo tocado. O Laboratório de Templates lê `criativo_skin`/`criativo_voz`/`criativo_formato`, não brand assets de site. |

**Observação sobre lacuna de Roadmap, não uma proposta de tarefa:** não existe
hoje, em `volc-os-workbook/ROADMAP-VIVO.json`, nenhuma iniciativa dedicada ao
Estúdio Criativo (schema `criativo_*`, backend `app/criativo`, páginas
`/criativos/*`). As três tarefas que a missão me pediu para checar pertencem a
outros domínios (Ads/Display, Meta Ads, Site Factory) e nenhuma delas é
movimentada por este trabalho. Registro isto para o dono decidir se quer abrir
uma iniciativa própria — não decido o texto, porque isso é edição de Roadmap e
está fora do meu envelope.

## 3. Delta de capability

### 3.1 `concept:creative-engine-registry` — recomendo manter `partial` (não aplicar a promoção do delta anterior como está)

| Campo | Valor |
|---|---|
| Estado atual (curadoria) | `partial` |
| Estado proposto pelo delta anterior | `implemented` — **não recomendo aplicar** |
| Estado proposto aqui | `partial`, com evidência revisada e ampliada |

Evidência a **acrescentar** (a anterior — manifesto + catálogo em memória do
commit `6eed77f` — continua verdadeira e não deve ser apagada):

> 28/08/2026 (`f6c7ff1`) — a leitura runtime que faltava agora existe:
> `GET /api/criativos/parque` (`backend/app/criativo/parque.py`) lê 9 tabelas em
> paralelo (motores, modos, formatos, finalidades, skins, vozes, gates,
> exigências de canal, tetos combinados), distingue tabela vazia (`[]`) de
> tabela que falhou (`null` + entrada em `naoLidas`), e expõe `divergencias`
> quando o banco declara algo que o executor não conhece (7 slots de formato no
> banco, 4 no executor — a diferença sai como dado, não como silêncio).
> `motor_id`/`modo_id`/`finalidade_id` deixam de nascer nulas: `Resolvedor`
> (`backend/app/criativo/parque.py`) traduz slug → uuid na criação do job.
> **Isto é resolução best-effort, não validação**: se o slug não bater com
> nenhuma linha do catálogo, o campo fica `None` silenciosamente — nenhum job é
> recusado, nenhuma UI é avisada. Não implementa a "escolha explícita entre
> modos" que o `concept:creative-production-modes` descreve; apenas amarra o
> texto livre já existente a uma FK, quando possível.
> **Adaptadores continuam 1 de 3**: só `gemini_imagem.py` implementa o Protocol
> `MotorDeCriativo`. PRENSA e `volc-factory` têm linha no catálogo
> (`criativo_motor`) e nenhum adaptador — `volc-factory` tem só uma leitura
> observacional (`video_observado.py`), que não é execução.
> **O catálogo continua triplicado, não unificado**: banco (`criativo_*`),
> `dominio.py` e `src/types/criativos.ts`/`criativosApi` seguem como três fontes.
> O teste que compara Python↔TypeScript foi endurecido nesta rodada e provado
> por mutação (G10 → mitigado nesse par), mas **nenhum teste compara o banco
> contra as outras duas** — a terceira cópia não tem guarda.

**Por que não promover:** o próprio resumo do conceito na curadoria inclui
"adaptadores" como parte do que "diz quem sabe fazer o quê". Com 1 adaptador
real de 3 motores catalogados e resolução best-effort sem validação, "quem sabe
fazer o quê" ainda não está garantido pelo sistema — está garantido só para o
caminho Gemini. `implemented` com ressalva por dentro é a mesma contradição que
o protocolo deste handoff pede para evitar.

### 3.2 `cap_creative_engines` — mantém `partial` (evidência nova)

Evidência a **acrescentar** (a anterior continua válida):

> 28/08/2026 (`f6c7ff1`) — o parque persistido em `v11_02` ganhou o primeiro
> consumidor HTTP (`GET /api/criativos/parque`) e o primeiro consumidor de
> produto (`/criativos/laboratorio`). O Laboratório compila uma `RenderRecipe` e
> valida contra `criativo_exigencia_de_canal`/`criativo_teto_combinado` reais —
> não contra fixture local (deliberado: `docs/design/SPEC-TEMPLATE-LAB.md §6`
> proíbe mockar o catálogo no bundle). **Não salva, e diz que não salva**: não
> há botão "Salvar" porque `criativo_template` (v11_03) está apenas planejada
> (`supabase/migrations/PLANO-v11_03.md`), não escrita como SQL, não aplicada.
> Custo estimado devolve `null` (não `0`) quando o motor não declara custo.
> **O que continua faltando, sem mudança desde o delta anterior**:
> `criativo_ponte` (Ads/Display) segue sem consumidor HTTP; o Display segue sem
> `validate_only`; 0 jobs e 0 projetos em produção
> (`docs/design/RECONCILIACAO-ESTUDIO-2026-08-28.md §3`); 0 buckets em
> `storage.buckets`; o executor é uma função serverless Vercel com
> `asyncio.create_task` fire-and-forget (`backend/app/criativo/execucao.py:275`,
> `backend/vercel.json`) — um modelo de execução que o próprio ADR desta rodada
> chama de incompatível com produção durável de mídia
> (`docs/architecture/ADR-REMOTION-RUNTIME-STORAGE.md`, Decisão 5).

### 3.3 `cap_asset_vault` — sem mudança nesta rodada

Nenhum arquivo desta rodada toca `docs/design/*cofre*` ou rotas
`/settings/cofre-ativos`. A evidência já registrada pelo delta anterior
(`criativo_motor.cofre_asset_id` costurando com os dois ativos
`creative_engine`) continua válida e não precisa de acréscimo.

### 3.4 Nós fora do escopo desta rodada — sem mudança, com o motivo

| id | por que não muda |
|---|---|
| `system:motor-imagem-volc` | Evidência é sobre `docs/creative-engines/snapshots/motor-imagem-2026-08-26.json` e a raiz `/Users/mac/volc-factory`. Nenhum arquivo desta rodada altera esse snapshot ou a fábrica externa. |
| `system:motor-video-volc` | Mesma razão — evidência é o snapshot de 26/08 e a fábrica externa. O ADR desta rodada (`ADR-REMOTION-RUNTIME-STORAGE.md`) **fala sobre** essa fábrica (versão do Remotion, executor) mas não a modifica; ver nó novo proposto em §4, ligado por aresta `documenta`. |
| `system:volc-creative-port` | Evidência é `volc_ads/criativo` no commit `6eed77f`/`db39f0b`. `gemini_imagem.py` já implementava esse Protocol **antes** desta rodada (documentado no delta anterior, 27/08). Esta rodada só adiciona `self.slug` ao motor — um atributo interno ao Estúdio, não ao Protocol da porta. |
| `concept:creative-production-modes` | Descreve escolha explícita de modo por job no runtime. O `Resolvedor.modo()` desta rodada só traduz um slug já fixo para FK — não implementa escolha nem validação. Ver ressalva em §3.1. |
| `concept:asset_lineage` | Domínio é `campanha.brief.Linhagem` e `subir.py` (Ads/Display). O Estúdio tem seu próprio modelo de procedência (`criativo_master`, proposto como `concept:asset-provenance` no delta anterior) — não é o mesmo conceito e não deve ganhar a mesma evidência. |
| `concept:creative_channel_boundary` | Domínio é `volc_ads/criativo_ponte.py`. O validador do Laboratório usa `criativo_exigencia_de_canal` — schema diferente, código diferente, sem import cruzado confirmado nesta rodada. |
| `doc:creative-service-adr` | Documenta `concept:creative-engine-registry` via `ADR-001-SERVICO-CRIATIVO-VOLC.md`, que não foi tocado. O ADR novo desta rodada é outro documento (§4) e não substitui este. |

## 4. Nós novos propostos

| id | rótulo | cluster | estado | evidência |
|---|---|---|---|---|
| `doc:adr-remotion-runtime-storage` | ADR — Remotion, runtime de render e storage do Estúdio | `platform` | — (documento; estado do próprio ADR é "proposto", decisão do dono) | `docs/architecture/ADR-REMOTION-RUNTIME-STORAGE.md`. Mede Remotion instalado 4.0.479 vs. latest 4.0.518; MCP hospedado desliga ≥31/08/2026; `@remotion/rough-notation` exige 4.0.490 (fábrica está abaixo); recomenda executor em Vercel Sandbox/Cloud Run Job e proíbe worker na caixa do Supabase (`ubuntu-4gb-ash-1`, mesma que roda o Postgres de produção). |
| `doc:spec-template-lab` | SPEC — Laboratório de Templates | `production` | — (documento; especificação, fatia vertical implementa nível 1) | `docs/design/SPEC-TEMPLATE-LAB.md`. Declara 18 contratos tipados, dos quais 7 já têm tabela em produção e 11 dependem de `v11_03` (não aplicada); marca explicitamente "onde não há consumidor, o contrato não existe". |
| `doc:matriz-estudio-legado-schema-runtime-frontend` | Matriz legado × schema × runtime × frontend | `production` | — (documento) | `docs/design/MATRIZ-ESTUDIO-LEGADO-SCHEMA-RUNTIME-FRONTEND.md`. Catalogou G1–G15; base factual de §3 e §4 deste delta. |
| `doc:plano-v11-03` | Plano da `v11_03` (templates, perfis, trava de finalidade) | `production` | — (documento; estado do plano é "PLANEJADA, NÃO ESCRITA COMO SQL, NÃO APLICADA") | `supabase/migrations/PLANO-v11_03.md`. Descreve 6 tabelas novas e a trava que falta em `criativo_entrega_autorizada` (finalidade da aprovação ≠ finalidade do pacote — "o defeito de negócio mais caro desta área"). |
| `defeito:executor-serverless-fire-and-forget` | Executor de criativo é fire-and-forget dentro de função serverless | `platform` | `open` | `backend/vercel.json` (função Python na Vercel) + `backend/app/criativo/execucao.py:275` (`asyncio.create_task(self._executar_protegido(job_id))`, com comentário próprio no código sobre referência fraca de task). A doc oficial do Remotion limita função Vercel a 800 s e não a oferece como executor (`ADR-REMOTION-RUNTIME-STORAGE.md`, Decisão 5). Classificado como **estrutural** na Matriz (G4), mas explicitamente **não bloqueante** para a fatia entregue (Matriz §5). |
| `risco:remotion-licenca-e-versao` | Licença Remotion (Free ≤3 pessoas) e defasagem de versão (4.0.479 vs. exigida 4.0.490+) | `platform` | `open` | `ADR-REMOTION-RUNTIME-STORAGE.md`, "Riscos que o ADR carrega para a decisão do dono", itens 1 e 3. Free License cobre organização até 3 pessoas; preço acima disso **não confirmado** (pricing por componente não devolveu valor). `@remotion/*` publica em lockstep — instalação parcial sem lock mistura versões. |

## 5. Arestas novas propostas

```
doc:adr-remotion-runtime-storage       --documenta-->     system:motor-video-volc
doc:spec-template-lab                  --documenta-->     cap_creative_engines
doc:matriz-estudio-legado-schema-runtime-frontend --documenta--> cap_creative_engines
doc:plano-v11-03                       --planeja-->        concept:creative-engine-registry
defeito:executor-serverless-fire-and-forget --bloqueia--> cap_creative_engines
risco:remotion-licenca-e-versao        --ameaca-->        system:motor-video-volc
```

**Arestas que dependo do delta anterior para poder propor, e por quê não as
proponho eu mesmo agora:** o delta anterior sugere `cap_estudio_criativo` como
nó novo (ainda não aplicado). Se/quando esse nó nascer, faz sentido que
`doc:spec-template-lab` e `doc:matriz-...` apontem para ele em vez de
(ou além de) `cap_creative_engines` — mas proponho a versão que funciona **hoje**,
contra o grafo como ele existe agora, para não empilhar uma aresta sobre um nó
hipotético.

`concept:creative-production-modes`, `concept:asset_lineage` e
`concept:creative_channel_boundary` **não** ganham aresta nova — ver §3.4.

## 6. O que este delta NÃO propõe mudar, e por quê

- **Nenhuma capability sobe para `implemented`.** `cap_creative_engines` continua
  `partial`; a recomendação para `concept:creative-engine-registry` é permanecer
  `partial` (revertendo a intenção do delta anterior — ver §0.1 e §3.1).
- **`cap_asset_vault` não recebe evidência nova**: nada nesta rodada toca o Cofre.
- **`P04-T05`, `P11-T02`, `P16-T03` não mudam de estado nem de prova.** Pertencem
  a subsistemas que esta rodada não tocou (Ads/Display, Meta Ads, Site Factory).
- **Nenhum job real, nenhuma peça produzida, nenhum custo medido.** 0 jobs, 0
  projetos, 0 buckets — números reconferidos em
  `docs/design/RECONCILIACAO-ESTUDIO-2026-08-28.md §3` no dia de hoje.
- **`concept:creative-production-modes` não é promovido** — o Resolvedor traduz
  slug para FK; não implementa escolha nem validação de modo por job.
- **Nenhum adaptador de motor além do Gemini é registrado como funcional.**
  PRENSA e `volc-factory` têm linha de catálogo, não execução.
- **O bucket de storage e o modelo de execução não são tocados por este delta.**
  Ambos são decisão do dono, registrados como risco/defeito (§4), não como fato
  resolvido.
- **A `v11_03` não é registrada como aplicada nem como schema existente** —
  `PLANO-v11_03.md` é plano, sem `.sql` correspondente, de propósito.
- **G1–G15 (Matriz) não viram achado "alto aberto" que bloqueie este handoff** —
  a própria Matriz, em §5, diz que a fatia entregue não depende do caminho de
  execução em produção. G4 é registrado como risco estrutural para a próxima
  fase, não como pendência desta.

## 7. Ordem de aplicação

1. **Resolver a colisão de `id` do §0.2** antes de tocar em qualquer arquivo:
   decidir com o dono se `concept:creative-job-contract` fica com a evidência
   Ads/Display (como está hoje) e o envelope do Estúdio ganha `id` próprio, ou
   se as duas evidências devem ser fundidas — e só então aplicar o delta
   anterior (`DELTA-PROPOSTO-ESTUDIO-C0-C1-C3.md`).
2. **Aplicar o delta anterior** (nós, arestas e evidências de `bf7062f`/`870b9df`)
   com a correção do item 1.
3. **Aplicar este delta por cima**: a revisão de `concept:creative-engine-registry`
   para `partial` (§3.1, substitui a intenção "implemented" do passo 2), a
   evidência nova de `cap_creative_engines` (§3.2), os nós novos (§4) e as
   arestas novas (§5).
4. **Reconstruir o Mapa Vivo** — não com `--reuse-technical`, porque a camada de
   código mudou (`backend/app/criativo/parque.py` é novo,
   `backend/app/routers/criativos.py` mudou, `src/components/criativos/laboratorio/`
   é novo):
   ```bash
   python3 scripts/atualizar_grafo_volc_os.py
   python3 scripts/atualizar_grafo_volc_os.py --check
   ```
5. **Não editar `volc-os-workbook/ROADMAP-VIVO.json`** para `P04-T05`, `P11-T02`
   ou `P16-T03` — nenhuma prova nova os sustenta (§2). Se o dono quiser uma
   iniciativa própria para o Estúdio Criativo, isso é uma decisão de Roadmap
   separada, não uma consequência automática deste delta.
