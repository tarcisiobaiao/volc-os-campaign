# A/B real — Attention Matrix com e sem JEV

Data: 08/10/2026. Tema congelado do run multipaís do Attention Matrix de
07/10/2026: subsídio infantil da Tailândia
(`เงินอุดหนุนเพื่อการเลี้ยงดูเด็กแรกเกิด`). Nada foi publicado.

## Pergunta

O perfil emocional do JEV melhora a arquitetura, a progressão e os CTAs do
funil quando todo o restante permanece igual?

## Desenho

- Mesmo pacote congelado: 74 mil buscas/mês, CPC de US$ 0,04, janela observada
  de 08 a 10/10, pico aprendido no dia 9 e o mesmo destino oficial.
- Mesmas cinco consultas reais em tailandês.
- A: classificador determinístico/fail-soft atual.
- B: uma chamada real ao `jev-latest`, servida por `jev-1.13.0`, sem fallback.
- Mesmo arquiteto `chatgpt/gpt-6.1-sol`, temperatura zero, uma amostra por lado.
- Dois julgamentos cegos por `chatgpt/gpt-6-astra`, com X/Y invertidos.
- Só esqueleto: nenhuma pesquisa nova, redação, imagem ou publicação.

## Falha descoberta antes da rodada válida

O primeiro A/B era inválido: `chave_da_pergunta` reutilizava o normalizador
ASCII do dossiê factual. Ele apagava o tailandês, descartava duas consultas e
reduzia três delas ao texto `2569`. O falso resultado favorecia o JEV em 6,5
pontos (87,5 × 81,0), mas foi excluído da conclusão.

A correção é localizada na deduplicação de demanda: NFKC + `casefold`,
preservando letras, marcas combinantes e números de qualquer escrita. Um teste
de regressão prova que as cinco consultas tailandesas continuam distintas.

## Rodada definitiva

O JEV respondeu em 0,46 s, com 5.651 tokens de entrada e 1.977 de saída. O
provedor não informou custo. Os cinco sinais foram classificados; a distribuição
ficou ambígua (31,2%), oportunidade (26,8%), incerteza (25,8%), desejo de
controle (8,6%), medo de perder (5,8%), necessidade de ação (1,6%) e prevenção
de erro (0,2%). O clímax foi a pergunta sobre o dia de entrada, classificada
como incerteza/calendário/ação, mas com confiança de apenas 44%.

| Critério | A: heurística | B: JEV |
|---|---:|---:|
| Aderência à demanda | 9,0 | 9,0 |
| Progressão da jornada | 8,5 | 8,5 |
| Distinção entre páginas | 9,0 | 7,0 |
| Força dos CTAs | 8,0 | 7,5 |
| Congruência CTA → destino | 8,5 | 9,0 |
| Precisão emocional | 8,0 | 8,5 |
| Uso do timing | 8,5 | 8,5 |
| Simplicidade mobile | 7,5 | 7,0 |
| Compatibilidade com monetização | 9,0 | 8,0 |
| Segurança de policy | 10,0 | 10,0 |
| **Total** | **86,0** | **83,0** |

Os dois juízes escolheram A, ambos com confiança média. A diferença principal
foi arquitetural: B criou uma página de triagem que repetia distinções já feitas
pela LP, calendário, consulta e troubleshooting. A criou uma quinta entrega mais
distinta (comparação entre programas), embora a demanda dessa comparação não
esteja medida e deva permanecer opcional.

B ganhou somente em precisão emocional e congruência CTA → destino. O melhor
elemento de B foi a linguagem concreta para ausência de pagamento: o que
conferir e quem procurar, sem prometer crédito ou solução.

Ambos os lados terminaram com o bloqueio `cta_principal_generico` e os avisos
`bloco_sem_entrega_correspondente` e `coorte_fria_sem_resposta_direta`. Nenhum
dos dois esqueletos está pronto para produção.

## Chamadas e tempo

- JEV: 1 chamada válida, 0,46 s, modelo servido igual ao esperado.
- Arquitetos: 2 chamadas, 217,58 s e 211,66 s.
- Juízes: 2 chamadas, 24,43 s e 27,27 s.
- Rodada definitiva: 4 chamadas OpenAI no plano + 1 JEV, 484,06 s.
- Sem API OpenAI faturada; custo JEV não informado.

Houve ainda uma chamada JEV técnica anterior cujo resultado não foi persistido
por um erro do harness ao serializar o objeto Pydantic. Ela não integra a amostra
nem a nota e é registrada para transparência operacional.

## Decisão

Este teste **não comprova ganho líquido do JEV na arquitetura**. O resultado
correto é manter `jev_enabled=false` por padrão.

O JEV demonstrou utilidade estreita e barata como sinal auxiliar para copy e
CTA, mas não deve decidir quantidade de páginas nem o grafo. Uma próxima rodada
só vale se testar uma integração menor: manter o esqueleto determinado pela
demanda medida e usar sinais JEV com confiança mínima para sugerir linguagem de
CTA ou revisar redundância. O JEV atual também não recebe volume, CPC, janela ou
força do sinal do Attention Matrix; recebe apenas as perguntas e contexto
básico. Sem essa fusão, chamá-lo de integração state of the art seria incorreto.

Artefatos completos e sanitizados:
`/Users/mac/Desktop/VOLC-OS-CAMPAIGN/canarios/jev-attention-ab-20261008/v2-unicode/`.
