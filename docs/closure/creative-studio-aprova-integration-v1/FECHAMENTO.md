# Assistente Criativo VOLC com experiência Aprova — fechamento

Branch `execution/volc-os-operacao-80-20`, worktree `/private/tmp/volc-os-operacao-80-20`.
Base da preparação `53d5774`, que era o próprio HEAD quando esta missão começou.

## Os quatro estados, separados de propósito

| Estado | Veredito | Prova |
|---|---|---|
| `SOURCE_IMPORTED` | **SIM** | 129 arquivos em `services/creative-studio/upstream`, travas conferidas de forma independente antes de rastrear |
| `LOCAL_FLOW_READY` | **PARCIAL** | briefing → estratégia → aprovação → refinamento → histórico retomável, mais o *plano* de geração. Galeria e download **não existem** |
| `OFFICIAL_DB_VERIFIED` | **NÃO** | nada aplicado em `database.agenciavolc.com.br`; estado físico permanece desconhecido |
| `LIVE_GENERATION_VERIFIED` | **NÃO** | nenhuma imagem gerada; nenhuma chamada paga feita |

## O que ficou utilizável

No Hub, com `rede=meta` em qualquer aba, o botão secundário **Assistente Criativo**
aparece abaixo de *Nova campanha Meta*, com a configuração discreta ao lado da
primária. O link não herda `?modo=demo`.

`/trafego/meta/assistente-criativo` e `/trafego/meta/assistente-criativo/:projectRef`,
protegidas, com `?view=` para histórico, briefing, estratégia e produção. Recarregar
recupera o contexto; a operação vive no servidor, não em `sessionStorage` nem em blob URL.

O fluxo: preencher briefing com fatos declarados e formatos do catálogo do motor →
criar (que enfileira e devolve as refs sem chamar modelo) → executar → ler diagnóstico,
grupos e peças → aprovar por ref → refinar com o lote anterior em mãos → conferir o
plano de produção com N×M, teto e custo → reabrir tudo pelo histórico.

## Os defeitos que esta missão fechou, e como eles apareciam

**Não havia listagem.** `RepositorioAgenteCriativo` não tinha `listar_operacoes` e
nenhuma rota devolvia as operações do dono. Histórico e retomada eram impossíveis, não
difíceis.

**O LLM rodava dentro do POST.** Duas gerações encadeadas passam de qualquer timeout de
proxy, e o `run_ref` só nascia na resposta que nunca chegava. `criativo/execucao.py` já
tinha documentado e resolvido esse mesmo defeito para imagem; aqui ele seguia de pé.

**A refinação não via o que refinava.** `continuar_operacao` reconstruía o pedido do
`input` original mais os congelados e nunca passava a saída anterior.

**O congelamento apontava para posições.** `/pecas/0` é "a primeira peça do lote", e o
lote é reordenado a cada geração. Pior: o padrão do contrato aceita `-`, e
`lista[int("-1")]` resolve para o **último** elemento — um índice negativo não é só
instável, ele nomeia uma posição que se move na direção contrária à esperada.

**A peça podia falar com o estado mental de outro grupo.** Existir na jornada bastava.

**A v11_05 deixava o cliente fabricar prova.** Com `grant select, insert, update to
authenticated` e policies `for all`, um cliente autenticado insere uma run, dá PATCH
para `COMPLETED` com `output` arbitrário, e insere uma decisão `APROVADO` com
`snapshot_sha256` que só passa por regex. E como ela revoga apenas de `anon`,
`authenticated` ainda herdava DELETE do default ACL quebrado e podia apagar a trilha.

## O que NÃO foi entregue, e por quê

**Galeria, zoom, download individual e ZIP.** Não houve autorização de geração paga,
então não existe asset para exibir. Construir a vitrine antes do acervo produziria uma
tela que parece pronta e não mostra nada — exatamente o "relatório de feito" que o
prompt desta missão proíbe. O caminho até lá está montado e testado: `POST .../geracoes`
cria os jobs pelo `Executor` canônico e a v11_07 registra a procedência.

**Validação visual.** A extensão de browser não conectou nesta sessão. Não há captura
autenticada, e eu **não** declaro aprovação visual. A URL para inspeção humana é
`http://localhost:8080/trafego/meta/assistente-criativo`.

**Cancelamento e retry da geração pela tela do Assistente.** O `Executor` distingue
`cancelado_pedido_em` de `cancelado_em` e o retry só preenche buraco, mas a vista de
produção ainda não expõe esses atos.

## Provas medidas

**Backend.** 4531 → 4556 passando. As 5 falhas restantes são as mesmas de antes de eu
tocar em qualquer coisa: `test_canario_pedido_aprovado` (2), `test_google_inteligencia_persistente`,
`test_meta_real_read_model`, `test_trafego`. Nenhuma nesta frente.

**Frontend.** 1843 → 1859 testes. As falhas são um subconjunto estrito das da base.
⚠️ A base é instável: duas execuções idênticas **antes** de eu mudar qualquer coisa
deram 18 e 20 falhas, e três arquivos `meta-criacao` que falhavam na base passam agora.
Por isso o veredito é "nenhuma falha nova", não um delta numérico exato.

**TypeScript.** ⚠️ `tsc -p tsconfig.json` **não checa nada**: a raiz tem `"files": []` e
só referências de projeto. A verificação honesta é `tsconfig.app.json`, que tem **76
erros pré-existentes** e **zero** nos arquivos desta missão. O primeiro run com o projeto
certo pegou um erro meu — default import de `Layout`, que é export nomeado.

**SQL.** `scripts/provar-ciclo-assistente-criativo.sh` prova v11_05 + v11_06 + v11_07 num
PostgreSQL descartável: apply, uso por `service_role`, recusa de fabricação por
`authenticated`, recusa de DELETE, FK composta barrando run de outro dono, unicidade e
append-only da ponte, rollbacks guardados e reapply idempotente. O cluster reproduz o
default ACL quebrado e dá `BYPASSRLS` a `service_role`, senão a prova de segurança seria
mais fácil que a realidade.

Dois defeitos meus foram pegos por essas provas: a ordem de FK/chave única quebrava o
reapply, e o rollback da ponte lia a confirmação antes de defini-la.

## Externo

Sem push, sem deploy, sem Meta/Google Ads, sem campanha, sem n8n, sem WordPress, sem
geração paga. Nenhuma migration aplicada em banco oficial. O projeto original do cliente
não foi acessado.

`localhost:8080` permaneceu no ar durante toda a missão (mesmo PID). O backend em 8010
foi reiniciado **uma vez**, porque subia sem `--reload` e as rotas novas não existiam
nele: mesma worktree, mesma porta, autoridade Supabase conferida antes, e `PYTHONPATH`
com a raiz como `start-dev.sh` documenta. As rotas novas respondem 401 sem sessão —
existem e falham fechadas.

## Próximo ato

1. Catálogo SQL real do banco oficial por `information_schema`, com conexão SQL — o 404
   do PostgREST não prova inexistência.
2. Autorização do delta v11_06 + v11_07 (a v11_05 já foi pedida pelo operador).
3. Autorização de geração com modelo, quantidade e teto de custo declarados; só então
   galeria, zoom, download e ZIP passam a ter o que mostrar.
4. Inspeção visual humana em 375/768/1440 nos dois temas.
