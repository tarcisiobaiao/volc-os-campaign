# Recuperação do motor real: causas e prova (09/10/2026)

Tarefa: P10-T22 (`partial`). Nó: `cap_funnel`. Mesmo card e mesma arquitetura
aprovada do ensaio da Tarifa Social de 09/10, para comparar antes e depois.

## Causas encontradas

| Defeito visto | Causa concreta |
|---|---|
| Interface ≠ motor validado | `publicacao.py`: `perfil_execucao="completo"` (padrão do diálogo) não aplicava preset → `config.yaml` (sem editorial V2, sem dossiê, 1 worker, redator Gemini com fallback pago). O worker passava só o plano pronto: sem PAA, pesquisa antecipada, brief nem pacotes pré-redação. Os 8 runs do worker em 08/10 não tinham brief. |
| CTAs "Entender como…" | `copy_rapida.jinja` ensinava "Entender o que muda…/Ver como…"; `copy_contract.py` reprovava consultar/calcular/receber e mandava usar "Ver como…"; o arquiteto pedia "dor + resposta + consequência" num botão (60–76 caracteres). |
| CTAs mornos | Classificador emocional desligado; o fallback heurístico marcou 84% das perguntas como "ambígua" e o brief disse ao arquiteto "não force emoção". |
| URL/"fonte:" na LP e pre-sell | Regras contraditórias: "número na mesma frase que o link da fonte", fatos com URL no prompt, "ponha o hyperlink real"; só a LP tinha regra sem link e o deslinkador só tirava `<a>`. Pre-sell real com 13 links ANEEL. |
| Lâmpada como hero | Briefing visual só com H1/objetivo/keywords; proibia âncoras do nicho e dizia "People are optional"; o revisor só checava risco, não contexto. |
| Sem prints | Detector de overlay tratava o botão residual "Redefinir Cookies" do gov.br (3,1% da tela) como banner. |
| Sem ferramentas | Arquiteto declarava 0 ativos e 0 prints em todas as páginas. |
| Texto cauteloso | Doutrina de escrita não cobria ressalvas empilhadas nem objeções que ninguém levantou. |

## Correções (caminho ativo)

Despacho canônico + card do Pautador para o motor (`perfil.py`, `worker.py`,
`publicacao.py`; retomada usa o preset com que o run nasceu); CTA por resultado
e curto no arquiteto e no redator, gate por risco real (consulta pessoal,
pagamento, aprovação, ferramenta inexistente) e não por verbo; fallback
emocional honesto; LP/pre-sell citam em prosa (instituição), sem URL, com
saneador também após o patch do revisor; soluções com link oficial uma vez por
fonte; briefing visual com a situação do leitor e revisor que reprova
natureza-morta no hero; detector de overlay ignora controle residual curto;
blocos Gutenberg pela forma do conteúdo; regras de prints e ferramentas no
arquiteto.

## Execução real (sem publicar)

`run-volc --card-pre-arquitetura` (o comando que o worker agora monta),
preset `completo_chatgpt`, 3 workers.

- 1.159 s no run + 146 s retomando a pre-sell (portão de citação corrigido) +
  recaptura dos prints. 31 tentativas de texto, todas `chatgpt/gpt-6-sol` ou
  `gpt-6.1-sol` pedido = servido, sem fallback, sem `response.incomplete`.
- Faturado: US$ 0,4854 (4 imagens + 4 revisões Gemini). Quota ChatGPT não
  tem preço por chamada; não é custo zero.
- Aprovadas: LP, pre-sell, 2 soluções. Retidas pelo revisor (decisão humana):
  distribuidoras, conferir na fatura e Desconto Social — evidência por
  distribuidora e critérios completos da TSEE ausentes no inventário.
- LP e pre-sell: 0 links externos, 0 URLs. Soluções: 1–2 saídas oficiais.
- 3 prints oficiais limpos (cookies recusados). Hero com pessoa, conta e
  medidor; sem logo.
- Calculadora de renda por pessoa declarada, não entregue: a pesquisa não
  comprovou o salário-mínimo vigente de 2026 nem o escopo da regra; a página
  explica a divisão em texto e não alega ferramenta.
- Chromium 390 px e 1440 px: todos os checks passam, exceto links para as 3
  páginas retidas. Preview local não executa tema, plugins, Elementor nativo
  nem anúncios.

Artefatos: `producao/recuperacao-motor-20261009/` (fora do Git).

## Limites restantes

Navegação incompleta enquanto p4/p5/p7 aguardam decisão; tabela de 2 colunas
quebra palavras a 390 px; print desktop fica pequeno no mobile; subtítulo da
LP ainda é meta ("Entenda… e escolha…"); rota HTTP → fila → worker não foi
exercitada ponta a ponta nesta rodada (o comando do worker foi).
