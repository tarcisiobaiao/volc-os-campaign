# Evidências — Cofre de Ativos + 1Password

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

Base `36bec04` → HEAD `664272f`, branch `sprint/asset-vault-onepassword-production-v1`.
Sete commits, 21 arquivos, +9776 −475.
Tudo medido em 01/09/2026 na worktree `/private/tmp/volc-asset-vault-1p-v1`.

Cada defeito tem quatro partes, e nenhuma delas é opinião: **o defeito**, a
**contraprova** que o expôs (comando e saída literal), a **correção** em
`arquivo:linha`, e a **prova de que não volta** (nome do teste).

Onde a contraprova foi reproduzida nesta sessão, a saída está colada. Onde ela
só existe no registro do commit, está dito que só existe lá.

⚠️ **Todo `arquivo:linha` deste documento está ancorado no commit `664272f`.**
O HEAD se moveu durante a montagem deste pacote — a primeira rodada de gates
mediu `1ddccf0`, três commits novos entraram, e **todos os gates foram
rerodados**. Os números abaixo são os da segunda rodada. Para conferir uma linha
citada aqui:

```bash
git show 664272f:backend/app/asset_vault/rotas.py | sed -n '84,113p'
```

---

## Índice dos defeitos

| # | Defeito | Onde | Commit | Reproduzido nesta sessão? |
|---|---|---|---|---|
| 1 | CHECK do Postgres ecoa a linha recusada em `DETAIL` | banco | `2c4a6b6` | sim |
| 2 | 422 do FastAPI ecoa o campo `input` | backend | `beeb9e7` | sim |
| 3 | Regex com contagem 2000 acima do teto 255 do Postgres | banco | `dc2208e` | sim |
| 4 | `FORCE RLS` sem policy exigiria que o dono atravesse RLS | banco | `2c4a6b6` | sim (produção, leitura) |
| 5 | `_traduzir` engolindo `HTTPException` | backend | `beeb9e7` | sim |
| 6 | `desfazer_relacao` sem validação de corpo | backend | `beeb9e7` | por leitura |
| 7 | `useQuery` disparando sem base configurada | frontend | `1ddccf0` | por leitura + teste |
| 8 | Navegação de 4 lentes inerte | frontend | `1ddccf0` | por leitura + teste |
| 9 | A fixture era a única fonte da tela | frontend | `1ddccf0` | por leitura + teste |
| 10 | Conferir UMA credencial marcava TODAS as referências do ativo | banco | `aea3b3c` | sim (no ciclo) |
| 11 | Três fontes divergindo em silêncio no catálogo de tipos e providers | contrato | `4c213de` | sim (teste que lê o SQL) |
| 12 | A revisão existia na API e era inalcançável pela tela | frontend | `664272f` | por leitura + teste |

Os defeitos 1 a 6 e 10 são de **vazamento ou de confiança inventada** — são os
que o Cofre existe para impedir, encontrados dentro do próprio Cofre. Os 7 a 9
e 12 são de **honestidade de interface**: a tela dizendo algo que o sistema não
sabe. O 11 é de **divergência de fonte**.

---

## 1. A CHECK do Postgres ecoa a linha recusada em `DETAIL`

**O defeito.** `cofre_credencial_referencia.localizador` guarda a *referência* ao
segredo, nunca o segredo. A gramática estava escrita direto na `CHECK`. Quando a
`CHECK` recusa uma linha, o Postgres anexa `DETAIL: Failing row contains (…)`
com a **linha inteira** — inclusive o valor recusado. Ou seja: alguém que
colasse uma senha no campo errado fazia a senha aparecer no log do servidor e no
corpo do erro do PostgREST. **A recusa vazava exatamente o que ela existia para
impedir.**

**Contraprova** (Postgres 15 descartável em Docker, nesta sessão):

```
$ docker exec -i $C psql -U postgres <<'SQL'
CREATE TABLE t (localizador text CHECK (localizador ~ '^op://[A-Za-z0-9._%~-]+/[A-Za-z0-9._%~-]+/[A-Za-z0-9._%~-]+$'));
INSERT INTO t VALUES ('Tr0ub4dor&3-SENHA-REAL');
SQL
CREATE TABLE
ERROR:  new row for relation "t" violates check constraint "t_localizador_check"
DETAIL:  Failing row contains (Tr0ub4dor&3-SENHA-REAL).
```

A senha está no `DETAIL`, literal, no valor que o PostgREST devolve ao cliente.

**A correção.** A gramática virou função nomeada, consultada **antes** do INSERT:

- `supabase/migrations/v13_01_cofre_de_ativos.sql:197` — `cofre_localizador_valido(p_provider, p_localizador)`, a gramática por provider em um lugar só.
- `supabase/migrations/v13_01_cofre_de_ativos.sql:1817` — `cofre_referenciar_credencial` consulta a função e levanta citando **provider e forma esperada**, nunca o valor.
- `supabase/migrations/v13_01_cofre_de_ativos.sql:716` — a `CHECK` continua na tabela como última linha de defesa, para escrita direta que não deveria existir. O caminho normal nunca chega nela.

**Prova de que não volta.**

- ciclo → `PROVA ok: senha bruta no localizador | 22023 ~ forma esperada`
- ciclo → `PROVA ok: a recusa nao repete o valor | referencia invalida para o provider 1password: a forma esperada e op://<cofre>/<item>/[secao/]<campo>, com esp…`
- ciclo → `PROVA ok: nenhuma funcao, snapshot, recibo ou motivo contem o localizador (10994 bytes varridos)`
- `backend/tests/test_cofre_ativos.py:324` — `test_senha_bruta_no_localizador_e_recusada_sem_ecoar_o_valor`
- `backend/tests/test_cofre_ativos.py:406` — `test_mensagem_do_postgres_com_a_linha_recusada_nunca_e_repassada` (a mensagem crua, com `DETAIL: Failing row contains`, não é repassada nem com o nome da tabela)

---

## 2. O 422 do FastAPI devolve o campo `input` — a senha voltava para o browser

**O defeito.** O pior dos três, porque o browser está do outro lado. O handler
padrão de `RequestValidationError` serializa `exc.errors()`, e **cada erro do
Pydantic v2 carrega o campo `input` — o valor rejeitado**. Num Cofre, esse
`input` é a credencial. A recusa automática devolvia ao navegador exatamente a
credencial que ela existia para recusar. Mesma classe do `DETAIL` do defeito 1,
um andar acima.

**Contraprova isolada** (app FastAPI mínimo, nesta sessão, com o mesmo
`extra="forbid"` que o Cofre usa):

```python
class Pedido(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str

@app.post("/x")
def x(p: Pedido): return {"ok": True}

r = c.post("/x", json={"nome": "a", "password": "SENHA-SECRETA-XYZ"})
```

```
status: 422
corpo : {"detail":[{"type":"extra_forbidden","loc":["body","password"],"msg":"Extra inputs are not permitted","input":"SENHA-SECRETA-XYZ"}]}
SENHA APARECE NO CORPO: True
```

**A correção.** Handler de exceção no FastAPI é de **app**, não de router:
consertar globalmente mudaria o corpo de erro de rotas que não são desta missão.
Então o Cofre — o único módulo onde um 422 pode conter credencial — lê o corpo
cru e valida sozinho:

- `backend/app/asset_vault/rotas.py:84` — `_corpo_json(request)`: lê o corpo sem deixar o FastAPI montar o 422. Corpo não-JSON ou não-objeto vira 400 com frase fechada.
- `backend/app/asset_vault/rotas.py:95` — `_validado(modelo, corpo)`: monta a mensagem a partir de `loc` (qual campo) e `msg` (qual regra). `input` e `ctx` são ignorados **de propósito** — são os campos onde o Pydantic guarda o valor.
- `backend/app/asset_vault/rotas.py:111` — cinto e suspensório: a mensagem montada ainda passa por `dom.recusar_material_de_credencial`, então se um `msg` do Pydantic um dia passar a citar o valor, a frase inteira cai em vez de ser publicada.

Custo assumido: o schema de request some do OpenAPI. Ele já não é publicado por
padrão (`VOLC_DOCS_ABERTAS`), e o contrato continua legível nos modelos
`_Estrito` em `backend/app/asset_vault/rotas.py:133-269`.

**Prova de que não volta.**

- `backend/tests/test_cofre_ativos.py:549` — `test_o_422_do_fastapi_nao_pode_devolver_o_valor_recusado`. Percorre **as oito rotas de escrita**, manda um campo proibido diferente em cada uma (`password`, `api_key`, `cookie`, `totp`, `recovery_code`, `private_key`, `senha`, `access_token`) e exige `400` + `SEGREDO not in r.text`.
- `backend/tests/test_cofre_ativos.py:598` — `test_corpo_que_nao_e_objeto_json_nao_ecoa_nada`. Um corpo que é só uma string também passaria pelo 422 padrão com `input`.

⚠️ **Este defeito continua nos outros routers deste backend.** Ver
`BACKLOG-NOMEADO.md`, item (a) — com a contagem medida.

---

## 3. Regex com contagem `{3,2000}`, acima do teto 255 do Postgres: a CHECK de `url_publica` nunca era avaliada

**O defeito.** A `CHECK` de `url_publica` usava
`'^https?://[^[:space:]]{3,2000}$'`. O limite de contagem de repetição do motor
de regex do Postgres é **255**. A migration aplicava **limpa** — porque `CHECK`
curto-circuita em `NULL` e a expressão nunca era compilada — e as 68 provas de
então passavam, porque nenhuma delas inseria `url_publica`. O defeito só
apareceria no primeiro ativo com endereço público, que no Cofre é **todo site,
toda página e todo perfil**.

Achado por um revisor paralelo enquanto o importador de engines era escrito.

**Contraprova** (Postgres 15 descartável, nesta sessão):

```
--- {3,2000} (a forma que estava na v13_01) ---
ERROR:  invalid regular expression: invalid repetition count(s)

--- {3,255} / {3,256} : onde e o teto ---
 r255
------
 t
(1 row)
ERROR:  invalid regular expression: invalid repetition count(s)

--- forma atual: + com teto por length() ---
 forma_atual
-------------
 t
(1 row)
```

`{3,255}` compila, `{3,256}` já levanta. O teto é 255, e 2000 está muito acima.

**A correção.** `supabase/migrations/v13_01_cofre_de_ativos.sql:439` —
`CONSTRAINT cofre_ativo_url_http`. A forma virou `+` (sem contagem) e o
comprimento passou a ser limitado por `length()`, que não tem esse teto:

```sql
CONSTRAINT cofre_ativo_url_http CHECK (
  url_publica IS NULL OR (
    length(url_publica) BETWEEN 11 AND 2000
    AND url_publica ~* '^https?://[^[:space:]]+$'))
```

O comentário do defeito, com a data da medição, ficou logo acima — para que o
próximo a mexer não reintroduza a contagem.

**Prova de que não volta.** A prova que denuncia a volta é a de 300 caracteres —
acima do teto de repetição, e portanto impossível de passar se alguém devolver
`{3,2000}`:

- ciclo → `PROVA ok: ativo COM url publica entra [service_role]`
- ciclo → `PROVA ok: a url publica foi mesmo gravada | https://exemplo.agenciavolc.com.br/pagina?a=1&b=2`
- ciclo → `PROVA ok: url nao HTTP(S) e recusada | 23514 cofre_ativo_url_http`
- ciclo → `PROVA ok: url acima de 2000 caracteres e recusada | 23514 cofre_ativo_url_http`
- ciclo → `PROVA ok: url de 300 caracteres (acima do teto de repeticao do regex)`
- `backend/tests/test_cofre_ativos.py:287` — `test_url_nao_http_e_recusada` (a mesma regra um andar acima, antes da rede)
- `src/features/asset-vault/__tests__/contract.test.ts` — `"recusa URL que não seja HTTP ou HTTPS"` (e um andar acima disso)

---

## 4. `FORCE ROW LEVEL SECURITY` sem policy exigiria que o dono atravesse RLS

**O defeito.** A v13_01 liga `FORCE ROW LEVEL SECURITY` nas nove tabelas e cria
**zero policies** — de propósito, porque quem contém o acesso são os `REVOKE`
nominais. Mas `FORCE` sujeita o **dono da tabela** a RLS. Num banco onde o dono
não atravessa RLS, o schema aplicaria limpo e **toda escrita governada falharia
depois**, em runtime — o pior momento possível para descobrir.

**Contraprova / verificação.** Consulta somente leitura a `pg_roles` no Supabase
oficial de produção (`database.agenciavolc.com.br`), repetida nesta sessão:

```
$ ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
    "docker exec -i supabase-db psql -U postgres -c \"SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname IN ('postgres','supabase_admin','service_role','authenticated','anon') ORDER BY 1;\""
    rolname     | rolsuper | rolbypassrls
----------------+----------+--------------
 anon           | f        | f
 authenticated  | f        | f
 postgres       | f        | t
 service_role   | f        | t
 supabase_admin | t        | t
(5 rows)
```

Dois fatos que essa tabela decide:

1. `postgres` **não é superusuário** neste Supabase — mas tem `BYPASSRLS`, e é só
   por isso que as funções `SECURITY DEFINER` funcionam sob RLS forçada.
2. `service_role` **também** tem `BYPASSRLS`. RLS não contém o backend. Quem o
   contém são os `REVOKE`. Confiar em RLS para conter `service_role` seria
   confiar na trava errada.

**A correção.** `supabase/migrations/v13_01_cofre_de_ativos.sql:2094-2109` — um
bloco `DO $guarda_rls$` que transforma a medição em pré-condição:

```sql
SELECT rolsuper OR rolbypassrls INTO atravessa FROM pg_roles WHERE rolname = current_user;
IF NOT coalesce(atravessa, false) THEN
  RAISE EXCEPTION 'v13_01 exige que % atravesse RLS (rolsuper ou rolbypassrls). …', current_user;
END IF;
```

Onde a medição não valer, a migration **aborta** em vez de deixar uma bomba
armada.

**Prova de que não volta.**

- o ciclo imprime a guarda executando: `v13_01: postgres atravessa RLS — funcoes governadas operarao sob FORCE`
- as 81 provas rodam **sob** `FORCE` num cluster que reproduz o `BYPASSRLS` do Supabase de propósito: `PROVA ok: RLS forcada nas 9 tabelas | 9`, `PROVA ok: zero policy em cofre_* | 0`
- e as provas de acesso **tentam** em vez de inspecionar catálogo: `PROVA ok: service_role NAO escreve direto na tabela [service_role] | permission denied for table cofre_ativo`, `PROVA ok: service_role nao tem privilegio NENHUM de tabela | 0`

---

## 5. `_traduzir` engolindo `HTTPException`: um 400 bem escrito virava 500 genérico

**O defeito.** Cada rota do Cofre termina em `except Exception as exc: raise
_traduzir(exc)`. Mas `_corpo_json` e `_validado` **já levantam `HTTPException`
sanitizada** (400, dizendo qual campo está errado). Como `HTTPException` é
subclasse de `Exception`, o `except` a capturava e `_traduzir` caía no ramo
final — 500 genérico. O operador perdia justamente a frase que dizia o que
corrigir.

**Contraprova isolada** (nesta sessão, replicando o padrão das rotas):

```
HTTPException e subclasse de Exception: True
SEM o ramo: status=500 corpo={"detail":{"codigo":"falha_interna","mensagem":"generica"}}
COM o ramo: status=400 corpo={"detail":{"codigo":"payload_invalido","mensagem":"ativo.nome: campo obrigatorio"}}
```

**A correção.** `backend/app/asset_vault/rotas.py:278-284` — primeiro ramo de
`_traduzir`, com o comentário que diz por que ele não é detalhe:

```python
if isinstance(exc, HTTPException):
    return exc
```

**Prova de que não volta.** Todo teste que exige `400` numa recusa de payload
falharia com `500`:

- `backend/tests/test_cofre_ativos.py:549` — `test_o_422_do_fastapi_nao_pode_devolver_o_valor_recusado` (`assert r.status_code == 400` em oito rotas)
- `backend/tests/test_cofre_ativos.py:598` — `test_corpo_que_nao_e_objeto_json_nao_ecoa_nada`
- `backend/tests/test_cofre_ativos.py:420` — `test_erro_do_postgrest_vira_400_sanitizado_e_nao_500` (o nome é a especificação)
- `backend/tests/test_cofre_ativos.py:704` — `test_nome_logico_malformado_e_recusado_antes_da_rede`

---

## 6. `desfazer_relacao` sem validação de corpo, numa substituição incompleta

**O defeito.** Quando as oito rotas de escrita foram convertidas de parâmetro
Pydantic para corpo cru (defeito 2), `DELETE /api/cofre/relacoes/{id}` ficou
sem a linha `pedido = _validado(...)` — mas continuou usando `pedido.motivo` e
`pedido.chave_idempotencia`. Isso é `NameError` em runtime: a rota inteira
quebrada, não uma validação frouxa.

**Contraprova.** O próprio teste de vazamento das oito rotas pegou o `NameError`
— `DELETE /api/cofre/relacoes/1` faz parte da lista, e um `NameError` vira 500,
não o 400 que o teste exige. Não reproduzi o estado quebrado nesta sessão porque
exigiria editar `backend/`, que esta missão não pode tocar.

**A correção.** `backend/app/asset_vault/rotas.py:452-461`:

```python
pedido = _validado(PedidoDeMotivo, await _corpo_json(request))
```

**Prova de que não volta.** `backend/tests/test_cofre_ativos.py:549` —
`test_o_422_do_fastapi_nao_pode_devolver_o_valor_recusado`, cuja última entrada
é exatamente `("DELETE", "/api/cofre/relacoes/1", {…, "access_token": SEGREDO})`
com `assert r.status_code == 400, f"{metodo} {caminho} -> {r.status_code}"`.
A mensagem da asserção nomeia a rota, então a próxima quebra diz qual foi.

---

## 7. `useQuery` disparando sem base configurada

**O defeito.** A tela consultava `/api/cofre` mesmo quando
`VITE_PAUTADOR_API_URL` não estava definida. A chamada falharia com `sem_base`
depois de montar cabeçalho e sessão — gastando uma ida à rede para descobrir o
que já se sabia, e enchendo de ruído o log de quem fosse investigar.

**Contraprova.** O teste que fez o defeito aparecer espiona `cofre.inventario` e
exige que ele **não** tenha sido chamado:

```js
vi.spyOn(cofre, "cofreConfigurado").mockReturnValue(false);
const espiao = vi.spyOn(cofre, "inventario");
mount();
expect(screen.getByRole("heading", { name: /não está configurado/i })).toBeTruthy();
expect(espiao).not.toHaveBeenCalled();
```

**A correção.**

- `src/features/asset-vault/cofreApi.ts:64` — `cofreConfigurado()`, que é só `Boolean(API_BASE)`.
- `src/features/asset-vault/AssetVaultContent.tsx:1440` — `enabled: cofre.cofreConfigurado()` na `useQuery`, com o comentário que explica por quê.
- `src/features/asset-vault/AssetVaultContent.tsx:1460` — a tela devolve o aviso de configuração antes de qualquer estado de dado. Configuração de ambiente **não é** ausência de dado: o inventário pode existir e estar inacessível daqui.

Na mesma `useQuery`, `retry: false` — três tentativas silenciosas transformam
indisponibilidade em lentidão sem causa visível.

**Prova de que não volta.** `src/features/asset-vault/__tests__/asset-vault.test.tsx:121`
— `"ambiente sem VITE_PAUTADOR_API_URL é configuração, não ausência de dado"`.

---

## 8. Navegação de 4 lentes inerte

**O defeito.** A primeira versão da tela renderizava a navegação das quatro
lentes (Inventário, Revisões, Relações, Contrato) e **mostrava sempre o
inventário**. Uma navegação que não navega é pior do que nenhuma: ela promete
uma vista que não existe e o operador conclui que a lente está vazia.

**Contraprova.** Registrada no commit `1ddccf0` e fechada dentro dele, então não
há um par antes/depois no `git log` para reproduzir. O teste abaixo é a
contraprova executável: ele clica em cada lente e exige o heading dela.

**A correção.**

- `src/features/asset-vault/AssetVaultContent.tsx:1453` — `trocarView` escreve a lente no query param.
- `src/features/asset-vault/AssetVaultContent.tsx:1539` — o corpo passou a ser escolhido por `view`: `contract` → `Contrato`, `inventory` → `Lista`, `reviews` → `Revisoes`, senão `Relacoes`.

Dois efeitos que vieram junto e não são cosméticos:

- `AssetVaultContent.tsx:1224` — `Revisoes` ordena por **consequência** (criticidade primeiro, depois número de lacunas), não por nome. Um ativo crítico sem prova e sem referência de acesso é outro problema que um inativo com revisão vencida; ordem alfabética faz o primeiro se perder no meio do segundo.
- A lente `Relações` exigiu que a **listagem** já trouxesse as arestas — senão desenhar o mapa seria um N+1 de detalhes. Provado no banco: `PROVA ok: a listagem traz as relacoes do ativo | Operacao de conteudo organico` e `PROVA ok: ativo sem relacao traz lista vazia, nao null | []`.

**Prova de que não volta.** `src/features/asset-vault/__tests__/asset-vault.test.tsx:174`
— `"as quatro lentes existem e cada uma muda a tela"`. Clica em Revisões,
Relações e Contrato e exige o heading próprio de cada uma; a asserção de
Relações é escopada ao `role="region"` da lente, porque a mesma aresta aparece
legitimamente no inspetor do ativo selecionado.

---

## 9. A fixture era a única fonte da tela

**O defeito.** Até `1ddccf0`, `AssetVaultContent` lia `fixtures.ts` — oito
ativos editoriais, honestos sobre serem um retrato. O problema não era a
fixture: era ela ser a **única** fonte. Uma tela que sempre mostra os mesmos
oito ativos não distingue "o Cofre está vazio" de "o Cofre não respondeu",
porque nunca esteve vazio nem deixou de responder.

**A correção.** A fonte virou `/api/cofre` e a fixture **não** virou fallback —
ficou onde estava, servindo o teste hermético do contrato público. Seis estados,
nenhum redundante, porque colapsá-los manda a pessoa para a ação errada:

| Estado | Ação que ele pede | Onde |
|---|---|---|
| sem configuração | definir `VITE_PAUTADOR_API_URL` | `AssetVaultContent.tsx:1460` |
| 401 | entrar de novo | `AssetVaultContent.tsx:1478` |
| 403 | pedir acesso (papel, não sessão) | `AssetVaultContent.tsx:1482` |
| 503 | esperar e tentar de novo | `AssetVaultContent.tsx:1486` |
| desconhecido | investigar | `AssetVaultContent.tsx:1491` |
| vazio de verdade | cadastrar — e mostra as sete gavetas com contagem zero, vindas do servidor, não uma página em branco que parece defeito | provado abaixo |

**Prova de que não volta.** `src/features/asset-vault/__tests__/asset-vault.test.tsx:93`
— `"indisponibilidade NÃO vira inventário vazio, e NÃO cai para a fixture"`. O
teste importa `INITIAL_ASSETS` e percorre os oito nomes exigindo que **nenhum**
apareça quando a API falha:

```js
for (const ativo of INITIAL_ASSETS) {
  expect(screen.queryByText(ativo.name)).toBeNull();
}
```

Se alguém reintroduzir a fixture como fallback "para a tela não ficar feia", a
suíte cai. E o vazio de verdade é provado à parte, em
`asset-vault.test.tsx:129` — as sete gavetas continuam visíveis com contagem
zero.

---

## 10. Conferir UMA credencial marcava TODAS as referências do ativo

**O defeito.** O mais grave dos doze em termos de significado, porque produz
**confiança inventada** — que é o que este schema inteiro existe para impedir, e
estava dentro dele. `cofre_registrar_verificacao` com `alvo='credencial'` fazia:

```sql
UPDATE cofre_credencial_referencia
   SET verificacao_estado = ...
 WHERE ativo_id = ativo AND aposentado_em IS NULL
```

**sem dizer QUAL referência.** Uma página do Facebook com `FB_PAGE_ADMIN` e
`ADSPOWER_API_KEY` teria as duas marcadas `verified` porque alguém abriu **uma**
no 1Password. O card diria "acesso comprovado" para uma credencial que ninguém
olhou.

**Contraprova.** Reproduzida no ciclo descartável, e a prova que a expõe é a
terceira da lista abaixo: sem o conserto, `ADSPOWER_API_KEY` sairia `verified`.

**A correção.** `supabase/migrations/v13_01_cofre_de_ativos.sql:1718-1758`.
A referência passou a ser **nomeada**, e a ambiguidade virou **erro** em vez de
escolha silenciosa:

- com `nome_logico`: atualiza só ela; se o nome não existir, `no_data_found` (P0002);
- sem `nome_logico` e com **mais de uma** ativa: `invalid_parameter_value` — "informe nome_logico para dizer qual foi verificada";
- sem `nome_logico` e com **nenhuma**: recusa também;
- sem `nome_logico` e com **uma só**: resolve sozinho, que é o caso comum.

**Prova de que não volta.** Seis provas novas no ciclo:

- `PROVA ok: segunda referencia no mesmo ativo [service_role]`
- `PROVA ok: verificar credencial sem dizer QUAL, com duas referencias | 22023 ~ informe nome_logico`
- `PROVA ok: verificar a referencia NOMEADA [service_role]`
- `PROVA ok: so a referencia nomeada ficou verificada | verified`
- **`PROVA ok: a OUTRA referencia continua nao verificada | unverified`** ← a que importa
- `PROVA ok: verificar uma referencia que nao existe | P0002 ~ nao tem referencia ativa chamada`

E um andar acima, antes da rede:

- `backend/tests/test_cofre_ativos.py:686` — `test_a_verificacao_de_credencial_pode_nomear_a_referencia`
- `backend/tests/test_cofre_ativos.py:704` — `test_nome_logico_malformado_e_recusado_antes_da_rede`

**Nota do mesmo commit — a view que saiu.** `cofre_inventario` foi removida.
Ela não tinha um único consumidor: as funções governadas juntam gaveta e tipo
direto das tabelas, e a única referência a ela no repositório era a prova de que
`anon` não a lê. Uma view que existe só para ser provada inacessível é
superfície sem benefício, e num schema cujo trabalho é **reduzir** superfície
isso é o oposto do desenho. A prova mudou de forma junto:
`PROVA ok: nao existe view no schema (superficie que nao existe nao vaza) | 0`.
Isso segue o CLAUDE.md — "código morto confirmado deve sair, não ser apenas
movido para uma pasta `legacy/`".

---

## 11. Três fontes divergindo em silêncio no catálogo de tipos e providers

**O defeito.** O contrato público (`src/features/asset-vault/contract.ts`), o
domínio do backend (`backend/app/asset_vault/dominio.py`) e a tabela
`cofre_tipo` da migration precisam concordar. Não concordavam:

1. `contract.ts` **não tinha `1password`** no enum de provider — enquanto o
   schema e o backend já tinham. O provider escolhido pelo ADR de 28/08 seria
   **rejeitado pelo próprio contrato que deveria descrevê-lo**.
2. `contract.ts` **não tinha `browser_profile`** nos tipos — enquanto a v13_01
   já o criava (é o tipo de perfil AdsPower, P03-T07). A API aceitaria um perfil
   que o contrato público recusaria.

Divergir em silêncio faz a API aceitar um tipo que a FK do banco recusa — e o
operador recebe um erro de integridade referencial onde deveria ter recebido
"tipo desconhecido".

**Contraprova.** O teste novo é a contraprova: ele **lê a migration** e compara
par a par. Antes do conserto, `expect(noSql.size).toBe(ASSET_KINDS.length)`
falharia por um.

**A correção.** `src/features/asset-vault/contract.ts`:

- `:56` — `"browser_profile"` entra na lista de tipos;
- `:114` — `browser_profile: "automation"`, e não `social_presence`, porque o perfil **executa** e a página **publica**; confundi-los faria o Cofre responder "temos duas páginas" quando há uma página e um perfil que a abre;
- `:148` — `z.enum(["1password", "bitwarden", "vaultwarden", "passbolt", "infisical"])`;
- `:267` — o rótulo humano.

**Prova de que não volta.** `src/features/asset-vault/__tests__/contract.test.ts`
— `"o catálogo de tipos é o MESMO da migration v13_01"`. Ele lê
`supabase/migrations/v13_01_cofre_de_ativos.sql`, extrai os pares
`(kind, cluster)` do `INSERT INTO public.cofre_tipo` e compara com
`ASSET_KINDS`/`KIND_CLUSTER`. Do lado do Python, `test_cofre_ativos.py:131` e
`:147` já faziam o mesmo (`test_os_tipos_do_dominio_sao_exatamente_os_do_banco`
e `test_as_gavetas_do_dominio_sao_exatamente_as_do_banco`), e `:155` compara
até a gramática do localizador
(`test_a_gramatica_do_localizador_concorda_com_a_do_banco`).

**Um tipo adicionado em um lugar só agora derruba duas suítes.**

---

## 12. A revisão existia na API e era inalcançável pela tela

**O defeito.** A missão pedia "cadastro e revisão" na interface. Havia o
cadastro, havia `revisarAtivo` no cliente HTTP, e **não havia formulário**: a
revisão existia na API e não existia para quem opera. Lacuna encontrada relendo
o escopo.

E, ao construí-lo, dois defeitos de desenho que teriam nascido junto:

1. **Mandar o formulário inteiro em vez do delta.** Toda revisão reescreveria
   todos os campos, e a trilha registraria "mudou tudo" quando alguém corrigiu
   uma vírgula. Pior: um campo que o formulário carregou vazio porque a API não
   o devolveu **apagaria o valor real**. O backend é `PATCH`; o cliente precisa
   falar `PATCH`.
2. **Chave de idempotência sem os campos mudados.** Duas revisões distintas do
   mesmo ativo dentro do mesmo minuto compartilhariam chave, e a segunda
   voltaria como *replay* da primeira — **silenciosamente descartada, com o
   recibo da outra**.

**A correção.** `src/features/asset-vault/AssetVaultContent.tsx:360-440` —
`FormularioDeRevisao`:

- `:387-407` — calcula o delta e manda só ele;
- `:415` — `chaveDoAto("revisao", ativo.ativo_id, Object.keys(mudancas).sort().join("."))`: a chave inclui os campos mudados;
- botão desabilitado sem mudança (`const nada = Object.keys(mudancas).length === 0`), porque um patch vazio criaria uma revisão que não revisa nada — o backend já recusa com 400, e recusar aqui evita a ida.

**Prova de que não volta.** `src/features/asset-vault/__tests__/asset-vault.test.tsx:263`
— `"a revisão manda só o que MUDOU, e a chave distingue revisões diferentes"`.

---

---

# Saída literal dos gates

Todos rodados nesta worktree em 01/09/2026, contra o HEAD `664272f`.

## 1. `./scripts/provar-ciclo-v13_01.sh`

Ciclo completo aplicar → operar → reverter → reaplicar num Postgres descartável.
**Exit 0. 81 provas** (`grep -c 'PROVA ok:'` = 81).

```
▶ cluster descartavel em Docker (postgres:15 — mesma major da producao)
  ✓ servidor 15.19 (Debian 15.19-1.pgdg13+2)
▶ semeando papeis do Supabase e o default ACL QUEBRADO de public
  ✓ default ACL aberto reproduzido (tabela nova nasce escrivel por anon)

DEGRAU 1 — aplicar
  v13_01: guardas ok (papel=postgres, versao=15.19 (Debian 15.19-1.pgdg13+2))
  v13_01: postgres atravessa RLS — funcoes governadas operarao sob FORCE
  v13_01: 9 tabelas revogadas nominalmente, RLS forcada, zero policies
  v13_01 OK: 9 tabelas, RLS forcada em 9, 0 policies, 0 grants a anon/authenticated
  ✓ v13_01 aplicada

DEGRAU 2 — operar
  PROVA ok: as 7 gavetas existem | 7
  PROVA ok: os 28 tipos existem (27 do contrato + browser_profile) | 28
  PROVA ok: nenhum tipo em duas gavetas | 0
  PROVA ok: facebook_page na gaveta errada (paid_media) | 23503 cofre_ativo_gaveta_coerente
  PROVA ok: anon nao le cofre_ativo [anon] | permission denied for table cofre_ativo
  PROVA ok: authenticated nao le cofre_ativo [authenticated] | permission denied for table cofre_ativo
  PROVA ok: nao existe view no schema (superficie que nao existe nao vaza) | 0
  PROVA ok: service_role NAO escreve direto na tabela [service_role] | permission denied for table cofre_ativo
  PROVA ok: service_role NAO le a tabela de referencias [service_role] | permission denied for table cofre_credencial_referencia
  PROVA ok: service_role NAO le a trilha de operacoes [service_role] | permission denied for table cofre_operacao
  PROVA ok: anon nao executa a API governada [anon] | permission denied for function cofre_listar_ativos
  PROVA ok: authenticated nao executa a API governada [authenticated] | permission denied for function cofre_listar_ativos
  PROVA ok: authenticated nao cadastra ativo [authenticated] | permission denied for function cofre_cadastrar_ativo
  PROVA ok: service_role nao chama o construtor de snapshot [service_role] | permission denied for function cofre_snapshot_ativo
  PROVA ok: service_role nao grava recibo direto [service_role] | permission denied for function cofre_registra_operacao
  PROVA ok: zero policy em cofre_* | 0
  PROVA ok: zero grant de tabela para anon/authenticated | 0
  PROVA ok: RLS forcada nas 9 tabelas | 9
  PROVA ok: DELETE nao foi concedido a nenhum papel do Data API | 0
  PROVA ok: service_role nao tem privilegio NENHUM de tabela | 0
  PROVA ok: campo sensivel simples no topo (password) | 22023 ~ nao conhece
  PROVA ok: campo sensivel ANINHADO em campo permitido | 23001 ~ campo proibido no Cofre
  PROVA ok: alias camelCase (accessToken) | 23001 ~ accessToken
  PROVA ok: alias com hifen e maiuscula (ACCESS-TOKEN) | 23001 ~ ACCESS-TOKEN
  PROVA ok: alias em portugues (codigo_recuperacao) | 23001 ~ codigo_recuperacao
  PROVA ok: campo sensivel dentro de array aninhado | 23001 ~ campo proibido no Cofre
  PROVA ok: campo desconhecido no payload | 22023 ~ nao conhece
  PROVA ok: localizador tentando entrar por cofre_cadastrar_ativo | 23001 ~ localizador
  PROVA ok: service_role cadastra ativo pela funcao governada [service_role]
  PROVA ok: ativo COM url publica entra [service_role]
  PROVA ok: a url publica foi mesmo gravada | https://exemplo.agenciavolc.com.br/pagina?a=1&b=2
  PROVA ok: url nao HTTP(S) e recusada | 23514 cofre_ativo_url_http
  PROVA ok: url acima de 2000 caracteres e recusada | 23514 cofre_ativo_url_http
  PROVA ok: url de 300 caracteres (acima do teto de repeticao do regex)
  PROVA ok: o ativo existe com revisao 1 | 1
  PROVA ok: a revisao 1 foi gravada na trilha | cadastro
  PROVA ok: referencia 1Password bem formada entra [service_role]
  PROVA ok: a referencia esta registrada | 1
  PROVA ok: senha bruta no localizador | 22023 ~ forma esperada
  PROVA ok: a recusa nao repete o valor | referencia invalida para o provider 1password: a forma esperada e op://<cofre>/<item>/[secao/]<campo>, com esp
  PROVA ok: JWT colado no resumo do ativo | 23514 cofre_ativo_prosa_limpa
  PROVA ok: chave PEM colada na proxima acao | 23514 cofre_ativo_prosa_limpa
  PROVA ok: referencia op:// com ?attribute=otp | 22023 ~ forma esperada
  PROVA ok: nenhuma funcao, snapshot, recibo ou motivo contem o localizador (10990 bytes varridos)
  PROVA ok: a postura publica o provider sem o endereco | 1password
  PROVA ok: a postura publica o nome logico | FB_PAGE_ADMIN
  PROVA ok: a postura NAO tem chave localizador | false
  PROVA ok: replay devolve o mesmo recibo, marcado idempotente
  PROVA ok: o retry NAO criou uma segunda revisao | 1
  PROVA ok: mesma chave de idempotencia com entrada diferente | 23505 ~ ja foi usada por outra operacao
  PROVA ok: UPDATE na trilha de revisoes | 23001 ~ append-only
  PROVA ok: DELETE na trilha de revisoes | 23001 ~ append-only
  PROVA ok: UPDATE na trilha de operacoes | 23001 ~ append-only
  PROVA ok: engine com zero formatos (contagem inventada) | 23514 cofre_engine_formatos_positivos
  PROVA ok: engine com formatos NULL (o manifesto nao declara)
  PROVA ok: limpando o perfil de engine da prova
  PROVA ok: credencial diz verified sem instante | 23514 cofre_credencial_verificacao_sem_carimbo
  PROVA ok: verificacao datada no futuro | 23514 cofre_verificacao_nao_futura
  PROVA ok: segunda referencia no mesmo ativo [service_role]
  PROVA ok: verificar credencial sem dizer QUAL, com duas referencias | 22023 ~ informe nome_logico
  PROVA ok: verificar a referencia NOMEADA [service_role]
  PROVA ok: so a referencia nomeada ficou verificada | verified
  PROVA ok: a OUTRA referencia continua nao verificada | unverified
  PROVA ok: verificar uma referencia que nao existe | P0002 ~ nao tem referencia ativa chamada
  PROVA ok: relacao de um ativo consigo mesmo | 23514 cofre_relacao_sem_laco
  PROVA ok: relacao com destino interno E externo | 23514 cofre_relacao_um_destino
  PROVA ok: relacao sem destino nenhum | 23514 cofre_relacao_um_destino
  PROVA ok: relacao para alvo externo entra [service_role]
  PROVA ok: a MESMA relacao ativa duas vezes | 23505 cofre_relacao_ativa_unica
  PROVA ok: aposentar o ativo [service_role]
  PROVA ok: o ativo continua existindo, aposentado | retired
  PROVA ok: o aposentado sai da listagem padrao | 0
  PROVA ok: e aparece quando pedido explicitamente | 1
  PROVA ok: reativar o ativo [service_role]
  PROVA ok: o ativo voltou | active
  PROVA ok: a trilha guardou aposentadoria E reativacao | 2
  PROVA ok: a listagem traz as relacoes do ativo | Operacao de conteudo organico
  PROVA ok: ativo sem relacao traz lista vazia, nao null | []
  PROVA ok: a listagem devolve as 7 gavetas | 7
  PROVA ok: gaveta vazia vem com contagem zero, nao some | 0
  PROVA ok: revisar ativo que nao existe | P0002 ~ nao existe no Cofre
 PROVAS CONCLUIDAS
  ✓ 81 provas passaram

DEGRAU 3 — reverter
  v13_99: removendo o dominio Cofre de Ativos (papel=postgres)
  v13_99 OK: nada com prefixo cofre_ restou
  ✓ nada com prefixo cofre_ restou

DEGRAU 4 — reaplicar
  ✓ reaplicavel depois do rollback
▶ conferindo que a migration recusa reaplicacao POR CIMA
  ✓ recusada com as tabelas ja existentes

════════════════════════════════════════════════════════════════
 81 provas · PostgreSQL 15.19 (Debian 15.19-1.pgdg13+2)
 v13_01 aplicavel → operavel → reversivel → reaplicavel
 cluster descartado. Nada foi tocado em producao.
════════════════════════════════════════════════════════════════
exit=0
```

## 2. `PYTHONPATH="backend:$(pwd)" backend/.venv/bin/python -m pytest backend/tests/test_cofre_ativos.py -q -p no:warnings`

```
......................................................                   [100%]
54 passed in 0.81s
```

## 3. `npx vitest run src/features/asset-vault`

```
 RUN  v4.1.10 /private/tmp/volc-asset-vault-1p-v1

 Test Files  2 passed (2)
      Tests  21 passed (21)
   Start at  20:07:07
   Duration  1.68s (transform 102ms, setup 0ms, import 270ms, tests 816ms, environment 562ms)
```

Os dois arquivos são `__tests__/asset-vault.test.tsx` (comportamento da tela) e
`__tests__/contract.test.ts` (o contrato público contra a migration).

## 4. `npx tsc --noEmit -p tsconfig.app.json 2>&1 | grep -c "error TS"`

```
76
```

**Zero deles em `asset-vault`** — `grep -c "asset-vault"` na mesma saída dá `0`.
São os 76 erros herdados do webgo que o CLAUDE.md já documenta, e a distribuição
bate com a documentada:

```
  31 src/services/supabaseDataService.ts
  12 src/pages/ProjectDashboard.tsx
   8 src/components/pautador-pro/AddOpportunityModal.tsx
   7 src/utils/healthChecks.ts
   4 src/pages/settings/ProjectsSettings.tsx
   3 src/pages/GeneralDashboard.tsx
   2 src/pages/settings/CampaignsSettings.tsx
   2 src/pages/Reports.tsx
```

`grep -c TS2688` = `0` — a armadilha das pastas `@types/* 2` não está presente
nesta worktree, então o número acima é a checagem semântica de verdade.

## 5. `npm run build 2>&1 | tail -5`

```
(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rollupOptions.output.manualChunks to improve chunking: https://rollupjs.org/configuration-options/#output-manualchunks
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.
✓ built in 7.95s
```

⚠️ `npm run build` **não** é gate de tipo: esbuild não checa tipos. Verde aqui
não contradiz os 76 do `tsc`.

## 6. `python3 scripts/importar_engines_no_cofre.py --autoteste 2>&1 | tail -3`

```
ok    [asset:engine:motor-video-volc] motivo da revisao 5..800

248 asserções ok, 0 falhas
```

Rodando sem `--autoteste`, o importador emite **7 engines** — medido nesta
sessão:

```
engines emitidos: 7
 - asset:engine:volc-os-creative-port | verified
 - asset:engine:aprova-ad-studio-official | verified
 - asset:engine:aprova-ad-studio-desktop-divergent | inactive
 - asset:engine:positivo-ad-studio | verified
 - asset:engine:volc-motor-imagem | verified
 - asset:engine:prensa | verified
 - asset:engine:motor-video-volc | verified
```

E o `stderr` marca a procedência de cada campo, com as ausências nomeadas em vez
de preenchidas:

```
campo                           origem          detalhe
ativo_id                        DERIVADO        asset:engine:<slug(id)> a partir de id=volc_os_creative_port
kind / cluster                  DECLARADO       creative_engine / creative_production — o par declarado em cofre_tipo
nome                            FONTE           label=Porta interna de criativos do VOLC O.S.
…
projeto                         AUSENTE         o caminho do manifesto não nomeia cliente ou projeto
vertical                        AUSENTE         nenhum manifesto declara vertical
display_id                      AUSENTE         engine não tem identificador de plataforma para exibir
```

## 7. `python3 tools/onepassword-smoke/run.py --autoteste 2>&1 | tail -3`

```
[PASSOU] prova f: recibos e logs não contêm o valor de teste -> arquivos varridos=10 contaminados=nenhum
logs do autoteste: /var/folders/n_/pq8ng_k14vsfx82xb9b8b3980000gp/T/volc-1p-autoteste-q3_rrdi9/logs
resultado: 0 falhas
```

## 8. `python3 tools/onepassword-smoke/run.py ; echo "exit=$?"`

```
`op` não está no PATH.
{
  "ferramenta": "onepassword-smoke",
  "tarefa": "P03-T09",
  "contrato_verificado_em": "2026-09-01 (www.1password.dev)",
  "gerado_em": "2026-09-01T22:50:29+00:00",
  "run_id": "e3b0c44298fc1c14",
  "estado": "blocked/cli_ausente",
  "exit_code": 10,
  "duple_em_uso": false,
  "duple_caminho": null,
  "plataforma": "Darwin",
  "referencia": {
    "presente": false
  },
  "verificado": [
    "preflight: sem --no-masking e sem service account implícito"
  ],
  "nao_verificado": [
    "app do 1Password",
    "sessão / conta",
    "listagem de nomes",
    "injeção em processo descartável"
  ],
  "evidencia": {
    "variaveis_op_no_ambiente": [],
    "op_no_path": false
  },
  "proximo_ato": "instale o app 1Password e o CLI, ligue Settings > Developer > 'Integrate with 1Password CLI' e rode o smoke de novo"
}
exit=10
```

⚠️ **`exit=10` é o resultado correto, não uma falha do smoke.** O ambiente foi
verificado item a item nesta sessão:

```
$ command -v op            → (ausente)
$ ls -d /Applications/1Password.app → No such file or directory
$ env | grep -c '^OP_'     → 0
$ command -v 1password-mcp → (ausente)
$ grep -c 1password ~/.claude.json → 0
```

## 9. `git status --short ; git diff --check`

**No momento em que os gates 1 a 8 rodaram**, com HEAD em `664272f`:

```
?? docs/closure/asset-vault-onepassword-production-v1/
?? scripts/onboarding_pagina_facebook.py
```

`git diff --check`: saída vazia, sem conflito de whitespace. Nada rastreado
estava modificado — os gates mediram exatamente o commit `664272f`.

**Ao fechar este pacote, minutos depois:**

```
 M backend/app/asset_vault/dominio.py
 M supabase/migrations/v13_01_cofre_de_ativos.sql
?? docs/closure/asset-vault-onepassword-production-v1/
?? scripts/onboarding_pagina_facebook.py
```

⚠️ **Só `docs/closure/asset-vault-onepassword-production-v1/` é deste pacote.**
A missão continuou produzindo enquanto o pacote era montado: as mudanças em
`dominio.py` e na `v13_01` **não foram medidas nem avaliadas aqui**, e
`scripts/onboarding_pagina_facebook.py` (1647 linhas, não rastreado) tampouco —
ele declara atacar P03-T02, P12-T02 e P03-T07, e nenhuma afirmação deste pacote
se apoia nele.

⚠️ **Esse script aponta para um arquivo que este pacote não tem:** o docstring
dele cita
`docs/closure/asset-vault-onepassword-production-v1/PEDIDO-AO-OPERADOR.md` como
"a outra metade, humana". Esta missão foi autorizada a criar exatamente quatro
arquivos neste diretório, e esse não é um deles. Ver `BACKLOG-NOMEADO.md`,
item (g).

---

# Verificação da suíte inteira, e três correções aos commits

## Vitest completo — `npx vitest run`

Medido com HEAD em `1ddccf0`, antes dos três últimos commits:

```
 Test Files  7 failed | 80 passed | 1 skipped (88)
      Tests  2 failed | 1062 passed | 3 skipped (1067)
```

Nenhuma das falhas está em `asset-vault`. As sete são:

| Arquivo | Causa medida |
|---|---|
| `src/components/trafego/hub/__tests__/u0-hub-multicanal.test.tsx` | `Error: Missing Supabase environment variables` em `src/lib/supabase.ts:7:9` |
| `src/components/trafego/inventario/__tests__/acessibilidade-do-inventario.test.tsx` | idem |
| `src/components/trafego/inventario/__tests__/achados-da-auditoria.test.tsx` | idem |
| `src/components/trafego/inventario/__tests__/cabecalho-grupo-e-colunas.test.tsx` | idem |
| `src/components/trafego/inventario/__tests__/ordem-do-servidor.test.tsx` | idem |
| `src/components/trafego/inventario/__tests__/regras-do-inventario.test.tsx` | idem |
| `src/components/settings/meta-capi/__tests__/wizard-smoke.test.tsx` | 2 testes: `AssertionError: expected '1Site e pixeldomínio, pixel e token2E…' not to contain 'Edge Function'` |

Seis são colapso na importação por `.env` ausente nesta worktree — não são
falhas de lógica. A sétima é o wizard do Meta CAPI, fora desta missão.
⚠️ **Não reexecutei a suíte inteira depois de `664272f`**; a suíte de
`asset-vault` foi reexecutada e passa (21/21).

## Três imprecisões nos commits desta branch, medidas aqui

Nenhuma muda uma conclusão, mas o pacote de fechamento não deve repetir número
que ele mesmo mediu diferente:

1. `1ddccf0` diz "8 suites falhas antes e depois". A medição foi **7 arquivos de
   teste falhos** (o vitest imprime **8 blocos de erro**: 6 colapsos de suíte +
   2 testes falhos). Provavelmente a origem da contagem.
   ⚠️ **Não confirmei o "antes".** Medir a baseline no SHA `36bec04` exigiria um
   checkout, que esta missão não pode fazer.
2. `beeb9e7` diz "Doze rotas sob /api/cofre". A contagem de decoradores em
   `backend/app/asset_vault/rotas.py` dá **13** desde então: 5 de leitura e 8 de
   escrita.
3. `aea3b3c` diz "54 testes backend, 20 frontend". A medição de agora, em
   `664272f`, dá **54 backend** (bate) e **21 frontend** — mas 664272f é o
   commit seguinte, que somou um teste. Em `aea3b3c` o número estava certo.
