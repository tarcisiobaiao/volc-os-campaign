# Dashboard Meta por nível — 10/09/2026

## Resultado local

Tarefa **P11-T06**, capacidade **cap_meta_ads**: implementação local verificada;
produção permanece **partial**. Não houve migração, escrita Meta, geração paga
ou alteração do Webgo nesta rodada.

Rota de validação: `/dashboard/campaign/campanha-descoberta-01?rede=meta&modo=demo`.
O demo injeta o mesmo contrato no componente real, sem fallback nem API remota.

## Experiência

- Campanha: KPIs globais, período, gestão existente e conciliação expansível.
- Conjuntos: finanças e entrega próprias; nome abre os anúncios daquele pai.
- Anúncios: busca, filtro de conjunto, miniatura, gasto, impressões, cliques,
  CTR, CPC e CPM. Abrir o anúncio mostra detalhe e ações contextualizadas.
- Criativos: galeria agrupada por identidade, usos em anúncios, copy e
  identidade/publicação quando esses campos existem na leitura.
- Pausa/duplicação continuam **preparando propostas**, sem executor de gestão
  remoto. Salvar no pack pertence ao anúncio, nunca ao conjunto.
- Os SVGs locais são prévias fictícias explicitamente marcadas, não imagens
  geradas nem reproduções dos ativos da conta. A leitura real atual não possui
  URL/copy persistidos suficientes: a UI informa indisponibilidade.

Impeccable orientou hierarquia, contraste das superfícies, ações compactas e
rolagem local. Ads orientou grão de medição e separação entre preparo e execução.

## Contrato e limites

`FinanceiroMeta` recebeu campos aditivos `anuncios`, `anuncios_completo` e
`anuncios_impedimentos`. Cada linha contém referências opacas do anúncio/pai,
gasto, impressões, cliques, CTR/CPC/CPM, frescor e completude. O backend resolve
campanha dentro da conta antes de consultar a cadeia conjunto → anúncio.

O coletor passa a ler Insights `campaign`, `adset` e `ad` no mesmo intervalo,
com orçamento total de 100 páginas e 90 segundos. Não soma níveis entre si.
A consulta de métricas por anúncio tem limite de 20×500 linhas e 20 segundos;
inventário limitado a 200 conjuntos/500 anúncios. Limites/falhas são explícitos.
Ausência de dias, moeda/fuso incompatível, grão incorreto ou duplicado não vira
zero nem total inventado. Taxas são recalculadas dos totais.

Receita GAM permanece no conjunto; campanha soma seus conjuntos. Não há rateio
de receita, ROAS ou lucro por anúncio/criativo. A galeria mostra desempenho dos
**anúncios atualmente vinculados**, não atribuição histórica comprovada à peça:
o snapshot de vínculo não é uma timeline de trocas do criativo.

Hooks escondem dados de outro escopo já no primeiro render, descartam respostas
atrasadas e impedem duplicar paginação com cliques/callbacks repetidos.

## Provas

- Vitest integrado: **65/65**, seis arquivos (demo, explorer, ações, leitura,
  escopo e financeiro). Reexecução da leitura após conciliação lazy: **25/25**.
- Pytest integrador: **87 passaram, 1 excluído**. Sem exclusão: 87 passaram e
  o teste legado `test_sql_e_rollback_de_insights_sao_coerentes` falhou por
  referenciar `supabase/migrations/v15_02_meta_ads_insights.sql`, inexistente.
  Os dois novos arquivos de backend cobrem 31 casos, incluindo transporte falso
  do adaptador real até o payload de snapshot.
- Build Vite aprovado; avisos globais de chunks/CSS permanecem.
- TypeScript global: **76 erros**, nenhum diagnóstico nos arquivos desta fatia;
  não declarado aprovado globalmente.
- Chrome hermético: 375/1440 × claro/escuro, abas e detalhe, 16 capturas;
  teclado e ausência de overflow do documento conferidos. Corrigido escape dos
  rótulos `sr-only` para fora da região rolável no mobile. Sem pageerrors.
  Capturas temporárias: `/private/tmp/meta-explorer-{largura}-{tema}-{vista}.png`.
- QA adicional da `MetaCampaignReadView` inteira com provider demo: 375/1440
  claro, quatro abas e detalhe, dez capturas em `/private/tmp/meta-main-*`.
  Cabeçalho/período integrados, alteração de período, teclado e largura do
  documento conferidos; nenhum erro JavaScript. Continua sem sessão autenticada.
- Frontend 8080 e backend 8010 responderam HTTP 200. Isso não prova autenticação.
- `git diff --check` focal limpo.
- Memória reconciliada em P11-T06 e `doc:meta_dashboard_levels`, ligado a
  `cap_meta_ads`. Rebuild canônico e `--check`: `current: true`, 10/09 04:43 -03.

## Pendências honestas

Faltam sincronização real dos três níveis e QA autenticado da campanha real.
Snapshots antigos sem nível `ad` não ganharão métricas retroativamente sem
releitura. Enriquecimento seguro de imagem/copy real e histórico de vínculos
não foram implementados. Executor governado de pausa/duplicação segue pendente.
Não houve alteração de permissões ou ativação de campanha.

Referência consultada: [paginação Supabase e ordenação](https://supabase.com/docs/reference/python/range).
A consulta do changelog markdown falhou; a página oficial Meta Insights retornou
429. Nenhuma capacidade remota nova foi declarada comprovada com base nisso.
