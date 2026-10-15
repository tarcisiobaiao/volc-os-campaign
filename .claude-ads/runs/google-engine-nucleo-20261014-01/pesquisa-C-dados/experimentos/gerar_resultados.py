import json, sys
D = "2026-10-14"
COMPAT_DRY = "dry-run pip 26.2.1, Python 3.14.6, constraint = freeze do backend/.venv (experimentos/compat/)"
K = ["id","alegacao","fonte_primaria","versao_ou_commit","licenca","finalidade_real","equivalente_volc",
     "requisitos_dados_acesso","compatibilidade","teste_executado","resultado_teste","classe_prova",
     "veredito_alegacao","correcao","recomendacao_decisao","justificativa","possivel_integracao","prerequisito_reconsiderar"]
R = []
def item(*v):
    assert len(v) == len(K), (v[0], len(v))
    d = dict(zip(K, v)); d["data_verificacao"] = D; R.append(d)

item("C01","Cliente assíncrono para afiliados/trackers/feeds.",
 "https://github.com/encode/httpx ; https://pypi.org/pypi/httpx/json","PyPI 0.28.1 (2024-12-06); repo ativo, push 2026-10-02","BSD-3-Clause",
 "Cliente HTTP sync/async.","Já instalado e pinado: backend/requirements.txt httpx==0.28.1 (usado em backend/app e volc_ads).",
 "Nenhum.","Instalado no backend/.venv (Py3.14); pip check limpo.","pip check no backend/.venv","No broken requirements found","experimento_local",
 "parcial","É o cliente que o VOLC já usa; não há afiliados/trackers/feeds no VOLC para consumir (grep sem Voluum/RedTrack/Keitaro/System1/Tonic/Sedo).",
 "reutilizar_existente","Já é dependência de runtime; a finalidade alegada (trackers/feeds) não existe no produto.","Nenhuma nova.","Só se um tracker/feed for contratado (ver C30/C31).")
item("C02","Validação ultra-rápida (Rust v2).","https://github.com/pydantic/pydantic ; PyPI","Instalado 2.13.4 (pydantic-core 2.46.4); PyPI atual 2.14.1 (2026-10-11)","MIT",
 "Validação/serialização tipada.","Contratos FastAPI e volc_ads; faixa pinada >=2.11.7,<2.14 em backend/requirements.txt (golden OpenAPI).",
 "Nenhum.","Instalado; 2.14.1 é recusado pelo resolver com o freeze (pin 2.13.4 do requirements-dev, intencional).",COMPAT_DRY,"pydantic==2.14.1 exit=1 (conflito com o pin, esperado)","experimento_local",
 "confirmada","—","reutilizar_existente","Já em uso; subir de versão exige regenerar golden OpenAPI (comentário do requirements.txt).","Nenhuma.","Golden OpenAPI regenerado e comparado.")
item("C03","Substituto SOTA do pandas; milhões de linhas em ms.","https://github.com/pola-rs/polars ; PyPI polars 2.0.0 (2026-10-06)","polars 2.0.0 (meta-pacote; binário em polars-runtime-32==2.0.0)","MIT",
 "DataFrame colunar em Rust.","nenhum (o VOLC agrega no Postgres: views vw_gads_arbitragem_* em supabase/migrations/v17_01/v17_04; pandas não está no backend).",
 "Precisaria de dado local em volume; autoridade é o Supabase único (AGENTS.md).","Resolve junto do freeze (2 pacotes novos, wheel cp314).",COMPAT_DRY,"exit=0; +polars, +polars-runtime-32","experimento_local",
 "nao_verificavel","Desempenho não medido: não há uso concreto. Volume medido em 08/10 (memória do projeto): coleta D-1 de 1 conta = 3.605 linhas; a escala não pede motor colunar local.",
 "rejeitar","Sem requisito: o banco agrega; trazer dados para DataFrame criaria segunda fonte fora da autoridade.","Nenhuma.","Análise offline recorrente > ~10^7 linhas que o Postgres não sirva.")
item("C04","OLAP in-process sobre Parquet.","https://github.com/duckdb/duckdb ; PyPI duckdb 1.5.6 (2026-09-28)","1.5.6","MIT",
 "SQL analítico embutido.","nenhum; mesmo papel das views SQL no Supabase. (garf-executors traz um duckdb_executor.)",
 "Arquivos Parquet locais = segunda fonte.","Resolve junto do freeze (1 pacote, wheel cp314).",COMPAT_DRY,"exit=0; +duckdb","experimento_local",
 "nao_verificavel","Experimento 1M linhas não feito por falta de uso concreto (instrução da missão).",
 "rejeitar","Mesmo motivo de C03; útil só como ferramenta ad hoc de analista, fora do produto.","Nenhuma no produto.","Necessidade de análise histórica fora do Postgres.")
item("C05","Melhor colunar real-time para bilhões de eventos.","https://github.com/ClickHouse/clickhouse-connect ; PyPI 1.10.1 (2026-10-14)","clickhouse-connect 1.10.1","Apache-2.0",
 "Driver para servidor ClickHouse.","nenhum; Supabase self-hosted é a autoridade única (CLAUDE.md, ADR-SUPABASE-AUTORIDADE-OPERACIONAL).",
 "Servidor ClickHouse novo (infra permanente: não autorizada).","Driver resolve (2 pacotes).",COMPAT_DRY,"exit=0; +clickhouse-connect, +lz4","experimento_local",
 "refutada","O VOLC não tem bilhões de eventos: não há tracker de clique próprio; fatos são agregados diários por família (v17_01).",
 "rejeitar","Criaria segundo banco e quebraria a autoridade única.","Nenhuma.","Tracker de eventos próprio com volume que o Postgres particionado não aguente.")
item("C06","Feature store para servir variáveis em tempo real.","https://github.com/feast-dev/feast ; PyPI 0.67.0 (2026-10-13)","0.67.0","Apache-2.0",
 "Feature store online/offline.","nenhum; features calculadas em volc_ads/inteligencia_decisao/pipeline.py a partir do banco.",
 "Store online (Redis/etc.) + offline.","INCOMPATÍVEL: 'feast 0.67.0 depends on tenacity<9' vs tenacity==9.1.4 do backend; sem versão, o resolver tenta pyarrow antigo em sdist e falha (No module named pkg_resources).",COMPAT_DRY,"exit=1 (ResolutionImpossible / build de pyarrow falhou)","experimento_local",
 "nao_verificavel","Não há modelo servido em tempo real no VOLC.","rejeitar","Conflito de dependência + sem consumidor.","Nenhuma.","Modelo online com features compartilhadas por vários consumidores.")
item("C07","Estado de lances, gasto por minuto, bloqueio de cliques fraudulentos.","https://github.com/redis/redis-py ; PyPI redis 8.1.0","redis-py 8.1.0","MIT",
 "Cliente Redis.","nenhum no produto (Redis só aparece em scripts/validar_postiz_pacote.py, pacote Postiz). Estado de gestão/ledger fica no Postgres (backend/app/trafego/ledger.py).",
 "Servidor Redis (infra nova).","Cliente resolve (1 pacote). Obs.: garf-core puxa redis como dependência obrigatória.",COMPAT_DRY,"exit=0","experimento_local",
 "refutada","Lance por minuto não existe na API (Smart Bidding decide no leilão); bloqueio de clique inválido é feito pelo Google (IVT) e IP exclusion é mutação não autorizada nesta missão.",
 "rejeitar","Sem requisito; estado em memória fora do ledger quebra a trilha.","Nenhuma.","Controle de execução distribuído com fila real.")
item("C08","Orquestrador superior ao Airflow.","https://github.com/PrefectHQ/prefect ; PyPI 3.8.8 (2026-10-06)","3.8.8","Apache-2.0",
 "Orquestração de fluxos.","Agenda única da família Google Ads: scripts/gate_agenda_unica_gads.py (n8n D0/D1 inativos, nenhuma unit systemd).",
 "Servidor/worker Prefect.","INCOMPATÍVEL: 'prefect 3.8.8 depends on fastapi>=0.139.0' vs fastapi==0.115.6; sem pin o resolver recua para prefect 1.4.1 (2021).",COMPAT_DRY,"exit=1 com 3.8.8; exit=0 só com prefect==1.4.1 (legado)","experimento_local",
 "nao_verificavel","'Superior ao Airflow' é opinião; irrelevante: o VOLC não usa Airflow.","rejeitar","Seria segunda agenda (viola o gate de agenda única) e conflita com o FastAPI do backend.","Nenhuma.","Decisão explícita de trocar a autoridade de agenda.")
item("C09","Alternativa ao Prefect orientada a ativos.","https://github.com/dagster-io/dagster ; PyPI 1.13.26 (2026-10-09)","1.13.26","Apache-2.0",
 "Orquestração por ativos.","idem C08.","Daemon + webserver Dagster.","INCOMPATÍVEL: 'dagster 1.13.26 depends on protobuf<7' vs protobuf==7.35.1 (exigido pelo google-ads 33); sem pin recua para dagster 1.5.13 com sdist pendulum 2.1.2.",COMPAT_DRY,"exit=1 com 1.13.26","experimento_local",
 "nao_verificavel","—","rejeitar","Conflito com protobuf do google-ads 33 + segunda agenda.","Nenhuma.","idem C08.")
item("C10","Inferência/lances em milhares de contas simultâneas.","https://github.com/ray-project/ray ; PyPI 2.59.0 (2026-10-02)","2.59.0","Apache-2.0",
 "Computação distribuída.","nenhum; motor opera 1 conta (Crédito Up) sob o MCC da casa (memória 08/10: credencial alcança 42 contas, motor usa 1).",
 "Cluster Ray.","Resolve (wheel cp314; +8 pacotes).",COMPAT_DRY,"exit=0","experimento_local",
 "refutada","Não há 'milhares de contas' nem lance por chamada (Smart Bidding).","rejeitar","Escala inexistente; quota da API é o gargalo, não CPU.","Nenhuma.","Centenas de contas ativas com cálculo pesado por conta.")
item("C11","Stream processing Rust/Python; janelas deslizantes em ms.","https://github.com/bytewax/bytewax ; PyPI bytewax 0.21.1","último release v0.21.1 em 2024-11-25 (GitHub releases); push no repo 2026-10-13","Apache-2.0",
 "Stream processing.","nenhum; não há stream de eventos no VOLC.","Fonte de stream (Kafka etc.).","SEM wheel para Python 3.13/3.14 (só cp38–cp312); instalação exigiria build Rust.",COMPAT_DRY,"exit=1 (falha ao gerar metadata do sdist)","experimento_local",
 "refutada","Projeto sem release há ~23 meses e sem wheel para o Python do VOLC.","rejeitar","Incompatível e sem fonte de stream.","Nenhuma.","Stream real de eventos + projeto voltar a publicar wheels.")
item("C12","Webhooks recebem cliques/conversões em tempo real.","https://github.com/fastapi/fastapi","FastAPI 0.115.6 instalado; PyPI 0.143.1","MIT",
 "Framework HTTP.","O backend JÁ é FastAPI (backend/app/routers/*). Não existe rota de webhook de tracker (sem tracker).",
 "Tracker/feeds que façam postback.","Upgrade para 0.143.1 conflita com o pin (esperado).",COMPAT_DRY,"fastapi==0.143.1 exit=1 (pin)","experimento_local",
 "parcial","FastAPI existe; o fluxo 'clique/conversão em tempo real via webhook' não tem fonte no VOLC.","reutilizar_existente","Não adicionar framework; se surgir postback, é rota no backend existente.","Rota de postback em backend/app/routers quando houver fonte contratada.","Contratação de tracker/feed (C30/C31).")
item("C13","Embeddings locais para agrupar search terms e achar negativas.","https://github.com/huggingface/sentence-transformers (redirecionado de UKPLab) ; PyPI 6.1.0","6.1.0 (2026-09-18)","Apache-2.0",
 "Embeddings de texto (traz torch + transformers).","volc_ads/inteligencia_search/governanca.py:conflitos_de_negativa (regra lexical) + família termo (volc_ads/coleta/familias/termo.py).",
 "Termos de busca com custo/receita; volume medido em 08/10: ~320 linhas de termo/dia em 1 conta.","Resolve (+30 pacotes, torch 2.14.1 cp314).",COMPAT_DRY,"exit=0","experimento_local",
 "parcial","Embedding agrupa, mas 'achar negativas' por cluster não é seguro: ver C16 (experimento).","rejeitar","Peso (torch) sem ganho medido; FastEmbed (ONNX) cobre o mesmo papel com 357 MB de venv se um dia for preciso.","Nenhuma agora.","Base real rotulada de termos com receita e avaliação offline mostrando ganho sobre a regra lexical.")
item("C14","Wrapper unificado de LLMs para RSA em massa.","https://github.com/BerriAI/litellm ; PyPI 1.105.1 (2026-10-14)","1.105.1","MIT fora de enterprise/ (LICENSE com porções sob enterprise/LICENSE)",
 "Gateway/SDK multi-provedor.","volc_ads/copy/ + google-genai 2.31.0 (Gemini) já instalado; harness em volc_ads/harness/.",
 "Chaves de vários provedores.","Resolve (+37 pacotes: openai, boto3, aiohttp…).",COMPAT_DRY,"exit=0","experimento_local",
 "parcial","Wrapper existe; 'RSA em massa' não depende dele. Risco de cadeia: versões 1.82.7/1.82.8 publicadas no PyPI em 24/03/2026 com ladrão de credenciais (fontes secundárias: Sonatype, OX Security).",
 "rejeitar","Um provedor (Gemini) já integrado; superfície de supply-chain comprovadamente explorada; 37 dependências.","Nenhuma.","Necessidade real de ≥2 provedores em produção com contrato de custo.")
item("C15","Tópicos para descobrir nichos de alto ROI em search terms.","https://github.com/MaartenGr/BERTopic ; PyPI 0.17.4 (2025-12-03)","0.17.4","MIT",
 "Topic modeling (UMAP+HDBSCAN+c-TF-IDF).","nenhum; pauta/nichos vêm do motor de pautas e Radar (memória do projeto).",
 "Corpus grande de termos.","Resolve (+40 pacotes, inclui torch, numba, umap).",COMPAT_DRY,"exit=0","experimento_local",
 "nao_verificavel","Sem base de termos com receita por termo (receita GAM não é atribuída a termo/placement: comentário em supabase/migrations/v17_04_arbitragem_reconciliada.sql).",
 "rejeitar","Sem a receita por termo, 'alto ROI' não é calculável; peso alto.","Nenhuma.","Receita atribuída por termo (UTM→GAM) reconciliada.")
item("C16","Cluster semântico de 500 termos de 1 clique; 'negativa a intenção inteira instantaneamente'.","Experimento próprio (experimentos/exp_semantica_fastembed_hdbscan.py)","fastembed 0.9.0, scikit-learn 1.9.1 (HDBSCAN nativo), hdbscan 0.8.44; modelo paraphrase-multilingual-MiniLM-L12-v2","BSD/Apache",
 "Agrupamento não supervisionado de termos.","volc_ads/inteligencia_search/governanca.py (regra lexical, só detecta negativa que bloqueia termo marcado 'valioso').",
 "Termos + rótulo de valor de negócio.","Instala limpo em Py3.14 (venv 357 MB, 13 s; modelo 240 MB, carga 25 s na 1ª vez).",
 "200 termos sintéticos PT-BR rotulados em 8 intenções (3 'manter', 3 'negativar', 2 'revisar'); TF-IDF char + HDBSCAN; FastEmbed + HDBSCAN (sklearn e pacote); aglomerativo cosseno (varredura); 1-NN com 3 sementes/intenção.",
 "HDBSCAN sobre embedding colapsa (sklearn: 2 clusters, ARI 0,005; pacote: 4 clusters, 53,5% ruído). Todas as variantes têm clusters MISTOS manter+negativar (1 a 5). Aglomerativo com limiar escolhido olhando o rótulo (teto otimista): ARI ≤0,33 e até 2 termos 'manter' negativados pela maioria. 1-NN semi-supervisionado: acurácia 0,614, 9/176 termos 'manter' previstos como 'negativar'.",
 "experimento_sintetico","refutada","Agrupar ≠ decidir negativa: os clusters misturam intenções que compartilham núcleo ('fgts', 'inss'); negativar o cluster inteiro corta tráfego valioso. Política do Google observada não autoriza proibição por palavra.",
 "rejeitar","Automação 'instantânea' é perigosa e a mutação de negativas não está autorizada; no máximo agrupar para revisão humana.","Opcional futuro: agrupar sugestões na Mesa de Termos (somente leitura) com rótulo do operador.","Base real rotulada e avaliação com dano medido < limiar acordado.")
item("C17","Busca vetorial do histórico com ROAS/EPC no payload; 'nasce pré-otimizada'.","https://github.com/qdrant/qdrant-client ; https://github.com/qdrant/fastembed ; PyPI","qdrant-client 1.19.1; fastembed 0.9.0","Apache-2.0",
 "Cliente de banco vetorial + embeddings ONNX.","nenhum (pgvector seria o caminho no Supabase, se necessário).","Servidor Qdrant + histórico com ROAS/EPC por criativo.","Ambos resolvem (qdrant-client +6, fastembed +13).",COMPAT_DRY,"exit=0 ambos","experimento_local",
 "refutada","'Nasce pré-otimizada' é afirmação sem base: similaridade com histórico não garante ROAS; EPC por criativo não existe (receita não atribuída).",
 "rejeitar","Segundo banco + premissa sem dado.","Nenhuma.","Receita por criativo atribuída + avaliação offline.")
item("C18","Monitorar Transparency Center e landers; criar campanha concorrente em rascunho.","https://github.com/apify/crawlee-python ; https://github.com/microsoft/playwright-python ; https://policies.google.com/terms","crawlee 1.10.4; playwright 1.64.0","Apache-2.0 (bibliotecas)",
 "Crawler/automação de navegador.","Playwright já aparece no backend como provedor de screenshot (backend/app/routers/publicacao.py:892); nenhum spy de concorrente.",
 "Acesso automatizado a serviços Google.","Ambos resolvem (crawlee +15; playwright +3 e baixa navegadores à parte).",COMPAT_DRY,"exit=0 ambos","experimento_local",
 "parcial","Termos do Google proíbem 'using automated means to access content … in violation of the machine-readable instructions' (policies.google.com/terms); robots.txt do adstransparency.google.com responde 404 (não autoriza nada por si). Fonte oficial existe (C50) mas cobre EEA+Turquia. 'Criar campanha concorrente automaticamente' = mutação não autorizada e risco de copiar marca/anúncio de terceiro.",
 "rejeitar","Risco jurídico/política e mutação fora do escopo; usar o dataset oficial onde houver cobertura.","Nenhuma.","Necessidade de inteligência competitiva com fonte oficial que cubra BR.")
item("C19","Monitorar anúncios de concorrentes >7 dias.","https://adstransparency.google.com ; https://storage.googleapis.com/ads-transparency-center/api-data/README.txt","README oficial lido em 2026-10-14","Google ToS + Ads Transparency Center Additional Terms",
 "Catálogo público de anúncios por anunciante.","nenhum.","Navegação web (sem API oficial de consulta por anunciante BR).","—","Leitura do README oficial; curl do robots.txt","robots.txt = 404; dataset oficial só traz region_stats de EEA e Turquia","doc",
 "parcial","Dá para ver criativos, mas não há acesso programático oficial para o Brasil; '>7 dias' depende de first_shown/last_shown, que só vêm no dataset (EEA/TR).",
 "rejeitar","Sem fonte programática oficial para o mercado do VOLC.","Consulta manual pelo operador.","Dataset oficial com cobertura BR.")
item("C20","Worker monta HTML por clique em <10 ms com layout+related searches de maior RPC.","https://support.google.com/adspolicy/answer/6020954 ; https://support.google.com/adspolicy/answer/6368661 ; https://support.google.com/adsense/answer/48182","páginas lidas em 2026-10-14","—",
 "Edge (Cloudflare Workers+KV / Upstash) servindo variação de página por clique.","nenhum; o VOLC publica conteúdo (WordPress/redator) monetizado por GAM/JoinAds.",
 "Conta Cloudflare/Upstash; infra permanente (não autorizada).","Não instalável em Python (serviço).","Leitura das políticas oficiais","Circumventing systems: 'Manipulation of ad components like … domain, or subdomains' → suspensão 'upon detection and without prior warning'; Destination: 'Tracking template or expanded URL that don't lead to the same content as the final URL', 'Destination content that is designed for the primary purpose of showing ads'; AdSense: proibido 'Placed on pages published specifically for the purpose of showing ads'","doc",
 "refutada","Página diferente por clique (para revisor vs usuário ou por RPC) cai em cloaking/destination mismatch e 'primary purpose of showing ads' dos dois lados (Ads e AdSense).",
 "rejeitar","Risco de suspensão de conta sem aviso (egregious).","Nenhuma.","Nenhum: risco é de política, não técnico.")
item("C21","ASN para detectar datacenter/proxy/VPN.","https://ipinfo.io/lite ; https://github.com/ipinfo/python ; PyPI ipinfo 5.6.0","ipinfo 5.6.0 (2026-04-22)","Lib Apache-2.0; dados Lite CC BY-SA 4.0 (atribuição obrigatória)",
 "Geolocalização/ASN por IP.","nenhum.","IP do visitante (dado pessoal sob LGPD) no servidor da landing; Lite traz país+ASN, 'privacy detection' (VPN/proxy) só no plano pago.",
 "Resolve (+10 pacotes, aiohttp).",COMPAT_DRY,"exit=0","experimento_local",
 "parcial","ASN existe no Lite gratuito; detecção de VPN/proxy é paga. Não há onde usar: VOLC não tem tracker de clique nem decide exibição por IP.",
 "rejeitar","Sem ponto de coleta; finalidade (C34) é arriscada.","Nenhuma.","Pipeline de IVT próprio com base legal LGPD e uso aprovado.")
item("C22","Geo/ASN lookup.","https://github.com/maxmind/GeoIP2-python ; https://www.maxmind.com/en/geolite2/eula","geoip2 5.3.0 (2026-07-16)","Lib Apache-2.0; GeoLite EULA (+CC BY-SA 4.0)",
 "Leitura de base GeoIP local.","nenhum.","Conta MaxMind; base local; EULA: atribuição, destruir versões antigas em 30 dias, uso 'internal business purposes'.","Resolve (+10 pacotes).",COMPAT_DRY,"exit=0","experimento_local",
 "parcial","Faz geo/ASN; anonymizer não está no GeoLite gratuito (não confirmado na página lida).","rejeitar","Mesmo motivo de C21.","Nenhuma.","idem C21.")
item("C23","Fingerprint de navegador anti-bot.","https://github.com/fingerprintjs/fingerprintjs (LICENSE)","repo push 2026-10-14","MIT (LICENSE 2025)",
 "Fingerprint de navegador no cliente.","nenhum.","JS na landing; identificador persistente = dado pessoal (LGPD) → exige base legal/consentimento e aviso.","JS, fora do venv.","Leitura da LICENSE via API GitHub","MIT","doc",
 "parcial","Lib existe e é MIT; 'anti-bot' preciso é o produto pago (Fingerprint Pro), não a lib aberta. Implantação em landing monetizada mexe com consentimento/CMP do GAM.",
 "rejeitar","Sem caso de uso e com custo regulatório.","Nenhuma.","Necessidade comprovada de IVT próprio + parecer LGPD.")
item("C24","Bounce >95% ou CTR interno 0% após X cliques => exclusão; discrepância cliques vs landings >35% => exclusão em <5 min.","Código VOLC + google-marketing-solutions/ads_placement_guardian@294c4c37 (entities.py:44-72; placement_excluder.py:143,420-430,670-685)","—","Apache-2.0 (APG)",
 "Regra de exclusão de placement por desempenho.","Coleta existe: volc_ads/coleta/familias/placement.py (detail/group/pmax) → google_ads_fato_granular_placement (v17_01); ação existe: volc_ads/gestao/acoes.py:ExcluirPlacements (campanha/conta). Sugestão legada get_placement_negation_suggestions (src/sql/) lê vw_display_roi, que está VAZIA (03_display_roi.sql: 'nao ha pipeline de ingestao').",
 "Placement × custo (Google) e × receita/landing (GAM/GA4) por placement de origem — inexistente (v17_04: 'não há ingestão que atribua receita ao placement').",
 "—","Leitura de código VOLC e APG","Lacuna: nenhum consumidor lê os fatos de placement coletados; métricas de pós-clique por placement não existem.","leitura_codigo",
 "parcial","'<5 min' é irreal: relatórios de placement têm latência de horas e a agenda VOLC é D0 6/6h; bounce/landing por placement exige atribuição que não existe. Exclusão automática não está autorizada.",
 "extrair_padrao","Os padrões do APG (lista não-excluível, PMax só em conta, formato de app) valem; a regra de bounce não tem dado.",
 "Ver delta D3: proposta de exclusão (somente leitura) sobre google_ads_fato_granular_placement, com regras de custo/conversão e guarda APG.","Atribuição de receita/landing por placement de origem (UTM→GAM).")
item("C25","pip install google-ads-api-report-fetcher; GAQL assíncrono com macros direto para Polars/DuckDB/ClickHouse/BigQuery.","https://github.com/google/ads-api-report-fetcher@03b85dee ; https://github.com/google/garf@0dbc9197 ; PyPI","google-ads-api-report-fetcher 1.18.3 (2026-02-04); garf-core 1.3.3; garf-io 1.5.1; garf-executors 1.7.0.post1; garf-google-ads 1.2.1","Apache-2.0",
 "Executor de GAQL com sintaxe estendida (alias, :campo aninhado, ~N, expressões, macros/jinja, builtins), writers (CSV/JSON/BQ/SQL/Sheets), simulador; código ativo migrou para o monorepo google/garf (namespace garf.community.google.ads; garf_google_ads emite DeprecationWarning). O main do garf já tem 'actors' (Excluder, BudgetChanger, StatusChanger) = caminho de MUTAÇÃO (não está no 1.2.1 instalado).",
 "volc_ads/coleta (contrato.py, executor.py, 15 famílias) + volc_ads/gads/catalogo.py (exige_valida no catálogo do servidor v25) + ledger/RPC volc_registrar_gads_fatos.",
 "google-ads.yaml; por padrão o cliente lê ~/google-ads.yaml (GOOGLE_ADS_CONFIGURATION_FILE_PATH) — o experimento isolou HOME.",
 "Instala limpo em Py3.14 (24 s, venv 365 MB; google-ads 33.0.0 + protobuf 7 + grpcio 1.84). Com o freeze do backend: resolve, mas adiciona 31 pacotes (pandas via garf-google-ads, numpy, opentelemetry-*, redis, typer, psutil, jwt).",
 "exp_gaarf_parse_sem_credencial.py (parse de 2 queries com template/macro + GoogleAdsRow v25 fabricada) e exp_gaarf_null_vs_zero.py",
 "Parse OK (campos no catálogo v25: 0 fora); ':topic' devolve só a lista de tópicos (perde type/constraints/evidences); macro ':YYYYMMDD-7' → 2026-10-07; padrão v25 do SDK. Campo AUSENTE vira 0: quality_score/impressions/historical_quality_score → [0,0,0], enquanto o contrato VOLC exige None.",
 "experimento_local","parcial","Não é 'assíncrono direto para Polars/DuckDB/ClickHouse': writers oficiais são CSV/JSON/BQ/SQL/Sheets (+ duckdb_executor no garf-executors); pacote real em evolução é garf-*.",
 "extrair_padrao","Faria melhor: macros de data, extratores aninhados, simulador, fan-out MCC. Quebraria: NULL≠0 (provado), dinheiro em micros (padrão /1e6), segunda fonte/escrita (writers), segunda agenda (CLI/workflows), lineage (sem catálogo/ledger), e traria caminho de mutação (actors).",
 "Extrair queries (pasta queries/) e, se útil, a ideia de macros de data para Contexto.janela_gaql. Não instalar.","Contrato de presença (None) garantido e ausência de writers/actors no caminho de produção.")
item("C26","Queries GAQL de policy_summary.approval_status/policy_topic_entries para monitorar políticas em MCC.","https://github.com/google-marketing-solutions/ads-policy-monitor@7d313aead8aa","último commit 2026-05-28; release v2.0.2 (2024-07-10)","Apache-2.0",
 "Cloud Function + BigQuery + Looker: snapshot diário de anúncios e assets não aprovados (ad_group_ad, customer/campaign/ad_group_asset).",
 "volc_ads/coleta/familias/estado.py (ad_group_ad, asset_group_asset, keyword, campaign_asset sem política do asset); volc_ads/observabilidade_pmax/queries.py (asset.policy_summary para PMax); backend/app/trafego/sentinela.py e diagnostico_persistido.py (DISAPPROVED, APPROVED_LIMITED, REVIEW_IN_PROGRESS/UNDER_APPEAL/ELIGIBLE_MAY_SERVE).",
 "Leitura GAQL somente.","requirements pina pydantic==2.4.2, numpy==1.26.1, gaarf 1.18.3 → numpy 1.26 sem wheel cp314; não instalar.","Extração verbatim + conferência no catálogo v25 (queries/policy-extraidas.sql, conferencia_catalogo_v25.json)",
 "4 queries, 0 campos fora do catálogo. Gaps do próprio projeto: usa segments.date DURING LAST_30_DAYS com metrics (risco de omitir reprovados sem impressão — a confirmar por A) e ':topic' descarta type/evidences/constraints.","leitura_codigo",
 "confirmada","—","extrair_padrao","O VOLC já lê mais que o projeto para ad_group_ad (sem janela de data, com type); faltam asset-level (customer/ad_group/campaign_asset → asset.policy_summary) e o detalhe evidence/constraint.",
 "Deltas D1/D2 (estado.py).","—")
item("C27","Monitoramento/automação de QS e relevância em escala ('arf' Ads Relevance Factory).","gh api repos/google-marketing-solutions/ads-relevance-factory → 404; .../arf → 404; listagem da org (152 repos) sem nome equivalente","—","—",
 "Não existe com esse nome. O mais próximo: google-marketing-solutions/arba (AdRank Booster: QS/IS).","Ver C36.","—","—","gh api + listagem completa da org","404 nos dois nomes","doc",
 "refutada","Repositório inexistente; provável confusão com ARBA.","nao_verificavel","Não há artefato a avaliar.","Ver C36.","Link real publicado.")
item("C28","Ferramenta de assets/imagens.","https://github.com/google-marketing-solutions/adios@e3a795fa","commit 2026-09-16","Apache-2.0",
 "App Script/TS: gera imagens (Imagen/Gemini no Vertex AI), valida contra política em texto e SOBE/vincula imagens a grupos.","volc_ads/criativo*/, backend/app/criativo (Estúdio Criativo) + volc_ads/criativo_ponte.py.",
 "Projeto GCP com Vertex AI; escrita na conta (upload/vínculo).","Apps Script/Node, fora do venv.","Leitura do README","Confirma upload e geração; validação de política é por LLM sobre regras escritas (não é política do Google).","leitura_codigo",
 "confirmada","—","extrair_padrao","Duplica o Estúdio Criativo e escreve na conta; 'política' por LLM ≠ política observada no Google.","Padrão do ciclo biblioteca→vínculo→métrica por asset, só como referência.","—")
item("C29","Templates SQL e modelos de propensão/LTV com Terraform.","https://github.com/GoogleCloudPlatform/marketing-analytics-jumpstart@465ef4f9","commit 2026-01-05","Apache-2.0",
 "Plataforma GCP (Terraform, BigQuery, Dataform, Vertex) sobre export GA4 para propensão/LTV e ativação.","nenhum.","Export GA4→BigQuery, projeto GCP, Terraform (não autorizado).","Não aplicável (infra).","Leitura do README","Confirma escopo GA4/e-commerce/lead gen.","leitura_codigo",
 "confirmada","Não se aplica a arbitragem de conteúdo sem usuário identificado.","rejeitar","Exige GA4+BQ+Terraform; sem LTV de usuário no modelo do VOLC.","Nenhuma.","Base first-party com usuários recorrentes.")
item("C30","Fonte de cliques/conversões pós-clique (Voluum, RedTrack, Keitaro).","grep no repositório VOLC","—","Proprietários (SaaS)",
 "Trackers de afiliados.","nenhum (0 ocorrências em backend/app, volc_ads, src, supabase).","Contrato + postbacks.","—","grep -i voluum|redtrack|keitaro","0 ocorrências","leitura_codigo",
 "nao_verificavel","O VOLC não usa tracker; pós-clique vem de GAM/JoinAds por página.","adiar_prerequisito","Sem decisão de negócio de usar tracker.","Rota no FastAPI existente.","Contrato de tracker + necessidade de atribuição por clique.")
item("C31","Monetização da ponta B (System1, Tonic, Sedo, Yahoo/Bing feed, AFD/AFS).","grep VOLC; ppc.land e searchengineland (secundárias) sobre AFD/RSOC","—","—",
 "Feeds de busca/parking.","nenhum; monetização VOLC = GAM/JoinAds (+AdSense) em páginas de conteúdo.","Contas de feed.","—","grep whole-word","0 ocorrências reais (hits eram substrings)","leitura_codigo",
 "refutada","Não é a ponta B do VOLC. Contexto (fontes secundárias, não verificado em primária): parked domains/AFD removidos da rede de parceiros (2025–fev/2026); RSOC exige referrerAdCreative desde 01/11/2025.",
 "rejeitar","Modelo de negócio diferente e em contração regulatória.","Nenhuma.","Decisão de negócio de operar RSOC.")
item("C32","Aprovação depende da página, RPM do layout agressivo; montar HTML dinâmico por clique.","Políticas citadas em C20","—","—","Lander dinâmico.","nenhum.","—","—","Leitura das políticas","ver C20","doc",
 "refutada","Layout agressivo + página por clique viola 'Destination experience'/'primary purpose of showing ads' (Ads) e 'pages published specifically for the purpose of showing ads' (AdSense).",
 "rejeitar","Risco de suspensão nos dois lados.","Nenhuma.","—")
item("C33","Capturar telemetria na LP (mouse X/Y, UA, ASN) para prever valor.","Inferência sobre LGPD (Lei 13.709/2018, art. 5º I dado pessoal) — parecer jurídico não feito","—","—",
 "Telemetria comportamental por WebSocket.","nenhum; o único WebSocket no repo é um teste que PROÍBE canais de rede novos (src/components/trafego/diagnostico/__tests__/seguranca-growth-engine.test.tsx).",
 "Script na landing + servidor WS + base legal/consentimento (CMP).","websockets 16.1.1 instalado; 17.2 conflita com o pin.","grep WebSocket","1 arquivo (teste de proibição)","leitura_codigo",
 "nao_verificavel","Sem modelo de valor que consuma isso; custo regulatório e de performance (CWV) na página monetizada.","rejeitar","Coleta pessoal sem finalidade comprovada.","Nenhuma.","Modelo de valor validado + parecer LGPD.")
item("C34","Bloquear monetização para ASN de datacenter/VPN; exclusão de IP/24.","Google Ads IP exclusion (API: campaign_criterion ip_block) — limites a confirmar pelo pesquisador A","—","—",
 "Filtro de tráfego por ASN.","nenhum.","IP/ASN do visitante; mutação de exclusão de IP (não autorizada).","—","—","—","nao_verificado",
 "nao_verificavel","Não renderizar anúncios para parte do tráfego pago e 'não enviar conversão' altera sinal de Smart Bidding; Google já filtra IVT. Esconder anúncios por ASN pode ser lido como manipulação se diferenciar revisor vs usuário.",
 "rejeitar","Sem dado de ASN no VOLC e sem autorização de mutação.","Nenhuma.","Evidência de IVT relevante não filtrada pelo Google (relatório invalid_clicks).")
item("C35","Métricas e alertas (Gaarf+Prometheus+Grafana).","https://github.com/google-marketing-solutions/ads-monitor@5e483028","commit 2026-02-16","Apache-2.0",
 "Exporter Prometheus (gaarf_exporter) + Grafana + Alertmanager; coletores de reprovação (ad, ad_group_ad_asset, sitelink, pmax).","backend/app/trafego/sentinela.py, alertas.py, deadman_coleta.py, diagnostico_persistido.py.",
 "VM/Docker com Prometheus/Grafana (infra não autorizada).","Não instalado.","Leitura de collector_definitions/disapprovals.yaml","Prova que ad_group_ad_asset_view.policy_summary é lido sem segments.date (linhas 28-52). BUG no projeto: review_status mapeado para approval_status (linhas 42 e 76).","leitura_codigo",
 "confirmada","—","extrair_padrao","Extrair os 4 coletores de reprovação; não copiar o mapeamento errado; não instalar a pilha.","Delta D1.","—")
item("C36","Diagnóstico de IS perdido e QS.","https://github.com/google-marketing-solutions/arba@72c5661a","commit 2026-07-09","Apache-2.0",
 "QS/IS por keyword + tagging de LP/anúncio por Gemini; dashboard Looker.","volc_ads/coleta/familias/keyword.py (quality_info + historical_* QS), campanha_dia.py e url.py (IS/landing).",
 "garf-google-ads + garf-executors[bq,gcp] + Vertex/Gemini.","Não instalado (garf, ver C25).","Extração de queries (queries/qs-extraidas.sql)","Campos no catálogo v25; VOLC já coleta QS histórico; IS em nível keyword (search_rank_lost_impression_share) não é coletado por keyword.","leitura_codigo",
 "confirmada","—","reutilizar_existente","Cobertura VOLC já sobrepõe; extra opcional é IS por keyword.","Opcional: IS por keyword na família keyword (sem ação automática).","Search com volume onde IS por keyword mude decisão.")
item("C37","Negativas que bloqueiam tráfego relevante.","https://github.com/google-marketing-solutions/negative_keyword_cleaner@e3443326","commit 2026-06-08","Apache-2.0",
 "Streamlit + LangChain/Vertex: LLM julga negativas contra o contexto da conta; lê negativas de grupo, campanha e LISTAS COMPARTILHADAS (shared_criterion).",
 "volc_ads/inteligencia_search/governanca.py:conflitos_de_negativa (lexical, consumida em volc_ads/inteligencia_decisao/pipeline.py:343); só escopos CAMPAIGN e AD_GROUP.",
 "Negativas + termos com valor de negócio.","Não instalado (streamlit 1.30, langchain).","Extração de queries (queries/negativas-extraidas.sql)","Lacuna VOLC: negativas de lista compartilhada (shared_set NEGATIVE_KEYWORDS via campaign_shared_set) não entram em conflitos_de_negativa.","leitura_codigo",
 "confirmada","—","extrair_padrao","Ideia já existe no VOLC, sem LLM; falta o escopo de lista compartilhada.","Delta D5.","—")
item("C38","Geração de RSA a partir da voz da marca.","https://github.com/google-marketing-solutions/copycat@6c5da123 ; PyPI gtech-copycat 0.0.11","0.0.11","Apache-2.0",
 "Gera RSA com Gemini (Vertex) a partir de anúncios exemplares + guia de estilo.","volc_ads/copy/ (ciclo.py, juiz_semantico.py, encomendar.py, render.py).",
 "Projeto GCP com Vertex AI (VOLC usa google-genai por chave).","Não testado (deps: google-cloud-aiplatform, pandas, scikit-learn).","Leitura do README e metadados PyPI","Confirma escopo.","leitura_codigo",
 "confirmada","—","extrair_padrao","Sem comparação medida contra a cascata do VOLC; não substituir.","Comparar prompts/guia de estilo em sandbox se houver rodada de copy.","Avaliação A/B offline de copy.")
item("C39","Tendências/first-party como insumo de pauta.","https://github.com/google-marketing-solutions/topic-mine@09fc973e (README)","commit 2026-10-06","Apache-2.0",
 "Gera temas/copy com Gemini a partir de dados próprios.","Motor de pautas/Radar (backend/app/motor_pautas) e Attention Engine.","—","—","Leitura do README","README: 'DEPRECATION NOTICE: This project is no longer actively maintained … No Security Updates'.","leitura_codigo",
 "refutada","Projeto oficialmente descontinuado.","rejeitar","Sem manutenção e duplica o Pautador.","Nenhuma.","—")
item("C40","Experimentos de feed Shopping.","https://github.com/google-marketing-solutions/feedx@64146ba3","commit 2026-09-07","Apache-2.0",
 "Desenho/análise de A/B de feed Merchant Center.","nenhum (Shopping fora dos canais decididos em 08/10: Search, Display, PMax, Demand Gen).","Merchant Center.","—","Leitura do README","Confirma escopo Shopping.","leitura_codigo",
 "confirmada","—","rejeitar","Canal fora do escopo.","Nenhuma.","Entrada em Shopping.")
item("C41","Testes de propriedade/estado (já instalado no venv dev).","https://github.com/HypothesisWorks/hypothesis ; PyPI 6.169.2","6.169.2 instalado","MPL-2.0",
 "Property-based/stateful testing.","Instalado no backend/.venv via volc_ads/harness/requirements.txt.","—","Instalado; pip check limpo.","pip freeze/pip check","hypothesis==6.169.2","experimento_local",
 "confirmada","—","reutilizar_existente","Já disponível em dev.","Testes de invariantes do coletor/ledger.","—")
item("C42","Fuzzing OpenAPI local.","https://github.com/schemathesis/schemathesis ; PyPI 4.31.1","4.31.1","MIT",
 "Fuzz de API por schema.","nenhum; golden OpenAPI existe no backend.","Backend local isolado, sem escrita externa.","Resolve com o freeze (+11 pacotes; usa hypothesis já instalado).",COMPAT_DRY,"exit=0","experimento_local",
 "confirmada","—","experimentar_sandbox","Dev-only, barato; nunca contra rotas de mutação reais.","requirements-dev em sandbox.","—")
item("C43","Mocks HTTPX.","https://github.com/lundberg/respx ; PyPI 0.23.1","0.23.1","BSD-3-Clause",
 "Mock de transporte httpx.","nenhum (testes usam outros dublês).","—","Resolve (+1 pacote).",COMPAT_DRY,"exit=0","experimento_local",
 "confirmada","—","experimentar_sandbox","Dev-only, leve; útil para Gemini/HTTP providers.","requirements-dev.","—")
item("C44","Traces intenção→readback.","https://github.com/open-telemetry/opentelemetry-python ; PyPI 1.45.1","1.45.1","Apache-2.0",
 "Tracing/métricas.","Recibos/ledger (backend/app/trafego/ledger.py, coleta Recibo) e log.jsonl.","Backend de traces (coletor OTLP) para ter valor.","SDK resolve (+3 pacotes).",COMPAT_DRY,"exit=0","experimento_local",
 "confirmada","—","adiar_prerequisito","Sem backend de observabilidade; recibos já cobrem auditoria.","Spans no executor de gestão quando houver coletor.","Coletor OTLP operado.")
item("C45","Instruções para agentes de desenvolvimento.","https://github.com/google/skills@b85f257d","166 SKILL.md; skills/ads inclui google-ads-api-account-diagnostics, data-manager-api-*","Apache-2.0",
 "Skills para agentes (inclui Ads API e Data Manager API).","Skills locais do projeto; docs em volc_ads/google_ads_api/.","—","Não é pacote.","gh api tree","Confirma conteúdo.","doc",
 "confirmada","—","extrair_padrao","Referência para dev (ex.: gotchas de GAQL), não capacidade de produto.","Consultar data-manager-api-event-ingestion na frente de conversão offline.","—")
item("C46","SDK oficial Meta (fronteira).","https://github.com/facebook/facebook-python-business-sdk ; PyPI facebook-business 26.0.2","26.0.2 (2026-09-21)","Licença própria da Meta (LICENSE: uso com plataforma Meta)",
 "SDK Marketing API.","Executor HTTP próprio: backend/app/trafego/meta_execucao/.","Token Meta.","Resolve (+13 pacotes, aiohttp).",COMPAT_DRY,"exit=0","experimento_local",
 "confirmada","—","adiar_prerequisito","Executor HTTP existente; trocar só se reduzir manutenção.","—","Etapa Meta priorizada.")
item("C47","Nova plataforma de pipelines (CRMint/BigQuery/Dataform).","https://github.com/google-marketing-solutions/crmint (redirect de google/crmint)","push 2026-06-21","Apache-2.0 (LICENSE com cabeçalho 'Files: **/*')",
 "Plataforma GCP de integração de dados.","Coletor + Supabase + agenda única.","GCP + BigQuery.","Infra.","gh api","Repo ativo.","doc",
 "confirmada","—","rejeitar","Segunda plataforma/autoridade de dados.","Nenhuma.","Migração deliberada para GCP.")
item("C48","Revisor genérico/agentes extras (JEV).","gh search repos jev","—","—",
 "Identidade ambígua: busca devolve projetos de terceiros ('Jev — TypeSafe AI's System One model' em yibie/awesome-jev); google/jev → 404.","Harness e revisores existentes (volc_ads/harness).","—","—","gh api/search","Sem repositório canônico identificável","doc",
 "nao_verificavel","Não foi possível fixar qual 'JEV' a fonte quis dizer.","nao_verificavel","Sem identidade, sem avaliação.","Nenhuma.","URL canônica.")
item("C49","Webhooks FastAPI -> ClickHouse; GAQL a cada 15-30 min.","scripts/gate_agenda_unica_gads.py; volc_ads/coleta/contrato.py","—","—",
 "Arquitetura de ingestão.","Coletor com disparo agenda/manual e passo (D0 6/6h, D-1 06h) — gate de agenda única.","—","—","Leitura do gate","Uma única autoridade de agenda; nada ligado ainda.","leitura_codigo",
 "refutada","15–30 min multiplica custo de quota sem dado novo (estatísticas de Ads atualizam com atraso) e criaria segunda agenda; ClickHouse ver C05.",
 "rejeitar","Viola agenda única e autoridade Supabase.","Nenhuma.","Necessidade intradiária medida (ex.: pacing) aprovada.")
item("C50","Fonte oficial alternativa ao scraping (BigQuery public dataset do Transparency Center).","https://storage.googleapis.com/ads-transparency-center/api-data/README.txt","README lido 2026-10-14","Google ToS + Ads Transparency Center Additional Terms",
 "Dataset bigquery-public-data.google_ads_transparency_center (tabelas creative_stats e removed_creative_stats) + JSON.","nenhum.","Projeto GCP com BigQuery (consulta paga por volume).","—","Leitura do README oficial","Existe; region_stats só para 'European Economic Area and Turkey' (removed: só EEA). Fórum de desenvolvedores relata cobertura parcial por anunciante (fonte secundária).","doc",
 "parcial","Oficial, mas NÃO cobre Brasil.","rejeitar","Não serve ao mercado do VOLC.","Nenhuma.","Expansão do dataset para BR/LatAm.")

# ---------- itens novos ----------
item("C51","(novo) Excluir placements ruins/spam de YouTube, apps e sites em escala.","https://github.com/google-marketing-solutions/ads_placement_guardian@294c4c37 — origem: varredura da org GMS por 'placement'","commit 2026-04-23","Apache-2.0",
 "Web app GCP que lê group/detail_placement_view (Display, Search, PMax, Demand Gen, Video), cruza com YouTube Data API e EXCLUI (conta/campanha/grupo/lista).",
 "volc_ads/coleta/familias/placement.py + volc_ads/gestao/acoes.py:ExcluirPlacements.","Escrita na conta (não autorizada); YouTube Data API.","Não instalado (SQLAlchemy==1.4.46, psycopg2, gaarf).","Extração (queries/placements-extraidas.sql)",
 "Padrões úteis: _NON_EXCLUDABLE_PLACEMENTS=(youtube.com, mail.google.com, adsenseformobileapps.com) (entities.py:45-49); PMax só excluível em conta (placement_excluder.py:143,423-430); format_app_id converte 'mobileapp::2-com.x' em '2-com.x' (placement_excluder.py:673-681) — o regex de app do VOLC (acoes.py:_TIPOS_PLACEMENT) recusaria o formato cru coletado.","leitura_codigo",
 "confirmada","—","extrair_padrao","Guardas baratas que evitam operação recusada/errada.","Delta D3.","—")
item("C52","(novo) Enriquecer placements YouTube com dados do canal/vídeo para excluir.","https://github.com/google-marketing-solutions/video-exclusion-toolbox@97d54487","commit 2026-09-28","Apache-2.0",
 "Relatório de canal (group_placement_view YOUTUBE_CHANNEL em VIDEO/DEMAND_GEN) e vídeo (detail_placement_view YOUTUBE_VIDEO) + YouTube Data API + BigQuery.","volc_ads/coleta/familias/placement.py (coleta todos os tipos, sem métricas de vídeo).",
 "YouTube Data API key; BigQuery.","Não instalado.","Extração (queries/placements-extraidas.sql)","Campos no catálogo v25 (metrics.video_trueview_views, video_quartile_p*_rate).","leitura_codigo",
 "confirmada","—","extrair_padrao","Mostra o recorte certo para canais YouTube de Demand Gen.","Delta D3 (filtro placement_type=YOUTUBE_CHANNEL na proposta).","—")
item("C53","(novo) Clusterização multilíngue de search terms (Google).","https://github.com/google-marketing-solutions/ml_toast (ARQUIVADO) @a1e9c831","arquivado; último commit 2024-05-07","Apache-2.0",
 "Embeddings + K-Means/HDBSCAN para TEMAS de termos (insight), não negativação.","nenhum.","—","—","README","Projeto da própria Google para o caso C16 foi arquivado.","doc",
 "confirmada","Reforça C16: era ferramenta de insight, não de negativação automática.","rejeitar","Arquivado.","Nenhuma.","—")
item("C54","(novo) Auditoria de boas práticas PMax (pMaximizer).","https://github.com/google-marketing-solutions/pmax_best_practices_dashboard@3dc6fa0d","commit 2026-09-03","Apache-2.0",
 "Queries gaarf de asset group, sinais, placement PMax (só impressões) e score de boas práticas.","volc_ads/observabilidade_pmax/ (coverage.py, kernel.py, queries.py) + backend/app/trafego/pmax_cockpit.py.","—","—","Extração (queries/assets-extraidas.sql, placements-extraidas.sql)","Confirma que performance_max_placement_view só tem impressões (mesma conclusão do VOLC em placement.py).","leitura_codigo",
 "confirmada","—","reutilizar_existente","VOLC já cobre; nenhuma lacuna nova além de asset_group_signal.approval_status (delta D4).","Delta D4.","—")
item("C55","(novo) Saúde de Demand Gen (DGPulse).","https://github.com/google-marketing-solutions/dgpulse@9cbb9d4e","commit 2026-09-25","Apache-2.0",
 "Queries de Demand Gen: assets por anúncio (multi-asset, vídeo responsivo), channel_controls do grupo, conversão.","backend/app/trafego/adaptador_demand_gen.py, volc_ads/campanha/ (criação DG).","—","—","Extração (queries/assets-extraidas.sql)","Campos no catálogo v25 (ex.: ad_group.demand_gen_ad_group_settings.channel_controls.*).","leitura_codigo",
 "confirmada","—","extrair_padrao","Ler channel_controls do grupo DG ajuda a explicar onde o DG veicula (YouTube/Discover/Gmail/Display).","Opcional: incluir channel_controls na leitura de estado DG.","—")
item("C56","(novo) Cobertura de imagem/vídeo em Demand Gen/Video.","https://github.com/google-marketing-solutions/asset_coverage_dashboard@32e154bf","commit 2025-09-09","Apache-2.0",
 "Cloud Workflow + BigQuery + Looker de cobertura de assets.","volc_ads/forca.py, observabilidade_pmax/coverage.py.","GCP.","—","README","Escopo confirmado.","leitura_codigo",
 "confirmada","—","rejeitar","Infra GCP para algo que o VOLC já mede.","Nenhuma.","—")
item("C57","(novo) garf-* como sucessor real do gaarf.","https://github.com/google/garf@0dbc9197 ; PyPI garf-core/io/executors/google-ads","garf-core 1.3.3, garf-io 1.5.1, garf-executors 1.7.0.post1, garf-google-ads 1.2.1","Apache-2.0",
 "Monorepo 'Call APIs with SQL' (Ads, YouTube, GA, DV360, Merchant) com executores (BQ, DuckDB, SQL, Elasticsearch/OpenSearch), Prometheus e actors de mutação.","Ver C25.","Ver C25.","Ver C25 (resolve, +18 a +31 pacotes; garf-core exige redis e opentelemetry-api).",COMPAT_DRY,"exit=0 (garf-core, garf-io, garf-executors, garf-google-ads)","experimento_local",
 "confirmada","—","extrair_padrao","Mesmos riscos de C25, mais API em migração de namespace.","Somente leitura de padrões.","—")
item("C58","(novo) Adicionar termos de busca como keywords automaticamente.","https://github.com/google-marketing-solutions/search_term_amp@84d878b4","commit 2025-09-19","Apache-2.0",
 "Google Ads Script que transforma termos em keywords nas campanhas.","nenhum (mutação).","Escrita na conta.","Apps Script.","README","Escopo confirmado.","leitura_codigo",
 "confirmada","—","rejeitar","Mutação automática não autorizada e fora do caminho de gestão do VOLC.","Nenhuma.","Regra de gestão aprovada pelo dono.")
item("C59","(novo) HDBSCAN já está no scikit-learn.","https://scikit-learn.org (sklearn.cluster.HDBSCAN) — verificado executando 1.9.1","scikit-learn 1.9.1","BSD-3-Clause",
 "Implementação nativa de HDBSCAN.","nenhum.","—","Instala limpo em Py3.14.","exp_semantica_fastembed_hdbscan.py","sklearn.cluster.HDBSCAN executou; pacote hdbscan separado é desnecessário.","experimento_local",
 "confirmada","Se algum dia agrupar, não precisa do pacote hdbscan.","rejeitar","Registro para evitar dependência redundante.","—","—")
item("C60","(novo) Exclusões em massa por Google Ads Scripts (MCC).","https://github.com/google-marketing-solutions/google-ads-exclusion-scripts (ARQUIVADO) @97bc9164","arquivado; commit 2023-10-16","Apache-2.0",
 "Scripts de exclusão de keywords/tópicos/placements em todas as subcontas.","volc_ads/gestao/acoes.py (listas compartilhadas e ExcluirPlacements).","Escrita em MCC.","Apps Script.","README","Arquivado.","doc",
 "confirmada","—","rejeitar","Arquivado e de mutação.","Nenhuma.","—")

assert [r["id"] for r in R][:50] == [f"C{i:02d}" for i in range(1, 51)], "ordem/IDs"
saida = {"schema": "volc-pesquisa-C-v1", "pesquisador": "C", "run_id": "google-engine-nucleo-20261014-01",
         "data_verificacao": D, "itens": R}
json.dump(saida, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
print(len(R), "itens")
from collections import Counter
print(Counter(r["recomendacao_decisao"] for r in R)); print(Counter(r["veredito_alegacao"] for r in R)); print(Counter(r["classe_prova"] for r in R))
