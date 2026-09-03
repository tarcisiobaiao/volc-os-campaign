# ACCESSIBILITY — Cofre operador v2

Alvo: WCAG 2.2 AA na superfície do Cofre (não o shell global).

## Teclado
- Abas com `aria-pressed` e hit ≥40×40.
- Onboarding: etapas `aria-current="step"`; Continuar/Voltar/Fechar focáveis.
- Tabela: identidade e “Abrir” são botões, não linhas mortas.
- Inspetor: ações e confirmação (`role="alertdialog"`) no tab order.
- Foco: `focus-visible:ring-2` instantâneo (não fade).

## Nome acessível
- Carregando: `role="status"` “Carregando o inventário”.
- Alertas de API: `role="alert"` com heading próprio (401/403/503/config).
- Gavetas: `{rótulo} {n}`.
- Região da tabela: “Ativos encontrados”; mobile: “Ativos no telefone” (DOM separado para não duplicar nomes no leitor).
- Fechar painéis: `aria-label="Fechar"`.

## Não só cor
Estado e verificação têm palavra (`STATE_LABEL`, `VERIFICATION_LABEL`) + marca. Números tabulares. “incompleta” escrito na coluna de relações.

## Motion
`active:scale-[0.96]` coberto por `motion-reduce:transition-none motion-reduce:active:scale-100`. Spinners `motion-reduce:animate-none`. Sem `transition: all`.

## Hit e texto
Botões `min-h-10 min-w-10`. Headings `text-balance`, corpo `text-pretty`. Nomes longos truncam na tabela (`min-w-0 truncate`), não estouram o viewport; a tabela desktop rola **dentro** de `overflow-x-auto`, a moldura tem `overflow-x-clip`.

## Contraste
Tokens do produto (`primary` / `muted-foreground` / `destructive`). Aviso 403 da página distingue autorização VOLC de cofre bloqueado em texto, não só em cor.

## Limitações
- O shell (`Layout` / `Navigation`) está fora do ownership; landmarks globais não foram redesenhados.
- Selects nativos herdam o UA; não há listbox custom.
- Confirmação de aposentar não prende o foco (não é modal). É um bloco inline — intencional para não empilhar diálogo sobre o inspetor.
