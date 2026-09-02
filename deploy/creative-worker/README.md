# Creative worker — runtime de vídeo aqui, empacotamento ainda não

⚠️ **Este cabeçalho mudou em 02/09/2026 e o anterior virou falso.** Ele dizia
"território reservado… nada aqui representa um worker disponível", e isso deixou
de ser verdade quando `remotion-runtime/` entrou. Um README que descreve o
diretório vazio de ontem é pior que nenhum: ele é lido como estado atual.

## O que EXISTE aqui agora

- `remotion-runtime/` — projeto npm próprio do VOLC O.S., com lockfile próprio,
  Remotion **4.0.479 em lockstep**, uma composição, e a fonte Inter que já estava
  versionada sob OFL 1.1. Não é a fábrica externa e não a lê.
- `sem-rede.sb` — perfil de `sandbox-exec` com `(deny network-outbound)` e
  exceção só para loopback. É o que faz o render ser hermético **por
  impossibilidade**: o kernel recusa `connect()`.
- `REMOTION-HERMETICO.md` — os requisitos levantados antes disto existir, com o
  que foi cumprido marcado.

`node_modules/` **não é versionado**: rode `npm ci` dentro de `remotion-runtime/`.
O Chrome Headless Shell é baixado pelo Remotion na primeira execução (~93 MB).

## O que CONTINUA não existindo

Empacotamento operacional. Não há imagem, manifesto, unit systemd nem entrada de
`Procfile` que suba `python -m app.criativo.bancada.worker` em produção. Fora do
teste, ninguém executa este worker.

⚠️ E a **equivalência de pixel macOS ↔ Linux é NÃO PROVADA**: o Chrome baixado é
`mac-arm64` e o compositor instalado é `@remotion/compositor-darwin-arm64`. O
determinismo provado é na mesma máquina.

A implementação futura só entra depois de existir a porta única de depósito de
P17-T04 e deve permanecer fora do processo web e da máquina do Supabase oficial.
