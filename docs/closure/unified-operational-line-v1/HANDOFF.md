# Linha operacional única

`execution/volc-os-operacao-80-20` é a única linha autorizada para a próxima
implementação. Branches `spec/*`, `sprint/*`, `integration/*`, `candidate/*` e
`agent/*` são evidência histórica; não são bases de execução.

## O que foi consolidado

- Código aceito de Search, Cofre, Pautador, Estúdio, Meta e Google multicanal já
  estava na história ou chegou por patches equivalentes da linha operacional.
- Os cinco pacotes documentais ainda exclusivos foram importados para
  `docs/specs/` sem alterar runtime.
- O contrato de frescor do grafo agora aponta para a autoridade versionada
  `docs/volc-os-graph/BUILD-STATUS.json`.

O inventário completo, incluindo SHAs e decisões de não integração, está em
`BRANCH-RECONCILIATION.json`.

## Regra para o próximo marco

Todo novo executor deve partir do HEAD publicado de
`execution/volc-os-operacao-80-20`, usar a mesma worktree operacional e produzir
commits lineares nela. Não crie feature branch ou worktree paralela sem uma
necessidade de isolamento explicitamente aprovada pelo operador.

O checkout `main` permanece em quarentena: ele contém uma fotografia antiga e
mudanças locais que não podem ser apagadas implicitamente. Limpeza de refs e
worktrees é uma etapa administrativa posterior ao push e exige autorização
específica.
