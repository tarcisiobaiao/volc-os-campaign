# A/B cego do escritor Gutenberg

Data: 08/10/2026. Escopo: escrita dos quatro posts internos do canário Gás do
Povo. Nenhuma pesquisa, imagem, publicação ou mutação externa foi executada.

## Método

- Mesmo estado, dossiê, pacote factual, jornada, rotas, prompt atual, gates e
  pós-processamento para os dois candidatos.
- Uma geração por página com `gpt-6-sol` e uma com `gpt-6.1-sol`, pela sessão
  ChatGPT do operador, sem fallback e sem retentativa.
- Avaliação cega por `gpt-6-astra`, sem revelar o modelo. Critérios: intenção,
  valor da resposta, progressão do CTA, brevidade, naturalidade, composição
  Gutenberg e fidelidade factual.
- O gate determinístico do writer prevalece sobre a nota subjetiva.
- Evidências textuais do juiz foram conferidas contra os artigos.

## Resultado

| Métrica | gpt-6-sol | gpt-6.1-sol |
|---|---:|---:|
| Nota média cega | 75,4 | **80,5** |
| Gates aprovados | 2/4 | **4/4** |
| Vitórias | 0 | **3** |
| Empates | 1 | 1 |
| Latência mediana do provedor | 53,3 s | **46,7 s** |
| Palavras por página | **538** | 596 |
| Tokens de saída, quatro páginas | **7.306** | 7.584 |

O `gpt-6.1-sol` ganhou as páginas 2, 3 e 4 e empatou a página 5. O ganho mais
forte não foi cosmético: o modelo passou 4/4 gates, enquanto o `gpt-6-sol`
falhou na página 2 (`directional_copy_outside_widget`) e na página 3
(`bloco_sem_fechamento` e `texto_fora_dos_blocos`). O modelo novo também foi
12,4% mais rápido na mediana e obteve 5,1 pontos a mais no placar cego.

## Limites e achados compartilhados

- É uma triagem com uma amostra por página, não uma medição de variância nem um
  teste de conversão. O resultado autoriza usar `gpt-6.1-sol` no próximo
  canário de escrita, não declarar superioridade universal.
- O modelo novo produziu artigos 10,8% mais longos. O prompt ainda precisa de
  um orçamento de palavras por papel e da regra "a abertura responde; o corpo
  avança, não repete" para atingir brevidade inteligente.
- Na página 4, os dois modelos receberam um CTA superior para CadÚnico antes de
  existir uma condição cadastral. Na página 3, ambos anteciparam a retirada.
  Como o motor preserva o CTA tipado, esses defeitos pertencem ao pacote/rota e
  não devem ser corrigidos escolhendo outro escritor.
- Na página 5, os dois repetiram parte da abertura no corpo. O `gpt-6.1-sol`
  organizou melhor o procedimento, mas a diferença de 1,5 ponto foi tratada
  como empate.
- Durante a montagem do harness, um lote de juiz não foi preservado após um
  `503` transitório. Duas tentativas posteriores foram recusadas com
  `invalid_json_schema` antes de inferência. O resultado acima usa somente as
  oito redações e os quatro julgamentos completos e persistidos; o consumo de
  quota das tentativas não persistidas não é informado pelo servidor.

## Veredito

Há ganho real e consistente nesta amostra. Recomenda-se promover
`gpt-6.1-sol` como escritor do próximo canário, mantendo `gpt-6-sol` apenas
como referência de benchmark, sem fallback silencioso. Antes de torná-lo o
padrão definitivo, repetir as duas páginas mais difíceis e medir o sinal real
de navegação/conversão.

Artefatos locais: `funnelforge-migracao/engine/runs-canario/ab-writer-gas-20261008/`.
