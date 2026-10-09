# Ferramentas antes da promessa e da redação

## Entrega

Delta no motor existente, sem outro engine, modelo padrão novo ou revisor extra:

- Perguntas PAA já presentes no contexto do Pautador dispensam nova SERP. A
  coleta existente vem do People Also Ask da DataForSEO; não foi criado um
  cliente novo do produto AlsoAsked.
- No fluxo com brief pré-arquitetura e widgets ligados, requisitos das
  ferramentas saem do complemento editorial e entram em pesquisa dedicada.
  Há até duas rodadas por compilador/run; a segunda recebe apenas as lacunas
  restantes. Evidência ou derivação suficiente dispensa a próxima rodada.
  Erro do provedor interrompe o complemento, sem retentativa cega. Uma rodada
  pode incluir busca e estruturação no adaptador existente: não equivale
  necessariamente a uma única chamada de modelo.
- O arquiteto pode declarar uma calculadora tipada: divisão, multiplicação ou
  percentual, duas entradas e pelo menos dois casos de teste. Python recalcula
  os exemplos; JavaScript fixo usa inteiros BigInt para reproduzir o
  arredondamento Decimal, a duas casas, metade para cima. Não há eval, fórmula
  livre, código gerado, consulta a cadastro ou confirmação de elegibilidade.
- A calculadora Gutenberg é montada e sanitizada antes da redação. O writer
  recebe sua capacidade, não CSS/JS. A injeção reaproveita o bloco congelado,
  também na pré-venda, sem chamada adicional de geração de widget.
- Sem fonte vinculada, componente suportado ou cálculo correto, o pacote usa
  fallback, explicita a limitação e exige revisão humana. Não promete a
  calculadora; não paga outra geração para tentar substituí-la no fim.
- Entrega efetiva e destinos são fechados antes dos CTAs. Rótulos ligados à
  capacidade alterada são reescritos pelo writer existente, mantendo hrefs e
  topologia. A arquitetura original permanece auditável. O JEV existente
  permanece consultivo e opt-in; nenhuma chamada ou mudança de padrão.

## Provas locais

- Motor: **1547 passed, 7 skipped, zero falhas**, incluindo ouro V1.
- Backend, contrato do arquiteto: **11 passed**.
- Chromium real local: divisão, multiplicação e percentual executados com os
  casos de Python; divisor zero recusado; viewport 390×844 sem overflow.
- Testes cobrem PAA sem recoleta, segunda rodada seletiva, limite total,
  timeout sem repetir, derivação sem segunda pesquisa, cálculo inválido,
  ausência de fonte, fallback/CTA e injeção sem chamada de LLM.
- A retomada não duplica o widget; a navegação automática não ressuscita a
  copy original de uma ferramenta retirada quando o writer não escreveu CTA.

## Limites e aceite

Nenhuma chamada real de pesquisa/redação/JEV foi feita nesta rodada. Não houve
WordPress, Supabase, Ads, deploy ou push. Os novos testes usam provedores e
fontes simulados; Chromium executa o widget real, não o tema WordPress real.

O delta de pesquisa e pacote é do caminho existente com
`--card-pre-arquitetura`. A fila HTTP do Pautador não foi exercitada nem
convertida automaticamente para esse caminho. Sua integração end-to-end
continua pendente; não se declara publicação em lote pronta.

O catálogo matemático inicial não resolve simulações financeiras compostas,
regras de elegibilidade ou qualquer fórmula arbitrária. Casos de teste provam
a aritmética, não a interpretação da regra do programa. Essas operações usam
fallback enquanto não houver componente específico e lastro.

P10-T22 permanece **partial**. Falta um canário real com um ativo tipado e fonte
verificada, validação da copy/CTA gerada, integração pela fila HTTP e visual
WordPress. Os bloqueios anteriores do FGTS não foram aprovados por esta prova.
