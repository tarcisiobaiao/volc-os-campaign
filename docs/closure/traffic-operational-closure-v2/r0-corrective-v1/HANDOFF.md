# Handoff — rodada corretiva R0 (A01 a A06)

Branch `execution/volc-os-operacao-80-20` · base `d54e100` · HEAD revisado
`187c4f1` · **HEAD final `91967b1`** · três commits nesta rodada, árvore limpa.

## O que estava errado, numa frase cada

Os seis achados tinham a mesma raiz: **o livro sabia menos do que o mundo, e o
código tratava esse silêncio como consentimento.**

| # | O defeito | O que ele custava |
|---|-----------|-------------------|
| A01 | O perfil publicado parava na 3ª migration; o runtime já usava a 4ª (e agora a 5ª) | Seguir o runbook aplicaria um schema que o código não consegue usar, e a descoberta viria no primeiro despacho, com a janela aberta |
| A02 | Falha ao gravar o read-back era engolida | Quatro objetos nasciam e a resposta era `200 CREATED_PAUSED` com **zero** confirmação durável |
| A03 | "ID registrado" e "read-back confirmado" eram a mesma coisa | Uma campanha existente e nunca conferida ficava **invisível** para a recuperação: `passos_ambiguos: 0`, zero leituras |
| A04 | `every()` sobre os passos que **existem** | Uma Campanha de quatro objetos exibia "Criada pausada · 1 de 1" |
| A05 | A validade da peça só era conferida na compilação, que o despacho não faz mais | Aprovação no minuto 59 despachava no minuto 61 com a atestação vencida |
| A06 | Idade promovia o órfão sem **cercar** ninguém | O trabalhador antigo voltava com a resposta velha e concluía por cima da promoção |

## O que mudou, e por quê

**A cerca (A06).** `prepare_step` passa a cunhar um `claim_token` na mesma
transação que insere a linha. Fechar, marcar ambíguo, falhar e anotar o
read-back exigem o token **vigente**; reentrar num passo e promover um órfão
**revogam** o anterior. O token **gira** ao fechar, porque anotar a leitura é
outro ato — sem o giro, uma anotação atrasada emitida com a autoridade do
despacho pousaria sobre uma conclusão mais nova.

E como banco nenhum cancela uma requisição já entregue, o trabalhador cercado
que voltou com um id real grava esse id em `observed_external_ids` — **ao lado**
da identidade concluída, nunca no lugar dela. Jogá-lo fora perderia a única
prova de que existe uma campanha órfã na conta.

> A garantia honesta é estreita e verificável: no máximo **um** trabalhador
> detém autoridade de conclusão por reivindicação, autoridade velha não
> sobrescreve conclusão mais nova, e o id que ela viu não se perde. **Não há
> exactly-once entre PostgreSQL e Meta**, e nada aqui promete um.

**A evidência (A02).** `_registrar_readback` deixou de engolir exceção. Sem
confirmação durável a saga **para** antes do próximo objeto e devolve 502
`META_READBACK_NOT_DURABLE` — com o id preservado, nada reenviado, e
`falhar_passo` deliberadamente **não** chamado: falha nossa não vira recusa
provada da Meta. A divergência sobrevive à falha de anotá-la; o que cai é a
durabilidade, declarada em campo próprio.

**A leitura pelo ID (A03).** O manifesto *server-only* passou a devolver o
`external_object_id` resolvido, e a recuperação lê **pelo id** com a máscara
exata do read-back da criação. Procedência prova mais que coincidência de nome —
e é por isso que um `AdCreative`, que a Marketing API não carimba com
`created_time`, agora pode ser conferido por id, embora continue sem poder ser
adotado por nome. O recibo do navegador continua dizendo `has_external_id` e
nada mais.

**A validade (A05).** Um relógio único e substituível (`contrato.agora_utc`), a
aprovação limitada pela prova que a sustenta, e a conferência do snapshot antes
do Keychain **e a cada degrau** — porque cada degrau é um POST novo. A leitura
histórica do mesmo snapshot expirado continua aberta: a assimetria é o contrato.

**A contagem (A04).** O denominador vem do manifesto aprovado. Ausência dele é
**desconhecido**, nunca sucesso. Duas contagens separadas — "conferidos por
leitura" e "com id gravado" — porque são duas perguntas, e uma linha só
obrigaria a escolher qual delas mentir. O `nascimento` em `useState` saiu: a
fonte é o recibo durável, que sobrevive ao reload.

**O perfil (A01).** Cinco arquivos, uma lista canônica, e o verificador deriva
do **código** quais RPCs precisam existir. O portão virou portão: a versão
anterior imprimia `(precisa ser false)` ao lado de um valor e escrevia
`FALHA (reaplicou)` **saindo com zero**. Agora são 30 asserções e qualquer
violação termina com código diferente de zero.

## Como conferir

```bash
cd /private/tmp/volc-os-operacao-80-20

# As sondas da revisão precisam FALHAR: elas passavam ao reproduzir o bug.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:backend/tests \
  backend/.venv/bin/python -B -m pytest \
  docs/closure/traffic-operational-closure-v2/r0-corrective-v1/evidence-recebida/test_review_probes.py \
  -q -p no:cacheprovider          # 4 failed  ← esperado

# As regressões precisam PASSAR: elas exigem o comportamento certo.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:backend/tests \
  backend/.venv/bin/python -B -m pytest backend/tests/ -k meta -q -p no:cacheprovider

npx vitest run src/pages/trafego/__tests__/meta-criacao-nascimento.test.tsx \
               src/components/trafego/meta/__tests__/estado-da-operacao.test.ts

python3 scripts/verificar_perfil_schema_meta.py
bash docs/closure/traffic-operational-closure-v2/prova-sql-local.sh
```

| Portão | Resultado |
|--------|-----------|
| sondas de observação | **4 failed** (antes: 4 passed) |
| backend focal + regressões R0 | **196 passed** |
| UI | **42 passed** |
| ciclo SQL descartável | **30 asserções, 0 falhas, exit 0** |
| controle negativo do portão SQL | perfil sem a cerca → **exit 1** |
| TypeScript | 44 erros herdados; **zero** nos paths tocados |
| build | ok |

## O que este handoff NÃO diz

- ❌ Migration oficial aplicada — **não foi**. As duas novas são candidatas.
- ❌ Meta aceitou o payload — **nenhuma chamada real** aconteceu.
- ❌ Campanha criada — nenhuma.
- ❌ Tráfego finalizado, produto em produção — não.
- ❌ **Inspeção visual** — a extensão do Chrome não está conectada nesta sessão.
  A rota responde HTTP 200 e o build passa, e **nenhuma das duas coisas prova
  pixel**. jsdom também não. Desktop/mobile, claro/escuro, foco e teclado e
  nomes longos continuam **não vistos**.

## Próximo ato mínimo do operador

Ler `ADJUDICATION.json` e decidir se autoriza a janela oficial de schema (CP2).
Antes dela, nesta ordem:

```bash
python3 scripts/verificar_autoridade_supabase.py
python3 scripts/verificar_perfil_schema_meta.py
bash docs/closure/traffic-operational-closure-v2/prova-sql-local.sh
# com autorização própria de LEITURA do catálogo oficial:
psql "$CONEXAO" -Atq -f docs/closure/traffic-operational-closure-v2/ler-catalogo-meta.sql > catalogo.json
python3 scripts/verificar_perfil_schema_meta.py --catalogo catalogo.json
```

O último comando classifica o catálogo em `NAO_APLICADO`,
`ESCADA_INCOMPLETA_ATE_<arquivo>`, `PERFIL_ATUAL` ou `PARCIAL_OU_DIVERGENTE` —
por colunas, constraints, assinaturas e grants, e nunca por existência de
tabela.

**Se houver dados no ledger, o conserto é para frente.** Reverter fora de ordem
é pior que não reverter, e os arquivos recusam isso sozinhos. Apagar o ledger
não apaga a campanha; apaga só a prova dela.

## Efeitos desta rodada

Zero push. Zero acesso ao Supabase oficial. Zero chamada real a Meta ou Google.
O Keychain não foi lido. Todo SQL rodou em cluster descartável criado com
`initdb` e destruído ao fim. As flags de criação continuam fechadas.
