# Redator: identidade editorial e artefatos seguros

Data: 2026-09-17. Escopo: engine local FunnelForge, sem deploy ou alteracao de WordPress, campanhas, GTM ou monetizacao.

## Diagnostico

Os prompts de imagem favoreciam sinais de confianca e resultado obtido, e a restricao de logos nao cobria toda a composicao. A LP pulava a revisao final de conteudo, aceitava HTML rico sem uma lista estrutural restrita e dependia do tema para identificar o portal. O caminho de publicacao precisava repetir as validacoes para artefatos antigos ou editados. Scripts arbitrarios podiam aproveitar a permissao de JavaScript destinada aos widgets internos.

## Mudancas implementadas

- Contrato editorial compartilhado pelos prompts de LP, presell, paginas internas, SEO, widgets e juiz. Preserva o assunto; nao substitui palavras em massa.
- Imagens geradas sem marcas de terceiros, brasoes, selos, documentos oficiais, replicas de aplicativos, dados pessoais ou sinais de aprovacao/contratacao.
- Revisao visual obrigatoria dos bytes finais da imagem; rejeicao, incerteza ou erro impedem seu uso. A pagina pode continuar sem imagem. Recibo SHA-256 vincula a revisao ao arquivo e e conferido antes de publicar.
- Aviso editorial deterministico antes do hero da LP Elementor, independente do tema, e no inicio das paginas internas. Identifica o dominio, o papel informativo e a ausencia de contratacao/coleta de credenciais.
- CTAs de execucao direta sao recusados individualmente. Linguagem como "Como fazer a solicitacao" continua permitida; nao ha reescrita cega do tema ou assunto.
- HTML rico da LP limitado a marcacao textual e links seguros; campos simples escapados. Scripts, formularios, iframes, eventos HTML e shortcodes nao sao aceitos nesse texto.
- Paginas internas recusam campos de texto para coleta, superfices HTML nao previstas e scripts diferentes do JavaScript deterministico dos widgets. Widgets exibem aviso de que nao confirmam elegibilidade ou aprovacao.
- Gate final da LP e rechecagem antes de qualquer upload/publicacao, inclusive retomadas manuais. Artefatos Elementor alterados ou antigos precisam ser reconstruidos.

## Evidencias locais

- Suite completa: 760 testes aprovados em 13,22 s (`pytest -q -p no:cacheprovider`). APIs de imagem/visao e WordPress simuladas nos testes; nenhuma chamada paga realizada.
- `git diff --check` passou. Ruff E4/E7/E9/F passou nos modulos centrais alterados e testes; a verificacao incluindo `widgets/render.py` aponta E741 preexistente na linha 207, fora da alteracao desta rodada.
- Casos de regressao: HTML hostil, URLs inseguras, shortcodes, scripts de redirecionamento/beacon, remocao do aviso, imagem modificada, revisao ausente/incerta e CTA transacional isolado.
- Preview local Playwright em 360x800, 390x844, 768x1024 e 1440x900: aviso visivel acima do titulo, 14px, fundo branco, texto escuro, sem overflow horizontal. Capturas examinadas em mobile e desktop.
- Preview e uma representacao simplificada, nao o CSS real do Elementor; nao constitui prova visual no WordPress. Evidencias temporarias em `/private/tmp/volc-editorial-preview/`.
- Arquivos centrais: `pipeline/editorial_safety.py`, `pipeline/lp_template.py`, `pipeline/steps.py`, prompts e `tests/test_editorial_safety.py`, sob `funnelforge-migracao/engine/`.

## Limites e proximo gate

Nenhum mecanismo garante ausencia absoluta de phishing ou aprovacao Google Ads. Um aviso nao corrige conteudo enganoso; revisao visual por modelo tambem pode falhar. A proibicao de logos nas ilustracoes e uma regra preventiva deste projeto, nao uma afirmacao de que toda citacao de marca viole a politica.

Antes dos tres funis: preparar o ambiente executavel do worker (o `.venv` do engine nao estava presente; testes usaram ambiente temporario), gerar em rascunho, conferir fontes e papel editorial, revisar imagem e layout Elementor reais, destinos de cada CTA e coerencia anuncio/keyword/pagina. Preservar o gate humano antes de publicar. Capturas de fontes oficiais em paginas internas continuam identificadas como reproducao; nao sao o hero gerado da LP.

## Fontes oficiais

- https://support.google.com/google-ads/answer/15936970?hl=en
- https://support.google.com/adspolicy/answer/6020955?hl=en

## Registro operacional

Tarefa P10-T17; no `cap_funnel`. Estado parcial: implementacao e provas locais concluidas; prova com imagem real e rascunho WordPress pendente. Nenhum funil novo foi criado nesta rodada.

Pipeline oficial de atualizacao do grafo executado, mas interrompido pelo verificador de segredos: possivel JWT preexistente em `.env_webgo` (valor nao exposto; arquivo nao alterado). `--check` confirmou `current: false`: snapshot de 2026-08-29, commit a539dbd7, enquanto HEAD e 9f70f65b. Fontes humanas atualizadas; grafo gerado continua desatualizado. Nao houve bypass do verificador.
