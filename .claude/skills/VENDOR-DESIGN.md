# Skills de design vendorizadas

Instaladas a pedido do Tarcisio em 15/10/2026 (thread "D0 direção de design e skills").
Elas são só instruções: nenhum código executa, e nenhuma dependência entrou no `package.json`.

## Precedência

`PRODUCT.md` e `design.md` vencem qualquer regra destas skills. Elas foram escritas para landing
pages e produtos genéricos. Algumas regras contrariam o VOLC de propósito, como "sem gradiente
azul-roxo", "duas famílias de fonte" e "nada acima de 24px na UI". Por isso, cada `SKILL.md`
ganhou uma nota local de precedência logo depois do frontmatter. Essa nota é a única alteração
feita no texto original.

## Origem

Baixadas em 15/10/2026 de `raw.githubusercontent.com/<repo>/main/...`. O proxy da nuvem não
expõe o SHA do commit, então a versão fica registrada pelo SHA-256 do arquivo original, antes da
nota local.

| Skill | Origem | Licença | SHA-256 (16 primeiros) |
|---|---|---|---|
| `design-taste` | `madebymustafa/design-taste` `skills/design-taste/SKILL.md` | MIT | `c848bbddfdea8996` |
| `taste-design-system` | `madebymustafa/design-taste` `skills/taste-design-system/SKILL.md` | MIT | `e8962e5db14e5714` |
| `taste-color` | `madebymustafa/design-taste` `skills/taste-color/SKILL.md` | MIT | `e56ad74bef333f3d` |
| `taste-typography` | `madebymustafa/design-taste` `skills/taste-typography/SKILL.md` | MIT | `8c9ce32d56237ade` |
| `taste-motion` | `madebymustafa/design-taste` `skills/taste-motion/SKILL.md` | MIT | `c8b4f6ae093ebee7` |
| `taste-accessibility` | `madebymustafa/design-taste` `skills/taste-accessibility/SKILL.md` | MIT | `4d293f850d91330f` |
| `taste-design-review` | `madebymustafa/design-taste` `skills/taste-design-review/SKILL.md` | MIT | `9082d8464ad0f5aa` |
| `better-design` | `marvkr/better-design` `skills/better-design/SKILL.md` | MIT | `aa8f5fd1146f87c4` |

O texto da licença MIT acompanha cada skill no arquivo `LICENSE` da sua pasta.

Ficaram de fora deste lote os packs de gênero (`dark-tech`, `quiet-luxury`…), `taste-gsap`,
`taste-landing-page` e o resto do catálogo, porque não servem a um dashboard de dados.

## Better Design: só a skill, sem o MCP

A skill `better-design` depende do MCP do Better Design para buscar as diretrizes. **O MCP não foi
conectado.** Sem ele, a própria skill avisa que não está conectada e para. Conectar o MCP é
decisão separada, por dois motivos:

1. O instalador (`npx better-design`) roda na máquina de quem conecta.
2. Ferramentas como `review-ui-code` mandam código para um serviço de terceiro. É a mesma
   questão que levou a recusar o Superdesign.

Se o MCP for ligado um dia, use só as consultas de princípio (`get-ui-principle`,
`get-ux-principle`, `get-review-rules`), que não enviam código.

## Atualizar

Baixe o `SKILL.md` original de novo, compare o SHA-256, reaplique a nota de precedência e atualize
esta tabela. Nunca instale por `npx skills add` direto no repo sem esta revisão.
