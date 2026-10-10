# FunnelForge: pesquisar uma vez e entregar melhor (10/10/2026)

Tarefa: P10-T22 (`partial`). Nó: `cap_funnel`. Uma execução real pelo caminho
canônico (`run-volc` + card + perfil, `--canario`: sem publicação e sem imagem
paga), mesmo tema e mesmo esqueleto aprovado do run de 09/10. Nada publicado.
Artefatos fora do Git: `producao/funil-bucket-20261010/`.

## O que mudou no motor

- **Bucket do run** (`adapters/bucket.py`): cada documento é baixado uma vez,
  com espera de quem já está baixando a mesma URL. O cache compartilhado tem
  validade de 24 h; a cópia do run em `bucket/documentos/` não expira. O recibo
  fica em `bucket/recibo_de_rede.json`. A sonda de anúncio e a busca de link
  profundo também passam a rodar uma vez por URL. As páginas citadas são lidas
  em paralelo (até 4).
- **Índice de evidências** (`bucket/indice_de_evidencias.json`). Para cada
  fato, registra:
  - afirmação, documento, trecho da própria fonte e URL final;
  - instituição, separando a conferida no documento da só declarada;
  - data de coleta, vigência quando a fonte traz e abrangência;
  - páginas que usam o fato e divergência.

  Por página, traz o estado de cada requisito. Campo que a fonte não traz fica
  vazio: não há data, nota ou selo inventado.
- **Pesquisa:** uma rodada complementar agrupada, que já inclui as provas das
  ferramentas. Antes eram até três rodadas.
- **Mesmo pacote para redator e revisor:** o inventário do revisor sai do
  pacote congelado (mesmos ids e trechos). O revisor não recebe mais os fatos
  "a conferir" da pesquisa antecipada.
- **Ferramentas antes da promessa:** uma chamada prepara o conteúdo dos widgets
  de orientação (roteador, navegador, comparador, diagnóstico); HTML, CSS e JS
  saem de `widgets/render.py`. Só vira ferramenta o que passa no contrato, no
  sanitizador e no lastro factual. O modelo pode responder `NONE`. No caminho
  com pacotes, nada é gerado depois da redação.
- **Sniper de CTAs** (`pipeline/ctas.py`): uma chamada para todos os botões,
  sobre entregas e ferramentas confirmadas. O código confere todas as arestas,
  limite de 60 caracteres, ausência de URL, número só dos fatos do destino e
  rótulos distintos para destinos distintos. Os rótulos entram nas rotas antes
  do hash do pacote. Numa nova congelada, só voltam ao modelo as arestas cujo
  destino mudou. A justificativa fica em `ctas_do_funil.json`.
- **Policiamento mecânico removido:** a regra "3 frases de 8 palavras" da LP
  saiu. A página sem valor próprio passou a ser achado bloqueante do revisor
  (`congruencia_destino`); repetição que não acrescenta virou ajuste.
- **Tempo por etapa** em `state.tempos`.

## Execução real (do zero, esqueleto aprovado)

| | 09/10 (do zero, depois retomado) | 10/10 bucket |
|---|---|---|
| Pesquisa | 8 chamadas (2 antecipadas + 3 rodadas × 2), 32 consultas | 4 chamadas (2 + 1 rodada agrupada × 2), 26 consultas |
| Arquiteto | 1 chamada, 248 s | 0 (plano aprovado preservado) |
| Ferramentas e CTAs | — | 2 chamadas (43 s + 18 s) |
| Redação | 9 tentativas (2 retentativas) | 10 tentativas (3 retentativas) |
| Revisão global | 1 chamada, 31 s | 1 chamada, 216 s, 310 mil tokens |
| Documentos | sem recibo | 42 leituras pedidas, 21 downloads (7 falharam por WAF/transporte) |
| Sonda de anúncio (Chromium) | sem recibo | 163 pedidas, 12 abertas |
| Parede | 1.159 s (sem terminar a p2) | 758 s |
| Faturado | US$ 0,49 (4 imagens) | US$ 0 (plano ChatGPT; PAA do cache de 16 h) |

As duas colunas não são equivalentes. A de 09/10 chamou o arquiteto, gerou
imagens e foi retomada depois. A de 10/10 preservou o esqueleto e não gerou
imagem.

Tempo por etapa em 10/10 (s): inteligência 140; dossiê global 22;
complemento e consolidação 145; pacotes, ferramentas e CTAs 61; redação 139
(até 3 chamadas em voo); revisão 216; acabamento 28.

Páginas:

- **LP, p3, p4, p6:** aprovadas, gate OK e Chromium OK a 390 e 1440 px.
- **p2:** a redação foi reprovada 3 vezes por defeito do validador (corrigido;
  ver abaixo). O último rascunho real passa agora sem bloqueio. Falta a
  revisão.
- **p5:** em revisão humana. O widget afirmava, sem fato, que a nomenclatura
  "varia entre distribuidoras". O revisor pegou.
- **p7:** em revisão humana. A comparação com o Desconto Social não tem fonte
  verificada; a promessa central fica sem lastro.

Widgets prontos antes da redação: p3, p4, p5. A p6 e a p7 responderam `NONE`,
com motivo. Calculadora da p2 conferida por código.

## Defeitos achados pela execução e corrigidos sem nova chamada

Todos foram conferidos sobre o estado real do run. Não foram exercitados numa
segunda execução.

1. **Validador de afirmação crítica:** só olhava a fonte do primeiro fato com o
   mesmo número. A p2 citava a ANEEL; o primeiro fato era da EDP. Agora vale
   qualquer fato que sustente a afirmação. Na LP e na pré-sell, número com fato
   verificado e fonte não nomeada vira ajuste do revisor; número sem fato
   continua bloqueando. Rascunho real da p2: de 4 bloqueios para 0.
2. **SEO determinístico:** cortava o H1 visível e a descrição no meio da frase
   ("…e por onde"). Agora mantém o título inteiro até 70 caracteres e fecha a
   descrição em frase completa. Conferido nas 7 páginas.
3. **Instrução de lacuna contraditória:** a p6 tinha 5 fatos com "100% nos
   primeiros 80 kWh" e a ordem "não afirme valor"; o redator tirou o número.
   Agora a lacuna só restringe o que não está nos fatos.
4. **Prompts:** fatos iam duas vezes ao redator, e o pacote ia inteiro ao
   revisor, com o CSS/JS dos widgets e as políticas repetidas por página. Agora
   o redator recebe os fatos uma vez, com o trecho da fonte (390 mil caracteres
   nas 7 páginas, contra 486 mil). A revisão global caiu de 1,08 milhão para 379
   mil caracteres. Os tamanhos foram medidos renderizando o estado real.
5. **Saída oficial:** com fatos compartilhados, as 5 páginas de solução saíam
   para a Cemig. Agora a ordem é fonte da própria página, depois emissor oficial
   nacional conferido. No estado real, as 5 passam para a ANEEL.
6. **Widget:** o prompt passou a proibir afirmar variação ou igualdade sem fato
   comparativo. Sem prova ao vivo.

## Contraprova da LP

- LP curta que responde passa no portão.
- O portão não conta frases.
- A LP-ponte é segurada por achado bloqueante do revisor, numa só chamada.
  Sem o achado, a cautela não segura a página.

Ver `tests/test_portao_destino_pago.py`.

## Limites e próximo passo

- **Cobertura ruidosa:** 5 de 7 páginas ficaram em "review". Os fatos da
  pesquisa antecipada ficam presos às perguntas do PAA, e não aos requisitos do
  esqueleto; a p6 marcou "alcance do desconto" como indisponível com o fato no
  bucket. Com esse sinal, propor ajuste de entrega automaticamente pioraria
  páginas boas. Por isso o ajuste de entrega da p7 **não** foi implementado.
- **Próximo passo:** com esqueleto aprovado, a primeira rodada deve pesquisar os
  requisitos do esqueleto (mesmas 4 chamadas). Só então o motor deve propor o
  menor ajuste de entrega e registrar o delta.
- **Primeira dobra da LP:** o subtítulo voltou a descrever a navegação, e o
  revisor aprovou.
- **Imagens:** as das prévias foram reaproveitadas do run de 10/10 (aprovadas
  por revisão de imagem) e marcadas no recibo de composição. Os prints oficiais
  são novos.
- **Prévia:** não é WordPress. O CSS do MU-plugin não está no site, e a rota
  HTTP não foi executada.
