# Runbooks — os atos externos que esta missão preparou e NÃO executou

> **Nada aqui foi executado.** Nenhuma chamada autenticada a Meta ou Google,
> nenhuma migration no Supabase oficial, nenhum canário, nenhuma ativação.
> Estes runbooks descrevem o que *seria preciso* para cada ato; eles não
> autorizam nem executam nada.

Base: `5cb654fbf1dbc226a995b0c60a37310c2aa4eb4c`
Branch: `execution/volc-os-operacao-80-20`

---

## Regra que vale para todos

Cada ato abaixo exige, sem exceção:

1. **autorização humana explícita e por escrito**, nomeando o ato e a conta;
2. **árvore limpa** no SHA que foi revisado (um ato sobre outro código não prova
   este código);
3. **prova de ausência antes** — a leitura que mostra que o objeto ainda não
   existe. ⚠️ Falha de leitura NÃO é prova de ausência;
4. **rollback reversível declarado antes de começar**;
5. **read-back depois de cada passo veiculável**, antes de avançar para o
   próximo;
6. **ambiguidade após despacho não autoriza retentativa.** Nunca. Reconciliação
   por leitura é o único caminho.

E a invariante que nenhum runbook pode afrouxar: **nenhum objeto nasce ENABLED,
e não existe rota de ativação.**

---

## RB-01 · Migration Meta `create_paused` no Supabase oficial

**Estado:** candidata, nunca aplicada em lugar nenhum.

- **Arquivos:** `supabase/migrations/20260904183418_meta_create_paused_executor.sql`
  (apply) e `..._rollback.sql`.
- **Detalhe completo:** `docs/closure/meta-creation-engine-operator-experience-v1/RUNBOOK-MIGRATION-META-CREATE-PAUSED.md`
  — ele continua sendo a autoridade sobre esta migration, incluindo os sha256.
- **Autoridade Supabase:** `https://database.agenciavolc.com.br`, e só ela.
  Rode `python3 scripts/verificar_autoridade_supabase.py` antes.
- **Precondições:** backup do banco tomado e verificado; janela combinada; o
  rollback testado no PostgreSQL descartável na MESMA ordem
  (apply → uso mínimo → RLS/grants → rollback → reapply).
- **Flags:** nenhuma. A migration cria estrutura; ela não abre ato nenhum.
- **Rollback:** o `..._rollback.sql` do par. Ele cita a assinatura completa das
  funções — conferir que a assinatura no banco é a que o arquivo espera.
- **Autorização humana ainda necessária:** SIM.

---

## RB-02 · `validate_only` real Meta com o plano novo

**⚠️ O recibo real existente ficou OBSOLETO nesta missão.**

O recibo aceito (`plan_sha256 = 10e5b56aaf0d1d4c4b87bc309532c148463f40ab721ac44de6b60cfcb061d767`,
`objects_created=0`, cobertura `INDEPENDENT_ROOTS_ONLY`) descreve um plano que
**não é mais o plano que este código compila**. Duas mudanças mexeram no hash:

1. o commit anterior (`5cb654f`) acrescentou `destination_spec` ao AdCreative;
2. esta missão (`a1d8898`) **removeu** esse campo e acrescentou
   `shop_redirect_proof` à matéria do hash.

- **Precondições:** RB-01 aplicada; `META_VALIDATE_ONLY_ENABLED=1`; credencial
  de leitura Meta no Keychain da máquina do operador (a rota exige host local).
- **Flags exatas:** `META_VALIDATE_ONLY_ENABLED=1`. **Nada mais.** As três de
  criação continuam fechadas.
- **Conta/canal:** opacos até o ato. A conta é escolhida na tela, e a rota
  resolve a referência opaca no backend.
- **Teto:** não se aplica — `validate_only` não gasta.
- **Plano/hash:** anotar o `plano_sha256` NOVO devolvido pela compilação, e
  compará-lo com o recibo gravado. Divergência = pare.
- **Quantidade:** raízes independentes apenas (Campaign + AdCreative). AdSet e
  Ad **não** são validáveis sem pai real — isso é contrato, não limitação.
- **Prova de ausência:** `objects_created` tem de voltar `0`.
- **Ambiguidade:** timeout em `validate_only` é o ÚNICO timeout retentável do
  executor, porque o pedido levava `execution_options=["validate_only"]` e não
  existe objeto que pudesse ter nascido.
- **Rollback:** nenhum necessário — nada é criado.
- **Autorização humana ainda necessária:** SIM.

---

## RB-03 · `create_paused` Meta — o primeiro canário

**Estado: BLOQUEADO por precondição de destino, e o bloqueio é deliberado.**

- **Precondições:** RB-01 e RB-02 fechados, com recibo durável válido e não
  expirado; aprovação humana com a frase literal `CRIAR PAUSADA`; manifesto de
  passos fixado; recibo de política de cada peça CLEAR/AUTHORIZED.
- **Flags exatas — as TRÊS, simultaneamente:**
  - `META_CREATE_PAUSED_ENABLED=1`
  - `META_CREATE_LEDGER_WRITE_ENABLED=1`
  - `META_SHOP_REDIRECT_CLEARED=1`
- **⚠️ A terceira é o bloqueio novo, e ela não é uma permissão a mais.** Ela
  declara que alguém FEZ a leitura externa de elegibilidade a Shop desta conta
  e ela deu não-elegível. Enquanto essa leitura não existir, a flag fica
  fechada e o despacho é recusado no executor, antes do primeiro POST, com
  `META_SHOP_REDIRECT_UNPROVEN`.
  **O que fecha essa lacuna:** provar (a) o campo/máscara oficial v26 que força
  website-only para OUTCOME_TRAFFIC/LPV, ou (b) que a conta selecionada não é
  elegível a redirecionamento para Shop. Hoje a evidência oficial recolhida
  marca `creative.destination_spec` como `RESEARCH_REQUIRED` /
  `remote_behavior_proven: false`.
- **Teto:** `daily_budget_minor` ≤ 1000 (R$ 10,00), moeda BRL, orçamento no
  AdSet.
- **Cardinalidade:** 1 Campaign + 1 AdSet + N Creative/Ad (1 ≤ N ≤ 10).
- **Prova de ausência:** a reconciliação por leitura, ANTES de qualquer
  segundo pedido. Nunca reenviar.
- **Read-back:** obrigatório entre cada passo. `FOUND+CONGRUENT` é o único
  fechamento automático positivo. `ABSENT` e `UNKNOWN` permanecem AMBÍGUOS e
  exigem adjudicação manual.
- **Ambiguidade:** sem retentativa automática, em nenhuma circunstância.
  `resolver_ausente` levanta por construção.
- **Rollback:** ⚠️ **NÃO EXISTE rollback automático.** Objetos criados são
  PAUSED e ficam. Remoção é ato manual, humano, fora deste sistema.
- **Autorização humana ainda necessária:** SIM.

---

## RB-04 · T05 — canário Display PAUSED

- **Precondições:** T01, T02, T03 e T12 verdes (feitos nesta missão);
  `validate_only` real do payload NOVO de Display aprovado (o payload mudou:
  ad group e anúncio agora nascem PAUSED e o RDA carrega `control_spec`).
- **⚠️ E a precondição que esta missão CRIOU:** o canal Display não está em
  `canario.CANAIS_COM_CRIACAO_AUTORIZADA`. Autorizar o canário Display é,
  literalmente, acrescentar `"DISPLAY"` a esse conjunto — e isso é uma mudança
  de código revisada, não uma variável de ambiente. É deliberado: a autorização
  de um canal para escrita real não deve caber num `export`.
- **⚠️ Segunda precondição nova:** o portão de política criativa está estrito
  (`CRIATIVO_POLICY_GATE_STRICT=1`) e não há detector de pixel registrado, então
  TODA peça Display é bloqueada com `GATE_UNAVAILABLE`. Antes do canário é
  preciso **registrar um detector de pixel real** (OCR + classificador de
  logotipo) por `registrar_detector_de_pixel()`, ou aceitar a lacuna por escrito
  abrindo a trava. A segunda opção deixa o recibo declarando
  `PIXEL_DETECTOR_NOT_REGISTERED` — a lacuna não some, ela fica registrada.
- **Flags:** a trava global de escrita do `volc_ads.gads.modo` + a autorização
  do canal. Nenhuma flag sozinha basta.
- **Conta/canal:** conta-laboratório do canário, canal DISPLAY.
- **Teto:** `TETO_DIARIO_POR_CANAL["DISPLAY"]` = R$ 20,00/dia. Display **não
  tem CPC nem rede** a declarar — cobrar isso dele seria uma recusa que o
  operador não teria como satisfazer.
- **Plano/hash:** o selo de `/provar` tem de ser IGUAL ao remontado em
  `/subir`. Esta missão fechou a divergência que impedia isso; o canário é
  quem prova que ela ficou fechada.
- **Prova de ausência:** `canario.campanhas_com_marca` e
  `campanhas_com_destino` antes do mutate. ⚠️ `campanhas_com_destino` consulta
  `ad_group_ad.ad.final_urls` — correto para Display e Search, **insuficiente
  para PMax**, que guarda a URL no asset group (ver RB-07).
- **Quantidade:** 1 campanha, 1 ad group, 1 RDA.
- **Read-back:** confirmar `status=PAUSED` nos TRÊS objetos e `control_spec`
  com os dois campos `false`.
- **Ambiguidade:** ledger `INDETERMINADO`; não reenviar.
- **Rollback:** campanha PAUSED não veicula. Remoção é ato manual.
- **Autorização humana ainda necessária:** SIM.

---

## RB-05 · T07 — canário Demand Gen PAUSED

- **Precondições:** RB-04 fechado; **T06 ainda NÃO foi implementado nesta
  missão.** Falta: `perfil.DEMAND_GEN.permite_mutacao_real=True`,
  `subir.CONSTRUTORES_POR_CANAL += DEMAND_GEN`, as três automações OPTED_OUT
  (`GENERATE_DESIGN_VERSIONS_FOR_IMAGES`,
  `GENERATE_VIDEOS_FROM_OTHER_ASSETS`,
  `GENERATE_ANIMATED_IMAGES_FROM_OTHER_ASSETS`), a tradução de
  `BUDGET_BELOW_PER_DAY_MINIMUM` em bloqueio legível, e o portão de política
  ligado em `_montar_plano_demand_gen`.
- **⚠️ Orçamento mínimo por moeda:** **não invente um número universal.** O
  valor vem da resposta da API (`BUDGET_BELOW_PER_DAY_MINIMUM` traz moeda e
  micros); o sistema deve traduzir a recusa, nunca antecipá-la com uma tabela
  copiada.
- **Flags:** as de Display mais a autorização do canal DEMAND_GEN.
- **Autorização humana ainda necessária:** SIM.

---

## RB-06 · T10 — migration v12_03 no Supabase oficial

- **Estado:** candidata. Mesmas regras da RB-01: autoridade única
  `https://database.agenciavolc.com.br`, backup antes, rollback testado no
  PostgreSQL descartável na ordem apply → uso → RLS/grants → rollback → reapply.
- **Autorização humana ainda necessária:** SIM.

---

## RB-07 · T11 — canário Performance Max PAUSED

- **Precondições:** RB-04, RB-05 e RB-06 fechados; **T08 ainda NÃO foi
  implementado nesta missão** (PMax continua sem `construtor` no perfil, e
  `/provar` ainda não aceita `canal=PERFORMANCE_MAX` pela rota tipada).
- **O que T09 JÁ fechou nesta missão:** as quatro automações OPTED_OUT,
  `excluded_parent_asset_set_types=[PAGE_FEED]`, asset group PAUSED, URL única
  sem `final_mobile_urls` e sem `path1`/`path2`.
- **⚠️ `url_expansion_opt_out` NÃO EXISTE em v25** — conferido no proto
  instalado. Quem procurar esse campo não vai achar, e emiti-lo faria a API
  recusar o mutate inteiro. O único caminho é `asset_automation_settings`.
- **⚠️ Duplicidade por destino:** `canario.campanhas_com_destino` consulta
  `ad_group_ad` e PMax **não tem ad group**. Para PMax a consulta precisa ler
  `asset_group.final_urls`. **Isto ainda não foi implementado** — rodar o
  canário PMax sem isso significa rodar sem prova de duplicidade por destino.
- **Mensuração:** a leitura vem do SERVIDOR (`pmax.ler_mensuracao`), nunca do
  corpo do pedido. Ausência ≠ zero; `INDETERMINADO` bloqueia.
- **Read-back:** confirmar 0 linhas em `campaign_asset_set` PAGE_FEED e 0 em
  `final_url_expansion_asset_view`. Qualquer linha = expansão aconteceu.
- **Autorização humana ainda necessária:** SIM.

---

## RB-08 · Detector de pixel para o portão de política

Não é um ato de provedor, mas é precondição de RB-04 em diante.

- **O que falta:** um motor determinístico de OCR + classificador de logotipo,
  com versão declarada, registrado por
  `app.criativo.politica.inspecao.registrar_detector_de_pixel()`.
- **Contrato:** recebe `(bytes, mime)` e devolve `LeituraDePixel(texto, rotulos)`.
  O hash dos bytes inspecionados TEM de bater com o `content_sha256` do recibo.
- **Enquanto não existir:** todo recibo declara o detector como `ERROR` e a
  decisão é `GATE_UNAVAILABLE`. Isso bloqueia mídia paga, e bloquear é a
  decisão certa: não conseguir olhar não é a peça estar limpa.
