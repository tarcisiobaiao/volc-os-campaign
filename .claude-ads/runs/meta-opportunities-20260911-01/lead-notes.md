# Revisão do lead sobre a pesquisa — 2026-09-11

A pesquisa teve grounding, mas isso não prova cada frase. Considere as fontes como
pistas; as páginas Meta consultadas diretamente pelo lead não puderam ser abertas.

1. Flexível em Tráfego NÃO foi confirmado. O guia fornecido anteriormente pelo
   operador limitava a OUTCOME_SALES e OUTCOME_APP_PROMOTION. Não afirmar Tráfego,
   limites de mídia, equivalência com dynamic creative ou endpoints sem confirmar
   a versão e a elegibilidade. Usar capability probe/contrato existente como requisito.
2. Remover números universais de elegibilidade VALUE/ROAS, limites de conversões e
   valores distintos: sem fonte específica conferida. Não propor falsificar Purchase
   com receita GAM nem tratar evento de rewarded como renda individual observada.
3. Não comprovada a condição 'webhook somente ACTIVE', lista exata de permissões,
   casing ou payload de recommendations. Tratar como contrato a verificar. A notificação
   é sinal e não substitui consulta/reconciliação periódica.
4. Não generalizar que LPV exige necessariamente Pixel/CAPI: a definição e requisitos
   precisam de fonte específica. Preservar diferença entre clicks, outbound clicks,
   LPV, sessão medida no site e impressão GAM, sem supor funil 1:1.
5. Google Publisher Tag tem trafficSource OPTIONAL, permite PURCHASED e alimenta a
   dimensão Traffic source. Sem configuração retorna undefined. Confirmado diretamente
   em https://developers.google.com/publisher-tag/reference#googletag.PrivacySettingsConfig.trafficSource .
   NÃO há nessa referência prova de penalidade automática pela ausência desse campo.
6. Receita estimada pode sofrer ajustes de tráfego inválido/fechamento/pós-pagamento.
   Confirmado em https://support.google.com/admanager/answer/12958957?hl=en e
   https://support.google.com/admanager/answer/6053295?hl=en . Google não expõe sempre
   detalhamento por data/site; não distribuir ajustes exatos a adsets sem evidência.
7. Limite de 10 dimensões, detalhes de freeform, datas de depreciação e subcodes de
   Advantage+ não foram conferidos pelo lead. Omitir números e datas não sustentados.
8. Fórmulas podem ser ferramentas internas condicionais. 'Receita por mil visitas'
   exige visitas reais e coorte compatível; receita GAM/adset pode ser estimada, não
   faturada. Break-even CPC exige outbound clicks atribuídos à mesma janela/coorte.
9. A função financeira já existe. O diferencial deve ser maturidade/confiança/custos
   ou ação/experimento, não refazer o mesmo dashboard. Copy já recebe contexto salvo.
10. Prioridade P0 aqui significa habilitador para decisão, não bug crítico comprovado.
    Nenhuma oportunidade equivale a feature implementada ou melhoria validada da conta.
