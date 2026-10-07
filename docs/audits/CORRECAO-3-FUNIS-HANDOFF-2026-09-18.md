# Handoff — correção cirúrgica dos 3 funis

> Atualizacao posterior: C6 e as duas pendencias factuais foram tratadas na
> rodada documentada em [CORRECAO-C6-E-PENDENCIAS-2026-09-18.md](CORRECAO-C6-E-PENDENCIAS-2026-09-18.md).
> Seis rascunhos corrigidos e relidos; todos os 15 continuam draft. O estado
> atual e DRAFT_WITH_GAPS por falta de preview autenticado, nao o veredito
> "sem erro factual conhecido". O restante abaixo preserva o relato anterior
> e suas evidencias; nao usar suas pendencias como estado atualizado.

**Estado**: C1–C5, C7 e C8 **aplicadas e verificadas** nos 11 posts que as continham.
C6 permanece **BLOQUEADA**. Nenhuma publicação. Custo de API paga: **US$ 0,00**.
**Sem credenciais neste documento.**

---

## 1. O que está feito e verificado

### 1.1 Post 2306 (LP SENAC) — aviso editorial reposto · **CORRIGIDO_VERIFICADO** (rodada anterior)

O operador confirmou a autoria da edição no Elementor e autorizou preservá-la. O container
`volc-editorial-notice` foi extraído do artefato determinístico do run e **prepended** ao
`_elementor_data` atual; o template antigo **não** foi restaurado.

| | Antes | Depois |
|---|---|---|
| `modified_gmt` | 2026-09-18T00:19:29 | 2026-09-18T00:36:23 |
| `_elementor_data` chars | 19.914 | 21.498 |
| sha256 (`_elementor_data`) | `82f4f10eedfe7e39…` | `2a9373f6f260998d…` |
| `volc-editorial-notice` | ausente | **presente, primeiro container** |
| copy do usuário ("Cursos Senac em 2026") | presente | **preservada** |

**Esta rodada não tocou no 2306.** Estado reconferido em 2026-09-18T00:59: `modified_gmt` e sha256
idênticos aos acima. A edição humana e o aviso seguem intactos.

### 1.2 C1–C5, C7 e C8 — **36 edições em 11 posts, todas verificadas**

Método por post: leitura REST `context=edit` → conferência de `modified_gmt` **e** sha256 do campo
contra o snapshot desta rodada → substituição de âncora literal (exigindo exatamente 1 ocorrência)
→ gate `editorial_safety.html_issues` → `json.loads` no `_elementor_data` das LPs → update só com
`status`, `template` (LPs) e o campo de conteúdo → **leitura de volta** conferindo identidade byte a
byte, aviso, slug e status → espelho no artefato local do run.

| Post | # | Correções | modified_gmt |
|---|---|---|---|
| 2309 | 2 | C3 | 2026-09-18T00:58:10 |
| 2312 | 3 | C8 | 2026-09-18T00:58:16 |
| 2318 | 8 | C3 | 2026-09-18T00:58:21 |
| 2321 (LP) | 1 | C4 | 2026-09-18T00:58:39 |
| 2324 | 2 | C4 | 2026-09-18T00:58:45 |
| 2327 | 4 | C2, C4 | 2026-09-18T00:58:51 |
| 2330 | 8 | C4 | 2026-09-18T00:58:57 |
| 2336 (LP) | 3 | C1, C7, C8 | 2026-09-18T00:59:15 |
| 2342 | 1 | C5 | 2026-09-18T00:59:21 |
| 2345 | 2 | C1 | 2026-09-18T00:59:27 |
| 2348 | 2 | C8 | 2026-09-18T00:59:33 |

**O que cada correção passou a dizer**

- **C1 (2336, 2345)** — a FAQ da LP passa a responder **"Não"** ao login Gov.br, descrevendo a tela
  real (identificação ou e-mail, senha, criar conta) e citando os Termos de Uso 2.1. No 2345, além
  da linha da tabela, foi corrigido o parágrafo que sobrevivia e que implicava integração federal
  opcional ("não exige a integração obrigatória").
- **C2 (2327)** — a etapa "Valide os requisitos no cadastro federal" e o link `gov.br/mec` saíram.
  O passo agora manda conferir escolaridade e documentos no edital do DR, com o exemplo sustentado
  do SENAI-RJ (pré-inscrição on-line + validação presencial obrigatória).
- **C3 (2309, 2318)** — a regra de sufixo saiu das duas páginas. O texto passa a mostrar que o
  formato varia (`psg.ce.senac.br`, `portal.sc.senac.br`, `senacrs.com.br` fora do `.senac.br`) e o
  contraexemplo `senacrj.com.br`, que **não** é do Senac RJ. A referência passa a ser o registro por
  Departamento Regional no portal nacional de transparência. No 2318 a correção precisou cobrir 8
  trechos: os 3 passos do bloco `wp:html`, os 2 parágrafos de abertura, o cenário "buscar" do widget,
  o passo de verificação do cenário "verificar" e o rodapé de atribuição do widget.
- **C4 (2321, 2324, 2327, 2330)** — todo número passou a ser exemplo com dono. Renda: 2 SM no termo
  de bolsas do SENAI-SP **e** 1,5 SM no edital de técnico gratuito do SENAI-RJ. Idade: 14 anos na
  data de início em SP (sem idade máxima), 16 anos em PE, 14–24 incompletos no PR. Prova: as 60
  questões passaram a ser identificadas como do técnico semipresencial do SENAI-SP. **As datas
  15/09–29/09/2026 foram removidas** (ver §3). "Não há segunda chamada" virou remissão ao edital.
- **C5 (2342)** — o link para o técnico integrado do IFRS Canoas saiu; o passo de certificação
  aponta para a ficha da turma no catálogo público da plataforma.
- **C7 (2336)** — a FAQ separa ausência de limite de vagas (sustentada) de turmas e prazos: turmas
  2026B com conclusão até 31/01/2027 e categoria de turmas anteriores.
- **C8 (2312, 2336, 2348)** — 2312: "habilitação reconhecida pelo MEC" virou o que o MEC de fato
  define (eixo e carga horária, via Catálogo Nacional de Cursos Técnicos), e **as duas** ocorrências
  de "nota máxima" saíram, substituídas pelo credenciamento datado (Portaria MEC nº 166/2022).
  2348 e 2336: a "validade jurídica" e a "validade legal direta para horas complementares" deram
  lugar ao que a própria plataforma responde — ela **não garante** validade para progressão
  funcional ou licença capacitação e remete à chefia ou empresa.

### 1.3 Verificação de fechamento (2026-09-18T00:59, leitura REST dos 15)

| Item | Resultado |
|---|---|
| Status | **15/15 `draft`** |
| Slugs | **15/15 idênticos**, nenhum `-2` |
| Aviso editorial | **15/15 presentes** |
| `template` das LPs | **3/3 `elementor_canvas`** |
| Leitura de volta byte a byte | **11/11 idêntica ao enviado** |
| Âncoras antigas remanescentes | **0** |
| Substituições presentes 1× | **36/36** |
| Varredura de 15 padrões de defeito nos 15 posts | **0 residuais** |
| `editorial_safety.html_issues` | **0** nos 14 gerados pelo motor |
| Mídias novas | nenhuma |

## 2. Como o texto novo foi validado antes de ir para o ar

Antes de qualquer escrita, as 24 substituições da primeira versão passaram por um painel
adversarial (11 céticos, um por post, + 3 revisores de coerência por funil), instruídos a **refutar**.
O painel reprovou 8 dos 11 posts. Os achados reais foram acatados e geraram a versão aplicada, que
tem **36 edições** — 12 a mais que a primeira versão, quase todas trechos que sustentavam o mesmo
defeito e não estavam mapeados no handoff anterior:

- **2312**: "nota máxima" aparecia **duas** vezes; o mapeamento original pegava só a da FAQ.
- **2318**: a correção de um passo deixava os passos 1 e 2, o cenário "buscar" do widget e o rodapé
  ainda ensinando o redirecionador nacional.
- **2345**: o parágrafo acima da tabela mantinha o defeito C1 em prosa.
- **2336**: a LP afirmava "validade legal direta … para comprovação de horas complementares",
  contradizendo a correção do 2348.
- **2330**: "Fora desse período…" ficava órfã após a remoção das datas, e o parágrafo sobre
  desistência repetia a generalização.
- **2327**: o widget interativo usava 2 SM como corte.

Parte dos achados do painel era **falso positivo por lacuna do meu dossiê**, não defeito do texto —
o dossiê resumia o ledger e havia cortado trechos literais. Reconferidos ao vivo e registrados em
`<scratchpad>/correcao/EVIDENCIA.md` (adendo L1–L6):

- **L1** `sp.senai.br/termo-de-compromisso---curso-bolsa` (200): "a renda per capita deve ser igual
  ou menor que 2 (dois) salários mínimos federais" — **2 SM no SENAI-SP é fonte real**, o ledger só
  tinha 2 SM para o SENAC.
- **L2/L3** `sp.senai.br` (200): "60 questões de múltipla escolha" (20+20+20) na prova digital
  presencial do semipresencial; "Ter, no mínimo, **14 anos na data de início do curso**"; "Não há
  idade máxima".
- **L4** `aprendamais.mec.gov.br/login/index.php` (200): campos "Identificação ou e-mail" e "Senha",
  **nenhum botão Gov.br** — as 45 ocorrências de "gov.br" no HTML são o próprio domínio.
- **L5** `transparencia.senac.br/assets/settings/settings.json` (200): 28 registros; o do RS aponta
  para `senacrs.com.br`, **único fora do `.senac.br`**.

## 3. Achado novo desta rodada: datas sem fonte no 2330

O período **"15/09/2026 a 29/09/2026"**, que o 2330 apresentava como o ciclo vigente de inscrições
do SENAI, **não tem fonte alguma**. Varredura no `ledger-fontes.json`, no `ledger-derrubadas.json` e
no `pesquisa-bruta.json` não encontrou nenhuma data de inscrição do SENAI; as duas ocorrências de
`15/09/2026` na pesquisa são o *Last modified* de uma página do Aprenda Mais. Também não há fonte
para "não há possibilidade de realizar uma segunda chamada". Ambos foram removidos.

Isso é diferente dos outros achados do parecer: não é uma generalização indevida de uma fonte real,
é número inventado publicado como fato operacional datado. Vale registrar para a revisão do motor.

## 4. C6 — BLOQUEADA. Patch proposto, **não aplicado**

Diagnóstico inalterado e confirmado no código:

- `config.yaml → routing.SOLUTION_TERMINAL`: `forbidden_targets` inclui `external_official`;
  `required_targets: [cross_funnel]`; `cta_min/cta_max = 1`.
- `routing.py:bind_official_route` retorna cedo quando `is_terminal`.
- `validators/checks.py:official_link_density` isenta a terminal.
- `config/perfil.py:aplicar_perfil` sobrepõe apenas `site.*`, `wordpress.*`, `tema.*` e os tetos —
  **não** sobrepõe `routing`. Não existe override por run.

**Patch mínimo para o Codex avaliar (não aplicar sem decisão):**

1. `config.yaml`, `SOLUTION_TERMINAL`: mover `external_official` de `forbidden_targets` para
   `allowed_targets`; acrescentar a `required_targets`; manter `cross_funnel` permitido mas não
   obrigatório; elevar `cta_max`.
2. `routing.py:bind_official_route`: remover a condição `or is_terminal` do early-return.
3. `validators/checks.py:official_link_density`: remover a isenção `ctx.get("is_terminal")`.
4. `prompts/redator_pages.jinja`, bloco `{% elif is_terminal %}`: trocar "só recircula cross-funnel"
   por "entregue o canal oficial primeiro; outra leitura, se houver, vem depois e claramente
   separada".
5. Testes que cobrem a regra atual e vão falhar: `test_route_validators.py`, `test_routing.py`,
   `test_gate_fail_closed.py`.

**Consequência desta rodada para C6**: a correção de C3 no 2318 (terminal do SENAC) foi escrita
**sem adicionar link externo oficial**, justamente para não criar a aresta `external_official` que o
contrato do motor proíbe na terminal. O leitor recebe o nome do portal de transparência em texto,
não um link. Enquanto C6 estiver bloqueada, a terminal do SENAC continua sem saída oficial clicável
— é a parte de R3/R6 que **não** foi resolvida.

## 5. Pendências abertas

1. **C6 bloqueada** por contrato do motor; patch em §4, não aplicado. Nada no engine foi alterado.
2. **Prova visual autenticada do Elementor**: pendente. Extensão do Chrome não conectada e o
   Application Password vale só para REST — não autentica o wp-admin. Rascunho devolve 404 anônimo.
   **Não publicar para testar**; usar os links de edição do índice privado.
3. **`post_content` do 2306 reprova o gate editorial** — 6× `svg`, 6× `path`, 1× shortcode. É efeito
   do salvamento de terceiro no Elementor, que gravou HTML renderizado num campo que antes tinha 0
   bytes; **pré-existente e não causado por esta rodada**. A LP renderiza pelo `_elementor_data`, não
   pelo `post_content`, então não há defeito visível — mas o gate do motor não aceita esse conteúdo.
   Decidir se limpa o `post_content` ou se o gate passa a ignorar LPs do Elementor.
4. **Card no Pautador**: não criado (rotas exigem JWT de sessão admin; `VOLC_SERVICE_KEY` ausente).
5. **Grafo**: `--check` → `current: false`; rebuild barrado pelo detector de segredos
   (`.env_webgo: jwt`, preexistente). **Não contornado, arquivo não lido.**
6. **Fora do escopo C1–C8, registrado pelo painel e não alterado**: no 2309, a linha "Consulta
   pública de certificados oficial" e o parágrafo sobre ferramentas de verificação do Senac SP não
   têm fonte no ledger (as entradas de validação pública de certificado são da Aprenda Mais). No
   2342, a tabela "20h→4 dias / 30h→5 dias / 40h→6 dias" é apresentada como regra do sistema, mas o
   ledger registra 4, 5, 6 e até 8 dias variando por curso.

## 6. Como aplicar (regras que continuam valendo)

- Reler cada post por REST (`context=edit`) e conferir `modified_gmt` **e sha256** imediatamente
  antes de cada update. Divergência inesperada = parar aquele objeto e reportar.
- Enviar só os campos autorizados: `status: "draft"`, `template` (nas LPs) e o campo de conteúdo ou
  `meta._elementor_data`. **Nunca** um snapshot inteiro.
- **LPs: edição pontual do `_elementor_data`, não re-render.** Foi o que esta rodada fez em 2321 e
  2336. Preserva imagem aprovada, aviso, template e IDs de widget, e o diff é provável byte a byte.
  O `lp_content.json` de origem é espelhado com a mesma substituição.
- Internas: edição pontual no HTML Gutenberg, espelhada no artefato local.
- **Armadilha do artefato**: o widget interativo (`section.vw-*`) e o bloco de imagem são injetados
  na publicação e **não existem** no `.gutenberg.html` do run; o remoto também converte emoji em
  entidades. Editar trecho de widget só é possível no remoto — o espelho local pula essas âncoras.
- Rodar `editorial_safety.html_issues`. **Não reduzir limiar para obter verde.**
- Nada de `run-volc` nem `resume --publish`. Update por ID.
- Depois de timeout, **ler de volta antes de repetir** — nunca reenviar às cegas.

⚠️ **Armadilha de ambiente**: o `.pth` do editable install do motor já parou de ser honrado nesta
máquina. Use `PYTHONPATH=<engine>/src` e o interpretador `<engine>/.venv/bin/python`.

## 7. Caminhos

| O quê | Onde |
|---|---|
| Perfil de execução | `funnelforge-migracao/engine/.perfil-run-creditoup-20260917/` |
| Artefatos dos runs | `…/engine/runs/{guia-cursos-senac-20260917-220001, guia-gratuidade-senai-20260917-230001, guia-aprenda-mais-mec-20260918-030001}/` |
| Manifesto original (**preservar**) | `…/entrega/manifesto-3-funis.json` |
| Manifesto desta rodada | `…/entrega/manifesto-correcao-aplicada-2026-09-18.json` |
| Ledger de fontes | `…/entrega/ledger-fontes.json` · `ledger-derrubadas.json` |
| Dossiê de evidência + adendo ao vivo | `<scratchpad>/correcao/EVIDENCIA.md` |
| Substituições aplicadas (âncora → texto) | `<scratchpad>/correcao/drafts.json` |
| Evidência por post (sha antes/depois) | `<scratchpad>/correcao/aplicado-<id>.json` |
| Snapshot pré-correção desta rodada | `<scratchpad>/base-20260918/` (15 JSONs + `_baseline.json`) |
| Aplicador (1 post por vez, ensaio + escrita) | `<scratchpad>/aplicar.py` |
| Índice privado (links de edição) | `…/entrega/INDICE-PRIVADO.md` |
| Parecer do Codex | `/Users/mac/Desktop/Rewrite-job-good-quality/REVISAO-3-FUNIS-CREDITOUP.md` |
| Credencial WP | perfil `0600` em diretório `0700` fora do repo — **não reproduzir caminho nem valor** |

Post IDs: SENAC `2306`(r) `2309 2312 2315 2318`(rec) · SENAI `2321`(r) `2324 2327 2330 2333`(rec) ·
MEC `2336`(r) `2339 2342 2345 2348`(rec).

## 8. Veredito

| Funil | Status | O que falta |
|---|---|---|
| SENAC | `DRAFT_SEM_ERRO_FACTUAL_CONHECIDO` | C6; preview autenticado; §5.3 e §5.6 |
| SENAI | `DRAFT_SEM_ERRO_FACTUAL_CONHECIDO` | C6; preview autenticado |
| MEC | `DRAFT_SEM_ERRO_FACTUAL_CONHECIDO` | C6; preview autenticado; §5.6 |

Os erros factuais apontados pelo parecer em C1–C5, C7 e C8 **não estão mais nos rascunhos**.
Nenhum funil está liberado para publicação: C6 segue bloqueada e a prova visual real continua
pendente. Os 15 continuam `draft`, com os mesmos IDs e slugs, e nenhuma mídia foi criada.
