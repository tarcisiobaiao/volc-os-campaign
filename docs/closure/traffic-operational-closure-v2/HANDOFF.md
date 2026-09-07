# Fechamento R0 — Meta estático recuperável, candidato local

Marco **R0** do pacote [`docs/specs/traffic-operational-closure-v2/`](../../specs/traffic-operational-closure-v2/GUIDE-EXECUCAO.md).

| | |
|---|---|
| Veredito | `META_R0_RECOVERABLE_LOCAL_CANDIDATE_READY` |
| Base inspecionada | `d54e100` |
| SHA testado | `a1454b4` |
| Branch | `execution/volc-os-operacao-80-20` |
| Worktree | `/private/tmp/volc-os-operacao-80-20` |
| Push | **não** |
| Conta Meta ou Google | **nenhuma chamada** |
| Supabase oficial | **nenhum acesso** |

O recibo executável, com gates, comandos e resultados, está em
[EXECUTION-RECEIPT.json](EXECUTION-RECEIPT.json).

## 1. O que passou a funcionar

**A peça é conferida de verdade.** O gate lia `Content-Type`, conferia o tamanho
e hasheava — nunca abria a imagem. Um corpo com o literal `NOT_AN_IMAGE`
rotulado `image/png` era selado como `AUTHORIZED` / `READY_FOR_PAID_MEDIA`, com
as dimensões copiadas do inventário. A prova de que a suíte media a ausência do
gate está nas próprias fixtures antigas: elas serviam `b"bytes-imagem-meta"` —
dezessete bytes de ASCII — e o caminho feliz inteiro ficava verde.

Agora a imagem é decodificada, o tamanho é julgado a partir do cabeçalho antes
de qualquer `load()`, o teto de bytes é cobrado **durante** o streaming, e as
dimensões vêm da medição. Uma miniatura de 128px deixa de ser certificada como a
peça: rotular com honestidade não bastava enquanto o selo ao lado dizia
`READY_FOR_PAID_MEDIA`.

**A fronteira HTTP fecha.** Os seis modelos de entrada rodavam com o padrão do
pydantic v2, `extra='ignore'`. Objetivo, faixa etária, países, placements e
`promoted_object` são fixos nesta receita — e `image_hash`, `page_id` e
`shop_redirect_proof` são do servidor. Todos eram absorvidos em silêncio, com
200. Hoje viram 422 nomeando o campo.

**A recuperação parou de fazer perguntas sobre o presente.** `/reconciliar`
recompilava: abria o Keychain, relia a conta, rebaixava os bytes do CDN. Como a
atestação de direitos vale uma hora e a aprovação vale quinze minutos, um passo
ambíguo só era recuperável dentro de uma janela que fecha sessenta minutos depois
de um clique feito **antes** de aprovar. Passada a janela, a recuperação
histórica era impossível — embora os objetos pudessem existir na conta.

Agora a aprovação congela o plano despachável, e criar e reconciliar leem esse
plano. `descongelar_plano` **recalcula** a identidade em vez de lê-la: um
snapshot é uma autorização de gasto guardada num banco, e uma linha editada por
fora não vira payload.

**O passo órfão deixou de ser invisível.** A rota filtrava `state == 'AMBIGUOUS'`
e nada mais. Um passo preso em `IN_FLIGHT` produzia a resposta
`passos_ambiguos: 0` — indistinguível de "nada travado" — enquanto o índice de
gêmeo entre aprovações o tratava como reivindicação viva e bloqueava
**permanentemente** qualquer aprovação futura daquele objeto.

**O recibo sobrevive ao reload.** A rota `POST /recibo` existia no backend e não
tinha cliente; o `approval_id` vivia só em `useState`. Fechar a aba apagava a
saída segura de um incidente. Pior: os controles de recuperação moravam dentro
do bloco condicionado à flag de criação — fechar a criação no servidor fechava
junto o recibo e o botão de reconciliar.

## 2. O que foi efetivamente testado

| Gate | Resultado |
|---|---|
| `pytest -k "meta"` | **278 passed** (baseline do lote: 129) |
| `scripts/gates-backend.sh` (suíte inteira) | 5 failed, **4083 passed**, 88 skipped |
| `vitest run src/pages/trafego/__tests__/` | **75 passed** (8 arquivos) |
| `vite build` | exit 0 |
| `tsc --noEmit` | 77 erros no projeto — o mesmo número histórico — e **zero** nos arquivos tocados |
| [`prova-sql-local.sh`](prova-sql-local.sh) | sete etapas, todas passando em PostgreSQL 17.9 descartável |

As **cinco falhas da suíte** estão nomeadas uma a uma no recibo. Nenhuma está na
lane Meta e nenhuma importa arquivo que este lote alterou: quatro são de
Google/n8n e uma é artefato de `cwd` (lê um path relativo e passa quando roda da
raiz). **Não** as reexecutei contra a base para prová-las vermelhas antes —
stash, reset e checkout destrutivo estão proibidos nesta missão, e abrir outra
worktree também. A evidência é indireta e está declarada como tal.

A prova SQL é o que mais importa aqui, porque é a única que exercita a fronteira
de autorização com os **papéis reais** em vez de superusuário: `anon` e
`authenticated` recusados na função, `service_role` **sem `INSERT` direto** nas
tabelas, e duas sessões concorrentes no mesmo passo produzindo exatamente **um**
`DESPACHAR`. E o invariante central, medido: com a aprovação `EXPIRED`,
`prepare_step` recusa (`META_APPROVAL_NOT_ACTIVE`) e o `reclaim` do órfão
**funciona** — expiração fecha novo despacho, não a recuperação.

### A revisão encontrou quatro P1 meus, e eles estão corrigidos

Uma rodada focal em cinco lentes, com verificação adversarial. O mais grave foi
apontado por **quatro lentes independentes**: o tratamento da divergência lia
`locals().get("dados")`, e `dados` é de escopo de função, não de iteração —
quando o read-back falhava no AdSet, a evidência durável era gravada com o
status e o objetivo do objeto **anterior**. Um recibo que descreve o objeto
errado é pior que um recibo vazio: ele parece adjudicável.

Os outros três: a referência da operação só entrava na URL no caminho de
sucesso, deixando o despacho ambíguo sem nada para reabrir; um recibo sem passos
aparecia como "Criada pausada" (`every` de lista vazia é `true`); e a miniatura
certificada. Todos em `a1454b4`.

Dois P2 confirmados ficam **declarados e não corrigidos**, com localização:
a correlação temporal em `reconciliacao.py:241-261` é de um lado só (um objeto
com `created_time` muito posterior a `prepared_at` passa), e a releitura do
manifesto em `trafego_meta_criacao.py` é condicionada a uma promoção
bem-sucedida, então numa corrida a rota pode responder sobre um manifesto
levemente velho. Nenhum dos dois cria despacho ou ativação.

## 3. O que ainda não pode ser afirmado

- **Nada sobre a conta Meta.** Zero chamadas. A máscara de `AdCreative` sem
  `effective_status` tem duas fontes oficiais concordantes, mas ausência no
  catálogo é sinal de risco, não prova de recusa da Graph.
- **Nada sobre o schema oficial.** O catálogo não foi lido. O manifesto **não**
  afirma que qualquer perfil esteja ausente, parcial ou aplicado no self-hosted.
- **Nenhum pixel.** Não houve inspeção visual autenticada. jsdom não prova pixel,
  foco real, 390px/1440px, claro/escuro nem `reduced-motion`. Os 75 testes de UI
  são harness, e HTTP 200 da SPA não prova fluxo nem autenticação.
- **O destino website-only continua bloqueado, com causa.** Três consultas
  oficiais independentes nesta rodada não estabelecem a semântica de
  `destination_spec` nem a aplicabilidade de Shop a esta receita. A premissa foi
  **mantida**; o que mudou é o diagnóstico da prova — ver
  [META-DESTINATION-EVIDENCE.json](META-DESTINATION-EVIDENCE.json).
- **A curadoria e o grafo descrevem a base, não o HEAD.** Quatro commits mudaram
  código e schema; nenhum rebuild foi executado, porque editar essas autoridades
  não está autorizado nesta janela. O delta proposto está em
  [CURATION-DELTA.json](CURATION-DELTA.json).

### Uma mudança de hash, declarada

Os valores medidos da peça entram no recibo de supply, logo no `plano_sha256`. A
revisão adversarial apontou o preço corretamente: enquanto `/reconciliar`
recompilasse, toda aprovação anterior passaria a falhar com
`META_APPROVED_PLAN_DIVERGED` — recuperação histórica bloqueada.

A correção não foi desistir da medida, que o contrato exige, e sim tirar a
recompilação do caminho — que é o que T03 manda. A mudança é versionada
(`meta-supply-v2`, `meta-compilador-v2`), e aprovação sem snapshot recebe
`META_LEGACY_RECOVERY_REQUIRED` com o recibo ainda legível, em vez de ser
reconstruída em silêncio.

## 4. O próximo ato mínimo do operador

**Conferir a bancada, autenticado como ADMIN:**

```
http://localhost:8080/trafego/meta/nova?etapa=revisao
```

O vite **desta** worktree já está de pé (PID com `cwd` em
`/private/tmp/volc-os-operacao-80-20`); nenhum processo de outro terminal foi
tocado. Para ver o recibo reabrível, acrescente `&operacao=<approval_id>` — é a
referência opaca, e é a única coisa que viaja na URL.

Não pedi nem usei sessão autenticada, e não vou pedir senha em chat. Sem essa
inspeção, os pixels continuam **não verificados**.

**Depois, escolher UMA janela externa.** As duas são independentes e nenhuma
delas cria objeto:

- **CP2 — schema.** Siga [SCHEMA-RUNBOOK.md](SCHEMA-RUNBOOK.md), classificando o
  estado do catálogo **antes** do apply e conferindo os `sha256` no momento da
  janela.
- **CP3 — leitura de conta.** Escopo mínimo, passos 1 e 2 do `external_proof_plan`
  em [META-DESTINATION-EVIDENCE.json](META-DESTINATION-EVIDENCE.json).

## 5. Commits e árvore

```
a1454b4  fix(meta): rodada corretiva da revisao focal — quatro P1 do proprio delta
9b7c519  fix(meta): recibo reabrivel e concorrencia honesta na bancada (T04)
24ad9a1  fix(meta): congelar o plano despachavel e enxergar o passo orfao (T03)
b7c2915  fix(meta): decodificar a peca de verdade e vincular o recibo de supply (T02)
21fb1f2  fix(meta): fechar a fronteira HTTP e tirar effective_status do AdCreative (T01)
07f8e26  docs(specs): preservar pacote traffic-operational-closure-v2 recebido
d54e100  (base inspecionada pelo spec)
```

Árvore limpa fora desta pasta de fechamento. Nenhum `git add` indiscriminado:
todo commit lista os paths. Nenhum stash, reset, merge, rebase ou amend; nenhuma
branch ou worktree nova; `origin`, `main` e `volc-os-v2` intocados.

**A worktree indicada na missão** (`…-80-os-campaign`) não existe. A única é
`…-80-20`, que é a que todos os paths canônicos da própria missão citam, a que o
`GUIDE-EXECUCAO.md` indica e a que roda o 8080. Trabalhei nela.

## 6. Coexecução

`Codex gpt-5.5` (reasoning high, read-only, briefing sanitizado) propôs as duas
migrations de T03. Integrei depois de adjudicar: **corrigi** o salt do lock
consultivo de 1602 — namespace do *plano* no `CREATE_ONLY` — para 1604, e
**mantive** duas defesas que ele acrescentou e eu não havia pedido: o `CHECK` de
pacote (os três campos do snapshot são os três ou nenhum) e, no read-back, a
exigência de um booleano `matched` coerente com o código, mais uma varredura
recursiva que recusa chave sensível na evidência.

`gemini-3.1-pro` estava disponível e **não foi acionado** — registro para não dar
a impressão de uma checagem independente que não aconteceu.

## 7. Arquivos deste fechamento

| Arquivo | O que é |
|---|---|
| [EXECUTION-RECEIPT.json](EXECUTION-RECEIPT.json) | O recibo executável: tarefas, gates, capacidades, bloqueios |
| [SCHEMA-DEPLOY-MANIFEST.json](SCHEMA-DEPLOY-MANIFEST.json) | Perfis, arquivos exatos, ordem, hashes, rollbacks excluídos do apply |
| [SCHEMA-RUNBOOK.md](SCHEMA-RUNBOOK.md) | O procedimento da janela CP2 |
| [prova-sql-local.sh](prova-sql-local.sh) | A prova SQL reproduzível, em cluster descartável |
| [META-DESTINATION-EVIDENCE.json](META-DESTINATION-EVIDENCE.json) | Adjudicação do destino website-only e o plano de prova externa |
| [CURATION-DELTA.json](CURATION-DELTA.json) | Delta de curadoria **proposto, não aplicado** |
