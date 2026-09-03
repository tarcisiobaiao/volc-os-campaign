# HANDOFF — espinha de política do destino pago, v2

Branch `sprint/paid-destination-policy-spine-v2`
Base `origin/volc-os-v2` @ `34dc7b41bce901bd8bebfdec0a01e293678cbf08`
Worktree `/private/tmp/volc-paid-destination-policy-spine-v2`
Supabase operacional verificado: `https://database.agenciavolc.com.br`

---

## 1 · A frase que a sprint existia para tornar verdadeira

> Uma página de destino pago não pode nascer sem papel operacional declarado,
> nem ser publicada sem avaliação do contrato, nem ser usada em campanha sem
> recibo válido.

As três metades eram falsas ao mesmo tempo, e por um motivo só:
**`backend/app/landing_policy` não tinha nenhum chamador.** O pacote existia,
era bem construído, tinha 61 testes — e nada o chamava fora dos próprios testes
e de um script de auditoria. Portão que nunca está no caminho não é portão.

---

## 2 · O achado que reorganizou a missão

O handoff anterior (`HANDOFF-PATCH-PUBLICACAO.md`) trazia um patch exato para
`POST /redator/runs/{id}/publicar/{page}`. Ele estava certo sobre aquela rota e
**incompleto sobre o sistema**, por três razões medidas:

1. **A escrita no WordPress não acontece no backend.** Ela acontece dentro do
   subprocesso do motor (`funnelforge/adapters/wordpress.py`, chamado de
   `pipeline/steps.py`). O backend só dispara o CLI.
2. **Existem DUAS portas.** `POST /redator/disparar` roda o funil inteiro com
   `publicar=True` e o handoff não a mencionava. Portão numa porta deixa a outra
   aberta.
3. **A LANDING PAGE era a única página isenta do portão de conteúdo do motor.**
   `step_content_gate` começava com `if page.page_type == "LANDING PAGE": …
   status=OK; return`. E o ramo Elementor de `step_publish` nunca rodava
   `_final_content_issues`. Os dois buracos somados faziam a LP — a página que
   recebe o clique comprado — ser o único artefato do sistema publicado sem
   verificação de conteúdo em ponto algum.

Além disso, o patch proposto tinha quatro defeitos que **não** foram copiados:
testava `if avaliacao.bloqueios` (ignorando os desconhecidos); derivava o papel
de um campo do payload; chamava `_buscar` duas vezes por um `if False else`; e
montava a URL com uma coluna (`wp_base_url`) que não existe.

---

## 3 · O que foi entregue

### 3.1 · O contrato (`backend/app/landing_policy/**`)

| item | o que mudou |
|---|---|
| `POLICY_CONTRACT_VERSION` | a versão da FORMA da avaliação, ao lado do hash da matriz |
| décima verificação `approval_receipt` | presença, veredito, vínculo com o conteúdo, versão e frescor do recibo |
| `impressao_canonica` | projeção estrutural que decide deriva; o byte fica como prova de igualdade |
| `papel_do_servidor` | o servidor apura o papel; o cliente só SOBE o rigor |
| `plano.py` | o plano renderizado como documento, avaliado pelas mesmas dez varreduras |
| `registro.py` | o recibo dentro de `paginas_publicadas` — **sem tabela nova** |
| política de links | `paid_destination` recusa TODO hyperlink externo clicável |
| `<title>`/`<h1>`/`<h2>` | o parser passou a colhê-los; antes a manchete era "mais uma frase do corpo" |

### 3.2 · As três barreiras

**BARREIRA 1 — geração** (`funnelforge-migracao/engine/**`)
Pré-voo do plano antes da primeira chamada paga ao LLM; isenção da LP apagada em
`step_content_gate`; portão como **primeira** instrução de `step_publish`, antes
dos três `upload_media` — antes ele rodava depois, e uma página recusada já tinha
deixado mídia órfã no site ao vivo. `checks.compliance` deixou de aceitar
`adsense OU utilidade pública`. O recibo entra em `state.published[n]`.

**BARREIRA 2 — publicação** (`backend/app/routers/publicacao.py`, `redator/**`)
Portão nas duas portas; `worker._disparar_motor` como único dono de `--publish`;
recibo de recusa gravado em disco atomicamente.

**BARREIRA 3 — campanha** (`backend/app/routers/trafego.py`)
Leitura ao vivo **tripla** (desktop, mobile, rastreador) em `/provar` e de novo
em `/subir`, entre a conferência do selo e `ledger.abrir` — recusar ali não deixa
estado órfão nem gasta consulta na conta do Google. A URL manual do cliente
passa pela avaliação completa: o recibo vai faltar, e faltar reprova.

**SUPERFÍCIE** (`src/lib/landing-policy/`, `src/components/landing-policy/`)
Dois fail-open corrigidos: `status_wp === null` renderizava "LP no ar" e marcava
a etapa pronta quando o servidor nunca leu o WordPress; e `BARRAM` era um `Set`
de dois códigos no cliente — qualquer código fora da lista virava observação
recolhida. Cinco estados que a tela recusa colapsar: pronto segundo o VOLC ·
publicado · verificado ao vivo · elegível para campanha · **aprovação do Google
DESCONHECIDA**.

---

## 4 · O que a revisão cruzada encontrou

Codex GPT-5.6 read-only produziu **12 achados, todos confirmados por execução**
antes de virarem conserto. Quatro deles eram falso verde e cinco eram **falso
bloqueio** — que é tão grave: portão que reprova página correta é desligado pela
operação, e portão desligado não protege nada.

Os que mais custaram:

- **O recibo era conferido e não era LIDO.** Versão e frescor eram checados; o
  veredito, não. Um recibo com `paid_destination_ready: false` e um bloqueio
  listado satisfazia a verificação. E um recibo de outra página também.
- **`status_http` era coletado e não decidia nada.** Destino que devolve 404 ao
  revisor ficava elegível — o caso literal de *destinations that don't work*, que
  `volc_ads/policy/spec.py::checar_destino` modelava sem nunca ser chamado "por
  falta de um status HTTP que ninguém aqui coleta". A barreira 3 passou a coletar.
- **Cloaking por JavaScript era invisível.** `location.assign` não estava na
  regex, e a impressão canônica ignorava scripts: injetar um redirecionamento
  que só pega quem não é Googlebot deixava a impressão idêntica.
- **`"cin"` casava dentro de "cinco"** e "visto" é particípio de "ver": "Aprenda
  a emitir notas em cinco passos" emitia `SERVICO_GOVERNAMENTAL_RESTRITO`.
- **Um erro de digitação em `role` desligava a régua**: qualquer valor
  irreconhecível virava `organic_article`, o papel mais frouxo.

E uma regra que **eu mesmo acrescentei** — CTA com destino vazio — produziu
falso bloqueio no primeiro contato com a realidade (num run `--only p1` as rotas
interiores ainda não existem, então todo CTA tem href vazio por ordem de
construção). Foi rebaixada a inventário e está registrada como lacuna aberta em
`REMAINING-RISKS.md` §4.

**Gemini: `CROSS_PROVIDER_REVIEW_NOT_AVAILABLE`** — sem método de autenticação
configurado. Registrado em menos de cinco minutos, harness não consertado,
compensado com revisão Claude fresca em quatro lentes adversariais.

---

## 5 · Os gates

| gate | base | HEAD | delta |
|---|---|---|---|
| backend pytest | 3064 passed / 112 skipped | **3188 / 112** | +124, zero falhas novas |
| engine pytest | 726 passed | **748** | +22, zero falhas novas |
| tsc | 76 erros | **76** | **zero** |
| vitest | 7 arquivos / 2 testes falhando | 7 / 2 | **zero** (todos herdados, nenhum no ownership) |
| `gate_sem_mutacao_google` | — | **3/3** | — |
| autoridade Supabase | — | **ok** | — |
| paridade da matriz | 33 = 33 | **42 = 42** | +9 regras, todas com fonte oficial |

Detalhe e comandos exatos em `GATES.md`.

⚠️ **O venv do motor não existia nesta máquina.** A suíte do motor nunca havia
sido executável aqui. Foi criada com o comando que `worker._executavel()`
prescreve — não é harness novo, é o ambiente documentado finalmente montado.

---

## 6 · A auditoria pública read-only

Quatro GETs, dois destinos × dois user-agents, pausa de 3 s, sem cookie, sem
autenticação, sem formulário. Autorizada pela seção 12 do briefing.

- **`/r/fgts-saque-aniversario/`** — os sete links `caixa.gov.br` de âncora
  numérica não aparecem mais no inventário estrutural: zero host `.gov.br`, zero
  âncora-de-valor em link de governo, contra sete na preservação. A Fase A2 item
  1 do `LIVE-REMEDIATION-PLAN` foi executada. **Mas o formato monetário
  malformado continua** (item 2), e `www.fabiolobo.com.br` segue sem
  classificação declarada (item 3).
- **`/r/antecipacao-saque-aniversario-fgts/`** — **zero link externo e onze
  bloqueios**: sem identidade de operador, sem contato, sem aviso de
  não-vínculo, marca de terceiro sem lastro. **A Fase A1 não foi executada.** É
  a contraprova 6 do briefing observada na página real, não numa fixture.
- **Cloaking refutado de novo**, com evidência nova: nos dois destinos o
  rastreador recebeu HTML de sha256 idêntico ao humano; zero redirecionamento.

Oito dos dez destinos `/r/` de `creditoup.com.br` e os quatro de
`portalmundomais.com` **não foram lidos**.

---

## 7 · O que NÃO foi feito, e por quê

- **Nenhuma migration, nenhuma tabela, nenhuma coluna.** O registro reusa
  `pautador_funnel_runs.paginas_publicadas jsonb`, que já existe e já é o
  contrato declarado com o módulo de campanha.
- **`volc_ads/pautador_ponte.py` não foi editado.** O buraco da URL manual
  continua lá como está descrito; o que foi fechado é o EFEITO — a URL manual
  passa pela avaliação ao vivo completa. A linha continua sendo dívida.
- **O CLI `python -m volc_ads.subir` não ganhou barreira 3.** O portão vive nas
  rotas, exatamente como o gate de mutação já declara sobre si mesmo.
- **Roadmap, curadoria e grafo não foram tocados.** Delta proposto em
  `CURATION-HANDOFF.json`; o integrador aplica **uma vez**, depois do merge.
- **`GATE-RECEIPTS.json` do pacote anterior não foi regenerado.** Seus cinco
  recibos foram emitidos contra `policy_source_version df252bc25e636d78` e a
  matriz agora é outra — pela regra da própria espinha, estão desatualizados.
  Regenerá-los quebraria as citações do pacote de apelação; não regenerá-los
  deixa o pacote citando uma versão que não existe mais. A decisão é do
  integrador; o delta v1→v2 vive num arquivo separado.
- **A notificação literal da suspensão continua não lida.** Nada aqui muda isso.

---

## 8 · Riscos que ficam de pé

Resumo; o texto completo é `REMAINING-RISKS.md`.

1. **A publicação mora num subprocesso.** Um portão em Python recusa DISPARAR;
   ele não para o motor no meio, e `funnelforge run … --publish` num terminal
   publica sem barreira nenhuma. É por isso que o portão dentro do motor não é
   opcional — e ele cai com um `git checkout` da pasta do motor.
2. **Pode existir um caminho de criação de campanha fora de `/subir`.**
   `canario.exigir` restringe a criação a um `customer_id`, e a conta suspensa
   mostrava campanhas que a tabela local não registrava. Se o caminho existir,
   **nenhuma das três barreiras cobre o caminho que causou o incidente.** Não foi
   possível determinar lendo código.
3. **Nenhuma das duas versões cobre os detectores.** Mover um código entre as
   tabelas de severidade muda o veredito com as duas versões idênticas.
4. **O portão lê HTML servido, não tela renderizada.** CSS de folha externa
   escondendo conteúdo continua invisível.
5. **Páginas publicadas antes desta sprint não têm recibo.** Elas reprovam na
   elegibilidade de campanha por `RECIBO_DE_APROVACAO_AUSENTE` — o que é a
   verdade, e é uma parada operacional real até que sejam reauditadas.

---

## 9 · O que este pacote NÃO afirma

Nenhum artefato desta sprint afirma, e nenhum pode ser citado como se
afirmasse:

- que a conta do Google está segura;
- que a suspensão foi resolvida;
- que qualquer página foi aprovada pelo Google;
- que a causa da suspensão é conhecida;
- que existe garantia contra nova suspensão;
- que algo está em produção;
- que qualquer tarefa do Roadmap está `done`.

O portão lê HTML. Ele não lê a intenção do revisor. `paid_destination_ready:
true` significa exatamente: *nesta avaliação, neste ponto de portão, contra esta
versão do contrato e desta matriz, não sobrou bloqueio nem desconhecido.*

Um portão que prometesse mais seria a mesma alegação forte sem evidência que ele
existe para impedir.
