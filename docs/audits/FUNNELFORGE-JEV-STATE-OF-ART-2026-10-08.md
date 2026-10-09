# JEV state of the art — integração e canário real

Data: 08/10/2026. Tema congelado: subsídio infantil da Tailândia
(`เงินอุดหนุนเพื่อการเลี้ยงดูเด็กแรกเกิด`), originado no Attention Matrix.
Nada foi publicado ou alterado em WordPress, Supabase ou Ads.

## Objetivo

Testar o JEV no lugar em que ele pode acrescentar valor sem governar o funil:

1. antes da arquitetura, como leitura semântica independente das microtensões;
2. depois da arquitetura, como verificador batelado de arestas e CTAs;
3. sempre consultivo, sem escrever copy, criar/remover páginas ou bloquear por
   uma probabilidade intermediária.

## Ajuste implementado

- Modelo fixado em `jev-1.13.0`, sem alias flutuante.
- As seis famílias emocionais usam `Noul` separadamente. Elas podem coexistir;
  deixam de ser uma escolha exclusiva que soma 100%.
- `Noul` também mede: sinal observável, sensibilidade temporal, consulta
  pessoal, necessidade de canal oficial, resposta editorial possível e
  existência de próximo passo concreto.
- `Choice` ficou restrito a categorias realmente exclusivas, como intenção,
  tipo de entrega e momento da jornada. `Score` mede intensidade, relevância,
  continuação, urgência e ganho informacional.
- O estado enviado inclui país, idioma, volume, CPC, janela, força do sinal,
  origem, prioridade e proveniência. Ausência de dado permanece ausência.
- A segunda chamada avalia todas as arestas em lote: resposta na origem,
  aderência do destino, valor novo, CTA genérico, promessa pessoal indevida,
  motivação e congruência.
- A saída pós-arquitetura só produz `usar`, `revisar` ou `recusar`; não muda o
  grafo e não reescreve CTA.
- O custo do JEV é estimado separadamente quando o provedor não informa valor.
- A normalização da jornada passou a preservar letras e números Unicode. O bug
  anterior fazia duas frases tailandesas distintas parecerem vazias e iguais.

## Desenho do canário

- Mesmo pacote congelado do A/B anterior: cinco consultas reais, 74 mil
  buscas/mês, CPC de US$ 0,04, janela de 08 a 10/10 e pico no dia 9.
- Controle: arquitetura JEV v1 anteriormente gravada, sem nova chamada OpenAI.
- Candidata: uma chamada JEV v2 pré-arquitetura, uma chamada real ao arquiteto
  `chatgpt/gpt-6.1-sol` e uma chamada JEV v2 pós-arquitetura.
- Para comparação justa, uma terceira chamada JEV pós-arquitetura avaliou o
  controle antigo.
- Sem pesquisa, redação, imagem, publicação ou fallback.

## Resultado da leitura pré-arquitetura

O modelo pedido e servido foi `jev-1.13.0`. A chamada levou 0,435 s, usou
9.402 tokens de entrada e 3.480 de saída, com custo estimado de US$ 0,000394884.

Presença média das famílias, sem forçar soma em 100%:

| Família | Probabilidade média |
|---|---:|
| Oportunidade | 63,6 |
| Medo de perder | 40,4 |
| Incerteza | 31,0 |
| Desejo de controle | 23,4 |
| Necessidade de ação | 20,8 |
| Prevenção de erro | 9,6 |

Uma consulta apresentou simultaneamente oportunidade, incerteza e medo de
perder acima de 60. Outra não apresentou emoção forte. Esse é o comportamento
esperado: emoção não é cota e ambiguidade não deve ser preenchida à força.

## Resultado da arquitetura e da revisão de arestas

| Medida | Controle | Candidata | Delta |
|---|---:|---:|---:|
| Páginas | 5 | 5 | 0 |
| CTAs/arestas distintos | 8 | 7 | -1 |
| Destino entrega o prometido | 75,9 | 83,1 | +7,2 |
| Destino acrescenta valor novo | 86,0 | 88,4 | +2,4 |
| CTA parece genérico (menor é melhor) | 51,2 | 50,4 | -0,8 |
| Motivação legítima para continuar | 77,1 | 80,0 | +2,9 |
| Congruência CTA → destino | 94,4 | 96,4 | +2,0 |
| Promessa de resultado pessoal (menor é melhor) | 20,9 | 23,7 | +2,8 |

Com os limiares finais, extremos e consultivos, as 8 arestas do controle e as
7 da candidata ficaram em `usar`; nenhuma foi marcada como `revisar` ou
`recusar`. O recibo bruto conserva a classificação inicial, feita antes dessa
correção: ela tratava a região intermediária do Noul como reprovação. O replay
dos mesmos outputs, sem nova chamada, é a leitura válida.

O validador estrutural também foi reexecutado depois da correção Unicode. O
bloqueio `cta_principal_generico` era falso: desapareceu nos dois lados. Restam
os avisos não bloqueantes `bloco_sem_entrega_correspondente`,
`coorte_fria_sem_resposta_direta` e `cta_sem_correspondencia_no_destino`. O
último é um proxy lexical fraco para tailandês e não contradiz a alta
congruência semântica medida pelo JEV.

## Chamadas, tempo e custo

- JEV: 3 chamadas, 0,435 s + 0,385 s + 0,444 s.
- Custo JEV total estimado: US$ 0,001039794.
- Caminho candidato em produção: 2 chamadas JEV, aproximadamente 0,879 s e
  US$ 0,000697914.
- Arquiteto: 1 chamada real no plano ChatGPT, 239,67 s, modelo servido igual ao
  pedido, 11.437 tokens de entrada e 12.291 de saída.
- Duração integral do canário: 242,61 s.

O JEV não é o gargalo. Nesta amostra, o arquiteto respondeu por praticamente
todo o tempo.

## Veredito

Há ganho técnico real e mensurável no papel estreito escolhido: a candidata
melhorou entrega do destino, valor novo, motivação e congruência, com custo e
latência desprezíveis. Ela também produziu uma aresta a menos sem perder
cobertura.

Isso **não prova ganho de CTR, páginas por sessão, receita ou ROI**. É uma única
amostra, em tailandês, e ainda há avisos estruturais. Portanto:

- manter `jev_enabled=false` por padrão;
- promover primeiro em canários e, depois, numa pequena coorte;
- não deixar o JEV decidir quantidade de páginas, fatos, publicação ou copy;
- medir continuidade, receita por sessão, abandono e revisão humana por
  país/idioma antes de adoção geral.

## Evidência

Artefatos sanitizados fora do repositório:
`/Users/mac/Desktop/VOLC-OS-CAMPAIGN/canarios/jev-state-of-art-20261008/`.

- `receipt.json`: recibo bruto e métricas das chamadas;
- `brief_candidate.json`: perfil multi-label e estado medido;
- `architecture_control.json` e `architecture_candidate.json`: esqueletos;
- `post_control.json` e `post_candidate.json`: respostas semânticas por aresta.

Suíte final do motor: **1.500 passed, 7 skipped, 0 failed**. O ouro V1 continua
intacto.
