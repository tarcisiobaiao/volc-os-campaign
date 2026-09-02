# Creative Factory — Production Go-Live V1

**Estado:** `LOCAL_CLOSURE_COMPLETE_EXTERNAL_CHECKPOINT_READY`

A fábrica criativa já implementada foi **integrada** na linha oficial que tinha
avançado, submetida a um pente-fino executável em sete contratos, corrigida numa
única rodada, e atravessada de ponta a ponta por uma peça-canário que passa por
um **processo de worker separado**. O que falta para chamar de produção depende
de autorização externa e está inteiro em `EXTERNAL-AUTHORIZATION.md`.

## Procedência

| | |
|---|---|
| Base | `382c5d4c67fc521d5e6739f8e76d1c36a96fdb53` (`origin/volc-os-v2`) — **igual ao esperado pelo prompt** |
| Feature integrada | `5235f0c6d8a6c526b42bf64342373471cd14ebe4` — **igual ao esperado** |
| Merge-base | `c8ca8628e83742dd7da5242f0a015f76292aafe7` |
| Merge | `87cfcef` (`--no-ff`, sem rebase, sem squash) |
| HEAD | `2fe767e` |
| Branch | `sprint/creative-factory-production-go-live-v1` |
| Worktree | `/private/tmp/volc-creative-factory-production-go-live-v1` |
| Árvore | limpa na criação e na entrega |

**64 arquivos** contra a base, dos quais **17 são desta lane** (os outros 47 vêm
da feature integrada).

## 1. A integração, e por que ela não podia ser silenciosa

A linha oficial avançou **4 commits** depois do ponto em que a feature saiu:
`publisher_quality` (scanner de superfície, fetch, ground truth), inventário de
repositório, curadoria e grafo. Rebasear ou fazer squash apagaria a procedência
de um dos dois lados.

O merge foi `--no-ff` explícito, e há três provas de que ele não perdeu nada:

1. **Zero arquivos em comum.** A interseção entre `diff(merge-base → feature)` e
   `diff(merge-base → oficial)` é vazia.
2. **`merge-tree` previu a árvore antes do merge**, e o `HEAD^{tree}` saiu
   `62bcc28e10ba0dd595665a7e5605debe328990ed` — idêntico à previsão.
3. **União pura, por aritmética de patches.** O `sha256` de
   `diff(oficial → HEAD)` é igual ao de `diff(merge-base → feature)`, e o de
   `diff(feature → HEAD)` é igual ao de `diff(merge-base → oficial)`. O merge
   **não alterou uma única linha de nenhum dos dois lados** — não houve resolução
   de conflito para errar.

Não-regressão medida por execução: `publisher_quality` 8/8; a bateria
publisher + asset vault + tráfego + mensuração **1114 passed · 15 skipped ·
0 failed**; nenhum id de teste da linha oficial desapareceu (a coleta cresceu de
2687 para 2725, e os 38 novos são todos da feature).

## 2. O que esta lane consertou, e como cada um foi provado

Cinco commits atômicos. Cada um traz a contraprova vermelha no corpo da mensagem.

### `c8c54c0` — o passo 0 mandava parar, e era ele que estava errado

`PACOTE-v11_03.md` abre mandando o operador conferir os `sha256` e **parar se um
divergir**. Dois dos oito estavam errados, e eram a própria migration e o arquivo
de provas. Medido: desde `e273103` — o commit que **escreveu** a tabela — o
arquivo sempre teve `3aa77687…` e a tabela sempre disse `33b55c52…`. O hash
**nunca esteve certo**, nem no nascimento.

O dano não é o susto. É o passo seguinte: quem encontra divergência num documento
que manda parar, e descobre que a divergência é do documento, aprende a pular o
passo 0 — e a guarda deixa de existir para o dia em que a divergência for real.
A contagem do ciclo caiu no mesmo buraco pela **terceira** vez (129 → 166 → 178).

O conserto que importa é `test_v11_03_identidades_declaradas.py`: o que faltava
não era acertar o número, era alguém conferir.

### `2ffaf5d` — o hash que o banco recusa não chega mais ao banco

`Publicacao.para_registro()` emitia `storage_sha256_remoto` com o prefixo
`sha256:`, e o CHECK `criativo_render_artefato_hash_remoto_forma` exige
`^[0-9a-f]{64}$`. **Contraprova em PostgreSQL 17 com a v11_03 aplicada:**

```
A) 'sha256:20981c58…'  ERROR: violates check constraint
                              criativo_render_artefato_hash_remoto_forma
B) '20981c58…'         1 linha gravada
```

É o mesmo formato do defeito da chave canônica de UM underscore, e a mesma
consequência: **no dia da aplicação da v11_03, toda gravação de artefato com hash
remoto conferido seria recusada.** Como aplicar a v11_03 é o item 1 da
autorização, o defeito atinge exatamente o ato que se vai autorizar.

E o conserto estava pela metade — quem mostrou foi um teste que já existia: o
escritor passou a normalizar e o **leitor** continuava comparando as formas cruas,
levantando "veredito contradiz o hash remoto" sobre uma linha **certa**.

### `dbf55ad` — a cerca estava no chamador e não no portão

`Operario._ainda_somos_donos` confere `(operario, tentativa, vivo)` e a docstring
diz "a posse é da REIVINDICAÇÃO, não do nome". Quem **grava** é o depósito — e ali
a única pergunta era o nome. O nome padrão é `worker-<pid>`, e PID repete entre
containers. Reproduzido:

```
zumbi     reivindica -> tentativa=1, 'worker-4242', lease vencido
dono vivo reivindica -> tentativa=2, 'worker-4242'   (mesmo PID)
o zumbi acorda e devolve o trabalho para a fila: ACEITO
```

Atinge o **item 4** da autorização — "um executor remoto para o worker" —, porque
o furo só aparece com mais de um worker, que é o que aquele item autoriza.

### `d15b4ca` — a rodada corretiva da auditoria interna

Auditoria de sete contratos com refutação adversarial por achado: **37 achados,
32 refutados, 5 sobreviveram**. Um deles era a cerca. Os outros quatro estão aqui:
o MIME era declarado pelo motor e nunca medido (gate novo, bloqueante); o contrato
publicado do gate de rede descrevia o desenho anterior; `validar_asset` nunca
julgava geometria de vídeo; e o gate oficial não cobria o adapter Postgres.

### `2fe767e` — a revisão do Codex derrubou quatro coisas minhas

E as quatro eram sobre correções que eu tinha **acabado de fazer**. A cerca de
`dbf55ad` tinha dois buracos que eu não vi (`motor_desconhecido` escrevia
`FAILED` sem cerca nenhuma; `bater()` deixava o zumbi renovar o lease do dono
vivo). O gate de MIME de `d15b4ca` tinha exatamente o buraco que veio fechar —
`image/webp` produzia dois `SKIPPED` não-bloqueantes, e dois SKIPPED somam um
caminho verde sem ninguém abrir o arquivo. A peça-canário podia dizer "todas as
afirmações conferidas" sem os fatos. E minhas próprias guardas podiam passar sem
conferir nada: uma linha malformada sumia em silêncio, e um CHECK **comentado**
contava como proteção.

Mais uma hipótese que ele registrou por não ter Postgres, e que era verdadeira:
em `autocommit=True`, o `select ... for update` de `DepositoPostgres.transicionar`
soltava o lock antes das guardas — check-then-act com janela real. Medido aqui,
consertado, e provado: 8 concorrentes disputando um estado terminal agora dão
**1 vencedor e 7 recusas**; antes, todos passavam.

## 3. A peça-canário do go-live

`scripts/produzir_peca_canario_go_live.py`. A canário do last-mile prova o
contrato do operário — mas chama `operario.executar(...)` **dentro do próprio
processo**. Em produção quem produz é `python -m app.criativo.bancada.worker`, e
um pedido que só funciona quando o web o executa não é um pedido durável.

Esta enfileira pela mesma porta, sobe o worker como **subprocesso real**, e lê o
recibo **do depósito** depois que esse processo já saiu.

| Peça | Formato | Bytes | sha256 | Storage | Produzida por |
|---|---|---|---|---|---|
| imagem | `image/png` 1200×628 | 27 568 | `31dbc13f…` | `VERIFIED_OK` | `worker-<pid>`, **outro processo** |
| vídeo | `video/mp4` 1080×1920 | 448 196 | `3e5ae270…` | `VERIFIED_OK` | idem |

O veredito confere **14 afirmações nomeadas** por peça — código de saída do
worker, existência do arquivo, estado do storage, destinos avaliados, nenhum gate
bloqueante em `FAIL`, entre outras — e elas entram no JSON de evidência. As 14
passam nas duas peças. A primeira versão deste veredito olhava menos do que
prometia, e foi a revisão do Codex que mostrou.

Os dois hashes são **bit-idênticos** aos que o last-mile declarou, reproduzidos
noutra worktree, com `npm ci` novo e noutro processo. Determinismo que se repete
em dois ambientes é o que sobrou de fato.

Nas duas, a aprovação nasceu `aguardando`. **Nenhuma foi aprovada** — aprovar em
nome do dono é ato externo. Varredura por URL de plataforma no recibo: **zero**.

⚠️ **Depósito local e descartável.** Isto **não** é produção: `mktemp`, SQLite,
armazenamento local. A declaração honesta é a do critério de encerramento A.

## 4. Revisores

- **Codex `gpt-5.6-sol`** — adversarial final, read-only. **Dois BLOQUEANTES,
  dois ALTOS e uma hipótese**, todos sobre correções desta lane, todos
  reproduzidos e fechados em `2fe767e`. Seção 6 de `GATES.md`.
- **Gemini 3.7 Flash — `PROVIDER_NOT_AVAILABLE`.** O CLI existe (`0.57.0`) e não
  tem método de auth nesta máquina: sem `~/.gemini/settings.json`, sem
  `~/.gemini/oauth_creds.json`, sem `GEMINI_API_KEY` e sem `GOOGLE_API_KEY` no
  ambiente. A chave existe dentro de arquivos `.env` de projeto, e **ler segredo
  de disco para alimentar um CLI é o padrão que a missão anterior flagrou como
  risco no parque externo**. Declarado em vez de simulado — é a mesma fronteira
  da missão anterior, e ela não mudou.
- **Auditoria interna** — 7 contratos, 44 agentes, refutação adversarial por
  achado. É de onde saíram os 5 sobreviventes da rodada corretiva.

## 5. O que esta lane NÃO fez, por restrição

Não editou — e não pode editar — `volc-os-workbook/ROADMAP-VIVO.json`,
`docs/volc-os-graph/curadoria-operacional.json`,
`docs/volc-os-graph/volc-os-graph.json` nem `graphify-out/**`. O delta proposto
vai em `CURATION-HANDOFF.json`, para o integrador único aplicar uma vez.

⚠️ **O Mapa Vivo está defasado, e isso é declarado.** `graphify-out/` não é
rastreado e não existe nesta worktree; na árvore principal, `UPDATE_STATUS.json`
diz `built_at_commit: a539dbd`, que não é o HEAD de lugar nenhum desta linhagem.
Nenhuma afirmação deste pacote depende do grafo.

## 6. Índice

| Arquivo | O que responde |
|---|---|
| `GATES.md` | todos os números, com o comando que os produziu |
| `CAPABILITY-MATRIX.json` | o que a fábrica faz de verdade, por destino |
| `EXTERNAL-AUTHORIZATION.md` | o pedido único de autorização |
| `CURATION-HANDOFF.json` | o delta para o integrador |
| `contraprovas/PECA-CANARIO-GO-LIVE.json` | a evidência técnica da canário |
