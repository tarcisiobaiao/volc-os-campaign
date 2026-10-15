# A/B cego do escritor Gutenberg

Mesmo estado, pacote factual, prompt, gates e pós-processamento. Só o modelo escritor muda.
Nenhum conteúdo foi publicado.

## Resumo

- Nota média: gpt-6-sol 75.4; gpt-6.1-sol 80.5.
- Gates do writer: gpt-6-sol 2/4; gpt-6.1-sol 4/4.
- Latência mediana do provedor: gpt-6-sol 53.3s; gpt-6.1-sol 46.7s.
- Tamanho médio: gpt-6-sol 538 palavras; gpt-6.1-sol 596 palavras.
- Dataset aceito: 8 gerações e 4 julgamentos cegos completos. API faturada: não.

| Página | gpt-6-sol | gpt-6.1-sol | Vencedor | Gates |
|---:|---:|---:|---|---|
| 2 | 75.0 | 83.0 | gpt-6.1-sol | gpt-6-sol: FAILED, gpt-6.1-sol: OK |
| 3 | 69.0 | 77.0 | gpt-6.1-sol | gpt-6-sol: FAILED, gpt-6.1-sol: OK |
| 4 | 76.5 | 79.5 | gpt-6.1-sol | gpt-6-sol: OK, gpt-6.1-sol: OK |
| 5 | 81.0 | 82.5 | empate | gpt-6-sol: OK, gpt-6.1-sol: OK |

Vitórias por página: `{"gpt-6-sol": 0, "gpt-6.1-sol": 3}`

## Página 2

Vencedor: **gpt-6.1-sol**.
A apresenta as três situações de entrada sem interrupção e contextualiza o primeiro botão com a dúvida que ele efetivamente resolve. B oferece destinos corretos, mas posiciona o primeiro CTA depois da orientação sobre retirada e antes de completar as opções, tornando a escolha menos fluida. Ambos usam títulos e botões funcionais e excedem a síntese necessária a um hub; A vence pela conexão mais consistente entre dúvida, explicação e próximo clique, não pela quantidade de conteúdo.

- gpt-6-sol: 75.0/100; 461 palavras; 4 tipos de bloco; 0 sinais lexicais de IA; 1 issues do writer.
- gpt-6.1-sol: 83.0/100; 443 palavras; 4 tipos de bloco; 0 sinais lexicais de IA; 0 issues do writer.

## Página 3

Vencedor: **gpt-6.1-sol**.
A vence pela precisão e pela utilidade nas seções que o leitor tende a procurar: o checklist traz os limites necessários e a seção de consulta reúne canais, telefones e interpretação sem exigir retorno à abertura. Também evita transformar qualquer motivo de ausência do vale em pendência. B é mais enxuto, mas parte dessa economia reduz a autonomia das seções. Ambos explicam corretamente o destino do clique final, porém antecipam indevidamente o primeiro botão de retirada.

- gpt-6-sol: 69.0/100; 477 palavras; 7 tipos de bloco; 0 sinais lexicais de IA; 2 issues do writer.
- gpt-6.1-sol: 77.0/100; 645 palavras; 7 tipos de bloco; 0 sinais lexicais de IA; 0 issues do writer.

## Página 4

Vencedor: **gpt-6.1-sol**.
B vence por pequena margem: informa já na primeira frase onde localizar a revenda, inclui uma orientação específica para dificuldade com SMS e posiciona a saída ao MDS logo após o procedimento de identificação. Isso melhora a ligação entre problema, resposta e encaminhamento, sem extrapolar os fatos. Ambos usam listas e tabela com função real e respeitam o dossiê factual. A principal falha compartilhada é o primeiro CTA para o CadÚnico: a condição correta no encerramento não corrige o desvio inicial.

- gpt-6-sol: 76.5/100; 708 palavras; 7 tipos de bloco; 0 sinais lexicais de IA; 0 issues do writer.
- gpt-6.1-sol: 79.5/100; 749 palavras; 7 tipos de bloco; 0 sinais lexicais de IA; 0 issues do writer.

## Página 5

Vencedor: **empate**.
B vence por pequena margem: transforma a verificação em uma sequência operacional escaneável, orientando acessar, comparar os dados com a situação familiar e identificar pendências. Essa composição ajuda a executar a tarefa, não é apenas decoração. Ambos entregam os fatos essenciais, respeitam o pacote e descrevem honestamente o clique como acesso à orientação externa do MDS, sem prometer consulta direta ou concessão. A principal limitação compartilhada é a repetição entre a abertura e o corpo.

- gpt-6-sol: 81.0/100; 505 palavras; 7 tipos de bloco; 0 sinais lexicais de IA; 0 issues do writer.
- gpt-6.1-sol: 82.5/100; 549 palavras; 7 tipos de bloco; 0 sinais lexicais de IA; 0 issues do writer.
