# Validação real: mineração → arquitetura → redação → WordPress draft

## Resultado

Parcial. Tema novo: **Tarifa Social de Energia Elétrica**, Brasil, português.
Os serviços reais mineraram o termo, a arquitetura gerou seis páginas e o motor
escreveu as seis com três workers. Três páginas passaram pela revisão e pelos
gates finais e foram criadas como rascunhos no CreditUp. Três continuam em
revisão, sem escrita no WordPress. O funil completo não está aprovado.

P10-T22 continua `partial`; nó operacional `cap_funnel`.

## O que foi exercitado

- `MiningOrchestrator`, com Google Ads Keyword Planner OAuth, DataForSEO e
  agentes Gemini reais: 92,029 s, 300 termos após combinação, sem mock.
- O termo `tarifa social de energia elétrica` teve 6.600 buscas/mês no resultado.
  O volume agregado inclui termos navegacionais amplos; não representa demanda
  exclusiva pelo benefício nem prova rentabilidade.
- PAA real pelo sensor DataForSEO já existente no Attention Matrix, com cache.
  Não foi uma chamada ao produto AlsoAsked nem houve mudança naquele engine.
- Oportunidade experimental, mineração e seis páginas da arquitetura registradas
  no Supabase operacional pelo serviço e pela PageFactory existentes.
- `build_deps` e `run_pipeline`, preset `completo_chatgpt`, Editorial V2,
  três workers, geração de hero, imagens, screenshots e widgets habilitados.
  Sem engine alternativo. Os pacotes pré-redação existentes continuam valendo.
- Texto e pesquisa via sessão ChatGPT do projeto; imagens Gemini e avaliação
  multimodal via API. Não houve fallback faturado da redação.
- Escrita remota pelo `step_publish` e `WordPressPublisher` originais, somente
  para páginas aprovadas, com `publish_status=draft`. Não houve geração manual
  de conteúdo substituindo o redator nem aprovação humana fabricada.

**Limite importante:** este ensaio chamou as classes reais pelo terminal. Não
provou o login, a rota HTTP de disparo, a fila e o worker da interface ponta a
ponta. Não marca essa integração como concluída.

## Correção pequena revelada pela execução

A pré-pesquisa terminou `response.incomplete: max_output_tokens`: o lote de
requisitos usava o teto de 2.500 tokens de um microprobe. Parei a execução antes
da redação, preservei a arquitetura e retomei apenas a pesquisa e as etapas
posteriores. Não regenerei a mineração ou a arquitetura.

`pesquisa_plano.py` agora calcula a saída pelo número de requisitos, com teto
finito de 12.000. Uma necessidade isolada preserva os limites anteriores.
`response.incomplete` continua recusado; uso e motivo da falha são conservados.
Não há nova retentativa automática nem aprovação de texto truncado.

Depois da correção e do complemento: 22 fatos, 19 verificados, dois não
comprovados e um indisponível. A pesquisa veio com citações do provedor e as
fontes foram verificadas pelo código.

## Páginas e rascunhos

| Página | Resultado | Inspeção autenticada |
| --- | --- | --- |
| LP | Aprovada; imagem gerada/aprovada e enviada; Elementor draft | [Editar LP](https://creditoup.com.br/wp-admin/post.php?post=2492&action=elementor) |
| Quem tem direito | Aprovada; Gutenberg e imagem; draft | [Editar pré-sell](https://creditoup.com.br/wp-admin/post.php?post=2495&action=edit) |
| Como obter | Revisão pendente; depende da página de canais | Sem escrita remota |
| Canal por distribuidora | Revisão pendente; entrega central sem canais verificados | Sem escrita remota |
| Confirmar na conta | Revisão pendente; rota central ausente e destino insuficiente | Sem escrita remota |
| Quanto se paga | Aprovada; Gutenberg e imagem; draft | [Editar solução](https://creditoup.com.br/wp-admin/post.php?post=2498&action=edit) |

REST autenticado confirmou os três status `draft`, tipos e mídia. WP-CLI somente
leitura confirmou na LP dados Elementor em array, três nós, modo `builder`,
template `elementor_canvas` e plugin carregado. A árvore válida não prova que o
editor visual abrirá sem erro: falta o usuário abrir o editor autenticado.

**Navegação incompleta:** a LP e a pré-sell ainda apontam também para páginas que
ficaram somente locais. Não tratar estes rascunhos como funil navegável completo.

## Qualidade, tempo e custo

- Seis redações; uma retentativa na pré-sell. Pico medido: três chamadas em voo.
- Retomada após correção: 620,078 s. Não é o tempo total desde a mineração:
  exclui a primeira pesquisa, o arquiteto (204,404 s), a interrupção e a inspeção.
- Imagens das três páginas aprovadas foram geradas e aprovadas. Hero inspecionado.
- 12 renders locais Chromium (seis páginas × mobile/desktop) passaram nos checks
  existentes de overflow, interação, contraste, headings e erros JavaScript.
  Os previews das páginas reprovadas são explicitamente não aprovados.
- Preview não executa PHP/DOM nativo Elementor, CSS completo do tema, plugins,
  editor autenticado ou anúncios reais; CLS local não prova CLS com anúncios.
- Ledger do motor registra US$ 0,294770 para geração/avaliação de imagens.
  O preço da quota ChatGPT não é retornado; não equivale a custo total zero.
  O custo integral da mineração não veio no recibo. Não afirmar um total fechado.
- A interrupção preservou o checkpoint, mas não há recibo completo da chamada
  de estruturação que estava em voo. Não afirmar contagem exata de todas as
  requisições desde o início, incluindo mineração e interrupção.

## Ajustes necessários, sem recomeçar tudo

1. Fechar a pesquisa de canais de distribuidoras elétricas antes de redigir a
   promessa operacional. O recorte entregue pelo harness incluía termos de
   saneamento (`tarifa social embasa`); a revisão detectou que uma fonte sobre
   água não resolve a entrega prometida sobre energia. Não substituir pesquisa
   insuficiente por link externo genérico nem aprovar esses textos à força.
2. Encurtar os CTAs pela ação e entrega reais. Os atuais continuam extensos e
   burocráticos; aprovação factual não comprova apelo ou CTR.
3. Melhorar a composição: a pré-sell ficou longa, com listas/tabela mas pouca
   variedade visual. Check técnico verde não significa composição excelente.
4. Exercitar um ativo tipado de verdade. A arquitetura deste ensaio declarou
   zero ativos; a pesquisa dedicada registrou zero tentativas. Não saiu widget,
   e este run não valida a calculadora ou sua segunda pesquisa ultranichada.
5. Recuperar o print oficial sem contaminação. O provider rejeitou o quadro por
   `lgpd-reset-cookies` (3,1% de área). Pode ser falso positivo de controle de
   privacidade, mas isso não foi comprovado nem contornado. Nenhum print foi
   embutido; etapa `OK` com aviso não significa screenshot entregue.

## Provas preservadas

Diretório local, fora do Git:
`/Users/mac/Desktop/VOLC-OS-CAMPAIGN/producao/validacao-e2e-20261009/`.

Contém mineração, recibos Pautador/WordPress, checkpoint antes da correção,
estado final, pesquisa/dossiê/pacotes, prompts, logs e `visual/receipt.json` com
screenshots. Helpers operacionais não contêm credenciais; utilizam os loaders
existentes em memória. Nada disso precisa ser copiado para o repositório.

Suíte completa após a correção: **1.550 passed, 7 skipped**; recorte de pesquisa,
publisher e screenshot: **84 passed**. Sem push, deploy, alteração de Ads,
migration ou alteração de páginas preexistentes. Apenas novos registros deste
ensaio e novos drafts/mídias autorizados.
