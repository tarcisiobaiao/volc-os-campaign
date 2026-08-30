# Mapa de decisão da landing page

## Decisão

Escolher a **opção B: três botões — PR1, P1 e P2 — e P3 como link contextual no corpo**.

O critério é receita por sessão, não simetria de interface. Como cerca de 80% dos cliques já se concentram na primeira ação, PR1 deve absorver a dúvida ampla e abrir uma rota interna coerente para as três soluções. Entre os cerca de 20% restantes, P1 e P2 atendem os dois próximos passos mais frequentes: confirmar o estado no aplicativo e comparar depois de cumprir as condições. Transformar P3 em quarto botão dividiria ainda mais essa parcela sem criar informação nova; um link imediatamente após o trecho sobre demissão e quitação mantém a intenção específica acessível e tende a preservar mais navegação interna antes da saída.

Assim, a LP tem **três botões e quatro destinos internos possíveis**. P3 não desaparece: perde apenas o peso visual de um botão concorrente.

## Hierarquia dos botões e do link contextual

| Ordem visual | Texto do botão | Destino | Papel |
|---|---|---|---|
| 1 — primário, acima da dobra | **Descobrir se posso antecipar** | `https://creditoup.com.br/rec/quem-tem-direito-antecipar-fgts-pr1/` | Entrada padrão e única pre-sell |
| 2 — secundário | **Consultar saldo e ativar no App FGTS** | `https://creditoup.com.br/rec/como-consultar-fgts-pelo-cpf-p1/` | Usuário sabe que precisa operar no aplicativo |
| 3 — secundário | **Comparar limites e caminhos para receber** | `https://creditoup.com.br/rec/bancos-antecipar-fgts-pix-whatsapp-p2/` | Usuário já passou pelas condições básicas |
| 4 — link contextual, não botão concorrente | **Fui demitido, já antecipei ou quero voltar** | `https://creditoup.com.br/rec/regras-demissao-quitar-emprestimo-fgts-p3/` | Estado posterior ou excepcional |

### Implementação visual

- Acima da dobra: uma promessa factual curta, uma linha de risco e somente o botão primário.
- Logo abaixo: bloco “Já sabe o que precisa fazer?” com os dois botões secundários.
- O destino P3 aparece como link textual após a explicação sobre demissão, quitação e retorno de modalidade.
- Não repetir quatro botões com o mesmo peso em cada seção.
- Todos os links internos permanecem na mesma aba.

## O que a LP precisa responder antes do clique

1. **O que é:** antecipação é um empréstimo garantido por direitos futuros do Saque-Aniversário.
2. **O que não é:** não é um saque livre de todo o saldo do FGTS.
3. **Quatro verificações mínimas:** modalidade ativa; 90 dias desde a adesão; direito anual de pelo menos R$ 100 para cessão; situação de operação já vinculada à próxima competência.
4. **Um exemplo executável:** saldo total de R$ 1.000,00 gera saque anual de R$ 450,00 pela tabela legal.
5. **A distinção crítica:** saque anual calculado, valor anual cedido, valor do contrato e valor líquido recebido não são o mesmo número.
6. **A consequência na demissão:** no Saque-Aniversário, a demissão sem justa causa dá acesso à multa rescisória quando devida, não automaticamente ao saldo principal.

## O que deve sair da LP

- A frase “o FGTS rende menos que a inflação”.
- Qualquer piso comercial apresentado como regra de todas as instituições.
- Promessa de aprovação, liberação instantânea ou prazo universal.
- Tabela completa, tutorial completo do App FGTS e explicação longa sobre quitação. A LP dá a resposta mínima e leva à página especializada.
- Repetição de aviso de independência em cada bloco. Um aviso claro no rodapé é suficiente.

## Bloco de copy recomendado para a dobra

> **Veja se a antecipação do Saque-Aniversário faz sentido no seu caso**
>
> Confira as regras atuais, calcule seu saque anual e descubra o próximo passo — sem confundir saldo do FGTS com valor que pode ser antecipado.
>
> **[Descobrir se posso antecipar]**
>
> A antecipação é um empréstimo com garantia de saques anuais futuros. Contratação, taxas e valor líquido dependem da instituição.

## Eventos mínimos da LP

| Evento | Disparo | Parâmetros permitidos |
|---|---|---|
| `lp_primary_cta_click` | clique no botão principal | `destination: pr1`, `placement: hero` |
| `lp_secondary_cta_click` | clique em P1 ou P2 | `destination`, `placement` |
| `lp_state_link_click` | clique no link para P3 | `destination: p3`, `placement` |

Não enviar saldo, CPF, nome, respostas de formulário ou texto digitado ao `dataLayer`.
