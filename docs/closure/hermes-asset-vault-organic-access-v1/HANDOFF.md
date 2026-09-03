# Handoff — espinha de acesso orgânico: Cofre → 1Password → AdsPower → página

> **SUPERSESSÃO (2026-09-03, `sprint/asset-vault-operator-experience-v2`).**
> `backend/app/asset_vault/broker/` é **CANDIDATO NÃO INTEGRADO/SUPERADO**.
> Não está na árvore final. A autoridade canônica única de P03-T11 é
> `tools/adspower-broker/`. Inventário real de perfis/grupos **não** foi
> transplantado. Ver [`SUPERSEDED.md`](SUPERSEDED.md).

**Missão:** `hermes-asset-vault-organic-access-v1`
**Branch:** `sprint/hermes-asset-vault-organic-access-v1` · **base:** `c8ca8628e83742dd7da5242f0a015f76292aafe7`
**Data:** 02/09/2026 · **Sessão Claude:** `553b5b9d-aa0e-4e87-9981-766952b591c7`
**Mesclada?** Não. **Enviada (push)?** Sim. **Commitada?** Sim — HEAD `67ac4ac5ed184eb5c4107fe2ac9285f16d6eaf2f`.

---

## Resultado em uma frase

O sistema passou a **saber responder** as nove perguntas da operação orgânica —
qual página, de quem, com qual perfil, onde mora a credencial, se ela já foi
resolvida, se o perfil está disponível, se uma peça pode ser recebida no Cofre,
se o acesso pode ser operado, se pode publicar e o que impede cada portão — e ganhou o **broker do P03-T11** que só pergunta; o que
continua faltando não é código, é **um dado real que ninguém digitou** e **uma
autorização de escrita**.

---

## 1. As três frentes, e o que cada uma entregou

### A — prontidão da página real: **lista, não cadastro**

Procurei fonte autorizada de leitura para a identidade da Página e **não existe
nenhuma** nesta máquina (sem credencial Meta, sem AdsPower, sem 1Password).
Nada foi inventado. A entrega é a lista mínima de campos que faltam, derivada do
modelo versionado: **30 pendências** com perfil AdsPower, **16** sem ele.

→ [`CAMPOS-QUE-FALTAM.md`](CAMPOS-QUE-FALTAM.md)

O fluxo de onboarding (`scripts/onboarding_pagina_facebook.py`) **não foi
tocado**: ele já emite as seis operações corretas, recusa placeholder, recusa
segredo em qualquer campo, mascara o ID da página e recusa referência com query
string. Mexer nele sem poder rodar seu autoteste (56/56) seria trocar uma
ferramenta provada por uma não provada.

### B — broker 1Password ↔ AdsPower (**P03-T11**): nasce sabendo dizer não

`backend/app/asset_vault/broker/` — quatro camadas, dentro da fronteira do
Cofre, porque é o Cofre que sabe qual perfil pertence a qual ativo.

O critério de aceite do Roadmap, item a item:

| Exigência de P03-T11 | Onde |
|---|---|
| sidecar em **loopback** | `exigir_endereco_de_loopback` — só IP literal de loopback; recusa `local.adspower.net` (DNS é reconfigurável por quem controla a rede), `https`, userinfo na URL, porta implícita e caminho |
| **Bearer ativo** | `exigir_bearer` — fail closed; sem chave não há modo degradado |
| segredo **injetado em runtime** | o broker **não fala com o 1Password**. Ele roda sob `op run --` e consome uma variável; se o cofre estiver trancado, a variável chega com o `op://` literal e ele **para** (`blocked/segredo_nao_resolvido`) em vez de mandar o endereço como se fosse a chave |
| **allowlist de perfil/ação** | `ACOES` (4 ações, todas não-mutantes) + `exigir_perfil` contra lista explícita |
| **timeout** | `exigir_timeout` — 0,5 s a 60 s, padrão 12 s; sem teto, um sidecar travado vira um job travado |
| **idempotência** | mesma gramática de chave do Cofre; mesma chave + mesma entrada = replay visível; entrada diferente = conflito |
| **recibo sanitizado** | postura do Bearer (presente / origem / nome da variável), nunca valor; forma + digest da referência, nunca os segmentos |
| **porta externa falha no preflight** | sim, e na **construção** — um broker apontado para fora não chega a existir |
| **modo sem verificação falha no preflight** | `--no-verify`, `--insecure`, `--sem-verificacao`, `--no-auth`, `--no-masking` e cinco variáveis de ambiente |

Três decisões que merecem ser lidas antes de mexer:

1. **`muta` é declarado por ação, nunca inferido do verbo.** No AdsPower
   `browser/start` é um **GET** e abre um navegador. Um broker que classificasse
   por método HTTP acharia que está lendo.
2. **A resposta é montada por PROJEÇÃO, não por remoção.** O `user/list` do
   AdsPower devolve o perfil inteiro — e o perfil guarda a **conta que ele
   autentica**: usuário, senha, cookie e chave de 2FA. Filtrar por blocklist
   copiaria todo campo que o AdsPower adicionasse numa versão futura; a projeção
   copia só o que está nomeado (`CAMPOS_DE_PERFIL`), e o proxy vira um booleano.
3. **Abrir perfil é recusado pelo NOME**, com estado próprio
   (`blocked/exige_checkpoint`), e não como "ação desconhecida" — que faria a
   próxima pessoa supor erro de digitação e tentar de novo.

O `Segredo` recusa `str`, `repr`, `format`, `json`, `copy`, `deepcopy`, `pickle`
e `len` (comprimento estreita o espaço de busca de quem procura a chave). Ele
sai por **uma** porta: `.revelar()`, chamada em **um** lugar do código inteiro —
a linha que monta o cabeçalho `Authorization`.

### C — prontidão de operação: a ponte até a peça aprovada

`backend/app/asset_vault/prontidao.py` + `GET /api/cofre/ativos/{id}/prontidao`
+ o painel `ProntidaoDeOperacao` na tela.

Nove respostas: oito perguntas e a lista de bloqueios. **Três valores, nunca um
booleano** — `desconhecido` não é `não`:

> "não há perfil de navegador relacionado" é um **fato do inventário**;
> "não sei se o perfil está aberto" é a **ausência de uma observação**.
> As duas frases levam a ações diferentes: cadastrar um perfil, ou ir até a
> máquina. Achatá-las é como o painel aprende a dizer "perfil indisponível"
> sobre um perfil que ninguém olhou.

Cada resposta carrega `procedencia`: `registro` (das tabelas) ou `sonda` (do
broker, ao vivo). **Esta API só produz `registro`** — ela não alcança a Local
API do AdsPower, que escuta em loopback no outro host, e não resolve `op://`.
Um `sim` inventado ali seria a pior resposta possível.

`pronto_para_receber_peca` agora é separado de `pronto_para_publicar`: ausência de
`P12-T09` bloqueia publicação, mas não torna falsa a associação futura de uma peça
aprovada ao destino no Cofre.
"Por que não publica?" tem de ter resposta lida, não investigada.

---

## 2. Arquivos

### Novos

```
backend/app/asset_vault/broker/__init__.py
backend/app/asset_vault/broker/dominio.py           regras, recusas, projeção
backend/app/asset_vault/broker/aplicacao.py         casos de uso e portas
backend/app/asset_vault/broker/infraestrutura.py    ambiente injetado + loopback
backend/app/asset_vault/broker/cli.py               sidecar + autoteste sem rede
backend/app/asset_vault/prontidao.py                as nove respostas (puro)
backend/tests/test_cofre_broker.py                  49 funções de teste
src/features/asset-vault/prontidao.ts               contrato + guarda de forma
src/features/asset-vault/ProntidaoDeOperacao.tsx    o painel
src/features/asset-vault/__tests__/prontidao.test.ts
docs/closure/hermes-asset-vault-organic-access-v1/  este pacote
```

### Modificados

```
backend/app/asset_vault/aplicacao.py     + CasosDeUso.prontidao; handoff passa a
                                           importar COMPONENTES_SEGUINTES (fonte única)
backend/app/asset_vault/rotas.py         + GET /ativos/{id}/prontidao
backend/tests/test_cofre_ativos.py       + bloco 11 (10 testes); a varredura de
                                           op:// passa a cobrir handoff e prontidao
src/features/asset-vault/cofreApi.ts     + prontidao()
src/features/asset-vault/AssetVaultContent.tsx   + <ProntidaoDeOperacao/> no inspetor
src/features/asset-vault/__tests__/asset-vault.test.tsx  + fixture PRONTIDAO
```

**Ownership:** nada fora do escopo autorizado. `backend/app/criativo/**`,
`volc_ads/criativo/**`, n8n, tráfego, Orakul, `ROADMAP-VIVO.json`,
`curadoria-operacional.json` e arquivos de grafo: **zero mudanças** (gate 4).

Uma escolha de ownership que merece registro: `backend/tests/test_cofre_broker.py`
é arquivo novo. A autorização listava `backend/tests/test_cofre_ativos.py` e
"testes de segurança relacionados a segredos" — este é o segundo caso, e os
gates exigidos pedem "broker loopback/allowlist/revocation/fail-closed tests".
Se o integrador discordar, o caminho é mover o conteúdo, não apagá-lo.

---

## 3. Estado honesto das tarefas do Roadmap

**Nenhuma tarefa é promovida por esta missão.** Trabalho que só existe numa
worktree não marca a fonte compartilhada. A proposta está em
[`CURATION-HANDOFF.json`](CURATION-HANDOFF.json), para o integrador aplicar.

| Tarefa | Antes | Proposta | Por quê |
|---|---|---|---|
| **P03-T11** broker | `todo` | **`partial`** | O sidecar existe com loopback, Bearer, allowlist, timeout, idempotência, recibo sanitizado e as duas recusas de preflight. Continua parcial porque **nenhuma chamada real foi feita** a nenhum AdsPower, os caminhos da Local API não foram exercitados contra um cliente, e abrir perfil segue bloqueado por checkpoint |
| **P03-T06** tela | `partial` | `partial` (evidência nova) | A tela passou a mostrar prontidão, dono, finalidade, última revisão e bloqueios. A lacuna que mantém `partial` é a mesma: **a ligação ao grafo continua aberta** |
| **P03-T02** página | `todo` | `todo` | Continua sem um dado real. O que mudou é que a lista do que falta ficou explícita |
| **P03-T07** perfil AdsPower | `todo` | `todo` | Nenhum perfil inventariado. O broker sabe consultar; não há o que consultar |
| **P03-T10** referências | `partial` | `partial` | Nenhuma referência real persistida nem resolvida |
| **P12-T02** onboard | `todo` | `todo` | Falta o input humano |
| **P12-T09** porta de publicação | `todo` | `todo` | Não tocada. É o bloqueio que `prontidao` nomeia |

---

## 4. Restrições lidas nas fontes obrigatórias, e como foram respeitadas

| Fonte | Restrição | Como esta missão a respeitou |
|---|---|---|
| `ADR-SUPABASE-AUTORIDADE-OPERACIONAL.md` | único Supabase é `database.agenciavolc.com.br` | nenhuma URL nova de banco; zero escrita e zero leitura autenticada |
| `ADR-1PASSWORD-ADSPOWER-…` | 1Password guarda valor; Supabase guarda só referência; broker em loopback com Bearer; **modo sem verificação não é configuração VOLC** | o broker recusa os dois modos no preflight e nunca guarda valor |
| `COFRE-DE-ATIVOS-CONTRATO.md` | sete gavetas, 28 tipos, campos sensíveis proibidos | nenhum tipo, gaveta ou campo novo; a rota nova é leitura |
| `COFRE-HANDOFF-PRODUCAO-E-PUBLICACAO.md` | o handoff traz provider e nome lógico, **jamais o localizador**; quem resolve é o broker | `prontidao` copia a mesma assimetria; o broker resolve **fora** do processo, por `op run` |
| `ADR-DISTRIBUICAO-ORGANICA-E-QA-VISUAL.md` | falha do AdsPower **não** reprova a página; perfil entra como referência, sem segredo bruto | `desconhecido` é um valor de primeira classe; a projeção recusa cookie/senha/2FA |
| `CL-12-…` | "nenhum segredo bruto no Cofre/grafo/API" | provado por teste, não prometido |
| `AGENTS.md` / `CLAUDE.md` | worktree não fecha tarefa; delta de curadoria, integrador aplica | `CURATION-HANDOFF.json` é **proposta** |
| `asset-vault-onepassword-production-v1/**` | pare de digitar número; congele o medido | nenhuma contagem inventada — ver §5 |

---

## 5. Limitações — o que este pacote NÃO prova

1. **Os caminhos da Local API do AdsPower não foram verificados contra um
   cliente real.** Eles vêm da documentação citada no ADR. O risco é contido por
   construção: toda ação publicada é não-mutante, e o transporte recusa qualquer
   ação com `muta=True` mesmo que ela apareça no catálogo.
2. **A idempotência do broker vive no processo.** Um sidecar reiniciado esquece.
   A durabilidade mora no Cofre, quando o recibo virar verificação.
3. **O Mapa Vivo está defasado** e não foi reconstruído: `graphify-out/` não
   existe nesta worktree. Instrução explícita do Hermes — registrar, não
   consertar.
4. **`prontidao` assume que `detalhe.verificacao[0]` é a mais recente**, como a
   tela já assumia desde 01/09/2026. Se a ordenação do banco mudar, os dois
   mentem juntos.

---

## 6. Gates e commits

Claude Code concluiu a implementação, mas sua camada de permissão bloqueou a execução de `python3`, `node` e `git add`. Hermes/Bia executou os gates e commits **depois** do executor encerrar, sem implementação paralela.

Evidência principal em [`GATES.md`](GATES.md):

- `176 passed` nos testes focais backend/Cofre/broker;
- `56/56` no autoteste de onboarding;
- broker `--autoteste` e `--preflight` verdes;
- smoke 1Password CLI verde;
- smoke MCP bloqueado honestamente por binário ausente;
- `40 passed` no frontend Asset Vault;
- build frontend verde;
- TypeScript mantém baseline herdado de 76 erros, com **0** em `src/features/asset-vault`;
- backend completo falha apenas em testes de `criativo`, fora do ownership;
- `git diff --check`, ownership e scanners de segredo verdes.

Os commits atômicos foram criados pela coordenadora Hermes/Bia após os gates e publicados somente na feature branch.

---

## 7. O próximo ato, em ordem

1. **Operador preenche a ficha** ([`CAMPOS-QUE-FALTAM.md`](CAMPOS-QUE-FALTAM.md)).
2. **Uma autorização** ([`CHECKPOINT-AUTORIZACAO.md`](CHECKPOINT-AUTORIZACAO.md))
   cobrindo: persistir página/perfil/referência, relacionar, resolução efêmera e
   consulta somente-leitura ao AdsPower.
3. Aplicar as seis RPCs governadas e **provar pelo readback**.
4. Rodar o broker no host do AdsPower, sob `op run`, em `--preflight` e depois
   `--acao inventario_perfis`.
5. O recibo do broker vira verificação no Cofre (`alvo: "credencial"`), e
   `prontidao` passa a responder pela **sonda** onde hoje responde `desconhecido`.
6. Só então P12-T09 (porta de publicação) entra em cena — e **publicar continua
   sendo um ato separado, com aprovação própria**.

## 8. Placar de ações externas: zero

Zero publicação · zero deploy · zero migration · zero escrita no Supabase
oficial · zero leitura autenticada no Supabase oficial · zero abertura de perfil
ou navegador AdsPower · zero consulta real ao 1Password · zero segredo lido, medido,
hasheado ou derivado · zero merge · push somente da feature branch · zero edição de Roadmap,
curadoria ou grafo.


---

## Microcorreção final

Após aceite no mérito como candidata `partial`, esta branch recebeu uma correção limitada:

- closure atualizado para refletir branch publicada, HEAD/SHA remoto e árvore limpa;
- estado do broker no produto separado do estado editorial do Roadmap;
- portões separados: receber peça, operar acesso e publicar;
- `publica` preservado como `false`.
