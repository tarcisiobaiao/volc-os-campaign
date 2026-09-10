# Superfície da jornada e ações por entidade

P11-T13: refinamento local de interface. Sem alteração de API, Supabase, permissões ou objetos Meta.

A skill Impeccable orientou uma superfície de trabalho distinta do canvas mineral, com tokens existentes dos dois temas, espaçamento responsivo, identificação da pergunta e navegação no mesmo bloco. Mantidos formulário, persistência, aprovação e execução.

Ações na hierarquia agora têm texto visível e alvo mínimo de 44px. Conjuntos oferecem apenas preparar pausa/cópia, abaixo da identificação do conjunto. Salvar no pack aparece somente nos anúncios, com guarda defensiva no handler do componente. O endpoint existente de pack não foi removido ou modificado. Pausa e cópia continuam propostas: o executor remoto dessas ações permanece indisponível, explicitamente informado no diálogo.

## Provas e limites

- Build e git diff --check passaram.
- Testes de ações e read view passaram (28 testes). Incluem ausência de salvar pack em conjunto e confirmação de pack com alvo de anúncio correto.
- Bancada antiga: 7 passaram e 12 falharam. Baseline isolada, retirando apenas o delta JSX deste ajuste por plugin de transformação, reproduziu exatamente os mesmos 12 nomes de falha. Não é uma suíte global verde nem evidência de fechamento do engine.
- Chrome isolado com componentes reais e fixtures de conta/rascunho: 375/768/1440, claro/escuro, perguntas Destino/Resultado e dashboard demonstrativo. Sem erro JavaScript ou overflow da página; teclado, diálogo de pack e reduced motion conferidos. Serviços externos bloqueados. Não usou sessão do operador nem publicou.
- Superfície clara medida: rgb(245,247,250) sobre canvas rgb(214,219,225); escura: rgb(23,28,39) sobre rgb(13,17,23).
- Capturas locais: /private/tmp/meta-workspace-{width}-{theme}.png, meta-result-{width}-{theme}.png e meta-hierarchy-{width}-{theme}.png. Harness: /private/tmp/qa-meta-workspace-surface.mjs; resultados: /private/tmp/meta-workspace-visual.log. Artefatos temporários não são retenção permanente.

O aceite remoto da campanha continua pendente em P11-T09/P11-T11. Este refinamento não muda esses estados.
