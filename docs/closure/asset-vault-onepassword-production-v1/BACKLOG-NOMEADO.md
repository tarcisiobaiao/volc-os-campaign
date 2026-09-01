# Backlog nomeado — o que esta missão NÃO resolveu

> ## ⚠️ Os números deste documento envelheceram, e isso tem conserto
>
> Este pacote foi escrito enquanto a branch ainda andava. Uma revisão de contrato
> em 01/09/2026 encontrou **nove números errados** aqui — "75 provas" quando eram
> 92, "47 testes" quando eram 67, contagens de linha e um HEAD anteriores.
> Nenhum era mentira: eram verdadeiros no minuto em que foram escritos.
>
> O conserto não é "revisar melhor". É não digitar número nenhum:
> **[`GATES.md`](GATES.md) é a fonte corrente**, gerada por
> `./scripts/medir-gates-cofre.sh`. Onde este texto divergir dela, vale ela —
> e a divergência é sinal de que alguém precisa rodar o script de novo.

Pendência nomeada é pendência que alguém pode pegar. Cada item aqui diz **o que
falta**, **por que não foi feito** e **o que já existe** para quem for fazer.
Tudo medido em 01/09/2026, na worktree `/private/tmp/volc-asset-vault-1p-v1`,
com HEAD em `664272f`.

Nenhum item abaixo é especulação: cada número foi medido nesta sessão, e onde
não foi, está escrito que não foi.

---

## (a) O 422 com `input` continua nos outros routers do backend

**O que falta.** O defeito 2 de `EVIDENCIAS.md` — o handler padrão de
`RequestValidationError` serializa `exc.errors()`, e cada erro do Pydantic v2
carrega `input`, o **valor rejeitado** — foi consertado só dentro de
`/api/cofre`. Ele continua vivo em todo o resto do backend.

**Quanto.** Medido por AST nesta sessão, com fecho transitivo de herança (um
modelo que herda de outro modelo também conta):

| Router | Modelos | Rotas com corpo Pydantic |
|---|---|---|
| `backend/app/routers/criativos.py` | 2 | **2** |
| `backend/app/routers/criativos_execucao.py` | 2 | **2** |
| `backend/app/routers/publicacao.py` | 13 | **2** |
| `backend/app/routers/trafego.py` | 22 | **7** |
| `backend/app/routers/trafego_inventario.py` | 4 | **4** |
| `backend/app/routers/entities.py` | 0 | 0 |
| `backend/app/routers/pautador.py` | 0 | 0 |
| `backend/app/routers/trafego_diagnostico.py` | 0 | 0 |
| `backend/app/routers/work_road.py` | 0 | 0 |
| `backend/app/asset_vault/rotas.py` | 11 | **0** ← consertado |

**5 routers, 114 rotas.** E `grep -rn "RequestValidationError\|exception_handler"`
fora de `asset_vault` retorna **vazio**: não há handler global sobrescrevendo o
padrão, então essas 114 rotas usam o handler que ecoa `input`.

**Por que não foi consertado.** Handler de exceção no FastAPI é de **app**, não
de router. Consertar globalmente mudaria o **contrato de erro** de 114 rotas que
não são desta missão — clientes que hoje leem `detail[].loc` passariam a receber
outra forma. Isso é uma mudança de contrato, e mudança de contrato precisa de
dono, inventário de consumidores e janela própria. Fazer por conta própria, no
meio de uma entrega de Cofre, seria exatamente o tipo de mistura que o CLAUDE.md
proíbe: "não misture reorganização estrutural ampla com mudança funcional ampla
no mesmo lote".

**Nota de severidade honesta.** Nem toda rota dessas trafega credencial, e o
vazamento só ocorre no **valor que falhou a validação**. O Cofre foi priorizado
porque lá o valor recusado é, por definição, a credencial. Nas outras 17 o risco
é menor, **mas não é zero** — qualquer campo mal preenchido volta literal para o
cliente e para o log.

**O que já existe para quem for fazer.** `backend/app/asset_vault/rotas.py:84`
(`_corpo_json`) e `:95` (`_validado`) são o padrão pronto: mensagem montada de
`loc` + `msg`, nunca de `input`, com uma varredura final de material de
credencial como cinto e suspensório. Alternativa mais barata para o resto do
backend: **um handler global** que reserialize `exc.errors()` removendo `input`
e `ctx` — o custo, aí, é combinar a nova forma com os consumidores.

---

## (b) A migration v13_01 não foi aplicada em produção

**O que falta.** Aplicar `supabase/migrations/v13_01_cofre_de_ativos.sql` em
`database.agenciavolc.com.br`. Sem isso, nada do Cofre existe fora do
laboratório: a API responderia 503, e a tela mostraria "o Cofre não respondeu".

**Medido nesta sessão** (consulta somente leitura, produção):

```
$ ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
    "docker exec -i supabase-db psql -U postgres -tAc \"SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'cofre\_%';\" ; \
     docker exec -i supabase-db psql -U postgres -tAc 'SHOW server_version;'"
0
15.8
```

Zero tabelas `cofre_*`. Produção é PostgreSQL **15.8**; o harness prova em
**15.19** — mesma major, e a diferença está registrada de propósito, porque
harnesses anteriores pediam `postgresql@16` sem conferir divergência.

**Por que não foi feito.** Aplicar schema em produção exige autorização
separada, e esta missão não a tem. O commit `2c4a6b6` já diz isso na última
linha: "NAO aplicada em producao. Exige autorizacao separada."

**O que já existe para quem for fazer.**

- O ciclo prova que ela é **aplicável, operável, reversível e reaplicável**: 81 provas, exit 0.
- A migration tem guardas próprias que **abortam** onde a pré-condição não vale — papel, versão, e a travessia de RLS (`v13_01_cofre_de_ativos.sql:2094`).
- Ela **recusa reaplicação por cima**: `✓ recusada com as tabelas ja existentes`.
- O rollback existe: `supabase/migrations/v13_99_cofre_de_ativos_rollback.sql`.

⚠️ **O rollback apaga dado que não tem outra cópia** — inventário, trilha
append-only e as referências de credencial (os segredos em si continuam no
1Password; o que se perde é o mapa de qual ativo usa qual item). O próprio
arquivo traz, no cabeçalho, os nove `\copy` de exportação que devem ser rodados
antes. Isso é um risco operacional nomeado, não um detalhe.

---

## (c) O 1Password não está instalado nesta máquina

**O que falta.** Instalar o app e o CLI, ligar
`Settings > Developer > 'Integrate with 1Password CLI'`, e rodar o smoke com uma
referência real.

**Medido nesta sessão**, comando a comando:

| Comando | Saída |
|---|---|
| `command -v op` | (ausente) |
| `ls -d /Applications/1Password.app` | `No such file or directory` |
| `env \| grep -c '^OP_'` | `0` |
| `command -v 1password-mcp` | (ausente) |
| `grep -c 1password ~/.claude.json` | `0` |

**Por que não foi feito.** Instalar software de gestão de segredos na máquina do
dono, autorizar um ambiente e criar um item de teste num cofre real são atos que
pertencem ao dono, não a um agente. E instalar sem isso produziria exatamente o
que o smoke existe para impedir: um "ok" que não significa nada.

**O que já existe para quem for fazer.** O smoke sai `blocked/cli_ausente`
(exit 10) hoje, e o campo `proximo_ato` do recibo é literalmente o passo a
passo. Quando o ambiente existir, `--referencia 'op://<vault>/<item>/<campo>'`
fecha a cadeia. Os dez estados e seus exit codes estão em
`tools/onepassword-smoke/run.py:46-59`.

---

## (d) O smoke cobre o CLI, e a tarefa P03-T09 diz "MCP"

**O que falta.** O servidor MCP do 1Password — `system:onepassword-mcp` no
grafo, `todo` — não foi instalado, configurado nem chamado. A cadeia que o
instrumento prova é **CLI `op` → app → sessão → injeção**, como o próprio
`tools/onepassword-smoke/README.md:3` declara.

**Por que não foi feito.** Depende inteiramente de (c). E é uma distinção que
não pode ser dissolvida: o MCP expõe segredos a um **agente**, com aprovação por
ambiente e visibilidade só de nomes; o CLI expõe a um **processo**. As duas
superfícies têm ameaças diferentes e merecem provas diferentes.

**Consequência para o roadmap.** `DELTA-CURADORIA.json` propõe P03-T09 como
`partial` **e diz explicitamente que `todo` continua defensável** se o
integrador ler o título ao pé da letra. A aresta proposta no grafo é
`tool:onepassword-smoke --nao_comprova_operacao_de--> system:onepassword-mcp`,
que é a relação honesta.

---

## (e) O broker que resolve `op://` não existe

**O que falta.** O componente que, no host isolado e com o papel `postgres`,
recebe provider + nome lógico e devolve o valor montado numa variável de
ambiente efêmera.

**Por que isso é uma pendência e não um esquecimento.** É deliberado, e a
assimetria é o ponto do handoff: `GET /api/cofre/ativos/{id}/handoff` traz
`referencia_de_acesso` com provider e **nome lógico**, e **nunca** o localizador.
Um handoff que já viesse com o endereço resolvido transformaria a rota na porta
do cofre — bastaria uma sessão ADMIN comprometida para enumerar todos os
endereços da operação de uma vez.

**O que já existe.** O contrato da fronteira, em
`docs/architecture/COFRE-HANDOFF-PRODUCAO-E-PUBLICACAO.md`, e a prova de que a
API não atravessa essa linha:
`backend/tests/test_cofre_ativos.py:647` — `test_o_handoff_NAO_devolve_o_localizador`.

---

## (f) A tela não escreve nada no grafo — a segunda metade de P03-T06

**O que falta.** O título da tarefa é "Criar a tela Cofre de Ativos **e ligá-la
ao grafo**". A primeira metade avançou (a tela lê `/api/cofre`, não a fixture,
e opera cadastro, revisão, relação, verificação, aposentadoria e reativação). A
segunda não foi tocada: **nenhuma** correspondência entre ativo do Cofre e nó do
Mapa Vivo é escrita, lida ou proposta.

**Por que não foi feito.** Escrever no grafo a partir da tela colidiria com a
regra de fechamento do CLAUDE.md: em trabalho paralelo, quem produz entrega um
**delta**; só o integrador aplica e reconstrói. Uma tela que escreve na curadoria
seria um segundo escritor na fonte humana, que é justamente o que o
`_guarda_fonte_humana` existe para impedir.

**O que precisa ser decidido antes de fazer.** Se a ligação é (1) uma coluna de
referência no `cofre_ativo` apontando para um id do grafo, (2) um delta emitido
para revisão humana, ou (3) uma correspondência derivada por nome. As três têm
custos de manutenção muito diferentes e nenhuma foi escolhida.

---

## (g) A worktree continuou mudando depois da medição

**O fato.** Este pacote foi montado enquanto a missão ainda produzia. A primeira
rodada de gates mediu `1ddccf0`; três commits entraram (`4c213de`, `aea3b3c`,
`664272f`) e **todos os gates foram rerodados** contra `664272f`. Ao fechar o
pacote, `git status --short` mostrava:

```
 M backend/app/asset_vault/dominio.py
 M supabase/migrations/v13_01_cofre_de_ativos.sql
?? docs/closure/asset-vault-onepassword-production-v1/
?? scripts/onboarding_pagina_facebook.py
```

Só `docs/closure/asset-vault-onepassword-production-v1/` é deste pacote.

**O que isso significa.**

1. Os números deste pacote valem para `664272f`. As mudanças não commitadas em
   `dominio.py` e na `v13_01` **não foram medidas nem avaliadas** aqui.
2. `scripts/onboarding_pagina_facebook.py` (1647 linhas, não rastreado) declara
   atacar P03-T02, P12-T02 e P03-T07: ele lê uma ficha preenchida por quem tem
   acesso à página e emite os payloads que o Cofre aceita. Não é deste pacote e
   nada aqui se apoia nele.
3. ⚠️ **Este diretório recebeu arquivos que não são deste pacote.** Enquanto
   ele era montado, o agente irmão criou aqui `PEDIDO-AO-OPERADOR.md` (a ficha
   humana: o que pedir a quem tem acesso à Página, sem senha nem token) e
   `FICHA-PAGINA-MODELO.json` (o modelo que
   `scripts/onboarding_pagina_facebook.py --ficha` consome). Esta missão criou
   exatamente quatro arquivos — `README.md`, `EVIDENCIAS.md`,
   `DELTA-CURADORIA.json` e `BACKLOG-NOMEADO.md` — e **nada aqui mede ou avaliza
   os outros dois**. Quem for auditar o pacote precisa saber de qual metade cada
   arquivo veio.

**O que precisa ser decidido.** Se duas frentes devem compartilhar worktree.
Enquanto compartilharem, todo pacote de fechamento tem de declarar o SHA que
mediu — como este declara — e reconferir antes de aplicar qualquer delta.

---

## (h) A branch não está mesclada, e o Mapa Vivo não foi reconstruído

**O que falta.** Merge de `sprint/asset-vault-onepassword-production-v1`,
aplicação do delta pelo integrador, e `python3 scripts/atualizar_grafo_volc_os.py`
seguido de `--check`.

**Por que não foi feito.** É o protocolo: "Trabalho que só existe numa
branch/worktree não pode marcar a fonte compartilhada como concluída", e
"investigadores, revisores e writers isolados não disputam Roadmap/curadoria.
Eles entregam um delta de curadoria; o integrador único aplica e reconstrói uma
vez após o merge."

**Consequência.** Enquanto isso não acontecer, `ROADMAP-VIVO.json` continua
dizendo `todo` para P03-T10 e `partial` para P03-T06 — **e está certo**.
O `--check` do grafo não foi rodado nesta missão porque rodá-lo aqui mediria o
frescor de uma árvore que não é a `main`.

---

## (i) Dívidas herdadas que continuam abertas e são visíveis daqui

Nenhuma é desta missão. Estão aqui porque foram **medidas** nesta sessão e
qualquer pessoa que rode os gates vai encontrá-las.

**76 erros de `tsc`**, zero em `asset-vault`. Distribuição medida:
`supabaseDataService.ts` 31, `ProjectDashboard.tsx` 12,
`AddOpportunityModal.tsx` 8, `healthChecks.ts` 7, e a cauda.

Destes, **14 são `TS2304` ("Cannot find name")** — bomba de runtime, não ruído
de tipo. ⚠️ O `CLAUDE.md` diz **12**; a medição de hoje dá **14**, e os dois a
mais são `SiteAnalysis.tsx(68,36)` e `(95,29)`, ambos
`generateCampaignAnalysisData`. Vale corrigir o número no `CLAUDE.md`.

```
src/components/dashboard/SiteAnalysis.tsx(68,36)  → Cannot find name 'generateCampaignAnalysisData'.
src/components/dashboard/SiteAnalysis.tsx(95,29)  → Cannot find name 'generateCampaignAnalysisData'.
src/pages/ProjectDashboard.tsx(544,9)  → Cannot find name 'setCustomDate'.
src/pages/ProjectDashboard.tsx(545,9)  → Cannot find name 'setRangeStartDate'.
src/pages/ProjectDashboard.tsx(546,9)  → Cannot find name 'setRangeEndDate'.
… (os mesmos três nomes repetidos em 568-570 e 594-596)
src/services/supabaseDataService.ts(1996,11)  → Cannot find name 'spendError'.
src/services/supabaseDataService.ts(1997,57)  → Cannot find name 'spendError'.
src/services/supabaseDataService.ts(1998,15)  → Cannot find name 'spendError'.
```

**7 arquivos de teste falhos no vitest completo**, nenhum em `asset-vault`
(medido com HEAD em `1ddccf0`; a suíte inteira não foi reexecutada depois de
`664272f`, só a de `asset-vault`, que passa 21/21). Seis colapsam na importação
com `Error: Missing Supabase environment variables` (`src/lib/supabase.ts:7:9`)
— é `.env` ausente nesta worktree, não lógica quebrada. O sétimo é
`wizard-smoke.test.tsx` (Meta CAPI), com 2 testes falhos:
`AssertionError: expected '1Site e pixeldomínio, pixel e token2E…' not to contain 'Edge Function'`.

⚠️ **Não confirmei que esse é o mesmo baseline de `36bec04`.** Medir exigiria um
checkout, que esta missão não pode fazer.

---

## (j) Pendências menores, mas reais

**O schema de request do Cofre sumiu do OpenAPI.** Custo assumido do conserto do
422: como o corpo é lido cru, o FastAPI não sabe mais a forma esperada. Já não
era publicado por padrão (`VOLC_DOCS_ABERTAS`), e o contrato continua legível nos
modelos `_Estrito` em `backend/app/asset_vault/rotas.py:133-269`. Mas quem
consome a API por documentação gerada perde a página.

**A gramática de referência cobre cinco providers e nenhum mais.**
`cofre_localizador_valido` (`v13_01:197`) conhece `1password`, `bitwarden`,
`vaultwarden`, `passbolt` e `infisical`; qualquer outro cai em `ELSE false`.
Isso é fail-closed e está certo — mas significa que adotar um sexto provider é
uma migration, não configuração.

**`?attribute=otp` é recusado de propósito.** MFA não entra no Cofre nem por
referência (`PROVA ok: referencia op:// com ?attribute=otp | 22023 ~ forma
esperada`). Se algum dia isso precisar mudar, é decisão de ADR e não de regex.

**O lock do 1Password nunca foi testado como revogação.** O critério de aceite
de P03-T09 pede que travar o app revogue o acesso. Impossível verificar sem (c).

**Não há `timeout` nem `gtimeout` nesta máquina.** Documentado em
`tools/onepassword-smoke/README.md`; por isso todo limite de tempo do smoke é
`subprocess.run(timeout=...)` do Python. Quem for portar o smoke para outra
máquina não deve reintroduzir a dependência do binário.

**O importador nunca escreveu no Supabase oficial.** Ele emite payloads e foi
provado ponta a ponta **contra o schema real num cluster descartável** — 7
engines entram, reaplicar o mesmo SQL não duplica, zero linha com caminho de
disco ou e-mail. Contra produção, nada: ver (b).

**A verificação de credencial exige `nome_logico` quando há mais de uma
referência.** É o conserto do defeito 10, e está certo — mas é uma mudança de
ergonomia: quem chamar `POST /ativos/{id}/verificacoes` com `alvo='credencial'`
num ativo com duas referências recebe `22023` em vez de um 201. Está provado
(`PROVA ok: verificar credencial sem dizer QUAL, com duas referencias | 22023 ~
informe nome_logico`) e documentado, mas quem integrar precisa saber.
