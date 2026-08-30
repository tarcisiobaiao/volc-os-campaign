# Guia de integração em P1, P2 e P3

Este arquivo não reescreve as três páginas inteiras. Ele define os trechos que precisam ser preservados ou substituídos para que o entorno dos novos widgets não volte a contradizer a PR1 canônica.

## P1 — consulta, modalidade e autorização

Preservar e atualizar para o caminho atualmente documentado:

> No App FGTS, toque em **MAIS → Autorização de consulta às informações do FGTS → Empréstimo saque-aniversário → Adicionar instituição**. Procure a instituição desejada e confirme.

Imediatamente depois, manter:

> **Autorizar a consulta não é contratar.** Essa etapa permite que a instituição selecionada consulte os dados necessários. O contrato só é formado depois da simulação, da conferência de taxa, CET e demais condições e da confirmação no canal da instituição.

Fonte oficial depois da explicação: [CAIXA — Perguntas Frequentes da Antecipação](https://www.caixa.gov.br/voce/credito-financiamento/emprestimo/antecipacao-saque-aniversario-FGTS/perguntas-frequentes/Paginas/default.aspx).

## P2 — comparação sem piso comercial falso

Excluir integralmente:

- a pergunta que agrupa R$ 20, R$ 30, R$ 40 e R$ 50 como “operação não permitida”;
- qualquer frase “nenhum banco faz contrato abaixo de R$ 100”;
- qualquer resultado que chame o piso regulatório de “valor mínimo recebido”.

Usar antes da comparação:

> Desde 1º de novembro de 2025, **cada direito anual cedido** à antecipação deve ficar entre R$ 100 e R$ 500. Esse intervalo não é sinônimo de saldo total, valor do contrato nem dinheiro líquido recebido. Uma oferta comercial pode anunciar contrato abaixo de R$ 100 sem alterar o piso do direito anual dado em garantia.

Ordem recomendada de P2:

1. distinção acima;
2. `widgets/roteador-elegibilidade.html`;
3. como comparar taxa e CET;
4. comparação comercial datada, com condição e fonte de cada instituição;
5. aviso de que autorização não é contratação;
6. CTA externo somente depois da comparação.

Não usar o valor comercial de uma instituição como regra do mercado. Se citar uma oferta abaixo de R$ 100, registrar data de verificação e linkar a página primária da própria instituição.

## P3 — demissão, quitação e retorno

Criar estas âncoras antes de inserir o widget:

```text
#multa-rescisoria
#saldo-principal
#quitar-antecipacao
#voltar-saque-rescisao
```

Ordem recomendada de P3:

1. `widgets/diagnostico-estado.html`;
2. multa rescisória;
3. saldo principal;
4. quitação e retirada da garantia;
5. retorno ao Saque-Rescisão;
6. débito automático anual.

Trechos canônicos:

> **Demissão:** enquanto o Saque-Aniversário estiver vigente, a demissão sem justa causa permite movimentar a multa rescisória, quando devida. Ela não libera automaticamente o saldo principal.

> **Quitação:** quitar com recursos próprios pode retirar o bloqueio da garantia depois do processamento. Isso não cria uma hipótese de saque do saldo principal e não encurta o prazo de retorno ao Saque-Rescisão.

> **Retorno:** sem antecipação vigente, o retorno pode ser solicitado, mas só produz efeito no primeiro dia do 25º mês após o pedido.

> **Pagamento automático:** não há prestação mensal descontada da renda. Cada direito anual cedido é debitado automaticamente da conta vinculada na data prevista para o Saque-Aniversário e repassado para liquidar o contrato correspondente.

Excluir qualquer prazo universal de desaverbação. A CAIXA documenta seu próprio fluxo, mas isso não autoriza transformar o prazo de uma instituição em regra para todas.
