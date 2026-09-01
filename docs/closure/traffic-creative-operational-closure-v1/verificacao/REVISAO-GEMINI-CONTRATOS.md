# Revisão Gemini dos contratos Google Ads v25 — pergunta, resposta e julgamento

*Worker 4 · verification · read-only sobre código*
*Modelo: `gemini-3.7-flash` via `/Users/mac/.npm-global/bin/gemini`*
*Data: 2026-09-01 · árvore `sprint/traffic-creative-operational-closure-v1`*

> **Gemini não é autoridade de escrita — é parecer.** Cada afirmação dele abaixo
> foi verificada por mim contra os protobufs v25 realmente instalados
> (`google-ads 31.3.0`, que traz `v21..v25`) ou contra o código. O que não passou
> na verificação está marcado **DESCARTADO** com a prova do descarte.

---

## 0. Declaração de procedência e um desvio de escopo que eu causei

**O que Gemini podia receber**, pelo contrato da missão: arquivos rastreados em
`volc_ads/campanha/**`, `volc_ads/criativo/**`, `volc_ads/criativo_ponte.py`,
`backend/app/routers/trafego.py`, `backend/app/trafego/**`.

**Desvio, na primeira chamada:** eu rodei o `gemini` com o cwd na raiz da
worktree. O CLI tem ferramentas de arquivo próprias (o stderr registra
`Ripgrep is not available. Falling back to GrepTool`) e **leu por conta própria**
arquivos que eu não enviei: `volc_ads/subir.py`, `volc_ads/gads/client.py`,
`volc_ads/gads/modo.py`, `docs/growth-engine/matriz-api/*.md` e
`docs/closure/.../PREFLIGHT-MEDIDO.md`.

- **Nenhum arquivo de categoria proibida foi alcançado**: sem `.env*`, sem chave,
  sem arquivo não rastreado, sem dump, sem dado pessoal, sem
  `~/Desktop/Volc Mídia Global/**`. Tudo o que ele leu é código e documentação
  versionados deste repositório.
- **Mas a lista de paths permitidos foi excedida**, e a falha é minha, não do
  modelo. Registro em vez de omitir.
- **Correção aplicada nas chamadas 2 e 3:** copiei só os arquivos permitidos para
  um diretório isolado no scratchpad e rodei o CLI com o cwd lá dentro. Ele
  passou a não ter repositório para percorrer.
- **Efeito colateral instrutivo:** o confinamento da chamada 2 **produziu dois
  falsos achados**, porque escondeu do modelo justamente o arquivo que contém a
  guarda que ele foi procurar. Está documentado em §2.
- A credencial nunca foi impressa: carregada só dentro de subshell com
  `set -a; . providers.env; set +a`, sem `cat`, `echo` ou `env`.

---

## 1. Chamada 1 — contratos de canal

**Enviado:** `volc_ads/campanha/perfil.py`, `comum.py`, `display.py`,
`demand_gen.py` (97 KB). **Perguntas:** conformidade v25; o que falta para PMax;
Demand Gen confundível com Search; Display completo para `validate_only`; risco
de mutate real escondido.

### 1.1 PROCEDENTE — e verificado por mim

| Afirmação do Gemini | Minha verificação | Veredito |
|---|---|---|
| `Campaign.contains_eu_political_advertising` existe na v25 | `Campaign._meta.fields` → **True** | **PROCEDENTE** |
| `Campaign.ai_max_setting` existe na v25 | idem → **True** | **PROCEDENTE** |
| `Campaign.demand_gen_campaign_settings` existe | idem → **True** | **PROCEDENTE** |
| Existe um **segundo** caminho de mutação real, em `backend/app/routers/trafego.py:3714`, `svc.mutate_campaigns(...)` via `CampaignService`, envolvido em `with modo.destravar(body.motivo)` | Confirmado. É a rota de **remoção** de campanha. `modo.destravar` (`gads/modo.py:49-69`) exige motivo ≥10 chars **e** `FORGE_PERMITIR_ESCRITA=1`, então é dois fatores de verdade | **PROCEDENTE — e foi o achado mais útil da rodada** |
| Demand Gen é estruturalmente impedido de mutar: `_exigir_selo` reconcilia o canal a partir de `campaign_operation.create` e só depois `_recusar_canal_sem_mutacao(selo.canal)` derruba | Confirmado em `volc_ads/subir.py:869-873` e `:923-932`. Reforço que o Gemini não citou: `PerfilDeCanal.permite_mutacao_real` tem **default `False`** (`perfil.py:122`), e só SEARCH (`:213`) e DISPLAY (`:236`) o ligam. Canal novo nasce sem poder criar **por omissão** | **PROCEDENTE** |
| Os mínimos de asset de PMax (HEADLINE 3–15/30, LONG_HEADLINE 1–5/90, DESCRIPTION 2–5/90 com ao menos uma ≤60, MARKETING_IMAGE ≥1 600×314, SQUARE_MARKETING_IMAGE ≥1 300×300, LOGO 1–5 128×128) | Batem **exatamente** com `docs/growth-engine/matriz-api/performance-max.md:87-106` | **PROCEDENTE, porém não é achado**: é a matriz do próprio repositório, que ele leu no desvio da §0. Não confirma nada de fora |

> ⚠️ **O achado do mutate #2 corrigiu um erro meu.** Minha primeira varredura
> usou `grep "\.mutate(\|mutate_campaigns"` — e `\|` em BRE no `grep` do macOS é
> um pipe **literal**, não alternância. A busca não achou nada e eu quase
> registrei "existe um único caminho de mutação". Refeita com `grep -E`, a
> superfície real é **três**: `client.py:170` (`validate_only=True`, seguro por
> construção), `client.py:201` (`validate_only=False`, atrás de
> `exigir_leitura_apenas`) e `trafego.py:3714` (remoção, atrás de `destravar`).

### 1.2 DESCARTADO — alucinação verificada

| Afirmação do Gemini | Prova do descarte | Por que importa |
|---|---|---|
| "**`Campaign.url_expansion_opt_out`** (booleano) para ativar/desativar a expansão de destino" é exigência de PMax na v25 | `Campaign` da v25 instalada: **o campo não existe** (`'url_expansion_opt_out' in Campaign._meta.fields` → `False`). E o próprio repositório já sabia: `docs/architecture/HANDOFF-PMAX-OBSERVABILITY-V25.md` diz que a query "deliberately does not select the **nonexistent** `campaign.url_expansion_opt_out`" | **É a alucinação perigosa da rodada.** Um builder de PMax que seguisse esse conselho escreveria um campo inexistente. Em GAQL isso derruba a query inteira; num payload, quebra na conta |
| "`SearchTheme` signals que **obrigatoriamente na v25** substituem as antigas palavras-chave" | `AssetGroupSignal` tem os campos `audience`, `search_theme`, `local_services_id`, `vertical_ads_item_group_rule_list`. `search_theme` **existe**, mas é uma alternativa entre sinais, e sinal não é obrigatório para criar `AssetGroup`. Também **não existe** `SEARCH_THEME` em `AssetFieldTypeEnum` | O campo é real; a **obrigatoriedade é inventada**. Meio-acerto apresentado com confiança total |
| "Não falta nada [em Display]. O payload é **100% completo e suficiente** para passar pelo `validate_only` em produção real" | Não é verificável sem executar `validate_only` contra a conta — que **não foi executado**. É a lacuna literal que separa P04-T04 de `done` | **Afirmação sem prova, com a forma de prova.** Aceitá-la fecharia P04-T04 sem o único ato que a fecha |
| "business_name é requisito de `AssetGroupAsset`" (PMax) | `performance-max.md:73` e `:134`: com `brand_guidelines_enabled` — **ligado por default desde a v21** — `BUSINESS_NAME` e `LOGO` vão para **`CampaignAsset`**, não `AssetGroupAsset` | Omissão material: exigi-los no lugar errado gera `CampaignError.REQUIRED_LOGO_ASSET_NOT_LINKED` |

### 1.3 O que Gemini NÃO viu, e eu vi

- **Não mencionou** a restrição de lance de PMax: só `MAXIMIZE_CONVERSIONS` e
  `MAXIMIZE_CONVERSION_VALUE` são suportadas, e **estratégias de portfólio são
  proibidas** (`performance-max.md:161-166`).
- **Não mencionou** que em PMax não-retail o `AssetGroup` e todos os
  `AssetGroupAsset` que satisfazem os mínimos precisam nascer **no mesmo bulk
  mutate** (`performance-max.md:33-53`) — a restrição que mais muda o desenho de
  um builder.
- **Não notou** que `perfil.permite_mutacao_real` é fail-closed por *default*, o
  que é a razão estrutural (e não disciplinar) do aceite 5 de P04-T09.

**Julgamento da chamada 1:** útil por um achado real (o mutate #2) e uma
alucinação bem localizada (`url_expansion_opt_out`). O tom é confirmatório
demais — respondeu "está tudo certo" em 4 das 5 perguntas, o que para um revisor
adversarial é o modo de falha esperado.

---

## 2. Chamada 2 — linhagem de asset e prontidão

**Enviado (isolado):** `criativo_ponte.py`, `criativo/contrato.py`,
`criativo/validacao.py`, `trafego/prontidao.py`.

### 2.1 DESCARTADO — falso achado causado pelo meu confinamento

Gemini abriu com uma "REFUTAÇÃO": no caminho de Display, um asset com **MIME ou
dimensão divergente seria PROMOVIDO**, porque a ponte só reconfere o hash; e
concluiu que `Linhagem.desconhecida` "**não existe** nem é referenciado". Daí
derivou (Q3) uma "prova de forja" de `confirmada`.

**As duas estão erradas, e a culpa é do recorte que eu dei a ele.** A guarda vive
em `volc_ads/subir.py`, que eu não enviei:

- `_medidas_batem` (`subir.py:468-540`) **decodifica os bytes reais** com
  `medir_imagem.medir(dados)` e corrobora, de forma independente do hash:
  `bytes_totais`, MIME **normalizado** (`image/jpg` → `image/jpeg`, caixa e
  parâmetro RFC tratados) e largura/altura. Assinatura não reconhecida ⇒ nada é
  corroborado ⇒ não confirmado.
- `_linhagem_do_payload` (`subir.py:543-620`) tem **três ramos de rebaixamento**
  para `Linhagem.desconhecida`: sem candidata; hash declarado que não bate com os
  bytes; e linhagem que **omite** o hash (esse último criado justamente porque
  omitir saía mais barato que mentir — inversão de incentivo achada em revisão
  adversarial anterior).
- O comentário em `:590-598` registra que a versão que reconciliava **por nome**
  aceitava linhagem inteiramente fabricada, e que isso foi medido em 27/08/2026.

**Veredito: DESCARTADO.** A invariante "por bytes, nunca por nome" está
implementada e é mais forte do que o Roadmap descreve.

**Lição de método, que vale mais que o achado:** confinar o modelo aos arquivos
permitidos **também esconde dele o contexto que refuta suas hipóteses**. Um
revisor sem o arquivo da guarda relata ausência de guarda. Isso não é defeito do
Gemini — é limite do recorte, e qualquer parecer produzido sob recorte precisa
ser lido com essa ressalva.

### 2.2 PROCEDENTE — e são achados de verdade

| # | Achado | Verificação | Severidade |
|---|---|---|---|
| **A** | `smart_bidding_eligible` **nunca pode sair `True`**: não existe nenhum ramo que atribua `meta_status = PRONTO` | Confirmado em `prontidao.py:121-165`. Os únicos valores atribuídos são `INDETERMINADO`, `PARCIAL` e `NAO_PRONTO`; logo `medicao == PRONTO` (`:203`) é inalcançável e `elegivel` (`:224`) é constante `False` | **Média — mas não é o defeito que o Gemini alegou** |
| **B** | `fontes = list(fontes_de_sinal_observadas or ())` colapsa `None` ("não li") em `[]` ("li e está vazio") | Confirmado, `prontidao.py:163`. Ambos caem em `sinal = NAO_PRONTO`. Consequência estrutural: o ramo `sinal == INDETERMINADO` em `:205` é **código morto** | **Média** |
| **C** | `metas_da_conta.get("primaria")` ausente derruba para o `else` "a conta não tem ação de conversão primária", **ignorando** `acoes[]` | Confirmado, `prontidao.py:125` vs `:150-165`. Ausência de chave vira zero medido | **Média** |
| **D** | `f"{len(primarias) or 1} ação(ões)"` imprime **1** quando a contagem é **0** | Confirmado, `prontidao.py:145`. Só afeta a nota textual, e ela pode contradizer `conversion_actions_primarias: []` no mesmo objeto | **Baixa (relato)** |
| **E** | Em `lote_de_pasta`, o **papel** do arquivo é decidido pela pasta (caminho), não pelos bytes | Confirmado. Mas `papel` não é identidade, e `subir.py:612` registra explicitamente que ele "veio da estrutura do brief e não de uma afirmação sobre o arquivo". É ferramenta de operador, offline | **Baixa** |

**Meu julgamento sobre o achado A, que o Gemini exagerou.** Ele chamou de "falha
de design catastrófica". **Não é.** É deliberado e correto para o estado atual: a
meta **efetiva** ainda não é lida (é exatamente o item 3 do aceite de P05-T12),
então declarar `PRONTO` seria mentir. O módulo é fail-closed e está certo.

**O que É procedente, e o Gemini não formulou:** enquanto o ramo `PRONTO` for
inalcançável, `smart_bidding_eligible=False` é **constante, não computação** — e
portanto **infalsificável**. Um teste que afirme "Smart Bidding bloqueado" passa
com qualquer entrada, inclusive com uma conta perfeitamente medida. Isso é o
anti-padrão *"teste que passa com qualquer entrada"* que esta missão manda caçar.
Consequência prática para P05-T12: quem fechar o item 3 **tem de** acrescentar o
ramo `PRONTO` **e** um teste que prove o portão **virando** — senão o portão
nunca foi testado, só observado desligado.

**Sobre B e C:** o mesmo módulo que separa com cuidado "não li" de "está vazio"
para `metas_da_conta` (o docstring em `:104-108` é explícito sobre isso)
**colapsa os dois** para as fontes de sinal e para a chave `primaria`. A direção
do colapso é a segura (ambos bloqueiam), então não há risco operacional hoje —
mas o `DEFINITION-OF-DONE.md` §1 trata colapso de estados como **reprovação de
gate**, sem cláusula de "colapso benigno". É dívida real, e barata de pagar.

### 2.3 Q5 — o achado da conta

Gemini respondeu que o desalinhamento (`biddable=true` só em DOWNLOAD/APP, com
oito ações PURCHASE primárias na conta) **passaria despercebido**, e citou o
próprio comentário do módulo.

**PROCEDENTE, e é a confirmação independente do que motivou P05-T12.** `prontidao.py`
lê `conversion_action`; não lê `customer_conversion_goal`,
`campaign_conversion_goal` nem `conversion_goal_campaign_config.goal_config_level`.
O status sai `PARCIAL` com o bloqueador nomeado — ou seja, o sistema **não afirma**
prontidão falsa; ele declara que não sabe. Isso é o comportamento certo. O que o
Gemini errou foi a última linha ("declarará que a campanha está elegível"):
`elegivel` é sempre `False`, então ele **não** declara elegibilidade. Meia
resposta certa.

---

## 3. Chamada 3 — PMax e `AssetGroupSignal` (pedido do lead)

**Enviado (isolado):** `volc_ads/observabilidade_pmax/types.py`, `queries.py`,
`coverage.py`. Este módulo já existia **antes** desta missão e nunca tinha sido
revisado contra o contrato externo.

### 3.1 A lane estourou — declarado, não preenchido

**A chamada não retornou.** Tentada duas vezes: a primeira pendurou por vários
minutos e morreu com exit 144; a segunda, com prompt encurtado e o arquivo
embutido em vez de lido por ferramenta, estourou um teto de 7 minutos e foi
encerrada por mim (exit 143). As duas primeiras chamadas do dia, no mesmo
binário e com a mesma credencial, funcionaram — então não é configuração.

**Não substituí por outro provedor e não inventei resultado.** Registro a lane
como indisponível para esta pergunta, do mesmo jeito que a sprint anterior
registrou a lane DeepSeek como ausente em vez de fingir cobertura.

**O que fiz no lugar é mais forte que o parecer que eu teria recebido:** em vez
de perguntar a um modelo quais campos GAQL existem, **conferi todos contra os
descritores protobuf da v25 instalada**. Ver §3.3.

### 3.2 Verificado por mim, contra os protos v25 instalados

| Objeto | Campos reais na v25 instalada |
|---|---|
| `AssetGroup` | `ad_strength`, `asset_coverage`, `campaign`, `final_mobile_urls`, `final_urls`, `google_local_services_info`, `id`, `name`, `path1`, `path2`, `primary_status`, `primary_status_reasons`, `resource_name`, `status` |
| `AssetGroupSignal` | `approval_status`, `asset_group`, `audience`, `disapproval_reasons`, `local_services_id`, `resource_name`, `search_theme`, `vertical_ads_item_group_rule_list` |
| `AssetGroupAsset` | `asset`, `asset_group`, `field_type`, `policy_summary`, `primary_status`, `primary_status_details`, `primary_status_reasons`, `resource_name`, `source`, `status` |

Fatos que decorrem disso e valem como gate para quem escrever PMax:

1. **`AssetGroup.asset_coverage` e `AssetGroup.primary_status` existem** — então a
   doutrina do `HANDOFF-PMAX-OBSERVABILITY-V25.md` ("elegibilidade derivada de
   `primary_status == ELIGIBLE`, não do `status` administrativo mutável") é
   sustentada pelo proto, não é preferência de estilo.
2. **`AssetGroupSignal.search_theme` existe**; `SEARCH_THEME` **não** é um
   `AssetFieldType`. Sinal e asset são eixos distintos, e confundi-los produz uma
   query inválida.
3. **`Campaign.url_expansion_opt_out` não existe** — ver §1.2.
4. **`AssetGroupAsset.primary_status_details` existe**, e é o que dá a razão de
   um asset não estar servindo. Um coletor que leia só `status` perde o motivo.

### 3.3 Conferência determinística das queries GAQL de PMax

Extraí toda referência `recurso.campo` de
`volc_ads/observabilidade_pmax/queries.py` e resolvi cada uma contra o
`DESCRIPTOR` protobuf da v25 instalada, descendo em campos aninhados. Recursos
cobertos: `campaign`, `asset_group`, `asset_group_asset`, `asset_group_signal`,
`asset`, `campaign_asset`.

**Resultado: 61 campos válidos, ZERO campos inexistentes.**

Dois candidatos apareceram na primeira passada, e **ambos eram defeito do meu
extrator, não do código**:

| Suspeito | Veredito | Prova |
|---|---|---|
| `asset_group.path` | **falso positivo meu** | O código usa `asset_group.path1` e `path2` (`queries.py:285-286`). Meu regex `[a-z_]+` não casa dígito e truncou o nome |
| `asset.type` | **falso positivo meu** | `queries.py:377` seleciona `asset.type`, o nome **de wire** correto em GAQL. No proto Python o campo se chama `type_`, porque `type` é reservado — confirmado: `'type_' in Asset.DESCRIPTOR.fields_by_name` → `True`; `'type'` → `False` |

**Conclusão:** o módulo de observabilidade PMax não tem campo GAQL morto. Como
uma query com campo inexistente falha **inteira** (`UNRECOGNIZED_FIELD`) e não
degrada, esse era o risco mais caro do módulo — e ele não se materializa.

Isso **não promove P04-T07**: o módulo continua sem consumidor de produção (único
importador é `backend/tests/test_observabilidade_pmax.py`), e o bloqueio de
criação de PMax continua sendo `sem_construtor`, não mensuração. Contrato correto
e desligado continua sendo contrato desligado.

---

## 4. Resumo do julgamento

| Categoria | Quantidade | Itens |
|---|---|---|
| **Procedente e útil** | 1 | segundo caminho de mutate (`trafego.py:3714`) — corrigiu um erro meu de método |
| **Procedente, achado real** | 5 | A (portão infalsificável), B (`None`→`[]`), C (chave ausente→zero), D (`or 1`), E (papel por pasta) |
| **Procedente mas não é achado** | 2 | limites de PMax e conformidade de campos — lidos do próprio repositório |
| **Descartado por alucinação** | 2 | `url_expansion_opt_out`; `SearchTheme` obrigatório |
| **Descartado por falso achado de recorte** | 2 | "linhagem promovida sem conferir bytes"; "forja de `confirmada`" |
| **Descartado por afirmar sem prova** | 1 | "Display 100% completo para `validate_only` real" |
| **Não obtido — lane estourou** | 1 | chamada 3 (PMax/`AssetGroupSignal`), substituída por conferência determinística contra os protos (§3.3) |

**Cobertura, dita com honestidade:** de três chamadas planejadas, **duas
retornaram e uma estourou**. A pergunta da chamada 3 foi respondida por
verificação própria contra os descritores protobuf, que é evidência mais forte
que parecer de modelo — mas as perguntas qualitativas dela (o código *trata* a
exclusão mútua entre `search_theme` e `audience`? algum ramo colapsa `[]` com
falha de coleta?) **ficaram sem segunda opinião externa**. Registro como lacuna,
não como cobertura.

**Conclusão sobre o uso do modelo.** Gemini 3.7 Flash foi útil como **segunda
varredura mecânica** — ele achou uma superfície de mutação que meu próprio `grep`
tinha perdido por um defeito de escape. Como **juiz de contrato externo** ele é
inseguro: inventou um campo v25 com confiança total, e o campo inventado é
exatamente do tipo que só falha na conta real. E como **revisor adversarial** ele
tende ao confirmatório: sem confinamento respondeu "está tudo certo" em quase
tudo; com confinamento, produziu refutações fortes sobre guardas que existiam
fora do recorte.

**Nenhum achado dele foi repassado adiante sem verificação, e nada dele é
autoridade de escrita.**
