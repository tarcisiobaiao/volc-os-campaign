# Validação real do redator — 09/10/2026

## Veredito

O motor existente rodou de ponta a ponta, com pesquisa real, arquiteto real e redação paralela. Não está aprovado para publicar em lote: a pré-sell reprovou por falta de citação de uma afirmação crítica. Prints e ferramentas não foram entregues neste canário. Nada foi publicado.

Teste executado pelo Codex neste chat, sem delegação, outra branch ou worktree. Checkout oficial: `volc-os-campaign-qg-real-20261007`, `main`, HEAD inicial/final do teste `65fe772`. O checkout histórico `volc-os-campaign` foi preservado.

## Prova real

- Tema: Gás do Povo, cinco páginas, com referência anterior congelada para preservar entregas e IDs.
- Origem: card congelado → implementação e prompt reais do arquiteto → pipeline normal FunnelForge. **Não** foi disparado pela interface/rota HTTP do Pautador nem por um card novo no Supabase.
- Modelo: `gpt-6.1-sol` em todas as chamadas; autenticação existente `chatgpt_plan`, catálogo conferido, sem API key nem fallback faturado.
- 11 chamadas: quatro de pesquisa/estruturação, uma do arquiteto, cinco de redação e uma de revisão batelada. As buscas grounded registraram cinco consultas, fontes e citações.
- Tempo total: **658,856 s (10min59s)**. Arquiteto: 256,824 s. Redação: aproximadamente 95,4 s para cinco páginas, com **pico observado de três chamadas simultâneas**. Revisão: 75,736 s. Pesquisa, checagens ao vivo e montagem entram no total.
- Dossiê final: 17 fatos verificados. Uma promessa central ainda teve lacuna de cobertura; verificação de fatos não equivale a cobertura integral.
- Cinco textos gerados. **Quatro content gates finais OK**: LP, validação, revenda e CadÚnico. A pré-sell não foi montada nem passou para revisão.
- Pré-sell: `critical_claim_without_citation`, trecho “24 meses”. O número tem lastro no dossiê, mas o corpo só atribui ao MDS por nome, sem a URL exigida pelo contrato das internas. A saída operacional foi desativada por falta de canal verificado; é necessário distinguir citação documental de botão para o serviço, sem flexibilizar a exigência factual.
- Revisão batelada: quatro páginas aprovadas. Revisão global determinística: aviso de primeira dobra na página da revenda, sem bloqueio e sem reescrita. Isso não aprova a página excluída.
- Prints oficiais: quatro rejeições por overlays em três soluções; nenhum print incorporado. Os gates impediram screenshots obstruídos, mas não provaram a recuperação da captura.
- Ferramentas: três registros `widget_ausente_publicado_assim_mesmo` (nome legado do alerta, **não houve publicação**). Disponibilidade interativa não demonstrada; fallback não equivale a widget funcionando.
- Geração de imagens, JEV e coleta paga PAA foram explicitamente excluídos. Portanto, **não há prova da imagem obrigatória da LP** nem comparação JEV nesta rodada.
- Custo do plano: não informado pelo servidor. Nenhuma chamada por chave de API; não tratar quota de assinatura como custo zero comprovado.
- `publisher=None`, `publish=false`, zero páginas publicadas. Sem mutações WordPress, Supabase, Ads, deploy ou push.
- O manifesto do código ficou estável durante a geração. As correções descritas abaixo ocorreram **depois**, com replay offline, não com um segundo canário de geração.

## Duas correções pequenas e duráveis

1. O gate existente agora confere URLs externas completas contra as fontes resolvidas da página, links oficiais e plataformas verificadas no contexto V2. Mesmo host com caminho errado ou query funcional diferente reprova. Fragmentos e parâmetros de rastreio conhecidos não criam falso bloqueio. O comportamento legado V1 não mudou.
2. A descrição SEO determinística usa o conteúdo redigido (intro da LP ou primeiro parágrafo), nunca instruções de `resposta_imediata`. Sem conteúdo válido, a descrição fica vazia. Sem nova chamada, classificador ou lista de palavras proibidas. O replay não sobrescreveu os textos, metadados corrigidos pelo revisor ou aprovações do canário.

Os testes novos falharam antes da correção e passaram depois. Teste de contexto comprova que o writer recebe a lista verificada, não apenas que o validador funciona isolado.

- Antes das correções: **1.500 passed, 7 skipped, zero falhas**.
- Depois: **1.519 passed, 7 skipped, zero falhas**; 19 regressões novas. Ouro V1 e testes de paralelismo continuam passando.
- Recorte inicial de pré-redação/contexto/copy/paralelismo: 112 passed.
- `git diff --check`: OK.
- Replay dos artefatos reais com o novo gate de URL: nenhum link externo não autorizado nas quatro páginas montadas. Replay SEO registrado lado a lado; não regenera nem substitui o recibo aprovado.

## Validação visual e qualidade percebida

Auditor Chromium existente, mobile 390×844 e desktop 1440×1000: **10/10 renders sem falhas nos checks locais** de rolagem horizontal, contraste, hierarquia, cliques, teclado, foco, tabelas, colunas e CLS local. Quatro artefatos montados + preview do **draft reprovado** da pré-sell, identificado no recibo; esse preview não é aprovação editorial. Primeira auditoria de subconjunto foi preservada: ela teve falso negativo nos links da LP por excluir o slug da pré-sell da lista do próprio renderer.

Inspeção humana das capturas: CTA de topo presente nas soluções; primeira rota da LP é a pré-sell; destinos e rótulos são diferentes. A copy ainda pode ser mais curta e concreta: há botão de 70+ caracteres no mobile e título “Entenda o Gás do Povo” pouco orientado a resultado. Não chamar isso de ganho de CTR, receita ou emoção comprovado.

As internas usam listas ordenadas/checklists, uma tabela e colunas. Não são apenas parágrafos, mas faltam prints utilizáveis e ferramentas interativas para cumprir a entrega visual desejada.

Limites: sem PHP/Elementor/tema/plugin real do WordPress, anúncios reais, imagem gerada ou ferramenta HTML executável. Checks de imagem sem imagens e checks de interatividade sem widgets não provam essas capacidades. Não há medida de ROI nem teste A/B nesta rodada.

## Artefatos preservados

Diretório local fora do Git:

`/Users/mac/Desktop/VOLC-OS-CAMPAIGN/canarios/fechamento-redator-codex-20261009/`

- `executar.py`, card e configuração pública congelados, locks da execução;
- `preflight-01.json`: primeira partida local falhou por caminho inexistente, **antes** de catálogo/inferência; preservada, sem consumo;
- `recibo-real.json`, `chamadas.json`, `state-final.json`, manifestos de código antes/depois;
- run com prompts, pesquisa grounded, fontes, fatos, pacotes SHA, logs, revisões, Gutenberg e Elementor;
- `diagnostico-offline.json`: reprodução das duas lacunas antes da correção;
- `auditoria-artefatos.json`: replay com gates corrigidos e comparação SEO;
- `recibo-visual-subset.json`: primeira auditoria de subconjunto, sem apagar a falha;
- `recibo-visual.json`: auditoria visual completa, com pré-sell marcada como draft reprovado;
- `visual-artefatos-montados/visual/`: HTMLs e capturas mobile/desktop.

## Próximo passo 80/20

Corrigir a distinção entre fonte documental e saída operacional no prompt/pacote para não impedir a citação da própria regra verificada. Em seguida, retomar **somente a pré-sell**, mantendo pesquisa, arquitetura e quatro páginas aprovadas. Separadamente, recuperar prints sem overlays e uma ferramenta sustentada pelos fatos, e então validar o preview autenticado WordPress e a imagem da LP. Não reabrir o motor nem regenerar o funil inteiro.

`P10-T22` permanece **partial**, nó `cap_funnel`: canário real parcial, sem prova de publicação em lote, matriz confirmatória ou sinal de negócio. O caminho normal Pautador/backend ainda precisa provar que gera e encaminha o brief pré-arquitetura; esta execução CLI não comprova esse fio operacional.
