# Verificação adversarial: inventário de regras e ledger

Frente A · Etapa 3 · 30/09/2026 · run `editorial-refactor-20260930`

Objetivo: tentar derrubar a etapa 2 (`inventario-regras.json`, `mapa-regras.md`) e a etapa 1 (`ledger.json`, `ledger.md`) com evidência nova. Reabri o código, busquei de novo as páginas oficiais e rodei trechos herméticos. As correções que se sustentaram já estão aplicadas nos dois JSON. Cada entrada alterada leva `corrigido_na_verificacao`, e o valor anterior fica em `antes_da_verificacao`.

## Resultado em uma tela

- **16 regras corrigidas e 3 acrescentadas.** O inventário passou de 168 para **171 regras**. As contagens foram recalculadas no JSON. Na tabela abaixo, "antes → depois" mostra a mudança.
- **Decisões que a verificação derrubou (4):**
  - ADS-15 (repetição dentro do mesmo asset): a política tem texto explícito e sem qualificador. Passa de C para **A**, de converter_em_aviso para **manter**.
  - ADS-08 (termo financeiro em portal informativo): no Brasil, a verificação de serviços financeiros é exigência explícita e é acionada pelo tema do anúncio. Passa de C para **B**, de converter_em_aviso para **contextualizar**.
  - BE-09: é o conteúdo de uma rota que o front-end consome, ou seja, um contrato de API. Passa de remover para **contextualizar**.
  - ADS-05: a classe D ("sem fundamento") estava errada. Passa a **B**. A decisão "remover" continua, porque as regras contextuais já cobrem o mesmo risco.
- **Classes que estavam erradas:**
  - FF-80 passa de A para **C**. A fonte citada é documentação de produto e o manifesto nunca chega à página publicada.
  - ADS-07, ADS-14 e ADS-43 passam de C para **B**. Existe texto da plataforma por trás do objetivo; o que é interno é só o limiar ou a lista.
- **Omissões no caminho ativo (3 regras novas):**
  - **FF-84**: a publicação da LP apaga em silêncio os emoji fora do BMP depois do portão final.
  - **ADS-75**: o prompt da Search apresenta listas internas por substring como "PROIBIDO … pela política oficial".
  - **ADS-76**: a regra `financeiro.emprestimo_pessoal.divulgacao` do spec.
- **Ledger:** as 189 citações `citacao_curta` foram conferidas no texto das páginas.
  - 179 casaram literalmente.
  - Outras 8 casaram depois de corrigir a codificação (latin-1 do planalto.gov.br) e o espaçamento do HTML.
  - As 2 restantes são marcadores ("não encontrado na política"), não citações.
  - Três entradas foram corrigidas (ADS-EDI-01, ADS-EDI-03, PUB-14) e duas entraram: **ADS-FIN-01** (Personal loans, 15188216) e **ADS-FIN-BR** (verificação financeira no Brasil, 15332527). Isso fecha a lacuna "política de serviços financeiros não consultada".
- **Caminho ativo:** todas as afirmações de status que conferi se sustentaram (lista na seção 5).
- **Deriva:** a implementação editou arquivos depois do build das 10:31. Os arquivos são `checks.py`, `base_factual.py` e 7 arquivos de `volc_ads`, e a lista está em `deriva_concorrente.apos_o_build`. As citações continuam ancoradas na versão lida.

| | antes | depois |
|---|---|---|
| total | 168 | 171 |
| manter / contextualizar / aviso / remover | 75 / 60 / 11 / 22 | 78 / 63 / 9 / 21 |
| A / B / C / D | 24 / 43 / 89 / 12 | 24 / 49 / 86 / 12 |

## Como verifiquei

- **Árvore verificada:** usei a versão lida (09:10–10:02), remontada em `scratchpad/fa-e3/lido`.
  - Os 17 arquivos de `deriva_concorrente` bateram com `sha256_lido`. As cópias vieram de `scratchpad/fa-e2/arvore`, `fa-e2/lido` e `b3a/orig`.
  - `volc_ads` bateu com as cópias "antes" do B3b (`b3b/antes`, sha256 idêntico em PROMPT.md, contrato.py, render.py, ciclo.py, encomendar.py, juiz_semantico.py e pautador_ponte.py).
  - Toda linha citada abaixo é dessa versão, salvo quando digo "worktree atual".
- **Busca de omissões:** varri as raízes do caminho ativo (motor, `volc_ads`, `backend/app`) com os padrões pedidos (`re.compile`, `re.sub`, `.replace(`, `PROIBID`, `EVITE`, `NUNCA`, morno, brando, calma, temperatura, blocklist, denylist, sensível, suaviz, neutraliz). Também procurei constantes de módulo com listas ou regex. Cada ocorrência foi comparada com todas as faixas `arquivo:linha` do inventário.
  - Deu 1.226 ocorrências, das quais 879 fora de qualquer faixa.
  - Tirei as de fora do escopo (motor de pautas, criativo, sincronização de tráfego, docs `.md` de auditoria) e os comentários. Li as restantes uma a uma.
- **Políticas:** baixei com `curl` a versão em inglês (`hl=en`) de cada URL do ledger e procurei a `citacao_curta` e as `fontes_adicionais` no texto da página. Nas regras em disputa usei também WebFetch. Todas as consultas são de 30/09/2026.
- **Execuções herméticas:** sem rede e sem LLM, usando o venv do repositório e a árvore lida.
  - `render._restricoes(spec, vertical='informativo', idioma='pt')` → prova de ADS-75.
  - A regex `_ASTRAL_RE` aplicada a um JSON com '1️⃣', '🎓' e '✅' → prova de FF-84.
  - Repetição dentro do item na copy da Frente C (`copy-v2/search-*.json`) → só 'Inscrição Passo a Passo', que é reduplicação idiomática e fica isenta.

## 1. Regras "remover" e "converter_em_aviso": alguma é exigência explícita ou contrato técnico?

Revisei as 33 regras. Cinco precisaram de correção.

| Regra | Antes | Depois | Evidência |
|---|---|---|---|
| **ADS-15** repetição de palavra dentro do mesmo asset (`volc_ads/policy/spec.json:257-337`) | C · converter_em_aviso | **A · manter** | A página 14848296 tem dois itens de "não permitido". A etapa 2 citou só o qualificado ("Non-standard, gimmicky, or unnecessary repetition…"). O outro não tem qualificador: *"Asset text that repeats words or phrases within the same asset or another asset in the same ad group, campaign, or account"*. Os exemplos oficiais são *"Repeating the advertiser name"* e *"Repeating the product name"*. Por isso os "exemplos legítimos bloqueados" da etapa 2 ('No Senac SP e no Senac RJ…', 'Cursos gratuitos e cursos pagos…') estão, literalmente, entre os proibidos. A checagem é objetiva e já isenta reduplicação idiomática. |
| **ADS-08** termo financeiro em vertical 'informativo' (`spec.json:480-512`) | C · converter_em_aviso | **B · contextualizar** | 15332527 (Brasil): *"Financial services providers and non-financial services providers are required to be verified by Google if you're running ads or targeting audiences who appear to be seeking certain financial services"*. A regra alcança afiliados e *"Educational programs or institutions that provide information on financial aid"*. Já o 15188216, citado pelo próprio spec, é a política de Personal loans: regula divulgação no destino e não traz lista de palavras. A exigência é acionada pelo **tema**, e a palavra é só o sinal. Decisão: bloquear quando o tema for produto financeiro e a conta não declarar verificação (habilitação, ADS-17/ADS-54). Nos demais casos, localizar e mandar à revisão. |
| **ADS-05** TRAVA 0 de `limites.yaml:88-110` | D · remover | **B · remover** | 'sem fundamento' era forte demais. 'empréstimo', 'antecipação', 'crédito aprovado' e 'dinheiro na conta' põem o anúncio no tema financeiro (ADS-FIN-BR). 'cura' e 'milagre' espelham *"\"Miracle cures\" for medical ailments"* (15936857). A remoção se mantém: a trava é global, vale por conceito e ignora o tema, e o risco real já é tratado com contexto em ADS-08, ADS-76 e na habilitação. |
| **BE-09** textos de `O_QUE_GOVERNA` (`backend/app/redator/configuracao.py:37-85`) | D · remover | **D · contextualizar** | É o corpo de `GET /api/publicacao/redator/configuracao` (`publicacao.py:1167`), consumido por `src/lib/pautadorApi.ts`, portanto contrato de API. A justificativa da própria etapa 2 dizia "corrigir a descrição". Remover quebraria a tela. |
| **ADS-07** "declarações não confiáveis" (`spec.json:425-453`) | C · converter_em_aviso | **B** · converter_em_aviso | A lista espelha exemplos explícitos ('miracle cures'; 'guaranteeing returns' em investimento), então a classe é B. A página também diz *"If you guarantee certain results, you're required to have a clear and easily accessible refund (money-back) policy"*: 'garantido' não é palavra vetada. A decisão se mantém. |

As demais se mantêm. Motivo por regra:

- **FF-01** (medo/escassez), **FF-12** (idioma), **FF-16** (cota de blocos), **FF-18** (força legal), **FF-36/37/42/44/52/53/54** (moldes de prompt), **ADS-35/37/38/39/41/50** (cotas e hedges): nenhuma fonte consultada exige o que elas exigem, e nenhuma é schema, limite de campo, URL, rastreio ou HTML.
- **FF-44**: o emoji de tecla '1️⃣' é BMP (U+FE0F e U+20E3), então sobrevive ao corte de FF-84. A decisão não muda.
- **FF-69**: depende de FF-18. Se FF-18 não virar aviso, tirar a instrução do widget aumenta as reprovações do widget em `critical_fact_grounding`, porque ele é validado com os fatos em `steps.py:2462-2464`.
- **ADS-43**: o objetivo (repetição entre assets) tem texto explícito, mas não tem limiar, e o RSA atual tem 'Cursos' em 5 de 8 títulos e está APPROVED (baseline). Passa a B, e converter em aviso continua certo.
- **FF-07, FF-29, FF-79, ADS-27, ADS-69** (legado): o status foi confirmado (seção 5). Nenhuma é contrato técnico que algo consuma, com uma ressalva. `REQUIRED_COMPLIANCE_ANCHORS` também é lida por texto em `backend/app/redator/configuracao.py:94-97`. Se a constante sumir, `_tupla_do_fonte` devolve lista vazia sem erro, então a remoção não quebra, mas a tela passa a mostrar a linha vazia. Isso deve ser feito junto com BE-09.

## 2. Regras "manter": são objetivamente verificáveis?

Li todas as "manter" cujo tipo menciona regex, lista, termo, token, rubrica ou regra quantitativa. Resultado:

- **Verificáveis e sem julgamento disfarçado:**
  - ADS-10/11/13 (caixa alta, pontuação e emoji): exemplos literais de 14847994 e 14848295, conferidos.
  - ADS-14: aviso.
  - FF-17 (número, R$, %, prazo ou lei → fato tipado com fonte): `checks.py:1472-1479` (`_CRITICAL_CLAIM_RE`). A comparação é por valor canônico (`_canon_numero`, `:1405-1444`) e por unidade (`_unidade_compativel`, `:1447`), não por sentido.
  - FF-27: CNPJ e placeholder.
  - FF-13, FF-14, FF-19, FF-22, FF-23, FF-71: HTML, URLs e proveniência.
  - ADS-54: default fechado por certificação declarada, determinístico.
- **ADS-66 (regex de marcadores): efeito corrigido, decisão mantida.** A etapa 2 registrou o efeito como "n/a", mas a contagem por regex vai para os prompts de reparo e de déficit como `verbo JÁ NO TETO` e `ano FALTAM 1` (`volc_ads/copy/ciclo.py:415-438`, `463-508`; `contrato.py:564-584`). Como `RX_EXEC` (`contrato.py:81-84`) conta 'Consulta'/'consulte' como verbo de execução, a regex decide o molde do substituto. Fica como medição. O uso como piso e teto segue ADS-38, que é converter em aviso.
- **FF-66 (juiz visual): natureza corrigida para misto.** O recibo sha256 e o schema são técnicos, mas os booleanos (`third_party_branding`, `implied_approval_or_outcome`, `anatomy_or_physics_error`, `topic_mismatch`) são julgamento de LLM (`editorial_safety.py:149-170`). A decisão continua certa, porque é juiz semântico declarado e não regex.
- **FF-80: não é exigência da plataforma e não tem efeito na página.** A etapa 2 o marcou como classe A, com base em PUB-14.
  - A página 9840201 é documentação de produto: *"The default frequency cap for web interstitials is 1 impression per 10 minutes"*, e o publisher pode reduzir. Não impõe teto nem fala de altura de slot.
  - O manifesto só vai para arquivos do run: `steps.py:2019-2022` grava `p<N>.admanifest.json`, e `:2083-2084` grava `p1.head.html` e o preview. O backend só o lê para exibir (`backend/app/redator/paginas.py:87`). `slot_hint_html` e `inject_ad_slots` não têm chamador (grep na árvore lida).
  - O HTML público de produção não tem `ff-ad-slot` nem `ff-ad-vignette` (backups de 30/09).
  - Classe passa a C; efeito: "nenhum na página publicada".
- **ADS-45: ressalva registrada, classe e decisão mantidas.** A parte "evitar 'saiba mais'" não é literal. 14848297 lista *"a generic call to action like \"click here\" that could apply to any ad"*, e 'saiba mais' é interpretação (B).
- **FF-25: locais e nota acrescentados.** O critério "não vive de anúncio display" é escolha de negócio: não mandar a sessão paga para arbitragem concorrente. Ele age pela lista `_MARCAS_DE_ANUNCIO` (`adapters/screenshot_playwright.py:7-44`) e só quando o Playwright está instalado.
- **Mantidas como instrução de prompt** (não são checagens, então "verificável" não se aplica): FF-35, FF-48, FF-49, FF-51, FF-70, FF-82, ADS-28, ADS-30, ADS-31, ADS-46, ADS-51, ADS-53, BE-01, BE-02, BE-11.
  - Em FF-35 conferi que a Misrepresentation cobre destinos (*"Ads or destinations that deceive users…"*, 6020955), o que sustenta o veto a sensacionalismo na página.

## 3. Ledger: citações, classes A × B e "o Google proíbe" sem texto

**Citações.** 189 pares (URL, citação) conferidos no texto das páginas; resultado no resumo do topo. Todas as citações existem.

**Correções:**

| Entrada | O que estava errado | Correção |
|---|---|---|
| ADS-EDI-01 (14847994) | `o_que_exige` citava '★' e o "visto verde" como exemplos da página. Nenhum está no texto. A página lista "Emoji" em *Invalid or unsupported characters* e **permite** *"Using an asterisk for star ratings, like \"5\* hotel\""*. | '★' e o "visto verde" foram para risco, marcados como interpretação. Entrou a exceção do asterisco de avaliação. |
| ADS-EDI-03 (14848296) | Não registrava que o item sobre repetição dentro do mesmo asset não tem qualificador. | Nota acrescentada; ela sustenta ADS-15 como A. |
| PUB-14 (admanager 9840201) | "Respeitar frequência" em `o_que_exige`. | Removido de `o_que_exige`. O teto é padrão aplicado pelo Google, não exigência ao publisher, e a página é documentação de produto. Mantido "permitir fechar" (vinheta *"can be skipped by users at any time"*, AdSense 16531962). |
| **ADS-FIN-01** (nova, 15188216) | O spec cita este id e o ledger não o tinha. | Personal loans. Cobre *"advertisers who offer loans directly, advertisers who are lead generators, and those who connect consumers with third-party lenders"*, exige divulgação no destino e não tem lista de palavras. |
| **ADS-FIN-BR** (nova, 15332527) | A lacuna "política de serviços financeiros não consultada". | No Brasil, é preciso verificação para anunciar ou segmentar quem busca serviços financeiros, inclusive afiliados e anunciantes não financeiros. |

**"O Google proíbe X" sem texto.** Nenhuma justificativa do inventário comete esse erro: varri 'política veta', 'proíbe', 'exige' e 'exigência explícita' e conferi cada ocorrência. O erro está no **código**, não na etapa 2: o prompt da Search diz ao modelo *"PROIBIDO — erro ou bloqueio pela política oficial. Uma ocorrência reprova:"* (`volc_ads/copy/PROMPT.md:637-638`) e embaixo põe listas internas por substring. Registrei isso como ADS-75. A execução hermética mostra a faixa renderizada para vertical 'informativo':

```
  - Declarações não confiáveis / promessas absolutas  [política 15936857]
      dispara em: '100% aprovado'; 'aprovacao garantida'; 'garantido'; ...
  - Portal informativo usando linguagem de prestador  [política 15188216]
      Portal informativo que fala como se executasse o serviço cai em deturpação.
      dispara em: 'emprestimo'; 'antecipacao'; 'credito aprovado'; ...
```

O 15188216 é a política de Personal loans e não diz isso.

**Classes A × B no ledger.** Não achei outra entrada com A sem texto. As entradas que já declaram "não se aplica literalmente" (ADS-ORB-GOV) ou "interpretação" estão coerentes.

## 4. Omissões no caminho ativo

**Acrescentadas ao inventário:**

| Nova | Onde (versão lida) | O que faz | Classe · decisão |
|---|---|---|---|
| **FF-84** | `funnelforge-migracao/engine/src/funnelforge/adapters/wordpress.py:8-11,137`, chamada por `step_publish` em `steps.py:2877` | Na publicação da LP, `_ASTRAL_RE.sub("", …)` apaga todo caractere fora do BMP de `_elementor_data`. O motivo é um banco utf8 de 3 bytes. O corte acontece **depois** do portão final: `_lp_final_issues` (`steps.py:2571-2597`) compara o JSON antes do corte. Execução: '🎓' some; '1️⃣' e '✅' ficam. | C · manter (contrato real), mas registrar o que foi cortado ou cortar antes do juiz. Entrou em `alteram_texto_pos_aprovacao`. Contradiz FF-43, que pede emoji. |
| **ADS-75** | `volc_ads/copy/render.py:465-515` (`_restricoes`); `PROMPT.md:637-638` | Toda regra do spec com severidade erro ou bloqueio vira "PROIBIDO pela política oficial", com amostras "dispara em". | D · contextualizar: manter a derivação e separar "exigência da plataforma" de "lista interna que o validador aplica". |
| **ADS-76** | `volc_ads/policy/spec.json:454-479` (es: 569-594; en: 683-708) | `financeiro.emprestimo_pessoal.divulgacao`: aviso para a vertical 'financeiro' ('emprestimo', 'antecipacao', 'credito pessoal', 'financiamento'). No prompt entra como REGULADO e, sem certificação, vira PROIBIDO (ADS-54). | B · manter (ativo_condicional; fora do caso Senac) |

**Locais que faltavam em regras existentes (acrescentados em `outros_locais`):**

- FF-04 ← `redator_p1.jinja:26,115`, `judge.jinja:53`. A instrução "nunca 1ª pessoa emocional" também está no prompt, e remover só a lista não basta.
- FF-25 ← `screenshot_playwright.py:7-44`, `config/settings.py:147-150` (`blocked_hosts`).
- FF-65 ← `image_prompt.jinja:31`. O negative prompt citado na finalidade está aí, não em `:8`.
- FF-82 ← `steps.py:538-551`: a pesquisa de reserva por LLM repete a instrução de URL exata.
- ADS-40 ← `render.py:277-287`: o veto a DKI em BROAD também é executado em código.
- ADS-66 ← `contrato.py:564-584`, `ciclo.py:415-438`, `ciclo.py:463-508`.

**Ocorrências lidas e deixadas de fora, com motivo:**

- `backend/app/entities/prompts.py` (15 ocorrências: "É PROIBIDO repetir entidades", "NUNCA invente entidades"), `backend/app/prompts.py:28,145`, `backend/app/motor_pautas/**`, `backend/app/n8n_prompts/kw_*`: escolhem tema, entidade ou keyword. Não redigem copy nem página.
- `backend/app/entities/normalize.py:17-59`: deduplicação de entidades.
- `checks.py:52-124` (extração de rótulo e href de botão), `:959-1020` (tokens de congruência CTA × destino, usados só por `cta_destination_congruent`, que não está configurado, FF-29), `steps.py:2109-2165` (posição do widget, parte de FF-67), `widgets/*` (escape e sanitização, parte de FF-71), `adapters/elementor.py:10-11`, `domain/models.py:14-15`, `runner.py:21`, `marcacao.py:171` (parte de ADS-22), `isencao.py:265-268` (parte de ADS-26): helpers ou contratos já cobertos pela regra-mãe.
- `volc_ads/pautador_ponte.py:131,921`, `subir.py:850` ("suavizar"): comentários que afirmam que não há suavização. Conferi que os portões são binários.
- `reviewer.py:54` (idioma por campo): coberto por BE-06.

## 5. Afirmações de caminho ativo

Todas conferidas na árvore lida por imports e chamadas. Nenhuma foi derrubada.

| Afirmação | Evidência |
|---|---|
| FF-29: validadores registrados e nunca configurados (length_p1, interior_min_length, no_trailing_buttons, no_leading_buttons, short_intro, min_headings, winning_lp, opening_line_unique, forward_only, cta_destination_congruent, bridge_before_cta) | Só aparecem no registro `VALIDATORS` (`checks.py:1627-1661`). Não estão em `config.yaml:177-178`, nem em `_FINAL_CONTENT_VALIDATORS` (`steps.py:2516-2524`), nem em `_lp_final_issues` (`:2578-2580`). O backend não injeta validadores (grep). `presell_opening_line` só alimenta o registro de frases (`steps.py:2970`), não reprova. |
| FF-07: âncoras "obrigatórias" não são exigidas | `REQUIRED_COMPLIANCE_ANCHORS` só é lida em `uniqueness.py:28,73` (subtração de boilerplate) e por texto em `configuracao.py`. Nenhum template usa `required_compliance_anchors`, embora `doctrine_context()` a exporte (`doctrine.py:181`). |
| FF-79: `banned_for_role`, `slot_hint_html` e `inject_ad_slots` sem chamador | grep na árvore lida: `admanifest` só é chamado por `build_ad_manifest` e `vignette_meta` (`steps.py:2019`, `:2083`). |
| ADS-05: a lista não roda no código | `validacao.checar_lista` e `checar_politica` só são chamadas dentro de `validacao.py:113` e por `campanha/testes_search.py:326`. `conteudo.py:248` usa o `checar_lista` do spec, não o de `validacao`. O prompt injeta a lista: `render.py:725-731` → `PROMPT.md:627-635`. |
| ADS-16: checagem de destino declarada e não executada | `spec.checar_destino` (`policy/spec.py:142-154`) não tem chamador. `campanha/search.py:33` confirma. |
| ADS-27 e ADS-69: legado | `forca.py` só em `testes_forca.py`; `copy/prompt.py` só em `testes_juiz_semantico.py:585`. |
| Cadeia da copy | `POST /api/trafego/copy` (`trafego.py:1055`) → `_escrever` (`:997-1004`) → `encomendar.escrever` → `ciclo.gerar(prompt_usuario=render.montar(enc), …)` (`encomendar.py:213-220`). O juiz de sentido vem ligado por padrão (`encomendar.py:180`), o que desliga C7 e C8 (`contrato.py:644-646`). |
| Cadeia do `/provar` | `trafego.py:1403` → `sb.preparar` (`:1463`). |
| FF-16 e FF-30 condicionais | `contextual_editorial = page.editorial is not None` (`steps.py:1241`); o salto está em `checks.py:1703-1707`. |
| FF-80 ativo | Roda, mas só produz artefatos do run (seção 2). |

## 6. Deriva depois do build das 10:31

A implementação continuou editando depois do build. As citações do inventário seguem ancoradas na versão lida, que continua íntegra no scratchpad. As posições em `deriva_concorrente.arquivos` valem para o build das 10:31, não para agora. Lista completa em `deriva_concorrente.apos_o_build`. Pontos que tocam regras:

- **`base_factual.py`** (10:32:28): FF-21 passa a retirar fatos `citavel=false` e a avisar no prompt ("FATOS RETIRADOS: N").
- **`checks.py`** (10:32:28): o sha256 não bate com o do build. Não reclassificado.
- **`volc_ads`** (B3b, 10:37–10:44):
  - Novas checagens determinísticas sempre ligadas, `_c5_tipo_do_fato` e `_c7_lastro_tipado`, com tipo `[contexto]` que nunca sustenta número, prazo ou condição. Ainda **não classificadas**.
  - O juiz de sentido deixa de falhar aberto: a falha vira pendência `JS.indisponivel` e a copy não é aceita (ADS-58).
  - `description1/2` passa a ser lida (resolve ADS-59).
  - As raízes do termo saem do teto de repetição (ADS-43).
  - Os termos de busca passam a ter três estados (ADS-57).
  - O cabeçalho do PROMPT.md foi corrigido (ADS-52, ADS-69).

## Pendências

- **`mapa-regras.md` não foi reescrito.** O pedido era corrigir os dois JSON. As contagens e as linhas de ADS-05/07/08/14/15/43, BE-09 e FF-80 no mapa estão desatualizadas em relação ao JSON, e as três regras novas não aparecem lá.
- **ADS-15 (A, manter)** vale para a copy nova da Frente C. A varredura de `copy-v2/search-*.json` só achou 'Inscrição Passo a Passo', que é reduplicação isenta.
- **Não verificado:** se o domínio creditoup.com.br leva a revisão do Google a classificar anúncios de outros temas como financeiros (ADS-FIN-BR). Também não verifiquei como o Google aplica na prática a repetição dentro do asset em nomes próprios como "Senac SP e Senac RJ". Ausência de reprovação passada não garante aprovação.
- As checagens novas do B3b e a tipagem de fatos (M-03) precisam de classificação numa próxima passada.
