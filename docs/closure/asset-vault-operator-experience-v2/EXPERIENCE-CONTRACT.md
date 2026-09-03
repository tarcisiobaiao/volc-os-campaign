# EXPERIENCE-CONTRACT — Cofre operador v2

Registro: PRODUCT (DESIGN.md / design.md).  
Cena: operador administrativo, de dia, cadastrando e conferindo patrimônio **antes** de operar campanha ou publicar.  
Direção: VOLC Mission Control — técnica, compacta, calma. Wow por clareza, não por aurora.

Hallmark · pre-emit critique: P5 H5 E4 S5 R5 V4  
Macrostructure: kicker + H1 + aurora-rule de identidade → faixa operacional de 3 colunas → tabela densa / workspace de onboarding → inspetor de prontidão.

## Perguntas que a página responde imediatamente

1. O que possuímos? — total + estados **nomeados**, só do GET.
2. O que está pronto? — classe dominante, com a ressalva de que **não é veredito de publicação**.
3. O que está sem acesso, vencido ou não verificado? — contagens ou **“sem amostra”** (nunca 0 fingindo saúde).
4. Quais ativos se relacionam? — coluna de relações + lente Relações + detalhe.
5. Qual o próximo ato seguro? — frase do ativo mais urgente, com atalho para o inspetor.

## Quatro áreas (não quatro cards)

### A. Visão operacional
Faixa `border-y`, três colunas assimétricas. Números `tabular-nums` e `font-display`. Frescor + fonte `GET /api/cofre/ativos`. Uma ação contextual: “Abrir este ativo”. Aurora **não** pinta status.

### B. Inventário
`<table>` comparável no desktop (identidade, tipo, owner, estado, verificação, relações, revisão, ação). Agrupamento por gaveta via `th scope=colgroup`. Mobile: lista fora da região “Ativos encontrados”, um ativo = um botão ≥40×40. Uma primária de cadastro no cabeçalho da **página**; empty state tem “Cadastrar o primeiro ativo” (ação de empty, não segunda primária de região).

### C. Onboarding progressivo
Workspace lateral (`xl:grid-cols-[26rem_1fr]`), não modal genérico. Sete etapas, rascunho em `sessionStorage` (`volc.cofre.onboarding.v2`) **sem localizador**. Cada etapa: porquê, obrigatório vs opcional, validação inline. Credencial: cofre / item / campo / nome lógico — o endereço é composto só no POST. MFA, query e campo de senha recusados. Sem botão copiar/revelar.

### D. Detalhe e prontidão
Identidade, procedência, relações, referência **mascarada**, verificações, bloqueadores (cada prontidão no seu painel), trilha, próximo ato. Aposentar/reativar exigem confirmação com consequência. `ProntidaoDeOperacao` e `ProntidaoVisual` permanecem — contratos distintos.

## 1Password — fronteira inequívoca

| Frase | Significado |
|---|---|
| 1Password contém o valor | o segredo não atravessa o browser |
| Cofre contém referência, owner, finalidade, estado | GET nunca devolve localizador |
| Conectado ≠ credencial válida | broker/postura ≠ prova |
| Referência cadastrada ≠ acesso provado | precisa verificação com recibo e data |
| Verificado | método + procedência + instante |
| Cofre bloqueado | `verificacao_estado === blocked` no registro |
| Autorização negada | HTTP 403 / papel ADMIN / página “Acesso restrito” |

Lacunas sem endpoint: resolver segredo, abrir AdsPower, publicar. A UI nomeia a lacuna; não inventa botão.

## Estados obrigatórios (mapeamento)

| Estado | Onde |
|---|---|
| carregando | `Carregando` role=status |
| vazio real | gavetas 0 + “O Cofre está vazio” + visão “Sem amostra” |
| indisponível | 503, texto vazio≠indisponível |
| sem sessão | 401 |
| sem permissão | 403 API **ou** papel ≠ ADMIN na página (VOLC, não cofre externo) |
| com dados | tabela + visão presente |
| falha de mutação | `ErroDoFormulario` role=alert |
| validação inline | etapas do onboarding |
| conflito/idempotência | 409 nomeado; toast de reenvio reconhecido |
| sucesso silencioso | recibo; efeito visível no inventário após invalidate |
| revisão vencida | classe + bloqueador |
| referência sem verificação | postura + classe “Referência sem verificação” |
| cofre bloqueado | `blocked` |
| autorização negada | 403 / página |
| sem correspondência | recorte de filtro |
| relação incompleta | coluna “incompleta” + bloqueador |

## Tokens e movimento

Space Grotesk + Inter via tokens existentes. Press `scale(0.96)`, 150ms `transition-transform`, `prefers-reduced-motion`, zero `transition: all`, foco visível, hit ≥40×40. Luz padrão, dark do shell. Aurora só como `aurora-rule w-16` de identidade.
