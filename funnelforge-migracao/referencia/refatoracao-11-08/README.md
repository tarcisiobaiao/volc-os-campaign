# Pacote de refatoração do funil FGTS

Artefatos preparados em **11/08/2026**. Nenhum arquivo de produção foi alterado e nada foi publicado no WordPress.

## Arquivos

- `01-base-factual.md` — fatos autorizados, fontes primárias, datas de vigência e alegações excluídas.
- `02-mapa-lp.md` — hierarquia dos quatro destinos e conteúdo mínimo da LP.
- `03-PR1-canonica-gutenberg.html` — copy integral em blocos Gutenberg, com CSS escopado e comentários `PROTEGE`/`MATA`.
- `widgets/roteador-elegibilidade.html` — widget completo para P2, antes da comparação comercial.
- `widgets/diagnostico-estado.html` — widget completo para P3, antes das explicações detalhadas.
- `04-redirecionamentos.md` — decisão, ordem de implantação, regras 301 e testes.
- `05-guia-integracao-p1-p2-p3.md` — substituições mínimas para que as páginas de solução não contradigam a PR1 e os widgets.

## Sequência recomendada de publicação

1. Salvar backups/revisões privadas de LP, PR1, PR2, PR3, P1, P2 e P3.
2. Publicar PR1 com o HTML do arquivo canônico.
3. Corrigir P2 e inserir o roteador de elegibilidade antes de qualquer oferta ou comparação.
4. Corrigir P3, criar as quatro âncoras documentadas no widget e inserir o diagnóstico de estado.
5. Revisar P1 preservando o passo explícito no App FGTS para modalidade e autorização.
6. Refatorar a LP com a hierarquia de CTAs documentada.
7. Atualizar todos os links internos para PR1.
8. Aplicar os 301 de PR2 e PR3.
9. Limpar caches e executar os testes funcionais, responsivos e de redirect.
10. Só então decidir sobre retomada de mídia.

## Regras de integração dos widgets

- Colar cada arquivo em um bloco HTML Personalizado ou em um componente que permita `<script>`. Uma conta administradora do WordPress normalmente é necessária para preservar scripts.
- Não reutilizar os mesmos IDs duas vezes na mesma página.
- Não mover os scripts para carregamento assíncrono sem testar a inicialização após cache/minificação.
- O roteador de P2 só libera a rota de comparação quando as cinco respostas básicas se alinham: modalidade, prazo, direito anual, operação ativa e autorização da instituição.
- O diagnóstico de P3 não usa pontuação: a prioridade declarada e os estados informados determinam uma rota nominal.
- Os eventos usam `dataLayer` e nunca enviam respostas, CPF, saldo, contrato ou texto digitado.

## Eventos emitidos

| Evento | Finalidade |
|---|---|
| `widget_start` | primeira interação |
| `widget_validation_error` | tentativa incompleta |
| `widget_complete` | primeiro diagnóstico concluído |
| `widget_result` | tipo nominal do resultado |
| `widget_cta_click` | clique no próximo passo |

Dimensões permitidas: `widget_id`, `result_type`, `error_type` e `destination`. Cada evento de ciclo é protegido contra disparos duplicados na mesma instância de página.

## Critérios antes de reabrir tráfego

- Fatos e números conferidos contra `01-base-factual.md`.
- Nenhum uso de “R$ 100” como contrato mínimo universal.
- Nenhuma promessa de que quitar libera o saldo principal para saque.
- Nenhuma frase absoluta de rendimento abaixo da inflação.
- PR2 e PR3 respondendo com um único 301 para PR1.
- P1, P2 e P3 respondendo `200` e sem canonical cruzado indevido.
- Widgets testados por teclado, em leitor de tela básico e em larguras de 320, 375, 768 e 1280 px.
- `dataLayer` sem respostas individuais nem dados pessoais.
- Consentimento, aviso editorial e política de privacidade conferidos no ambiente publicado.
- Regra transitória sinalizada para nova revisão em 01/11/2026.
