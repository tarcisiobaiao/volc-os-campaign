# Livro-razão de políticas oficiais — caso Senac

Frente A · Etapa 1 · consulta feita em **30/09/2026** · run `editorial-refactor-20260930`
Caso: funil Senac em creditoup.com.br (LP 2306 + internas 2309, 2312, 2315, 2318) e campanha Search 24278665189 (conta 547-809-6539). O publisher **não** é o Senac.

## Como ler

- **Fontes.** Só páginas oficiais públicas: Central de Políticas do Google Ads, Ajuda do Google Ads, documentação da Google Ads API, Publisher Policies, AdSense, Ad Manager, Platforms Policies, Search Central, Coalition for Better Ads (padrão citado pelo Google), planalto.gov.br e senac.br. Nenhum acesso autenticado, nenhuma API paga.
- **Literalidade.** O HTML público de cada página foi baixado (inglês com `?hl=en`, pt-BR onde indicado). Um script conferiu que **cada citação existe literalmente** no texto extraído — tolerando só diferença de aspas retas/curvas e de espaços — e tem **no máximo 25 palavras**. As 90 URLs citadas foram checadas de novo no fim da consulta: todas HTTP 200.
- **Idioma oficial.** As páginas do Google Ads dizem que a versão em inglês é a oficial para aplicação das políticas; os títulos em pt-BR aparecem entre parênteses só como referência.
- **Classes.** **A** = exigência explícita da plataforma · **B** = interpretação contextual de risco · **C** = preferência editorial interna · **D** = regra obsoleta ou sem fundamento. Em cada regra, "Exige" é A e "Só sugere risco" é B. Ausência de proibição **não** é garantia de aprovação.
- **Repositório.** Referências `arquivo:linha` apontam para o worktree de 30/09/2026 (o ref `main` está inconsistente; não foi tocado).
- **Arquivo irmão.** `ledger.json` tem as mesmas entradas, filtráveis por `tipo` (`regra`, `nao_escrito`, `crenca_sustentada`, `fato_contexto`, `mudanca_recente`, `falha_de_consulta`).

## Síntese para o integrador

1. **O risco dominante é afiliação implícita com o Senac.** "Unacceptable business practices" é *egregious*: suspensão da conta na detecção, sem aviso. A copy precisa deixar claro que o Crédito Up é guia independente e não inscreve, e essa ressalva só aparece em todo anúncio se estiver fixada em T1, T2 ou D1. → ADS-MIS-01, ADS-MIS-02, API-03
2. **"Government documents and official services" não se aplica literalmente.** A política cobre documentos e serviços *emitidos pelo governo*, de uma lista fechada; cursos do Senac não estão nela, e o Regulamento do Senac o define como "instituição de direito privado". O risco residual é classificação automática se a copy falar em "governo" ou "benefício". → ADS-ORB-GOV, FATO-01
3. **Não há veto a "grátis", pergunta, imperativo, "você", Title Case ou primeira pessoa** nas páginas consultadas (exceção: "Grátis" como valor de snippet estruturado é texto promocional vetado). O que é vetado é afirmação falsa ou improvável (nem todo curso é gratuito; o PSG exige renda per capita de até 2 salários-mínimos), CTA genérico ("clique aqui") e clickbait. → NE-01 a NE-08, ADS-MIS-03, ADS-MIS-04
4. **A promessa do anúncio precisa estar fácil de achar no destino.** Título sobre curso específico ou "inscrições" exige página que trate disso. O AdSense exige o mesmo de sites que compram tráfego. → ADS-MIS-05, ADS-MIS-06, PUB-12
5. **Arbitragem não é proibida; destino de baixo valor é.** Google Ads reprova destino com mais anúncios que conteúdo, pouco conteúdo ou página-ponte; Publisher Policies cortam anúncios nessas telas, e links para outras páginas do site **não contam como conteúdo**. → ADS-DST-03, PUB-04, PUB-05
6. **Interstitial é permitido no formato Google** se não dificultar a saída nem esconder o conteúdo pedido. Interstitial que impede o Google de avaliar a LP é *cloaking* (egregious). Dividir a resposta em várias páginas para multiplicar vinhetas cruza doorway, pretexto falso e tela de navegação (risco B). → ADS-DST-02, ADS-ABU-02, PUB-14, NE-18
7. **API v25: o RSA é atualizável in-place** (AdService.MutateAds + update_mask) "without losing their performance data"; o ID se mantém (inferência forte); toda edição reinicia a revisão. Não está documentado se a versão anterior continua servindo durante a revisão. → API-01, ADS-REV-01
8. **Limites:** títulos 3–15 de até 30 caracteres; descrições 2–4 de até 90; path até 15 (path2 exige path1); sitelink 1–25 com descrições 1–35 em par; callout 1–25; snippet com 3–10 valores de até 25 e header da lista oficial. → API-02 a API-06
9. **validate_only** pega só violações comuns da requisição; **isenção** salva o recurso, mas o deixa inelegível até nova revisão. O repositório já trata os dois corretamente. → API-07, API-08
10. **Limited ad serving** (ampliado em 2026, gradual até 2028): anunciante que cita marca de terceiro (sobretudo se novo ou pouco conhecido) pode ter impressões limitadas, sem reprovação. Boa prática: marca própria visível e domínio fixado no T1. O custo em Ad Strength não afeta elegibilidade. → ADS-LAS-01, NE-11
11. **Snippet "Cursos" não serve a um publicador** (é para aulas que provedores educacionais oferecem) e "Grátis" não pode ser valor de snippet. → ADS-FMT-03
12. **Mudanças de 2026 que importam:** "Text ad requirements" foi descontinuada (17/03); Government documents endurece provedores autorizados a partir de 05/10; Limited ad serving foi ampliado; recursos contra decisões só até 6 meses. → CHG-01 a CHG-05

## Respostas diretas às perguntas da tarefa

| Pergunta | Resposta curta | Entradas |
|---|---|---|
| "Government documents and official services" se aplica ao Senac? | **Não, pelo texto.** Definição: documentos emitidos e serviços prestados *pelo governo*; a lista abrangente não inclui cursos; o Senac é "instituição de direito privado" (Dec. 61.843/1967, art. 4º). Hoje a política fica em *Other restricted businesses*, não em Misrepresentation. Confiança alta no texto, média no comportamento dos classificadores. | ADS-ORB-GOV, FATO-01, CHG-01 |
| Afiliação implícita / deturpação | Vetada. Afiliação falsa é *egregious*; omitir que o site não oferece os cursos é Misleading representation. Aviso de não afiliação é *recomendado* ("consider a disclaimer"), não exigido. | ADS-MIS-01, ADS-MIS-02, NE-14 |
| Afirmações não confiáveis | Vetado prometer resultado improvável como provável: vaga, aprovação, gratuidade universal. | ADS-MIS-04 |
| Destino / experiência do destino | Funcional, rastreável pelo AdsBot, sem bloquear conteúdo, sem mexer no botão Voltar, dentro dos Better Ads Standards; conteúdo original acima de anúncios. | ADS-DST-00 a 03, PUB-09 |
| Relevância pouco clara | Cada asset precisa descrever o destino real; DKI exige texto padrão relevante. | ADS-MIS-05 |
| Clickbait / sensacionalismo | Vetados: "segredos", "clique para descobrir", "você não vai acreditar", medo/culpa com evento negativo para pressionar ação. | ADS-MIS-03, NE-13 |
| RSA pode ser atualizado in-place? ID, estatísticas, revisão? | Sim na v25 (tipo *Mutable*). Estatísticas preservadas (literal). ID preservado (inferência forte: o update endereça o `resource_name` imutável). Revisão recomeça. Serviço durante a revisão: **não verificado**. | API-01, ADS-REV-01 |
| Limites de campos e pins | Ver síntese, item 8; pins em T1/T2/D1 são garantidos, T3/D2 não. | API-02 a API-06 |
| validate_only | Valida sem executar e devolve só erros; útil para violações comuns (palavras, pontuação, capitalização, tamanho). Não substitui a revisão. | API-07 |
| PolicyViolationKey / exempt | Keywords: `exempt_policy_violation_keys` com `is_exemptible`. Anúncios: `ignorable_policy_topics`. Exclusivos entre si. Isento = salvo e inelegível. | API-08 |
| Publisher: baixo valor, implementação, IVT, interstitials | Sem anúncio em tela de navegação ou de baixo valor; anúncios ≤ conteúdo; nada colado a botões; rótulo "Publicidade"; nada de pedir clique; vinheta só no formato Google. | PUB-01 a PUB-17 |
| Scaled content abuse (fragmentar respostas) | Risco B: muitas páginas finas geradas para ranquear, e doorways que afunilam para a parte útil, são spam; isso afeta também Ads e AdSense. | SEO-01, SEO-02, ADS-ABU-01, PUB-07 |

## Índice das regras

| ID | Superfície | Título | Consequência | Confiança |
|---|---|---|---|---|
| ADS-MIS-00 | search_ads | Misrepresentation — visão geral (pt-BR: Deturpação) | Depende da subpolítica: Unacceptable business practices e Coordinated deceptive practices são 'egregious' (suspensão sem aviso); as demais avisam ≥7 dias antes de suspender. | alta |
| ADS-MIS-01 | search_ads | Unacceptable business practices (pt-BR: Práticas comerciais inaceitáveis) | Egregious: 'your Google Ads accounts will be suspended upon detection and without prior warning'. | alta |
| ADS-MIS-02 | search_ads | Misleading representation (pt-BR: Declarações enganosas) | Aviso ≥7 dias antes de eventual suspensão. | alta |
| ADS-MIS-03 | search_ads | Clickbait ads (pt-BR: Deturpação: Anúncios clickbait) | Aviso ≥7 dias antes de eventual suspensão. | alta |
| ADS-MIS-04 | search_ads | Unreliable claims (pt-BR: Deturpação: declarações não confiáveis) | Aviso ≥7 dias antes de eventual suspensão. | alta |
| ADS-MIS-05 | search_ads | Unclear relevance (pt-BR: Deturpação: relevância pouco clara) | Aviso ≥7 dias antes de eventual suspensão. | alta |
| ADS-MIS-06 | search_ads | Unavailable offers (pt-BR: Deturpação: ofertas indisponíveis) | Aviso ≥7 dias antes de eventual suspensão. | alta |
| ADS-MIS-07 | search_ads | Dishonest pricing practices (pt-BR: Práticas desonestas de preço) | Aviso ≥7 dias antes de eventual suspensão. | media |
| ADS-MIS-08 | search_ads | Misleading ad design (pt-BR: Deturpação: design enganoso do anúncio) | Aviso ≥7 dias antes de eventual suspensão. | media |
| ADS-EDI-00 | search_ads | Editorial — visão geral | Aviso ≥7 dias antes de eventual suspensão. | alta |
| ADS-EDI-01 | search_ads | Punctuation and symbols (pt-BR: Pontuação e símbolos) | Aviso ≥7 dias antes de eventual suspensão. | alta |
| ADS-EDI-02 | search_ads | Capitalization (pt-BR: Requisitos editoriais: letras maiúsculas) | Aviso ≥7 dias antes de eventual suspensão. | alta |
| ADS-EDI-03 | search_ads | Repetition (pt-BR: Requisitos editoriais: repetição) | Aviso ≥7 dias antes de eventual suspensão. | alta |
| ADS-EDI-04 | search_ads | Style and spelling (pt-BR: Requisitos editoriais: estilo e ortografia) | Aviso ≥7 dias antes de eventual suspensão. | alta |
| ADS-EDI-05 | search_ads | Unidentified business (pt-BR: Requisitos editoriais: empresa não identificada) | Aviso ≥7 dias antes de eventual suspensão. | media |
| ADS-EDI-06 | search_ads | Business name requirements (Editorial) | Aviso ≥7 dias antes de eventual suspensão. | alta |
| ADS-EDI-07 | search_ads | Misuse of ad features (Editorial) | Aviso ≥7 dias antes de eventual suspensão. | media |
| ADS-EDI-08 | search_ads | Unacceptable spacing (Editorial) | Aviso ≥7 dias antes de eventual suspensão. | alta |
| ADS-DST-00 | landing_page | Destination requirements — funcionamento, rastreabilidade e acesso | Reprovação do anúncio; aviso ≥7 dias antes de suspensão. | alta |
| ADS-DST-01 | landing_page | Destination mismatch (pt-BR: Destino não correspondente) | Reprovação; aviso ≥7 dias antes de suspensão. | alta |
| ADS-DST-02 | landing_page | Destination experience (pt-BR: Experiência de destino) | Reprovação; aviso ≥7 dias antes de suspensão. | alta |
| ADS-DST-03 | landing_page | Insufficient original content (pt-BR: Conteúdo original insuficiente) | Reprovação; aviso ≥7 dias antes de suspensão. | alta |
| ADS-TM-01 | search_ads | Trademarks (pt-BR: Marcas registradas) | Restrição do uso da marca no anúncio (após reclamação); aviso ≥7 dias antes de suspensão. | alta |
| ADS-ORB-GOV | search_ads | Government documents and (official) services — Other restricted businesses (pt-BR: Documentos e serviços do governo) | Restrição/limitação (anúncio não veicula sem certificação); aviso ≥7 dias antes de suspensão. | alta |
| ADS-LAS-01 | search_ads | Limited ad serving (pt-BR: Veiculação limitada de anúncios) | Limitação de impressões; sem reprovação individual. | alta |
| ADS-ABU-01 | search_ads | Abusing the ad network: Spam policies for Google Web Search | Reprovação; aviso ≥7 dias antes de suspensão. | alta |
| ADS-ABU-02 | search_ads | Abusing the ad network: Circumventing systems (cloaking) | Egregious: suspensão na detecção, sem aviso prévio. | alta |
| ADS-ABU-03 | search_ads | Abusing the ad network: Unfair advantage | Aviso ≥7 dias antes de suspensão. | alta |
| ADS-FMT-01 | search_ads | Sitelink asset requirements (pt-BR: Requisitos do recurso de sitelink) | Reprovação do asset; aviso ≥7 dias antes de suspensão. | alta |
| ADS-FMT-02 | search_ads | Callout asset requirements (pt-BR: Requisitos do recurso de frase de destaque) | Reprovação do asset; aviso ≥7 dias antes de suspensão. | alta |
| ADS-FMT-03 | search_ads | Structured snippet requirements (pt-BR: Requisitos para snippets estruturados) | Reprovação do asset. | alta |
| ADS-REV-01 | search_ads | About the ad review process | n/a | alta |
| ADS-PERS-01 | search_ads | Restricted targeting in Personalized advertising — negative financial status / imposing negativity | Anúncio não veicula para públicos do anunciante na categoria. | media |
| API-00 | api | Versões da Google Ads API (v25 em uso pelo código) | n/a | alta |
| API-01 | api | Atualizar RSA in-place (AdService.MutateAds) × criar anúncio novo | n/a | alta |
| API-02 | api | Limites do RSA: títulos, descrições, paths | Erro de validação/API. | alta |
| API-03 | api | Pins (fixação) no RSA | n/a | alta |
| API-04 | api | SitelinkAsset (v25): link_text, description1/2 | Erro de validação/API. | alta |
| API-05 | api | CalloutAsset (v25) | Erro de validação/API. | alta |
| API-06 | api | StructuredSnippetAsset (v25) | Erro de validação/API. | alta |
| API-07 | api | validate_only (MutateAdsRequest e demais mutates) | n/a | alta |
| API-08 | api | Isenção de política: PolicyViolationKey, exempt_policy_violation_keys, ignorable_policy_topics | n/a | alta |
| PUB-01 | monetizacao_publisher | Google Publisher Policies — Misleading representation | Bloqueio de anúncios na página/site ou suspensão da conta de publisher. | alta |
| PUB-02 | monetizacao_publisher | Google Publisher Policies — Deceptive practices | Bloqueio de anúncios ou suspensão. | alta |
| PUB-03 | monetizacao_publisher | Google Publisher Policies — Ads interfering (conteúdo e interação) | Bloqueio de anúncios ou suspensão. | alta |
| PUB-04 | monetizacao_publisher | Google Publisher Policies — Inventory value: telas sem conteúdo do publisher / baixo valor | Limitação/desativação de anúncios na página. | alta |
| PUB-05 | monetizacao_publisher | Google Publisher Policies — Mais anúncios que conteúdo do publisher | Limitação/desativação de anúncios. | alta |
| PUB-06 | monetizacao_publisher | Google Publisher Policies — Conteúdo replicado | Limitação/desativação de anúncios. | alta |
| PUB-07 | monetizacao_publisher | Google Publisher Policies — Spam policies for Google web search | Desativação de anúncios; exclusão da Pesquisa. | alta |
| PUB-08 | monetizacao_publisher | Google Publisher Policies — Abusive experiences | Bloqueio de anúncios; Abusive Experience Report. | alta |
| PUB-09 | monetizacao_publisher | Better Ads Standards (referenciado por Google Ads e Publisher Policies) | Desativação de anúncios; reprovação de destino no Google Ads (ADS-DST-02). | alta |
| PUB-10 | monetizacao_publisher | AdSense — rótulos de anúncio e incentivo a cliques | Desativação de anúncios/conta. | alta |
| PUB-11 | monetizacao_publisher | AdSense — navegação enganosa e cliques acidentais | Desativação de anúncios/conta. | alta |
| PUB-12 | monetizacao_publisher | AdSense — fontes de tráfego (tráfego pago) e páginas feitas para anúncios | Desativação de anúncios/conta. | alta |
| PUB-13 | monetizacao_publisher | Tráfego inválido / atividade inválida (AdSense e Platforms program policies) | Retenção de ganhos, limitação ou encerramento da conta. | alta |
| PUB-14 | monetizacao_publisher | Interstitials web (Ad Manager 'Traffic web interstitials') e vinhetas (AdSense) | n/a (documentação de formato; violações caem nas políticas citadas). | alta |
| PUB-15 | monetizacao_publisher | Ad Manager — Policies for ad units that offer rewards (rewarded) | Desativação do formato/inventário. | media |
| PUB-16 | monetizacao_publisher | Google Ad Manager Partner Guidelines (Open Auction) | Suspensão/encerramento do uso do Ad Manager. | alta |
| PUB-17 | monetizacao_publisher | Google Publisher Restrictions (restrições de conteúdo e comportamento) | Menos fontes de demanda; sem anúncios do Google Ads no conteúdo restrito. | alta |
| SEO-01 | search_organico | Spam policies for Google web search — Scaled content abuse (e scraping) | Rebaixamento ou remoção da Pesquisa; ação manual. | media |
| SEO-02 | search_organico | Spam policies for Google web search — Doorway abuse | Rebaixamento/remoção da Pesquisa. | media |
| SEO-03 | search_organico | Spam policies for Google web search — Misleading functionality / Scam and fraud | Rebaixamento/remoção da Pesquisa. | media |
| SEO-04 | search_organico | Search Central — Avoid intrusive interstitials and dialogs (orientação) | Possível pior desempenho orgânico. | media |

## Regras — Search Ads (anúncio, assets, conta)

### ADS-MIS-00 · Misrepresentation — visão geral (pt-BR: Deturpação)

**Fonte:** https://support.google.com/adspolicy/answer/6020955?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Guarda-chuva de 10 subpolíticas: Unacceptable business practices, Coordinated deceptive practices, Misleading representation, Dishonest pricing practices, Clickbait ads, Misleading ad design, Manipulated media, Unreliable claims, Unclear relevance e Unavailable offers. Anúncios e destinos não podem enganar omitindo informação relevante ou dando informação enganosa sobre produto, serviço ou empresa.

**Citação:** “The Misrepresentation policy strives to ensure that ads are clear, honest, and provide information that users need to make informed decisions.”

**Exige (A):**
- Anúncio e destino claros e honestos sobre quem anuncia e o que é oferecido.
- A lista atual NÃO contém mais 'Government documents and official services': esse tema vive hoje em 'Other restricted businesses' (ver ADS-ORB-GOV).

**Só sugere risco (B):**
- A página de visão geral usa redação ligeiramente diferente da subpágina ('supported by' × 'affiliated with'); a subpágina é a mais específica.

**Caso Senac:**
- Viola: Qualquer combinação de título/LP que faça o leitor crer que o Crédito Up é o Senac ou matricula em cursos.
- Não viola: Título: Cursos Senac: Guia Informativo — já APPROVED em 30/09 (baseline).

**Consequência:** Depende da subpolítica: Unacceptable business practices e Coordinated deceptive practices são 'egregious' (suspensão sem aviso); as demais avisam ≥7 dias antes de suspender.

**Confiança:** alta · **Observações:** Aviso padrão da página: a versão em inglês é a oficial para aplicação das políticas do Google Ads.

**Fontes adicionais:**
- Misrepresentation (overview) — “Make it seem like you’re supported by another brand, organization or government entity when you’re not” — https://support.google.com/adspolicy/answer/6020955?hl=en

### ADS-MIS-01 · Unacceptable business practices (pt-BR: Práticas comerciais inaceitáveis)

**Fonte:** https://support.google.com/adspolicy/answer/15938071?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: landing_page)

**Regra (paráfrase):** Proíbe enganar escondendo ou deturpando informação sobre o negócio: fazer parecer afiliação com outra marca, organização ou entidade governamental; oferecer o que não se tem/não se pode entregar; personificar outra marca para obter dinheiro ou dados. Violação é 'egregious': suspensão na detecção, sem aviso prévio.

**Citação:** “Make it seem like you’re affiliated with another brand, organization or government entity when you’re not”

**Exige (A):**
- Não sugerir vínculo com o Senac, a CNC ou governo (o Crédito Up não é parceiro nem autorizado).
- Não oferecer matrícula, inscrição ou vaga — o site não entrega isso.
- Não usar identidade do Senac (nome como se fosse o anunciante, logotipo, cores) de modo a esconder a própria identidade.

**Só sugere risco (B):**
- Boa prática (não exigência): se referencia outra marca sem ser parceiro, 'consider a disclaimer' no site e nos anúncios.
- Boa prática: página 'Sobre' com contato e explicação do que a empresa faz; usar a própria marca.

**Caso Senac:**
- Viola: Título: Senac Oficial: Inscreva-se
- Viola: Sitelink: Portal do Senac — apontando para página do creditoup.com.br
- Viola: LP com logotipo do Senac no topo e cabeçalho 'Portal de Cursos Senac'.
- Não viola: Título: Cursos Senac: Guia Editorial
- Não viola: Descrição: Guia do Crédito Up, sem vínculo com o Senac. A inscrição é feita no site do Senac.

**Consequência:** Egregious: 'your Google Ads accounts will be suspended upon detection and without prior warning'.

**Confiança:** alta · **Observações:** É a regra de maior consequência do caso: afiliação implícita com o Senac é suspensão da conta sem aviso. A LP pública salva em 30/09 já traz 'Portal editorial independente ... sem vínculo com as instituições citadas' (backups-producao/.../wordpress/public-guia-cursos-senac.html).

**Fontes adicionais:**
- Unacceptable business practices — best practices — “If you reference another brand but you're not an official or authorized partner, consider a disclaimer on your website and in your ads.” — https://support.google.com/adspolicy/answer/15938071?hl=en
- Unacceptable business practices — consequência — “your Google Ads accounts will be suspended upon detection and without prior warning” — https://support.google.com/adspolicy/answer/15938071?hl=en

### ADS-MIS-02 · Misleading representation (pt-BR: Declarações enganosas)

**Fonte:** https://support.google.com/adspolicy/answer/15936666?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: landing_page)

**Regra (paráfrase):** Proíbe declarações enganosas, ocultação ou omissão de informação material sobre identidade, afiliações ou qualificações; e nome de empresa impreciso ou que não represente claramente o anunciante.

**Citação:** “Implying affiliation with or endorsement by another organization, brand, or private citizen without their knowledge or consent”

**Exige (A):**
- Não omitir que o Crédito Up é editorial e não oferece os cursos.
- Nome de empresa (quando o formato pedir) deve representar o anunciante (ver ADS-EDI-06).

**Só sugere risco (B):**
- Por analogia com o exemplo oficial do afiliado de serviços jurídicos: anúncio de 'cursos Senac' que não deixa claro que o anunciante não presta o serviço.

**Caso Senac:**
- Viola: Título: Matrículas Senac 2026 — omite que o site não matricula
- Viola: Título: Faça Seu Curso no Senac — sem nenhum ativo dizendo que é um guia
- Não viola: Título: Como Se Inscrever no Senac
- Não viola: Descrição: Guia editorial independente sobre cursos Senac. Entenda requisitos e ofertas por estado. — texto atual, APPROVED

**Consequência:** Aviso ≥7 dias antes de eventual suspensão.

**Confiança:** alta · **Observações:** Aviso ≥7 dias antes de suspensão. Diferença para ADS-MIS-01: aqui a omissão/ambiguidade basta; lá há intenção de enganar/personificar.

**Fontes adicionais:**
- Misleading representation — exemplo — “An affiliate marketer advertising legal services without disclosing that they do not provide legal services” — https://support.google.com/adspolicy/answer/15936666?hl=en

### ADS-MIS-03 · Clickbait ads (pt-BR: Deturpação: Anúncios clickbait)

**Fonte:** https://support.google.com/adspolicy/answer/15936667?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Proíbe táticas de clickbait ou texto/imagem sensacionalista para gerar tráfego (ex.: 'revelar segredos', 'Click here to find out', 'You won't believe...') e o uso de eventos negativos de vida (morte, doença, prisão, falência etc.) para provocar medo/culpa e pressionar ação imediata.

**Citação:** “Ads that use clickbait tactics or sensationalist text or imagery to drive traffic are not allowed.”

**Exige (A):**
- Nada de 'segredo', 'o que ninguém conta', 'você não vai acreditar', 'clique e descubra'.
- Nada de medo/culpa com evento negativo de vida para forçar o clique (ex.: desemprego como ameaça).

**Só sugere risco (B):**
- Pergunta que retém a resposta para forçar o clique se aproxima do exemplo 'to encourage the user to click on the Ad in order to understand the full context'.
- 'Poucos sabem' se aproxima de 'claim to reveal secrets'.

**Caso Senac:**
- Viola: Título: O Segredo dos Cursos Grátis
- Viola: Título: Clique e Descubra Seu Curso
- Viola: Título: Desempregado? Corra Já
- Não viola: Título: Quem Pode Fazer Curso Grátis? — a LP responde (renda per capita até 2 salários-mínimos, fonte senac.br)
- Não viola: Título: Requisitos da Gratuidade Senac

**Consequência:** Aviso ≥7 dias antes de eventual suspensão.

**Confiança:** alta · **Observações:** É a base oficial da proibição de sensacionalismo que o repo já cita (funnelforge-migracao/engine/src/funnelforge/prompts/redator_p1.jinja:3).

**Fontes adicionais:**
- Clickbait — exemplo — “Ads that claim to reveal secrets, scandals or other sensationalist information about the product or service being advertised” — https://support.google.com/adspolicy/answer/15936667?hl=en
- Clickbait — eventos negativos — “Ads that use negative life events such as death, accidents, illness, arrests or bankruptcy to induce fear, guilt or other strong negative emotions” — https://support.google.com/adspolicy/answer/15936667?hl=en

### ADS-MIS-04 · Unreliable claims (pt-BR: Deturpação: declarações não confiáveis)

**Fonte:** https://support.google.com/adspolicy/answer/15936857?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: landing_page)

**Regra (paráfrase):** Proíbe afirmações imprecisas ou que atraiam com resultado improvável (mesmo que possível) apresentado como o resultado provável. Exemplos oficiais concentram-se em saúde/peso, finanças e política; o princípio é geral.

**Citação:** “claims that entice the user with an improbable result (even if this result is possible) as the likely outcome a user can expect”

**Exige (A):**
- Não prometer vaga, aprovação, gratuidade universal ou certificado como desfecho provável.
- Afirmações factuais (renda, requisitos) precisam ser corretas.

**Só sugere risco (B):**
- Educação/cursos não aparece nos exemplos oficiais: aplicar ao Senac é interpretação pelo princípio geral.
- Em saúde, a página exige política de reembolso para garantias e aviso em depoimentos — não se transpõe automaticamente para cursos.

**Caso Senac:**
- Viola: Título: Vaga Garantida no Senac
- Viola: Título: Curso Grátis Para Todos
- Viola: Título: Aprovação Rápida no PSG
- Não viola: Título: Gratuidade Depende de Renda
- Não viola: Descrição: No PSG, a gratuidade exige renda familiar per capita de até 2 salários-mínimos. — fato de senac.br

**Consequência:** Aviso ≥7 dias antes de eventual suspensão.

**Confiança:** alta · **Observações:** Fato de apoio: 'Apenas pessoas com renda familiar per capita até 2 salários-mínimos podem participar.' (https://www.senac.br/, ver FATO-04).

### ADS-MIS-05 · Unclear relevance (pt-BR: Deturpação: relevância pouco clara)

**Fonte:** https://support.google.com/adspolicy/answer/15936964?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: landing_page)

**Regra (paráfrase):** Promoções irrelevantes para o destino são proibidas: título sem relação com o conteúdo, anúncio que não descreve com precisão o destino, inserção de palavra-chave sem 'default' relevante, palavras-chave genéricas demais ou spam de palavras-chave.

**Citação:** “Promotions that are not relevant to the destination are not allowed.”

**Exige (A):**
- Cada título/descrição precisa descrever o que a página de destino de fato contém.
- Se usar DKI ({KeyWord:...}), o texto padrão precisa ser relevante.

**Só sugere risco (B):**
- Termos de busca reais incluem cursos específicos ('manicure', 'operador de caixa', 'libras'); títulos sobre cursos específicos exigem que a LP/interna trate deles.

**Caso Senac:**
- Viola: Título: Lista de Cursos Grátis 2026 — a LP atual não traz lista de cursos
- Viola: Título: Inscrições Senac Abertas — a LP é um guia, não um canal de inscrição
- Não viola: Título: Como Consultar Cursos no Senac — a LP explica onde e como consultar

**Consequência:** Aviso ≥7 dias antes de eventual suspensão.

**Confiança:** alta · **Observações:** Com ADS-MIS-06, é o elo direto entre a copy do RSA e o conteúdo real das páginas 2306/2309/2312/2315/2318.

**Fontes adicionais:**
- Unclear relevance — exemplo — “Ads that don’t accurately describe the content of the destination” — https://support.google.com/adspolicy/answer/15936964?hl=en
- Unclear relevance — DKI — “Ads that use the keyword insertion feature without a relevant "default" keyword” — https://support.google.com/adspolicy/answer/15936964?hl=en

### ADS-MIS-06 · Unavailable offers (pt-BR: Deturpação: ofertas indisponíveis)

**Fonte:** https://support.google.com/adspolicy/answer/15937063?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: landing_page)

**Regra (paráfrase):** Proíbe prometer no anúncio produto, serviço ou oferta indisponível ou difícil de encontrar a partir do destino, incluindo chamada para ação que não está facilmente disponível no destino.

**Citação:** “Promising products, services, or promotional offers in the ad that are unavailable or aren't easily found from the destination is not allowed.”

**Exige (A):**
- O que o anúncio promete (ex.: 'requisitos', 'como consultar por estado') precisa estar fácil de achar na LP.
- CTA do anúncio precisa existir no destino: 'Inscreva-se' não existe no creditoup.

**Só sugere risco (B):**
- Promessa satisfeita só depois de várias páginas internas pode ser lida como 'not easily found from the destination' (interpretação).

**Caso Senac:**
- Viola: Título: Curso de Manicure Grátis — a LP não trata dessa oferta
- Viola: Título: Inscreva-se Hoje no Senac — o destino não inscreve
- Não viola: Título: Cursos Senac por Estado — a LP tem a seção 'Onde procurar a oferta do seu estado'

**Consequência:** Aviso ≥7 dias antes de eventual suspensão.

**Confiança:** alta · **Observações:** O repo já tem regra alinhada para páginas: 'Não ofereça "Inscreva-se" quando o clique apenas abre outra página editorial.' (funnelforge-migracao/engine/src/funnelforge/prompts/interior_editorial.jinja:35).

**Fontes adicionais:**
- Unavailable offers — exemplo — “Call-to-action in the ad that isn't easily available from the destination” — https://support.google.com/adspolicy/answer/15937063?hl=en

### ADS-MIS-07 · Dishonest pricing practices (pt-BR: Práticas desonestas de preço)

**Fonte:** https://support.google.com/adspolicy/answer/15938375?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Exige divulgar com clareza modelo de pagamento e custo total; proíbe práticas que criem impressão falsa de custo (ex.: isca-e-troca, apresentar app como gratuito quando é pago, teste grátis sem informar cobrança).

**Citação:** “create a false or misleading impression of the cost of a product or service”

**Exige (A):**
- 'Grátis/gratuito' só quando verdadeiro para o que se anuncia; o Crédito Up não cobra nada, mas a gratuidade dos cursos é do Senac e tem critério.

**Só sugere risco (B):**
- A política mira o preço do que o anunciante vende; aplicá-la a afirmação sobre gratuidade de terceiro é interpretação — o enquadramento mais direto é ADS-MIS-04/06.
- Se alguma oferta gratuita tiver custos acessórios (material, taxa), 'grátis' sem ressalva vira risco — não verificado para o PSG.

**Caso Senac:**
- Viola: Título: Cursos Senac 100% Grátis — a própria LP diz 'Nem todo curso do catálogo é gratuito'
- Não viola: Título: Gratuidade Tem Regra de Renda

**Consequência:** Aviso ≥7 dias antes de eventual suspensão.

**Confiança:** media · **Observações:** Exemplo oficial literal sobre 'free': 'Promoting apps as free when a user must pay to install the app'.

**Fontes adicionais:**
- Dishonest pricing — exemplo 'free' — “Promoting apps as free when a user must pay to install the app” — https://support.google.com/adspolicy/answer/15938375?hl=en

### ADS-MIS-08 · Misleading ad design (pt-BR: Deturpação: design enganoso do anúncio)

**Fonte:** https://support.google.com/adspolicy/answer/15937463?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: landing_page)

**Regra (paráfrase):** Proíbe anúncios que dificultem perceber que se trata de anúncio (imitar avisos de sistema, botões que não funcionam, setas etc.). A visão geral inclui 'inconsistências entre o anúncio e a landing page'.

**Citação:** “Ads that make it difficult for the user to understand they're interacting with an ad aren't allowed.”

**Exige (A):**
- Para Search texto, o ponto aplicável é a consistência anúncio ↔ LP.

**Só sugere risco (B):**
- A maior parte dos exemplos é de anúncios de imagem; relevância para RSA é baixa.

**Caso Senac:**
- Viola: Anúncio 'guia independente' que leva a uma LP visualmente idêntica ao site do Senac (cores, logotipo, rodapé).
- Não viola: LP com a marca Crédito Up visível no topo, como no HTML público salvo em 30/09.

**Consequência:** Aviso ≥7 dias antes de eventual suspensão.

**Confiança:** media · **Observações:** Artigo atualizado em ago/2026 com mais exemplos, 'This does not change enforcement of the policy.' (https://support.google.com/adspolicy/answer/17600038).

**Fontes adicionais:**
- Misrepresentation (overview) — Misleading ad design — “Inconsistencies between the ad and the landing page/app.” — https://support.google.com/adspolicy/answer/6020955?hl=en

### ADS-EDI-00 · Editorial — visão geral

**Fonte:** https://support.google.com/adspolicy/answer/6021546?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Padrões editoriais e profissionais: só anúncios, assets e destinos claros, fáceis de interagir e relevantes. Subpolíticas: Business name requirements, Capitalization, Image quality, Misuse of ad features, Phone number in ad text, Punctuation and symbols, Repetition, Style and spelling, Unacceptable spacing, Unidentified business, Video quality.

**Citação:** “Google Ads only allows ads, assets, and destinations that are clear, easy to interact with, and relevant to users.”

**Exige (A):**
- Cumprir as subpolíticas ADS-EDI-01 a ADS-EDI-08.

**Só sugere risco (B):**
- (nenhum)

**Caso Senac:**
- Viola: Ver subentradas.
- Não viola: Ver subentradas.

**Consequência:** Aviso ≥7 dias antes de eventual suspensão.

**Confiança:** alta · **Observações:** Violações editoriais NÃO geram suspensão imediata: a página diz que haverá aviso ≥7 dias antes. A política 'Text ad requirements' foi descontinuada em 17/03/2026 (ver CHG-02).

**Fontes adicionais:**
- Editorial — consequência — “Violations of the policies below will not lead to immediate account suspension without prior warning.” — https://support.google.com/adspolicy/answer/6021546?hl=en

### ADS-EDI-01 · Punctuation and symbols (pt-BR: Pontuação e símbolos)

**Fonte:** https://support.google.com/adspolicy/answer/14847994?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Proíbe pontuação/símbolos fora do uso correto ou do propósito (repetição consecutiva, troca de letras por símbolos, sobrescrito não padrão, bullets/asteriscos decorativos, uso excessivo ou 'gimmicky') e caracteres inválidos (ex.: emoji). Permite asterisco para condições legais e símbolos em marcas usados de forma consistente no destino (com revisão).

**Citação:** “Punctuation or symbols repeated consecutively, like "flowers!!"”

**Exige (A):**
- Sem '!!', '??', emoji (ex.: o 'visto verde'), '★', 'C.U.R.S.O.S', letras trocadas por números/símbolos.
- Asterisco só para condições legalmente exigidas ou notas de avaliação.

**Só sugere risco (B):**
- Símbolos não listados (ex.: '|' como separador) não aparecem na página — risco de leitura como 'non-standard symbol', não regra explícita.

**Caso Senac:**
- Viola: Título: Cursos Grátis Senac!!
- Viola: Título: ★ Cursos Senac ★
- Viola: Título: Cursos Senac [emoji de visto verde]
- Não viola: Título: Cursos Senac: Guia Informativo
- Não viola: Título: Quem Pode Estudar de Graça?

**Consequência:** Aviso ≥7 dias antes de eventual suspensão.

**Confiança:** alta · **Observações:** A página vigente não menciona ponto de exclamação único em título/descrição; em sitelink/callout/snippet ele está listado como exemplo proibido (ver ADS-FMT-01..03 e NE-02).

**Fontes adicionais:**
- Punctuation — símbolos — “Non-standard symbols or characters like bullet points or asterisks, like "*flowers*"” — https://support.google.com/adspolicy/answer/14847994?hl=en
- Punctuation — exceção — “Using an asterisk to indicate that legally required conditions apply” — https://support.google.com/adspolicy/answer/14847994?hl=en

### ADS-EDI-02 · Capitalization (pt-BR: Requisitos editoriais: letras maiúsculas)

**Fonte:** https://support.google.com/adspolicy/answer/14848295?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Proíbe capitalização incorreta ou fora do propósito — exemplos: 'FLOWERS', 'FlOwErS', 'F.L.O.W.E.R.S'. Permite abreviações comuns, códigos de cupom e marcas com capitalização própria (sujeito a revisão).

**Citação:** “Capitalization that isn't used correctly or for its intended purpose”

**Exige (A):**
- Sem palavra comum em caixa alta ('GRÁTIS', 'SENAC CURSOS') nem caixa alternada.

**Só sugere risco (B):**
- Title Case não é mencionado (nem exigido nem vetado) — ver NE-08.

**Caso Senac:**
- Viola: Título: CURSOS GRÁTIS SENAC
- Viola: Título: CuRsOs SeNaC
- Não viola: Título: Cursos Senac por Estado — Title Case, APPROVED em 30/09
- Não viola: Título: Programa Senac (PSG)

**Consequência:** Aviso ≥7 dias antes de eventual suspensão.

**Confiança:** alta · **Observações:** A marca se grafa 'Senac' no site oficial; a sigla 'SENAC' aparece no Decreto-Lei 8.621/1946. Siglas comuns são aceitas pela política.

**Fontes adicionais:**
- Capitalization — exceções — “Capitalization that’s considered non-standard may be allowed in some cases, such as common abbreviations like “ASAP” and in coupon codes.” — https://support.google.com/adspolicy/answer/14848295?hl=en

### ADS-EDI-03 · Repetition (pt-BR: Requisitos editoriais: repetição)

**Fonte:** https://support.google.com/adspolicy/answer/14848296?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Proíbe repetição não padrão, 'gimmicky' ou desnecessária de nomes, palavras ou frases (inclusive assets que repetem texto já presente no anúncio) e texto de asset que repete palavras/frases no mesmo asset ou em outro asset do mesmo grupo, campanha ou conta.

**Citação:** “Asset text that repeats words or phrases within the same asset or another asset in the same ad group, campaign, or account”

**Exige (A):**
- Callout/sitelink não pode repetir texto de título, descrição ou outro asset.
- Nada de 'Senac Senac', 'Cursos Senac Cursos Grátis Senac'.

**Só sugere risco (B):**
- A política não fixa limiar numérico; o limite interno 'palavra de 4+ letras em no máximo 4 títulos' é preferência (ver NE-10).
- Sobreposição parcial (callout 'Guia Independente' × título 'Guia Editorial Independente') passou na revisão atual — aprovação passada não garante as próximas.

**Caso Senac:**
- Viola: Título: Senac Cursos Senac Grátis
- Viola: Callout: Conheça as Modalidades — idêntico a um título existente
- Não viola: Callout: Fontes do Senac Citadas — se a LP citar as fontes
- Não viola: Callout: Consulta por Estado — APPROVED em 30/09

**Consequência:** Aviso ≥7 dias antes de eventual suspensão.

**Confiança:** alta · **Observações:** Exemplos oficiais: 'Repeating the advertiser name', 'Repeating the product name'.

**Fontes adicionais:**
- Repetition — primeira regra — “Non-standard, gimmicky, or unnecessary repetition of names, words, or phrases, including assets that repeat text that’s already present in the ad text” — https://support.google.com/adspolicy/answer/14848296?hl=en

### ADS-EDI-04 · Style and spelling (pt-BR: Requisitos editoriais: estilo e ortografia)

**Fonte:** https://support.google.com/adspolicy/answer/14848297?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Proíbe ortografia/gramática não aceitas, texto incompreensível ou genérico demais, texto cortado, e estilo incompatível com a apresentação clara e informativa da Pesquisa (listas com marcadores/numeradas, CTA genérico como 'click here').

**Citação:** “Ads that contain a generic call to action like "click here" that could apply to any ad”

**Exige (A):**
- Sem 'Clique aqui' e equivalentes genéricos.
- Sem listas numeradas/marcadores no texto do anúncio.
- Sem texto truncado ou genérico ('Cursos, vagas e mais').

**Só sugere risco (B):**
- 'Saiba mais' isolado é CTA genérico em espírito; não está listado literalmente.

**Caso Senac:**
- Viola: Título: Clique Aqui e Veja
- Viola: Descrição: 1. Requisitos 2. Estados 3. Inscrição
- Viola: Título: Cursos Senac para quem
- Não viola: Título: Veja os Requisitos do PSG
- Não viola: Título: Entenda as Opções de Cursos — APPROVED em 30/09

**Consequência:** Aviso ≥7 dias antes de eventual suspensão.

**Confiança:** alta · **Observações:** Imperativo específico (Veja/Entenda/Confira + objeto informativo) não é vetado; o veto é ao CTA que serviria a qualquer anúncio.

**Fontes adicionais:**
- Style — listas — “Ads that use bullet points or numbered lists” — https://support.google.com/adspolicy/answer/14848297?hl=en
- Style — texto genérico — “Gibberish or overly generic ad text” — https://support.google.com/adspolicy/answer/14848297?hl=en

### ADS-EDI-05 · Unidentified business (pt-BR: Requisitos editoriais: empresa não identificada)

**Fonte:** https://support.google.com/adspolicy/answer/14848399?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: landing_page)

**Regra (paráfrase):** Anúncios ou destinos precisam nomear o produto, serviço ou entidade que promovem (nome de produto, empresa ou URL de exibição).

**Citação:** “Ads or destinations that don't name the product, service, or entity they are promoting”

**Exige (A):**
- O destino precisa identificar o Crédito Up como publicador (hoje atendido pelo aviso no topo da LP).

**Só sugere risco (B):**
- Pelo exemplo oficial ('product name, company name, or display URL') o domínio exibido do RSA tende a satisfazer o anúncio; ter a marca num título é recomendação de Limited ad serving (ADS-LAS-01), não exigência desta política.

**Caso Senac:**
- Viola: LP sem qualquer menção ao Crédito Up, só 'Cursos Senac' no cabeçalho.
- Não viola: LP com 'O Crédito Up publica guias informativos...' no topo, como em 30/09.

**Consequência:** Aviso ≥7 dias antes de eventual suspensão.

**Confiança:** media · **Observações:** Interpretação do 'or' do exemplo oficial marcada como média.

**Fontes adicionais:**
- Unidentified business — exemplo — “Ads that don’t include a product name, company name, or display URL” — https://support.google.com/adspolicy/answer/14848399?hl=en

### ADS-EDI-06 · Business name requirements (Editorial)

**Fonte:** https://support.google.com/adspolicy/answer/14847993?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Nos formatos com campo de nome da empresa, o nome deve ser o domínio, o nome reconhecido do anunciante ou o app promovido; proíbe linguagem promocional e nomes genéricos/geográficos.

**Citação:** “Providing a business name that's anything other than the domain, the recognized name of the advertiser, or the promoted downloadable app”

**Exige (A):**
- Nome da empresa = 'Crédito Up' (ou o domínio), nunca 'Cursos Senac' ou 'Guia Senac'.
- Com Advertiser Verification concluída, o nome precisa bater com o domínio ou com o nome verificado.

**Só sugere risco (B):**
- (nenhum)

**Caso Senac:**
- Viola: Nome da empresa: Cursos Senac Grátis
- Viola: Nome da empresa: Guia Senac
- Não viola: Nome da empresa: Crédito Up

**Consequência:** Aviso ≥7 dias antes de eventual suspensão.

**Confiança:** alta · **Observações:** O baseline não registra asset de nome da empresa na campanha; a regra vale se for adicionado.

**Fontes adicionais:**
- Business name — promocional — “Using promotional language in the business name field” — https://support.google.com/adspolicy/answer/14847993?hl=en

### ADS-EDI-07 · Misuse of ad features (Editorial)

**Fonte:** https://support.google.com/adspolicy/answer/14847686?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Proíbe usar recursos do anúncio fora do propósito: campo de URL como linha extra de texto, ValueTrack visível, anúncio sem conteúdo promocional, texto faltando.

**Citação:** “Using the URL field as an additional line of text”

**Exige (A):**
- path1/path2 descrevem o caminho do conteúdo, não fazem chamada promocional.

**Só sugere risco (B):**
- Path como 'inscricao/gratis' tende a ser lido como texto promocional no campo de URL (interpretação).

**Caso Senac:**
- Viola: Path: inscreva-se — e path2 'gratis-hoje'
- Não viola: Path: cursos-senac — e path2 'requisitos'

**Consequência:** Aviso ≥7 dias antes de eventual suspensão.

**Confiança:** media · **Observações:** O RSA atual não usa path1/path2 (baseline).

**Fontes adicionais:**
- Misuse — ValueTrack — “Making ValueTrack tags visible in ad text” — https://support.google.com/adspolicy/answer/14847686?hl=en

### ADS-EDI-08 · Unacceptable spacing (Editorial)

**Fonte:** https://support.google.com/adspolicy/answer/14848500?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Proíbe omitir espaço, adicionar espaços extras ou usar espaçamento excessivo/'gimmicky' (ex.: 'f l o w e r s').

**Citação:** “Excessive or gimmicky use of spacing”

**Exige (A):**
- Sem 'C u r s o s', sem espaço duplo, sem 'Senac,cursos'.

**Só sugere risco (B):**
- (nenhum)

**Caso Senac:**
- Viola: Título: C u r s o s  S e n a c
- Não viola: Título: Cursos Senac por Estado

**Consequência:** Aviso ≥7 dias antes de eventual suspensão.

**Confiança:** alta

### ADS-TM-01 · Trademarks (pt-BR: Marcas registradas)

**Fonte:** https://support.google.com/adspolicy/answer/6118?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: landing_page)

**Regra (paráfrase):** O Google só restringe uso de marca após reclamação do titular, analisando o uso no texto do anúncio. Não restringe marca como palavra-chave; restringe uso por concorrente direto e uso confuso, enganoso ou desorientador; não restringe anúncio cuja LP tenha como propósito principal informar sobre produtos/serviços da marca, nem uso descritivo.

**Citação:** “Ads using the trademark where the primary purpose of the landing page is to provide informative details about products or services corresponding to the trademark”

**Exige (A):**
- Uso de 'Senac' no texto não pode ser confuso ou enganoso sobre quem anuncia.

**Só sugere risco (B):**
- O Senac pode registrar reclamação a qualquer momento — não verificado se existe.
- Legislação brasileira de marcas e concorrência desleal: fora do escopo, não verificada.

**Caso Senac:**
- Viola: Título: Senac: Site de Inscrição — uso confuso/enganoso, passível de restrição após reclamação
- Não viola: Título: Cursos Senac: Guia Informativo — LP informativa; APPROVED sem tópicos de política em 30/09

**Consequência:** Restrição do uso da marca no anúncio (após reclamação); aviso ≥7 dias antes de suspensão.

**Confiança:** alta · **Observações:** Baseline (ads.json, 30/09): policy_summary do RSA = REVIEWED/APPROVED, sem entradas de tópico (nenhuma limitação por marca registrada naquele momento).

**Fontes adicionais:**
- Trademarks — uso restrito — “Ads that use the trademark in a confusing, deceptive, or misleading way” — https://support.google.com/adspolicy/answer/6118?hl=en
- Trademarks — gatilho — “If a trademark owner submits a complaint to Google about the use of their trademark” — https://support.google.com/adspolicy/answer/6118?hl=en

### ADS-ORB-GOV · Government documents and (official) services — Other restricted businesses (pt-BR: Documentos e serviços do governo)

**Fonte:** https://support.google.com/adspolicy/answer/13156083?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Só governos certificados e provedores autorizados podem anunciar aquisição direta de documentos e serviços específicos de governo da lista abrangente (identificação, certidões, mudança de nome/endereço, identificadores de empresa, antecedentes criminais, programas/benefícios de saúde e assistência, restituições, vistos, passaportes, habilitação, pedágios, registro/placa de veículo, licenças de caça/pesca, loterias de residência).

**Citação:** “Government documents and services are official documents issued by the government and official services rendered by the government.”

**Exige (A):**
- NÃO SE APLICA LITERALMENTE ao caso: cursos do Senac não estão na lista abrangente e o Senac não é governo — o Regulamento do Senac diz que é 'uma instituição de direito privado' (FATO-01).
- Se aplicaria se a copy promovesse aquisição de documento/benefício de governo da lista (não é o caso).

**Só sugere risco (B):**
- Classificação automática: a página prevê formulário de exclusão para quem é afetado sem promover documentos/serviços de governo; a página 'Other restricted businesses' cita exclusão para serviços 'purely editorial, educational, or consultancy-based'.
- Copy que chame o curso de 'benefício do governo' ou 'programa do governo' seria falsa (Misrepresentation) e aproximaria o anúncio da categoria de benefícios.

**Caso Senac:**
- Viola: Título: Curso Grátis do Governo — o Senac não é governo; deturpação e risco de classificação indevida
- Não viola: Título: Requisitos do PSG do Senac

**Consequência:** Restrição/limitação (anúncio não veicula sem certificação); aviso ≥7 dias antes de suspensão.

**Confiança:** alta · **Observações:** Resposta à pergunta da tarefa: a política existe e está em 'Other restricted businesses' (seção 'Government documents and official services'; página própria 'Government documents and services'); pelo texto, não alcança cursos do Senac. Atualização com vigência em 05/10/2026 endurece critérios de 'authorized provider' (CHG-01), sem mudar a lista. O repo registra experiência com o tópico em outros funis: 'FULLY_LIMITED medido em 57 anúncios de 39 contas sob GOVERNMENT_DOCUMENTS_AND_OFFICIAL_SERVICES' (volc_ads/isencao.py:14-16) — dado da operação, não verificado aqui.

**Fontes adicionais:**
- Government documents and services — regra — “Only certified governments and authorized providers may run ads that promote direct acquisition of specific government documents and services.” — https://support.google.com/adspolicy/answer/13156083?hl=en
- Other restricted businesses — exclusão editorial/educacional — “If your services are purely editorial, educational, or consultancy-based and do not facilitate the direct acquisition of government documents” — https://support.google.com/adspolicy/answer/6368711?hl=en
- Decreto nº 61.843/1967 (Regulamento do Senac), art. 4º — “O Serviço Nacional de Aprendizagem Comercial é uma instituição de direito privado, nos têrmos da Lei civil” — https://www.planalto.gov.br/ccivil_03/decreto/1950-1969/d61843.htm

### ADS-LAS-01 · Limited ad serving (pt-BR: Veiculação limitada de anúncios)

**Fonte:** https://support.google.com/adspolicy/answer/13889491?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** O Google limita impressões de anunciantes 'não qualificados' em cenários com maior potencial de experiência negativa. Em Search, anúncios que citam outras marcas e anúncios genéricos sem marca podem confundir quanto à identidade do anunciante; nesses casos pode limitar impressões em certas buscas. Anúncios individuais não são reprovados.

**Citação:** “ads that reference other brands and generic ads that have no branding at all may confuse users about the identity of the advertiser”

**Exige (A):**
- Mecanismo existe e é da plataforma (limitação de impressões, não reprovação).

**Só sugere risco (B):**
- Boas práticas (não exigências): marca própria visível no anúncio e na LP; clareza sobre a relação com marcas citadas; evitar copy genérica; fixar o domínio no início do título, especialmente para anunciante novo.
- Anúncios que citam a marca de terceiro 'Senac' em buscas que contêm a marca são o cenário descrito; não verificados a maturidade/qualificação da conta nem se ela está limitada (nenhuma notificação consta no baseline).

**Caso Senac:**
- Viola: Não é 'violação': risco de impressões limitadas com títulos só 'Cursos Senac ...' e nenhum 'Crédito Up' servindo.
- Não viola: Título: Crédito Up: Guia de Cursos — fixado na posição 1 (trade-off: fixar reduz rotação e Ad Strength)

**Consequência:** Limitação de impressões; sem reprovação individual.

**Confiança:** alta · **Observações:** Ampliações em jun/2026 (Search) e ago/2026 (todos os anúncios), implementação gradual até 2028 (CHG-03). Hoje o título 'Crédito Up: Guia Informativo' existe, mas não está fixado.

**Fontes adicionais:**
- Limited ad serving — fixar domínio — “Pin your domain to the front of the ad title, especially if you're a new advertiser or your brand is less well-known.” — https://support.google.com/adspolicy/answer/13889491?hl=en
- Limited ad serving — sem reprovação — “Individual ads will not be disapproved.” — https://support.google.com/adspolicy/answer/13889491?hl=en

### ADS-ABU-01 · Abusing the ad network: Spam policies for Google Web Search

**Fonte:** https://support.google.com/adspolicy/answer/15936769?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: search_organico)

**Regra (paráfrase):** Proíbe práticas que violem as políticas de spam da Pesquisa (keyword stuffing, cloaking, redirecionamento enganoso, doorway pages). Anúncios para destinos removidos da Pesquisa por ação manual são reprovados.

**Citação:** “Ads that point to destinations that have been removed from Google Search through a manual action will be disapproved.”

**Exige (A):**
- Manter creditoup.com.br livre de ação manual por spam (scaled content, doorway etc.).

**Só sugere risco (B):**
- Liga diretamente o risco orgânico (SEO-01/02) à veiculação paga.

**Caso Senac:**
- Viola: Anunciar a LP depois de o site receber ação manual por conteúdo em escala.
- Não viola: Site sem ação manual — não verificado (sem acesso ao Search Console nesta etapa).

**Consequência:** Reprovação; aviso ≥7 dias antes de suspensão.

**Confiança:** alta

### ADS-ABU-02 · Abusing the ad network: Circumventing systems (cloaking)

**Fonte:** https://support.google.com/adspolicy/answer/15938075?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: landing_page)

**Regra (paráfrase):** Proíbe contornar ou interferir nos sistemas de anúncios: variações para escapar de reprovação, contas novas após suspensão, uso abusivo de recursos, cloaking (mostrar ao Google conteúdo diferente do mostrado às pessoas, inclusive interstitial intrusivo que impede o Google de avaliar o destino). Violação 'egregious'.

**Citação:** “A pop-up, also known as an “intrusive interstitial” that blocks access to the majority of your website’s content, meaning Google cannot access your landing page”

**Exige (A):**
- AdsBot e usuário recebem a mesma página e o mesmo produto.
- Nenhum overlay/interstitial cobrindo a maior parte da LP de modo que o Google não consiga avaliá-la.
- Não criar variações de anúncio/domínio para contornar reprovação.

**Só sugere risco (B):**
- Esconder blocos de anúncio ou o interstitial do AdsBot (detecção de user agent) seria cloaking — não há indício disso no HTML salvo; não verificado.

**Caso Senac:**
- Viola: Servir ao AdsBot a LP sem anúncios e ao visitante a LP com vinheta imediata.
- Não viola: Mesma LP para todos; interstitial só do formato Google, fechável.

**Consequência:** Egregious: suspensão na detecção, sem aviso prévio.

**Confiança:** alta · **Observações:** A mesma página diz que reprovações editoriais não geram suspensão por esta política.

**Fontes adicionais:**
- Circumventing systems — editorial não suspende — “Accounts aren't suspended under this policy for having ad disapprovals related to editorial issues like formatting or misspelled words.” — https://support.google.com/adspolicy/answer/15938075?hl=en
- Circumventing systems — cloaking — “Showing Google a landing page or an ad's destination that complies with Google Ads' policies while showing people different content.” — https://support.google.com/adspolicy/answer/15938075?hl=en

### ADS-ABU-03 · Abusing the ad network: Unfair advantage

**Fonte:** https://support.google.com/adspolicy/answer/15936768?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Proíbe ganhar vantagem de tráfego injusta no leilão, p.ex. tentar mostrar mais de um anúncio do mesmo negócio/site no mesmo espaço; cada site promovido deve oferecer valor distinto.

**Citação:** “Trying to show more than one ad for your business, app, or site in a single ad location”

**Exige (A):**
- Uma campanha/um domínio por intenção; nada de domínios-espelho para a mesma busca 'cursos senac'.

**Só sugere risco (B):**
- Multiplicar funis quase iguais sobre o mesmo tema em domínios distintos.

**Caso Senac:**
- Viola: Dois domínios da operação com LPs equivalentes disputando 'cursos gratuitos senac'.
- Não viola: Uma campanha (24278665189) para um domínio.

**Consequência:** Aviso ≥7 dias antes de suspensão.

**Confiança:** alta · **Observações:** Relevância baixa no estado atual (uma campanha).

**Fontes adicionais:**
- Unfair advantage — valor distinto — “Each website or app that you promote should offer distinct value to users.” — https://support.google.com/adspolicy/answer/15936768?hl=en

### ADS-FMT-01 · Sitelink asset requirements (pt-BR: Requisitos do recurso de sitelink)

**Fonte:** https://support.google.com/adspolicy/answer/1054210?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Sitelinks: não repetir texto do link; URLs do mesmo domínio da URL final (exceções limitadas, com domínio no texto); sem pontuação/símbolo só para chamar atenção (ex.: exclamação, ►); texto do link deve indicar com precisão o que há no destino.

**Citação:** “Sitelink URLs that don’t match the domain of the ad’s final URL”

**Exige (A):**
- Todos os sitelinks para creditoup.com.br.
- Texto do sitelink descreve a página de destino.
- Sem '!' e sem símbolos decorativos.

**Só sugere risco (B):**
- Link para senac.br via sitelink é exceção não prevista para este caso (exemplos oficiais: varejistas, redes sociais).

**Caso Senac:**
- Viola: Sitelink: Portal do Senac — apontando para senac.br
- Viola: Sitelink: Inscreva-se Já!
- Não viola: Sitelink: Requisitos e Caminhos — /rec/por-onde-comecar-senac-pr/, APPROVED em 30/09

**Consequência:** Reprovação do asset; aviso ≥7 dias antes de suspensão.

**Confiança:** alta

**Fontes adicionais:**
- Sitelinks — relevância — “link text should clearly and accurately indicate what kind of product, service, or other content is found at the link’s destination” — https://support.google.com/adspolicy/answer/1054210?hl=en
- Sitelinks — repetição — “Using the same link text for more than one sitelink” — https://support.google.com/adspolicy/answer/1054210?hl=en

### ADS-FMT-02 · Callout asset requirements (pt-BR: Requisitos do recurso de frase de destaque)

**Fonte:** https://support.google.com/adspolicy/answer/6084196?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Callouts: sem pontuação/símbolos só para chamar atenção; o texto não pode se repetir dentro do callout nem em outros callouts, no texto do anúncio ou em sitelinks do mesmo grupo, campanha ou conta.

**Citação:** “the text can’t repeat within a callout or from other callouts, ad text, or sitelink text within the same ad group, campaign, or account”

**Exige (A):**
- Callout não repete título/descrição/sitelink (exemplo oficial: 'Free shipping' repetido).

**Só sugere risco (B):**
- Sobreposição parcial de palavras é zona cinzenta; hoje 'Guia Independente' convive com 'Guia Editorial Independente' e está APPROVED.

**Caso Senac:**
- Viola: Callout: Conheça as Modalidades — igual a um título
- Viola: Callout: Grátis!
- Não viola: Callout: Conteúdo Informativo — APPROVED em 30/09

**Consequência:** Reprovação do asset; aviso ≥7 dias antes de suspensão.

**Confiança:** alta

### ADS-FMT-03 · Structured snippet requirements (pt-BR: Requisitos para snippets estruturados)

**Fonte:** https://support.google.com/adspolicy/answer/6283300?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Snippets: sem pontuação para chamar atenção; valores não se repetem; um item por valor; sem texto promocional; o valor precisa corresponder ao cabeçalho. No cabeçalho 'Cursos', só aulas específicas que provedores educacionais oferecem; em 'Serviços', só serviços prestados mediante pagamento.

**Citação:** “Values that do not list specific classes educational providers offer, or that promote entire degree programs”

**Exige (A):**
- Não usar o cabeçalho 'Cursos' listando cursos do Senac: o Crédito Up não é provedor educacional.
- Não usar 'Grátis' como valor (texto promocional).

**Só sugere risco (B):**
- Cabeçalho 'Tipos' com tipos de guia (ex.: 'Guia de requisitos') parece compatível com 'variações de uma categoria de produto', mas não foi verificado em revisão.

**Caso Senac:**
- Viola: Snippet: Cursos: Manicure, Operador de Caixa, Libras
- Viola: Snippet: Tipos: Grátis, Online, Presencial
- Não viola: Snippet: Tipos: Guia de Requisitos, Guia por Estado, Guia de Inscrição — provável, não verificado

**Consequência:** Reprovação do asset.

**Confiança:** alta · **Observações:** A campanha não tem snippet hoje (baseline). O cabeçalho pt-BR 'Cursos' existe na lista oficial da API, o que não o torna adequado a um publicador.

**Fontes adicionais:**
- Snippets — promocional — “Promotional text in snippet values” — https://support.google.com/adspolicy/answer/6283300?hl=en
- Snippets — Serviços — “Values that are not specific offerings of a service provider, meaning services performed in exchange for money” — https://support.google.com/adspolicy/answer/6283300?hl=en

### ADS-REV-01 · About the ad review process

**Fonte:** https://support.google.com/adspolicy/answer/1722120?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: api)

**Regra (paráfrase):** Toda criação ou edição de anúncio/asset inicia revisão automática (texto, palavras-chave, destino). Mudanças reiniciam a revisão; a maioria termina em um dia útil. Anúncios pausados também são revisados.

**Citação:** “After you create or edit an ad or asset, the review process begins automatically.”

**Exige (A):**
- Tratar toda edição do RSA 825455438614 como nova revisão (inclusive do destino).

**Só sugere risco (B):**
- Aprovação atual não se transfere: um texto novo pode ser reprovado mesmo parecido com o anterior.

**Caso Senac:**
- Viola: Não se aplica (processo).
- Não viola: Não se aplica (processo).

**Consequência:** n/a

**Confiança:** alta · **Observações:** Ver API-01 para o que acontece com ID e estatísticas numa edição via API.

**Fontes adicionais:**
- Review — reinício — “Changes to your ad or assets restart the review process and may cause delays.” — https://support.google.com/adspolicy/answer/1722120?hl=en

### ADS-PERS-01 · Restricted targeting in Personalized advertising — negative financial status / imposing negativity

**Fonte:** https://support.google.com/adspolicy/answer/16700443?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Categorias sensíveis (ex.: situação financeira negativa — inclui serviços assistenciais e de desemprego; 'imposing negativity' — sugerir resultados negativos se o usuário não agir) não podem usar públicos definidos pelo anunciante (customer match, remarketing, lookalike etc.); públicos predefinidos do Google podem.

**Citação:** “Content related to negative financial status is a sensitive interest category”

**Exige (A):**
- Só relevante se a campanha usar públicos do anunciante; a campanha 24278665189 não tem critério de público (baseline: idioma, local, dispositivos).

**Só sugere risco (B):**
- Copy centrada em 'baixa renda'/'desemprego' + remarketing restringiria a segmentação.

**Caso Senac:**
- Viola: Remarketing com o anúncio 'Desempregado? Estude de graça'.
- Não viola: Campanha por palavra-chave, sem público do anunciante (situação atual).

**Consequência:** Anúncio não veicula para públicos do anunciante na categoria.

**Confiança:** media · **Observações:** A operação cita estes IDs em volc_ads/copy/PROMPT.md:290-292 para vetar menção à situação financeira do leitor — o texto oficial trata de segmentação, não de redação.

**Fontes adicionais:**
- Imposing negativity in personalized advertising — “Suggesting negative outcomes for users if they don’t take specific actions” — https://support.google.com/adspolicy/answer/16700847?hl=en

## Regras — Landing page (destino do anúncio)

### ADS-DST-00 · Destination requirements — funcionamento, rastreabilidade e acesso

**Fonte:** https://support.google.com/adspolicy/answer/6368661?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** O destino precisa funcionar em navegadores/dispositivos comuns, ser rastreável pelo AdsBot e acessível na região segmentada. Subpolíticas: not working, mismatch, not crawlable, not accessible, experience, insufficient original content, URL inaceitável etc.

**Citação:** “Destinations that return an HTTP error code for Google AdsBot web crawlers on common devices globally.”

**Exige (A):**
- LP e internas respondendo 200 ao AdsBot (desktop e mobile) no Brasil.
- Nada de bloqueio de AdsBot por plugin de segurança/cache ou robots.

**Só sugere risco (B):**
- WP Rocket, Ad Inserter e 'join ads loader' ativos (baseline) — não verificado se algum altera resposta ao AdsBot.

**Caso Senac:**
- Viola: LP retornando 403/5xx para o AdsBot por regra de firewall.
- Não viola: LP /r/guia-cursos-senac/ com 200 para AdsBot mobile e desktop.

**Consequência:** Reprovação do anúncio; aviso ≥7 dias antes de suspensão.

**Confiança:** alta · **Observações:** Página oferece guia para simular o user agent do AdsBot no Chrome DevTools (answer/16431325).

**Fontes adicionais:**
- Destination not working — “Destinations that don't function properly or have been set up incorrectly.” — https://support.google.com/adspolicy/answer/16428019?hl=en

### ADS-DST-01 · Destination mismatch (pt-BR: Destino não correspondente)

**Fonte:** https://support.google.com/adspolicy/answer/16428020?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** URL de exibição, final e mobile precisam ser do mesmo domínio; redirecionar a URL final para outro domínio é proibido (salvo exceção pré-aprovada); tracking template/URL expandida deve levar ao mesmo conteúdo da URL final.

**Citação:** “Redirects from the final URL take the user to a different domain”

**Exige (A):**
- /r/guia-cursos-senac/ não pode redirecionar para senac.br.
- O final_url_suffix com UTMs e vc_* não pode mudar o conteúdo servido.

**Só sugere risco (B):**
- Parâmetros de rastreamento na URL final podem causar mismatch; a página recomenda {ignore} antes do parâmetro.

**Caso Senac:**
- Viola: URL final que faz 302 para https://www.senac.br/
- Não viola: URL final no creditoup.com.br com sufixo de UTMs/vc_* que não altera o conteúdo.

**Consequência:** Reprovação; aviso ≥7 dias antes de suspensão.

**Confiança:** alta · **Observações:** Atualização de jun/2026: redirecionamento para outro domínio só com aprovação prévia (CHG-04).

**Fontes adicionais:**
- Destination mismatch — tracking — “The tracking template or expanded URL doesn't lead to the same content as the final URL” — https://support.google.com/adspolicy/answer/16428020?hl=en
- Destination mismatch — {ignore} — “you should add {ignore} before the tracking parameter in your final URL” — https://support.google.com/adspolicy/answer/16428020?hl=en

### ADS-DST-02 · Destination experience (pt-BR: Experiência de destino)

**Fonte:** https://support.google.com/adspolicy/answer/16427615?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Destino fácil de navegar e seguro. Interstitials são permitidos se não dificultam sair do site; proíbe pop-ups/interstitials que impedem ver o conteúdo pedido, interferência no botão Voltar, experiências abusivas (links de navegação que levam a anúncio, redirecionamento automático) e experiências fora dos Better Ads Standards.

**Citação:** “Google Ads allows interstitials if they don't make it difficult for a user to leave a site.”

**Exige (A):**
- Conteúdo da LP visível ao chegar do anúncio; nada de interstitial que bloqueie o conteúdo pedido.
- Botão Voltar funcionando; nenhum elemento de navegação ('Próximo', 'Ver requisitos') levando a anúncio.
- Conformidade com Better Ads Standards (ex.: sem prestitial com contagem regressiva, sem sticky grande).

**Só sugere risco (B):**
- Interstitial disparado no clique em link interno é o formato oficial do GAM/AdSense; o risco é a frequência e o bloqueio — cadência não verificada nesta etapa.
- Cloaking: pop-up/interstitial que impede o Google de acessar a maior parte do conteúdo é 'Circumventing systems' (egregious) — ver ADS-ABU-02.

**Caso Senac:**
- Viola: Vinheta disparada assim que o visitante chega do anúncio, antes de ver a LP.
- Viola: Botão 'Ver requisitos' que abre um anúncio em vez da página interna.
- Não viola: Vinheta do formato Google entre páginas, fechável, com frequência padrão (1 a cada 10 min no GAM), com a LP legível ao chegar.

**Consequência:** Reprovação; aviso ≥7 dias antes de suspensão.

**Confiança:** alta · **Observações:** Os exemplos de 'abusive experiences' coincidem com os do Publisher Policies (PUB-08).

**Fontes adicionais:**
- Destination experience — interstitials — “Websites with pop-ups or interstitials that interfere with the user's ability to see the content requested” — https://support.google.com/adspolicy/answer/16427615?hl=en
- Destination experience — navegação enganosa — “Page features such as scroll bars, play buttons, “next” arrows, close buttons, or navigation links that lead to an ad or landing page when clicked.” — https://support.google.com/adspolicy/answer/16427615?hl=en

### ADS-DST-03 · Insufficient original content (pt-BR: Conteúdo original insuficiente)

**Fonte:** https://support.google.com/adspolicy/answer/16427718?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** O destino precisa oferecer valor único: proíbe conteúdo feito com o propósito principal de exibir anúncios (inclui tráfego via 'arbitragem' para páginas com mais anúncios que conteúdo, pouco conteúdo ou anúncios excessivos), conteúdo replicado sem valor, páginas-ponte/doorways cuja única função é mandar para outro site, páginas 'em construção' ou incompreensíveis.

**Citação:** “Driving traffic through "arbitrage" or other methods to destinations with more ads than original content, little or no original content, or excessive advertising”

**Exige (A):**
- LP com conteúdo original que responda à dúvida por si (requisitos, como achar a oferta, o que fazer depois).
- Anúncios em quantidade menor que o conteúdo; nada de LP que é só um menu de botões para as internas.
- Nada de reproduzir o texto de senac.br sem acréscimo.

**Só sugere risco (B):**
- A LP 2306 termina com 'Escolha o guia que responde à sua dúvida agora' e distribui o leitor por 4 internas — aceitável enquanto a LP entregar resposta própria; a proporção anúncio/conteúdo não foi medida nesta etapa.

**Caso Senac:**
- Viola: LP com dois parágrafos, quatro botões para internas e blocos de anúncio entre eles.
- Viola: Interna que só repete o texto do portal do Senac com sinônimos.
- Não viola: LP que explica o PSG (renda per capita, fonte senac.br), como localizar a oferta regional e o que conferir na turma, com anúncios discretos.

**Consequência:** Reprovação; aviso ≥7 dias antes de suspensão.

**Confiança:** alta · **Observações:** É o texto oficial que nomeia explicitamente a 'arbitragem' — o modelo de negócio da operação. Não proíbe arbitragem em si; proíbe o destino de baixo valor/anúncio excessivo.

**Fontes adicionais:**
- Insufficient original content — páginas-ponte — “Bridge pages, doorways, gateways, or other intermediate pages that are only used to link to other sites” — https://support.google.com/adspolicy/answer/16427718?hl=en
- Insufficient original content — como corrigir — “Don’t overload the destination with ads, regardless of how relevant the ads are to your ad text.” — https://support.google.com/adspolicy/answer/16427718?hl=en

## Regras — Google Ads API (v25)

### API-00 · Versões da Google Ads API (v25 em uso pelo código)

**Fonte:** https://developers.google.com/google-ads/api/docs/sunset-dates — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Tabela oficial: v25 lançada em 22/07/2026, sunset em ago/2027; v25.1 (19/08/2026) e v25.2 (23/09/2026) são as mais recentes; v26 prevista para out/2026. Versões são desligadas ~1 ano após o lançamento.

**Citação:** “We aim to sunset a version 1 year after its release.”

**Exige (A):**
- v25 válida até ago/2027 (tentativo).

**Só sugere risco (B):**
- As referências de campo abaixo foram lidas na v25; mudanças da v25.1/25.2 não foram revisadas campo a campo.

**Caso Senac:**
- Viola: n/a
- Não viola: n/a

**Consequência:** n/a

**Confiança:** alta

### API-01 · Atualizar RSA in-place (AdService.MutateAds) × criar anúncio novo

**Fonte:** https://developers.google.com/google-ads/api/docs/ads/ad-types — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Tipos mutáveis podem ser alterados via AdService sem perder dados de desempenho; ResponsiveSearchAd é 'Mutable' na tabela oficial. No RSA atualizam-se headlines, descriptions e pins com field mask (a amostra oficial também altera final_urls). O update exige o resource name existente (customers/{customer_id}/ads/{ad_id}), que é Immutable. Tipos não mutáveis precisam ser removidos e recriados; os dados do removido continuam visíveis, mas não são mais atualizados. Status (pausar/remover) é pelo AdGroupAdService.

**Citação:** “You can mutate your ads without losing their performance data by using AdService.”

**Exige (A):**
- Update in-place do RSA 825455438614 via AdService.MutateAds com update_mask.
- ID: preservado — inferência forte (o update endereça o resource name imutável do mesmo ad_id); não há frase literal 'o ID não muda'.
- Estatísticas: preservadas (literal acima).
- Revisão: toda edição reinicia a revisão de política (ADS-REV-01).

**Só sugere risco (B):**
- Se a versão anterior continua servindo durante a revisão da edição: NÃO VERIFICADO. A Ajuda diz que a nova versão passa pela aprovação antes de rodar e recomenda criar anúncio novo quando se quer manter o original rodando.
- path1/path2 não aparecem no guia de update; o campo não é marcado Immutable na referência — atualização provável, não testada.

**Caso Senac:**
- Viola: n/a
- Não viola: Trocar títulos/descrições do RSA 825455438614 por update mantém ID e histórico; criar RSA novo em paralelo mantém o atual servindo enquanto o novo é revisado.

**Consequência:** n/a

**Confiança:** alta · **Observações:** Fontes: tabela 'Ad type compatibility' (ResponsiveSearchAd: Search = sim, Display = não, Mutable = sim, Shareable = sim); guia Mutate ads; referência Ad/AdOperation v25; Ajuda 'About version history' e 'Edit your text ads'.

**Fontes adicionais:**
- Mutate ads — campos do RSA — “For Responsive Search Ads (RSAs), you can update headlines, descriptions, and pinned assets using a field mask to indicate which fields to alter.” — https://developers.google.com/google-ads/api/docs/ads/mutate-ads
- Ad types — não mutáveis — “If an ad type is not mutable, it must be removed and recreated to affect changes.” — https://developers.google.com/google-ads/api/docs/ads/ad-types
- Ad.resource_name (v25) — “Immutable. The resource name of the ad.” — https://developers.google.com/google-ads/api/reference/rpc/v25/Ad
- About version history — “Before your new ads start running, they’ll go through the ad approval process, which can take up to one business day.” — https://support.google.com/google-ads/answer/7502216?hl=en

### API-02 · Limites do RSA: títulos, descrições, paths

**Fonte:** https://support.google.com/google-ads/answer/7684791?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: search_ads)

**Regra (paráfrase):** RSA: 3 a 15 títulos de até 30 caracteres; 2 a 4 descrições de até 90; path1/path2 até 15 cada; path2 só com path1. Caracteres de largura dupla contam 2. Assets podem aparecer em qualquer ordem e cada um precisa fazer sentido sozinho; títulos não usados podem servir como links (tipo sitelink) e títulos podem aparecer no início da descrição.

**Citação:** “The headline fields for responsive search ads support up to 30 characters. The description fields support up to 90 characters each”

**Exige (A):**
- Cada título ≤30, cada descrição ≤90, path ≤15; 3–15 títulos, 2–4 descrições.
- Cada asset precisa ser correto e não enganoso isoladamente e em qualquer combinação.

**Só sugere risco (B):**
- 'Enhanced flexibility': um título solto pode aparecer como link ou no início da descrição — ressalvas como 'Guia Independente' não ficam garantidas ao lado de 'Cursos Senac' sem fixação.

**Caso Senac:**
- Viola: Título: Cursos Senac Gratuitos em Todo o Brasil — 41 caracteres, excede 30
- Não viola: Título: Cursos Senac por Estado
- Não viola: Path: cursos-senac — 12 caracteres

**Consequência:** Erro de validação/API.

**Confiança:** alta · **Observações:** O código já registra 30/90 e 3–15/2–4 em volc_ads/campanha/limites.yaml:5-6. Estado atual: 8 títulos, 4 descrições, sem path, sem pins.

**Fontes adicionais:**
- RSA — mínimo/máximo de títulos — “You’ll need to enter a minimum of 3 headlines, but you can enter up to 15.” — https://support.google.com/google-ads/answer/7684791?hl=en
- RSA — mínimo/máximo de descrições — “You’ll need to enter a minimum of 2 descriptions, but you can enter up to 4.” — https://support.google.com/google-ads/answer/7684791?hl=en
- RSA — paths — “the path fields support up to 15 each” — https://support.google.com/google-ads/answer/7684791?hl=en
- ResponsiveSearchAdInfo.path2 (v25) — “This field can only be set when path1 is also set.” — https://developers.google.com/google-ads/api/reference/rpc/v25/ResponsiveSearchAdInfo
- RSA — combinações — “Assets can be shown in any order, so make sure they make sense individually or in combinations, and don't violate our policies or local law.” — https://support.google.com/google-ads/answer/7684791?hl=en

### API-03 · Pins (fixação) no RSA

**Fonte:** https://support.google.com/google-ads/answer/7684791?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: search_ads)

**Regra (paráfrase):** Texto que deve aparecer em todo anúncio (ex.: ressalva) precisa ser fixado em Título 1, Título 2 ou Descrição 1; posições Título 3 e Descrição 2 não são garantidas. Vários assets podem ser fixados na mesma posição (rotacionam); asset não fixado não serve em posição que tenha fixados. Fixar não é recomendado para a maioria e pode afetar o Ad Strength.

**Citação:** “you must pin it to either Headline position 1, Headline position 2, or Description position 1”

**Exige (A):**
- Se a ressalva 'guia independente / sem vínculo' precisar aparecer SEMPRE, fixar em T1, T2 ou D1.

**Só sugere risco (B):**
- Fixar reduz combinações e pode baixar o Ad Strength — que não afeta elegibilidade (ver NE-11).

**Caso Senac:**
- Viola: Contar com 'Guia Editorial Independente' não fixado para esclarecer a natureza do site em todo anúncio.
- Não viola: Descrição 1 fixada: Guia editorial independente sobre cursos Senac. Entenda requisitos e ofertas por estado.

**Consequência:** n/a

**Confiança:** alta · **Observações:** Pinned field na API: AdTextAsset.pinned_field (ServedAssetFieldType).

**Fontes adicionais:**
- AdTextAsset.pinned_field (v25) — “An asset that is unpinned or pinned to a different field will not serve in a field where some other asset has been pinned.” — https://developers.google.com/google-ads/api/reference/rpc/v25/AdTextAsset
- RSA — custo da fixação — “pinning isn't recommended for most advertisers and can affect ad strength” — https://support.google.com/google-ads/answer/7684791?hl=en
- RSA — títulos como links — “Up to 2 unused responsive search ad headlines within the same ad can serve as link-based assets” — https://support.google.com/google-ads/answer/7684791?hl=en

### API-04 · SitelinkAsset (v25): link_text, description1/2

**Fonte:** https://developers.google.com/google-ads/api/reference/rpc/v25/SitelinkAsset — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** link_text obrigatório, 1–25 caracteres; description1 e description2 opcionais, 1–35 cada, e uma exige a outra. São necessários pelo menos 2 sitelinks para aparecerem; até 6 no desktop e 8 no mobile.

**Citação:** “Required. URL display text for the sitelink. The length of this string should be between 1 and 25, inclusive.”

**Exige (A):**
- link_text ≤25; descrições ≤35 e em par.

**Só sugere risco (B):**
- (nenhum)

**Caso Senac:**
- Viola: Sitelink: Requisitos do Programa Senac de Gratuidade — 46 caracteres
- Não viola: Sitelink: Requisitos da Gratuidade

**Consequência:** Erro de validação/API.

**Confiança:** alta · **Observações:** Sugestão da plataforma em 30/09: +2 sitelinks (baseline).

**Fontes adicionais:**
- SitelinkAsset.description1 — “If set, the length should be between 1 and 35, inclusive, and description2 must also be set.” — https://developers.google.com/google-ads/api/reference/rpc/v25/SitelinkAsset
- About sitelink assets — “You need at least 2 sitelinks (for desktop), and at least 2 sitelinks (for mobile) for the sitelinks to appear in the ad.” — https://support.google.com/google-ads/answer/2375416?hl=en

### API-05 · CalloutAsset (v25)

**Fonte:** https://developers.google.com/google-ads/api/reference/rpc/v25/CalloutAsset — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** callout_text obrigatório, 1–25 caracteres; até 10 callouts podem aparecer conforme espaço.

**Citação:** “Required. The callout text. The length of this string should be between 1 and 25, inclusive.”

**Exige (A):**
- callout ≤25.

**Só sugere risco (B):**
- (nenhum)

**Caso Senac:**
- Viola: Callout: Conteúdo Independente e Gratuito — 36 caracteres
- Não viola: Callout: Conteúdo Informativo

**Consequência:** Erro de validação/API.

**Confiança:** alta

### API-06 · StructuredSnippetAsset (v25)

**Fonte:** https://developers.google.com/google-ads/api/reference/rpc/v25/StructuredSnippetAsset — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** header obrigatório e restrito à lista predefinida (pt-BR inclui Marcas, Comodidades, Estilos, Tipos, Destinos, Serviços, Cursos, Bairros, Programas, Cobertura do seguro, Programas de graduação, Hotéis em destaque, Modelos); 3–10 valores de 1–25 caracteres.

**Citação:** “The size of this collection should be between 3 and 10, inclusive. The length of each value should be between 1 and 25 characters, inclusive.”

**Exige (A):**
- 3–10 valores ≤25; header da lista oficial.

**Só sugere risco (B):**
- Lista de headers: https://developers.google.com/google-ads/api/data/structured-snippet-headers (a URL /reference/data/... redireciona para ela).

**Caso Senac:**
- Viola: Snippet com 2 valores.
- Não viola: Snippet com 3 valores de até 25 caracteres, compatíveis com o header (ver ADS-FMT-03).

**Consequência:** Erro de validação/API.

**Confiança:** alta

### API-07 · validate_only (MutateAdsRequest e demais mutates)

**Fonte:** https://developers.google.com/google-ads/api/reference/rpc/v25/MutateAdsRequest — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Com validate_only=true a requisição é validada como se fosse executada, mas nada é gravado; só erros voltam. Útil para pegar violações comuns (palavras, pontuação, capitalização, tamanho) detectadas na requisição. Não substitui a revisão pós-envio, que avalia também o destino.

**Citação:** “If true, the request is validated but not executed. Only errors are returned, not results.”

**Exige (A):**
- Usar validate_only antes de qualquer mutate real (o repo já faz: volc_ads/campanha/validacao.py:1-9).

**Só sugere risco (B):**
- validate_only verde ≠ anúncio aprovado: destino, misrepresentation, marca e limitações surgem na revisão.

**Caso Senac:**
- Viola: n/a
- Não viola: n/a

**Consequência:** n/a

**Confiança:** alta

**Fontes adicionais:**
- API Structure — validate_only — “validate_only is particularly useful in testing ads for common policy violations.” — https://developers.google.com/google-ads/api/docs/concepts/api-structure
- API Structure — rejeição automática — “Ads are automatically rejected if they violate policies such as having specific words, punctuation, capitalization, or length.” — https://developers.google.com/google-ads/api/docs/concepts/api-structure

### API-08 · Isenção de política: PolicyViolationKey, exempt_policy_violation_keys, ignorable_policy_topics

**Fonte:** https://developers.google.com/google-ads/api/reference/rpc/v25/PolicyValidationParameter — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Keywords: PolicyViolationError traz PolicyViolationDetails.is_exemptible e a PolicyViolationKey (policy_name + violating_text); a isenção vai em exempt_policy_violation_keys (na AdGroupCriterionOperation). Anúncios: PolicyFindingError traz PolicyTopicEntry; a isenção vai em ignorable_policy_topics (PolicyValidationParameter). Os dois campos são mutuamente exclusivos. Nem toda violação é isentável. O recurso isento é salvo, mas fica inelegível até re-revisão, mudança de política ou de certificados.

**Citação:** “Resources that violate these policies will be saved, but will not be eligible to serve.”

**Exige (A):**
- Isenção = pedido de revisão, não aprovação.
- Só isentar o que vier marcado como isentável (keywords) / tópicos devolvidos no erro (ads).

**Só sugere risco (B):**
- Usar isenção para empurrar copy que imita afiliação com o Senac pode ser lido como contorno de sistemas (egregious) — interpretação.

**Caso Senac:**
- Viola: Pedir isenção para 'Senac Oficial: Inscreva-se' após reprovação.
- Não viola: Pedir isenção de um tópico de pontuação num termo legítimo, após revisão humana.

**Consequência:** n/a

**Confiança:** alta · **Observações:** O repo já documenta isso corretamente em volc_ads/isencao.py:1-50 ('Isento não é aprovado').

**Fontes adicionais:**
- exempt_policy_violation_keys — “This field is used for keyword policy exemptions.” — https://developers.google.com/google-ads/api/reference/rpc/v25/PolicyValidationParameter
- ignorable_policy_topics — “This field is used for ad policy exemptions.” — https://developers.google.com/google-ads/api/reference/rpc/v25/PolicyValidationParameter
- AdGroupCriterionOperation — “Not all policy violations are exemptable” — https://developers.google.com/google-ads/api/reference/rpc/v25/AdGroupCriterionOperation
- PolicyViolationDetails.is_exemptible — “Whether user can file an exemption request for this violation.” — https://developers.google.com/google-ads/api/reference/rpc/v25/PolicyViolationDetails
- PolicyViolationKey.violating_text — “Must be specified for ad exemptions.” — https://developers.google.com/google-ads/api/reference/rpc/v25/PolicyViolationKey
- PolicyFindingError.POLICY_FINDING — “The resource has been disapproved since the policy summary includes policy topics of type PROHIBITED.” — https://developers.google.com/google-ads/api/reference/rpc/v25/PolicyFindingErrorEnum.PolicyFindingError

## Regras — Monetização (publisher: AdSense, Ad Manager, Publisher Policies)

### PUB-01 · Google Publisher Policies — Misleading representation

**Fonte:** https://support.google.com/publisherpolicies/answer/11185754?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Não monetizar conteúdo que deturpe, omita ou esconda informação sobre o publisher, o autor, o propósito ou o próprio conteúdo, nem que implique falsamente afiliação/endosso de terceiro.

**Citação:** “falsely implies having an affiliation with, or endorsement by, another individual, organization, product, or service.”

**Exige (A):**
- Páginas do funil sem aparência de site do Senac; propósito editorial explícito.

**Só sugere risco (B):**
- Mau uso de logotipo de terceiros é exemplo oficial.

**Caso Senac:**
- Viola: Interna com o logotipo do Senac como cabeçalho e título 'Portal Senac'.
- Não viola: Aviso 'Portal editorial independente ... sem vínculo com as instituições citadas' no topo (presente em 30/09).

**Consequência:** Bloqueio de anúncios na página/site ou suspensão da conta de publisher.

**Confiança:** alta

**Fontes adicionais:**
- Misleading representation — propósito — “misrepresents, misstates, or conceals information about the publisher, the content creator, the purpose of the content, or the content itself.” — https://support.google.com/publisherpolicies/answer/11185754?hl=en

### PUB-02 · Google Publisher Policies — Deceptive practices

**Fonte:** https://support.google.com/publisherpolicies/answer/11185755?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Proíbe atrair o usuário para interagir com conteúdo sob pretextos falsos ou pouco claros, phishing e alegações falsas/desonestas.

**Citação:** “enticing users to engage with content under false or unclear pretenses.”

**Exige (A):**
- Rótulo de botão/link interno promete exatamente o que a página seguinte entrega.

**Só sugere risco (B):**
- Botão 'Ver lista de cursos gratuitos' que leva a página sem lista — pretexto falso para mais uma pageview (e mais uma vinheta).

**Caso Senac:**
- Viola: Botão 'Ver cursos com vagas abertas' levando a texto genérico.
- Não viola: Botão 'Encontrar oferta no estado' levando à interna que ensina onde consultar a oferta regional.

**Consequência:** Bloqueio de anúncios ou suspensão.

**Confiança:** alta

### PUB-03 · Google Publisher Policies — Ads interfering (conteúdo e interação)

**Fonte:** https://support.google.com/publisherpolicies/answer/11035030?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Proíbe anúncios sobrepostos ou adjacentes a itens de navegação/ação que causem interação não intencional, anúncios que atrapalham gravemente o consumo do conteúdo e anúncios em telas 'sem saída'.

**Citação:** “overlay or are adjacent to navigational or other action items and may lead to unintended ad interactions,”

**Exige (A):**
- Nenhum bloco de anúncio colado aos botões 'Escolher um curso', 'Ver requisitos', 'Encontrar oferta no estado'.

**Só sugere risco (B):**
- Mesmo sem intenção, layout que gera clique acidental pode gerar notificação (AdSense).

**Caso Senac:**
- Viola: Bloco de anúncio entre dois botões de navegação da LP.
- Não viola: Botões agrupados, com espaçamento e separação visual clara do bloco rotulado 'Publicidade'.

**Consequência:** Bloqueio de anúncios ou suspensão.

**Confiança:** alta

**Fontes adicionais:**
- Ads interfering — dica oficial — “Be careful when placing links, play buttons, download buttons, navigation buttons (e.g., “Previous" or “Next"), game windows, video players, drop-down menus, or applications near ads” — https://support.google.com/publisherpolicies/answer/11035030?hl=en

### PUB-04 · Google Publisher Policies — Inventory value: telas sem conteúdo do publisher / baixo valor

**Fonte:** https://support.google.com/publisherpolicies/answer/11112688?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Proíbe anúncios em telas sem conteúdo do publisher ou com conteúdo de baixo valor, em construção, ou usadas para alertas, navegação ou outros fins comportamentais; orienta não pôr anúncios em conteúdo gerado automaticamente sem revisão/curadoria manual.

**Citação:** “that are used for alerts, navigation or other behavioral purposes”

**Exige (A):**
- LP e internas precisam ser páginas de conteúdo, não 'hub' de navegação com anúncios.
- Conteúdo gerado pelo motor (FunnelForge) precisa de revisão/curadoria humana antes de receber anúncios.

**Só sugere risco (B):**
- LP cuja função principal é distribuir o leitor para as internas se aproxima de 'screen used for navigation'.

**Caso Senac:**
- Viola: Página 'Escolha seu guia' só com botões + anúncios.
- Não viola: LP que responde à dúvida e oferece as internas como aprofundamento opcional.

**Consequência:** Limitação/desativação de anúncios na página.

**Confiança:** alta

**Fontes adicionais:**
- Inventory value — conteúdo automático — “Don’t place ads on automatically generated content without manual review or curation.” — https://support.google.com/publisherpolicies/answer/11112688?hl=en

### PUB-05 · Google Publisher Policies — Mais anúncios que conteúdo do publisher

**Fonte:** https://support.google.com/publisherpolicies/answer/11169917?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Proíbe anúncios em telas com mais anúncios/material pago do que conteúdo do publisher. Conteúdo do publisher NÃO inclui espaço em branco, cabeçalho, rodapé nem links para outros conteúdos do site.

**Citação:** “it does not include whitespace, header or footer content, or links to other content on the site.”

**Exige (A):**
- Na conta de proporção, botões/links para as internas e o bloco 'Notícias Relacionadas' não contam como conteúdo.

**Só sugere risco (B):**
- Proporção real das páginas 2306–2318 não medida nesta etapa (15 ocorrências de 'adsbygoogle' e 16–22 de 'joinads' no HTML salvo não equivalem a 15 blocos visíveis).

**Caso Senac:**
- Viola: LP com 3 blocos de anúncio para 4 parágrafos curtos + 4 botões.
- Não viola: Texto próprio claramente maior que a área de anúncios em mobile.

**Consequência:** Limitação/desativação de anúncios.

**Confiança:** alta · **Observações:** Ad Manager Open Auction tem regra equivalente (PUB-16).

**Fontes adicionais:**
- More ads than content — regra — “with more ads or other paid promotional material than publisher-content.” — https://support.google.com/publisherpolicies/answer/11169917?hl=en

### PUB-06 · Google Publisher Policies — Conteúdo replicado

**Fonte:** https://support.google.com/publisherpolicies/answer/11190248?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Proíbe anúncios em telas com conteúdo copiado/incorporado sem comentário, curadoria ou valor; inclui reescrita com sinônimos ou técnicas automatizadas e conteúdo gerado automaticamente sem revisão.

**Citação:** “Sites that copy content from other sites, modify it slightly (for example, by substituting synonyms or using automated techniques), and republish it”

**Exige (A):**
- Guias do Senac não podem ser paráfrase automatizada das páginas do senac.br.

**Só sugere risco (B):**
- Motor com LLM reescrevendo fontes oficiais é exatamente o padrão descrito se não houver acréscimo (comparação, checklist, diferenças regionais, fontes).

**Caso Senac:**
- Viola: Interna que reescreve a página do PSG do Senac com sinônimos.
- Não viola: Interna que compara regras de SP e AC com links para cada regional e checklist próprio (como a 2309 faz em parte).

**Consequência:** Limitação/desativação de anúncios.

**Confiança:** alta

**Fontes adicionais:**
- Replicated content — automático — “Automatically generated content without manual review or curation;” — https://support.google.com/publisherpolicies/answer/11190248?hl=en

### PUB-07 · Google Publisher Policies — Spam policies for Google web search

**Fonte:** https://support.google.com/publisherpolicies/answer/11035931?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: search_organico)

**Regra (paráfrase):** Publisher não pode pôr anúncios em telas que violem as políticas de spam da Pesquisa; sites violadores podem sair da Pesquisa e ter anúncios desativados.

**Citação:** “place Google-served ads on screens that violate the Spam policies for Google web search.”

**Exige (A):**
- Funil sem doorway/cookie-cutter/keyword stuffing (ver SEO-01/02).

**Só sugere risco (B):**
- O risco de spam orgânico vira risco de monetização e de Ads (ADS-ABU-01).

**Caso Senac:**
- Viola: Gerar dezenas de páginas 'Cursos Senac + cidade' quase iguais.
- Não viola: 5 páginas com funções distintas e conteúdo próprio.

**Consequência:** Desativação de anúncios; exclusão da Pesquisa.

**Confiança:** alta

**Fontes adicionais:**
- Spam — dica oficial — “Don’t create "doorway" pages created just for search engines, or other "cookie cutter" approaches such as affiliate programs with little or no original content.” — https://support.google.com/publisherpolicies/answer/11035931?hl=en

### PUB-08 · Google Publisher Policies — Abusive experiences

**Fonte:** https://support.google.com/publisherpolicies/answer/11128079?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: landing_page)

**Regra (paráfrase):** Proíbe anúncios em telas com experiências abusivas: mensagens falsas, áreas de clique inesperadas, comportamento enganoso (links de navegação/setas/fechar que levam a anúncio), manipulação do histórico (botão Voltar), redirecionamento automático, ponteiro falso, malware.

**Citação:** “Page features such as scroll bars, play buttons, “next” arrows, close buttons, or navigation links that lead to an ad or landing page when clicked.”

**Exige (A):**
- Nenhum 'Próximo >>>' ou link de navegação que leve a anúncio.
- Botão Voltar sem manipulação.

**Só sugere risco (B):**
- CTAs com '>>>' (exemplares aprovados no repo: funnelforge-migracao/engine/src/funnelforge/pipeline/doctrine.py:146-153) só são seguros se levarem a conteúdo, nunca a anúncio.

**Caso Senac:**
- Viola: Seta 'Continuar >>>' que dispara anúncio em vez de abrir a próxima página.
- Não viola: 'Ver requisitos' abre /rec/por-onde-comecar-senac-pr/ (a vinheta do formato Google pode aparecer na transição).

**Consequência:** Bloqueio de anúncios; Abusive Experience Report.

**Confiança:** alta · **Observações:** Conteúdo em iframe/player conta como parte do site.

**Fontes adicionais:**
- Abusive — botão Voltar — “Prevents the normal function of the “Back” button by keeping the user from returning to the previous destination.” — https://support.google.com/publisherpolicies/answer/11128079?hl=en

### PUB-09 · Better Ads Standards (referenciado por Google Ads e Publisher Policies)

**Fonte:** https://support.google.com/publisherpolicies/answer/11127848?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: landing_page)

**Regra (paráfrase):** Publisher não pode pôr anúncios em telas fora dos Better Ads Standards. No mobile web o padrão lista: pop-up, prestitial, densidade de anúncios acima de 30%, animação piscante, vídeo com som automático, postitial com contagem regressiva, scrollover em tela cheia, sticky grande, vídeo sticky pop-out, vídeo sticky com anúncio inline grande.

**Citação:** “place Google-served ads on screens that do not conform to the Better Ads Standards.”

**Exige (A):**
- Mobile: densidade de anúncios ≤30% da página; sem prestitial; sem sticky grande.

**Só sugere risco (B):**
- Densidade real das páginas do funil não medida nesta etapa; 93% das impressões e 96% dos cliques da campanha foram em mobile (google-ads/daily_network_device.json, 21–30/09).

**Caso Senac:**
- Viola: Página mobile com anúncios ocupando mais de 30% da altura rolável.
- Não viola: Poucos blocos entre seções longas de texto.

**Consequência:** Desativação de anúncios; reprovação de destino no Google Ads (ADS-DST-02).

**Confiança:** alta · **Observações:** Lista oficial dos padrões: https://www.betterads.org/standards/ (Coalition for Better Ads), consultada em 30/09/2026.

**Fontes adicionais:**
- The Initial Better Ads Standards — Mobile Web — “Ad Density Higher Than 30%” — https://www.betterads.org/standards/

### PUB-10 · AdSense — rótulos de anúncio e incentivo a cliques

**Fonte:** https://support.google.com/adsense/answer/1346295?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Anúncios só podem ser rotulados como 'Advertisements' ou 'Sponsored Links' (pt-BR oficial: 'Publicidade' ou 'Links Patrocinados'; a página pt-BR de políticas do programa cita 'Links Patrocinados' ou 'Anúncios'); proíbe cabeçalhos enganosos ('recursos', 'links úteis') e linguagem que peça cliques ('support us', 'click the ads').

**Citação:** “Publishers may only label Google ads with either "Advertisements" or "Sponsored Links".”

**Exige (A):**
- Rótulo 'Publicidade' (ou 'Anúncios'/'Links Patrocinados'); nunca 'Cursos recomendados', 'Veja também', 'Links úteis' sobre um bloco de anúncio.
- Nenhum 'apoie o site clicando nos anúncios'.

**Só sugere risco (B):**
- Rótulo exibido pelos blocos JoinAds/AdSense não aparece no HTML estático salvo — não verificado.

**Caso Senac:**
- Viola: Bloco de anúncio sob o título 'Outros cursos para você'.
- Não viola: Bloco rotulado 'Publicidade'.

**Consequência:** Desativação de anúncios/conta.

**Confiança:** alta · **Observações:** Em Ad Manager Open Auction, anúncios do Google Ads também seguem as políticas do AdSense (PUB-16).

**Fontes adicionais:**
- Políticas de posição de anúncios (pt-BR) — “Os publishers só podem rotular anúncios do Google como "Publicidade" ou "Links Patrocinados".” — https://support.google.com/adsense/answer/1346295?hl=pt-BR
- AdSense Program policies — incentivo — “Encourage users to click the Google ads using phrases such as "click the ads", "support us", "visit these links" or other similar language.” — https://support.google.com/adsense/answer/48182?hl=en

### PUB-11 · AdSense — navegação enganosa e cliques acidentais

**Fonte:** https://support.google.com/adsense/answer/48182?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: landing_page)

**Regra (paráfrase):** Proíbe implementar anúncios onde possam ser confundidos com menu, navegação ou links de download, e navegação enganosa (links para conteúdo inexistente, redirecionamento para páginas irrelevantes). Layout que gera clique acidental pode gerar violação mesmo sem intenção.

**Citação:** “Pages where ads are implemented in placements that are intuitively meant for navigation.”

**Exige (A):**
- Nenhum anúncio no lugar onde o leitor espera o botão do próximo guia.

**Só sugere risco (B):**
- Formatar anúncio nativo com a mesma aparência dos cards de 'Notícias Relacionadas' = conteúdo indistinguível de anúncio.

**Caso Senac:**
- Viola: Anúncio logo abaixo de 'Qual dúvida você precisa resolver agora?', no espaço dos botões.
- Não viola: Anúncio entre seções de texto, longe dos botões e rotulado.

**Consequência:** Desativação de anúncios/conta.

**Confiança:** alta

**Fontes adicionais:**
- Ad placement — cliques acidentais — “Even if the layout unintentionally leads to accidental clicks, publishers may still receive a violation notification.” — https://support.google.com/adsense/answer/1346295?hl=en
- Deceptive site navigation — conteúdo inexistente — “Linking to content that doesn’t exist” — https://support.google.com/adsense/answer/48182?hl=en

### PUB-12 · AdSense — fontes de tráfego (tráfego pago) e páginas feitas para anúncios

**Fonte:** https://support.google.com/adsense/answer/48182?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Sites com anúncios só podem receber tráfego de publicidade online se cumprirem o espírito das diretrizes de qualidade de landing page do Google (o usuário encontra fácil o que o anúncio promete); anúncios não podem estar em páginas publicadas especificamente para exibir anúncios.

**Citação:** “Receive traffic from online advertising unless the site complies with the spirit of Google's Landing Page Quality Guidelines.”

**Exige (A):**
- O que o anúncio do Google Ads promete precisa estar fácil de achar na LP (mesma exigência de ADS-MIS-06).

**Só sugere risco (B):**
- Arbitragem é compatível com o AdSense só se a página não for 'feita para mostrar anúncios'.

**Caso Senac:**
- Viola: LP que só existe para receber o clique pago e distribuir para páginas com vinheta.
- Não viola: LP útil por si, que também recebe tráfego orgânico.

**Consequência:** Desativação de anúncios/conta.

**Confiança:** alta

**Fontes adicionais:**
- Traffic sources — promessa do anúncio — “For instance, users should easily be able to find what your ad promises.” — https://support.google.com/adsense/answer/48182?hl=en
- Ad placement — páginas para anúncios — “Placed on pages published specifically for the purpose of showing ads.” — https://support.google.com/adsense/answer/48182?hl=en

### PUB-13 · Tráfego inválido / atividade inválida (AdSense e Platforms program policies)

**Fonte:** https://support.google.com/adsense/answer/16737?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Tráfego inválido inclui cliques/impressões que inflam custo do anunciante ou ganho do publisher, intencionais ou acidentais: publisher clicando, cliques repetidos, incentivo a cliques, implementações com muitos cliques acidentais, robôs. Plataformas proíbem gerar impressões/eventos solicitados por pagamento ou falsa representação.

**Citação:** “ad implementations that may cause a high volume of accidental clicks”

**Exige (A):**
- Nenhum texto que peça clique em anúncio ou prometa algo para gerar pageview/impressão.
- Responsabilidade do publisher mesmo quando o tráfego inválido vem de terceiros.

**Só sugere risco (B):**
- Otimizar o Google Ads por 'adViewInterstitial' (impressão visível) não aparece como proibido nas páginas consultadas; o risco está no desenho que força pageviews/impressões por pretexto falso (interpretação).

**Caso Senac:**
- Viola: 'Clique em Continuar para ver os cursos liberados' quando o Continuar só dispara vinheta e a página não traz a lista.
- Não viola: Navegação opcional entre guias que entregam o que o rótulo promete.

**Consequência:** Retenção de ganhos, limitação ou encerramento da conta.

**Confiança:** alta · **Observações:** Baseline: conversões primárias do Google Ads são impressões visíveis (adViewInterstitial, adView) com valor fixo.

**Fontes adicionais:**
- Platforms program policies — prohibited activity — “You must not generate impressions, queries, conversions, and/or ad events solicited by payment of money or false representation from end-users.” — https://support.google.com/platformspolicy/answer/3013851?hl=en

### PUB-14 · Interstitials web (Ad Manager 'Traffic web interstitials') e vinhetas (AdSense)

**Fonte:** https://support.google.com/admanager/answer/9840201?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: landing_page)

**Regra (paráfrase):** Formato oficial de anúncio em tela cheia entre páginas: saída clara, frequência configurável (padrão 1 a cada 10 min, mínimo 1/min), fechamento pelo botão Voltar. Gatilhos: clique em link (âncora); opcionais: voltar à aba, barra de navegação, fim do artigo, inatividade, botão 'Continuar' que expande conteúdo borrado. Links podem ser excluídos com data-google-interstitial="false". AdSense tem o equivalente 'vignette ads'.

**Citação:** “Web interstitials are full-page web ads and are an additional inventory and revenue source.”

**Exige (A):**
- Usar só o formato Google (GPT OutOfPageFormat.INTERSTITIAL ou vinheta do AdSense), nunca overlay próprio.
- Respeitar frequência; permitir fechar.

**Só sugere risco (B):**
- Cada clique entre LP e internas é oportunidade de vinheta: dividir a resposta em várias páginas para multiplicar vinhetas cruza com PUB-02, PUB-04, SEO-02 e ADS-DST-03 (interpretação).
- O gatilho opcional 'Continuar' com conteúdo borrado exige que o conteúdo prometido esteja de fato abaixo.

**Caso Senac:**
- Viola: Frequência de 1/min + páginas curtas encadeadas para gerar vinheta a cada clique.
- Não viola: Frequência padrão e links de rodapé/menu com data-google-interstitial="false".

**Consequência:** n/a (documentação de formato; violações caem nas políticas citadas).

**Confiança:** alta · **Observações:** Página 'Disallowed interstitial implementations' do Ad Manager (answer/6309309) trata de apps (abertura/saída de app, recorrência) — não é norma web, serve só de analogia. Publisher Restrictions proíbe 'Google-served ads that fully or partially obscure content for any period of time' (answer/11127388); a página não explicita como isso convive com o formato oficial — não verificado.

**Fontes adicionais:**
- Web interstitials — exclusão de links — “You can prevent specific links from triggering GPT-managed web interstitials by adding a data-google-interstitial="false" attribute to the anchor element” — https://support.google.com/admanager/answer/9840201?hl=en
- Web interstitials — frequência — “The default frequency cap for web interstitials is 1 impression per 10 minutes.” — https://support.google.com/admanager/answer/9840201?hl=en
- About vignette ads (AdSense) — “Vignette ads are full-screen ads that appear between page loads and can be skipped by users at any time.” — https://support.google.com/adsense/answer/16531962?hl=en
- Publisher Restrictions — ads obscuring content — “fully or partially obscure content for any period of time” — https://support.google.com/publisherpolicies/answer/11127388?hl=en

### PUB-15 · Ad Manager — Policies for ad units that offer rewards (rewarded)

**Fonte:** https://support.google.com/admanager/answer/7496282?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Rewarded exige opt-in afirmativo, divulgação clara da ação e da recompensa, possibilidade de pular/dispensar; pular não pode atrapalhar o uso normal do site; sem texto que induza ('assista para apoiar'); recompensa não pode ser dinheiro.

**Citação:** “must not impede or interfere with the normal usage of the platform, website or app.”

**Exige (A):**
- Se houver rewarded no funil: conteúdo do guia acessível sem assistir ao anúncio.

**Só sugere risco (B):**
- Trancar a resposta do guia atrás de rewarded tende a colidir com 'normal usage' e com PUB-02 — interpretação; não verificado se o funil Senac exibe rewarded (o GTM publicado tem a conversão 'adViewRewarded', disparada em impressão Rewarded — baseline).

**Caso Senac:**
- Viola: 'Assista a um anúncio para liberar a lista de cursos gratuitos' com o texto bloqueado até assistir.
- Não viola: Sem rewarded nas páginas do funil, ou rewarded opcional para um extra (ex.: checklist em PDF) com o guia inteiro aberto.

**Consequência:** Desativação do formato/inventário.

**Confiança:** media

**Fontes adicionais:**
- Rewarded — opt-in — “must only be served after a user affirmatively and unambiguously opts in” — https://support.google.com/admanager/answer/7496282?hl=en

### PUB-16 · Google Ad Manager Partner Guidelines (Open Auction)

**Fonte:** https://support.google.com/admanager/answer/9059370?hl=en&ref_topic=28145&rd=1 — HTTP 200; 1 redirecionamento (topic/28145 → answer/9059370; parâmetro de sessão visit_id omitido do registro); consultado em 30/09/2026

**Regra (paráfrase):** No Open Auction, anúncios não podem ficar sob ou ao lado de botões/objetos a ponto de interferir na interação típica; anúncios e material pago não podem exceder o conteúdo do site; quem exibe demanda do Google Ads também segue as políticas do AdSense; sites com pop-ups que atrapalham a navegação não podem monetizar.

**Citação:** “placed underneath or adjacent to buttons or any other object such that the placement of the ad interferes”

**Exige (A):**
- Mesmas exigências de PUB-03/05/10/11 para o inventário GAM (JoinAds).

**Só sugere risco (B):**
- Não verificado se o creditoup opera por MCM (parceiro) ou conta própria — no MCM o 'Child' e o 'Parent' respondem pelas violações.

**Caso Senac:**
- Viola: Bloco GAM sob o botão 'Guia de inscrição no portal regional'.
- Não viola: Blocos entre seções de texto.

**Consequência:** Suspensão/encerramento do uso do Ad Manager.

**Confiança:** alta · **Observações:** Última atualização informada na página: 1º de maio de 2025. A URL de tópico redirecionou para a answer/9059370 (parâmetro visit_id omitido).

**Fontes adicionais:**
- Partner Guidelines 3.5 — “When displaying Google ads on their Sites, Partner must also comply with the AdSense Program Policies” — https://support.google.com/admanager/answer/9059370?hl=en&ref_topic=28145&rd=1
- Partner Guidelines 3.1 — “do not exceed the amount of Site content.” — https://support.google.com/admanager/answer/9059370?hl=en&ref_topic=28145&rd=1

### PUB-17 · Google Publisher Restrictions (restrições de conteúdo e comportamento)

**Fonte:** https://support.google.com/publisherpolicies/answer/10437795?hl=en — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Restrições não proíbem monetizar, mas reduzem as fontes de anúncio; anúncios do Google Ads não servem em conteúdo restrito. Conteúdo: sexual, chocante, explosivos, armas, tabaco, drogas recreativas, álcool, jogos de azar online, medicamentos etc. Comportamento: anúncios do Google que cobrem total ou parcialmente o conteúdo e conteúdo que cobre anúncios.

**Citação:** “Google Ads (formerly AdWords) advertisements will not serve on content labeled with these restrictions.”

**Exige (A):**
- Nenhuma categoria de conteúdo restrito se aplica ao tema Senac/cursos.
- Anúncio servido pelo Google não pode cobrir conteúdo, 'for any period of time' (restrição de comportamento).

**Só sugere risco (B):**
- Overlay/sticky próprio do carregador de anúncios cobrindo texto do guia reduziria demanda (inclusive Google Ads) nas páginas.

**Caso Senac:**
- Viola: Anúncio âncora que cobre o botão 'Guia de inscrição' ou parte do texto.
- Não viola: Blocos in-page que não cobrem texto; vinheta do formato Google entre páginas.

**Consequência:** Menos fontes de demanda; sem anúncios do Google Ads no conteúdo restrito.

**Confiança:** alta · **Observações:** Página principal de Google Publisher Policies (answer/10502938): obrigação geral de cumprir as políticas ao monetizar com código de anúncios do Google (ver fonte adicional).

**Fontes adicionais:**
- Google-served ads obscuring content — “fully or partially obscure content for any period of time” — https://support.google.com/publisherpolicies/answer/11127388?hl=en
- Google Publisher Policies (página principal) — “When you monetize your content with Google ad code you are required to adhere to the following policies.” — https://support.google.com/publisherpolicies/answer/10502938?hl=en

## Regras — Search orgânico (risco B)

### SEO-01 · Spam policies for Google web search — Scaled content abuse (e scraping)

**Fonte:** https://developers.google.com/search/docs/essentials/spam-policies — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Muitas páginas geradas com o propósito principal de manipular rankings e não de ajudar usuários, 'não importa como' foram criadas: IA generativa sem valor, scraping/sinônimos, costura de conteúdos, múltiplos sites para esconder a escala, páginas sem sentido com palavras-chave.

**Citação:** “Scaled content abuse is when many pages are generated for the primary purpose of manipulating search rankings and not helping users.”

**Exige (A):**
- Nenhuma produção em escala de páginas quase iguais (ex.: por cidade/estado) sem valor próprio.

**Só sugere risco (B):**
- Fragmentar uma resposta em muitas páginas finas geradas por LLM (a pergunta da tarefa) se aproxima de scaled content + doorway — o funil Senac tem 5 páginas, mas o motor escala por tema.

**Caso Senac:**
- Viola: Gerar 27 páginas 'Cursos Senac + UF' com o mesmo texto e só a sigla trocada.
- Não viola: Uma página por dúvida real (requisitos, oferta regional, inscrição) com conteúdo distinto e fontes.

**Consequência:** Rebaixamento ou remoção da Pesquisa; ação manual.

**Confiança:** media · **Observações:** Classe B pedida na tarefa: é política do Search orgânico, não do Google Ads/AdSense; conecta-se a eles por ADS-ABU-01 e PUB-07. Página com 'Last updated 2026-08-28 UTC'.

**Fontes adicionais:**
- Scaled content abuse — IA — “Using generative AI tools or other similar tools to generate many pages without adding value for users” — https://developers.google.com/search/docs/essentials/spam-policies
- Scraping — sinônimos — “Copying content from other sites, modify it only slightly (for example, by substituting synonyms or using automated techniques), and republish it” — https://developers.google.com/search/docs/essentials/spam-policies

### SEO-02 · Spam policies for Google web search — Doorway abuse

**Fonte:** https://developers.google.com/search/docs/essentials/spam-policies — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Páginas criadas para ranquear em buscas semelhantes que levam a páginas intermediárias menos úteis que o destino final: páginas por cidade/região que afunilam para uma página; páginas geradas para afunilar o visitante para a parte útil do site; páginas parecidas com resultado de busca.

**Citação:** “Generating pages to funnel visitors into the actual usable or relevant portion of a site”

**Exige (A):**
- A LP não pode ser só um funil para a 'parte útil' nas internas.

**Só sugere risco (B):**
- O desenho LP → internas é compatível só se cada página tiver utilidade própria.

**Caso Senac:**
- Viola: LP que resume em 2 linhas e manda o leitor para a interna onde está a resposta.
- Não viola: LP que responde e oferece internas para aprofundar.

**Consequência:** Rebaixamento/remoção da Pesquisa.

**Confiança:** media · **Observações:** Classe B (orgânico).

**Fontes adicionais:**
- Doorway — regiões — “Having multiple domain names or pages targeted at specific regions or cities that funnel users to one page” — https://developers.google.com/search/docs/essentials/spam-policies

### SEO-03 · Spam policies for Google web search — Misleading functionality / Scam and fraud

**Fonte:** https://developers.google.com/search/docs/essentials/spam-policies — HTTP 200; sem redirecionamento; consultado em 30/09/2026 (também: landing_page)

**Regra (paráfrase):** Proíbe sites que prometem funcionalidade (calculadora, dicionário etc.) e levam a anúncios enganosos em vez de entregá-la; e imitação de empresa/serviço oficial por sites impostores.

**Citação:** “intentionally leads users to deceptive ads rather than providing the claimed services”

**Exige (A):**
- Widget/calculadora do funil (ex.: 'veja se você se enquadra no PSG') precisa funcionar de verdade.

**Só sugere risco (B):**
- O próprio senac.br oferece calculadora de renda do PSG; replicar a promessa sem entregar é o caso descrito.

**Caso Senac:**
- Viola: 'Calcule se você tem direito ao curso grátis' → botão abre vinheta e nenhuma calculadora.
- Não viola: Widget que calcula a renda per capita com o critério citado do senac.br e remete ao Senac.

**Consequência:** Rebaixamento/remoção da Pesquisa.

**Confiança:** media · **Observações:** Classe B (orgânico).

**Fontes adicionais:**
- Scam and fraud — “impersonating an official business or service through imposter sites” — https://developers.google.com/search/docs/essentials/spam-policies

### SEO-04 · Search Central — Avoid intrusive interstitials and dialogs (orientação)

**Fonte:** https://developers.google.com/search/docs/appearance/avoid-intrusive-interstitials — HTTP 200; sem redirecionamento; consultado em 30/09/2026

**Regra (paráfrase):** Orientação (não política de spam): interstitials/diálogos intrusivos dificultam ao Google entender o conteúdo e podem piorar o desempenho na Pesquisa; preferir banners; não cobrir a página inteira.

**Citação:** “Don't obscure the entire page with interstitials.”

**Exige (A):**
- (nenhum)

**Só sugere risco (B):**
- Boa prática para o orgânico; não é regra de reprovação.

**Caso Senac:**
- Viola: Overlay próprio cobrindo a LP inteira ao carregar.
- Não viola: Vinheta entre páginas do formato Google.

**Consequência:** Possível pior desempenho orgânico.

**Confiança:** media · **Observações:** Página com 'Last updated 2025-12-10 UTC'.

## O que NÃO está escrito

Crenças que circulam na operação e o que o texto oficial de fato diz. Classe atribuída à **crença**, não à política. Ausência de proibição não é garantia de aprovação.

| ID | Crença | Classe | Confiança |
|---|---|---|---|
| NE-01 | perguntas em títulos são proibidas — ou, no sentido oposto, 'pergunta é o formato mais seguro' | D para 'proibido'; C para 'mais segura' (medição interna, não política) | alta |
| NE-02 | ponto de exclamação único é proibido em título/descrição | B (risco), não A | media |
| NE-03 | CTA em primeira pessoa ('quero ver', 'e se eu') viola política | C | alta |
| NE-04 | imperativo ('Veja', 'Confira', 'Consulte') é proibido ou arriscado por si | C (com base B para verbos de execução) | alta |
| NE-05 | as palavras 'grátis'/'gratuito' são proibidas ou 'parecem sistema' | D se tratada como proibição geral | alta |
| NE-06 | segunda pessoa ('você') é proibida | D | alta |
| NE-07 | a palavra 'oficial' (e 'parceiro', 'autorizado') é proibida em qualquer asset | C (conservadora; base B) | alta |
| NE-08 | Title Case é obrigatório ('REGRA ABSOLUTA') — ou proibido | C | alta |
| NE-09 | o formato '<Marca/Órgão>: <promessa>' é 'o template literal de afiliação oficial falsa' (atribuído a 6020955 + 13156083) | C (a atribuição a 13156083 é D) | alta |
| NE-10 | 'nenhuma palavra de 4+ letras em mais de 4 títulos' é a política de repetição (14848296) | C | alta |
| NE-11 | Ad Strength 'Média/Ruim' reprova ou limita a veiculação | D | alta |
| NE-12 | termos como 'garantido', '100%', 'crédito', 'empréstimo' causam 'suspensão imediata' | D (para 'suspensão imediata' por palavra) | alta |
| NE-13 | urgência/prazo é proibido — ou 'seguro por hedge' ('prazo pode expirar', 'use agressivamente') | C (listas internas); o 'use agressivamente' é C com risco B | alta |
| NE-14 | aviso 'sem vínculo' + âncoras 'google adsense' / 'não temos relação com facebook ou google' são exigidos pela política | C (boa prática) | alta |
| NE-15 | link para o site oficial é exigido pela política | C | alta |
| NE-16 | interstitial é proibido no destino de Google Ads | D | alta |
| NE-17 | arbitragem (comprar clique e monetizar com anúncios) é proibida — ou está liberada se a página tiver aviso | D (nas duas versões) | alta |
| NE-18 | dividir a resposta em várias páginas é proibido — ou é neutro | B | media |
| NE-19 | usar a marca 'Senac' no texto do anúncio é proibido para quem não é o Senac | D | alta |
| NE-20 | o separador '\|' é proibido | C (conservadora; base B) | media |
| NE-21 | pedir isenção de política resolve a reprovação | D (a crença); o repo está correto | alta |
| NE-22 | validate_only sem erro = anúncio aprovado | D (a crença); o repo está correto | alta |

### NE-01 · Crença: perguntas em títulos são proibidas — ou, no sentido oposto, 'pergunta é o formato mais seguro'

**Onde aparece:** volc_ads/README.md:101-108 (copy manual com 0% de perguntas); volc_ads/copy/PROMPT.md:281 ('M8 · PERGUNTA ... a mecânica MAIS SEGURA'); volc_ads/copy/REFERENCIA-n8n-sniper.md:17 ('"Você Tem Direito?" é seguro por ser pergunta')

**Texto conferido:** https://support.google.com/adspolicy/answer/14847994?hl=en — “Punctuation or symbols repeated consecutively, like "flowers!!"”

**O que a política diz:** Nenhuma página consultada proíbe o ponto de interrogação ou a forma de pergunta; o vetado é pontuação repetida ('??'). Também nada diz que pergunta é 'segura': pergunta que esconde a resposta para forçar o clique cai no exemplo de clickbait (ADS-MIS-03).

**Caso Senac:** Viola: Título: Você Não Vai Acreditar Nisso? · Não viola: Título: Quem Pode Fazer Curso Grátis?

**Classe da crença:** D para 'proibido'; C para 'mais segura' (medição interna, não política) · **Confiança:** alta

### NE-02 · Crença: ponto de exclamação único é proibido em título/descrição

**Onde aparece:** crença comum; nenhuma regra específica no repo (busca em volc_ads, funnelforge-migracao/engine/src, backend/app); o repo veta 'pontuação repetida' (volc_ads/copy/PROMPT.md:651)

**Texto conferido:** https://support.google.com/adspolicy/answer/1054210?hl=en — “Punctuation and symbols in the link text or description that serve no purpose other than to draw attention to the ad”

**O que a política diz:** Não encontrado na página vigente de Punctuation and symbols para títulos/descrições (só a repetição '!!' e o uso 'gimmicky'). Em sitelinks, callouts e snippets, exclamação que só chama atenção é exemplo explícito de proibido. A política 'Text ad requirements' foi descontinuada em 17/03/2026 (CHG-02). Ausência de proibição não garante aprovação: uso 'gimmicky' continua vetado.

**Caso Senac:** Viola: Sitelink: Veja os Requisitos! · Viola: Título: Cursos Grátis!! · Não viola: Título: Cursos Senac por Estado

**Classe da crença:** B (risco), não A · **Confiança:** media

### NE-03 · Crença: CTA em primeira pessoa ('quero ver', 'e se eu') viola política

**Onde aparece:** funnelforge-migracao/engine/src/funnelforge/pipeline/doctrine.py:49-60 (BANNED_CTA_FIRST_PERSON, só na LP); funnelforge-migracao/engine/src/funnelforge/prompts/judge.jinja:52

**Texto conferido:** https://support.google.com/adspolicy/answer/14848297?hl=en — não encontrado na política

**O que a política diz:** Nenhuma página consultada (Editorial, Misrepresentation, Destination, Publisher, AdSense) menciona primeira pessoa. É preferência editorial interna.

**Caso Senac:** Viola: n/a (não há regra) · Não viola: Botão: 'Quero ver os requisitos' — permitido pela política; vetado só pela doutrina interna na LP

**Classe da crença:** C · **Confiança:** alta

### NE-04 · Crença: imperativo ('Veja', 'Confira', 'Consulte') é proibido ou arriscado por si

**Onde aparece:** volc_ads/copy/PROMPT.md:226 ('imperativo nu é PROIBIDO' quando há tema regulado); funnelforge-migracao/engine/src/funnelforge/pipeline/doctrine.py:67-75 (BANNED_CTA_EXECUTION)

**Texto conferido:** https://support.google.com/adspolicy/answer/14848297?hl=en — “Ads that contain a generic call to action like "click here" that could apply to any ad”

**O que a política diz:** A política veta CTA genérico ('click here') e clickbait ('Click here to find out'), não o modo imperativo. O RSA atual usa 'Veja', 'Conheça', 'Entenda', 'Leia' e está APPROVED. O risco real é semântico: imperativo de execução ('Inscreva-se', 'Emita') num site que não executa → ADS-MIS-02/06.

**Caso Senac:** Viola: Título: Inscreva-se no Senac Hoje — o site não inscreve · Não viola: Título: Veja os Requisitos do PSG

**Classe da crença:** C (com base B para verbos de execução) · **Confiança:** alta

### NE-05 · Crença: as palavras 'grátis'/'gratuito' são proibidas ou 'parecem sistema'

**Onde aparece:** volc_ads/campanha/limites.yaml:107-108 ('consulta grátis aqui' em suspeitos_execucao); crença comum

**Texto conferido:** https://support.google.com/adspolicy/answer/15938375?hl=en — “Promoting apps as free when a user must pay to install the app”

**O que a política diz:** 'Free' só aparece como problema quando falso (Dishonest pricing) ou como valor promocional em snippet ('Free shipping'). O Senac usa 'Cursos Grátis' no próprio site. Para o caso, a exigência é precisão: nem todo curso é gratuito e o PSG tem critério de renda (ADS-MIS-04).

**Caso Senac:** Viola: Título: Cursos Senac Grátis Para Todos · Não viola: Título: Cursos Grátis: Veja Critérios

**Classe da crença:** D se tratada como proibição geral · **Confiança:** alta

### NE-06 · Crença: segunda pessoa ('você') é proibida

**Onde aparece:** crença comum; nenhuma regra no repo (busca rg)

**Texto conferido:** https://support.google.com/adspolicy/answer/6021546?hl=en — não encontrado na política

**O que a política diz:** Não há veto a 'você' nas páginas consultadas. As políticas de publicidade personalizada tratam de segmentação por categoria sensível, não de pronomes (ADS-PERS-01).

**Caso Senac:** Viola: n/a · Não viola: Título: Você Pode Estudar no Senac?

**Classe da crença:** D · **Confiança:** alta

### NE-07 · Crença: a palavra 'oficial' (e 'parceiro', 'autorizado') é proibida em qualquer asset

**Onde aparece:** volc_ads/copy/PROMPT.md:617-621

**Texto conferido:** https://support.google.com/adspolicy/answer/15938071?hl=en — “Make it seem like you’re affiliated with another brand, organization or government entity when you’re not”

**O que a política diz:** O veto é à afiliação implícita, não à palavra. A descrição atual 'A inscrição ocorre no canal oficial.' está APPROVED. 'Oficial' qualificando o anunciante/site é violação grave; qualificando o canal do Senac, claramente de terceiro, é uso factual (risco residual B).

**Caso Senac:** Viola: Título: Site Oficial de Cursos Senac · Não viola: Descrição: A inscrição é feita no site oficial do Senac, não aqui.

**Classe da crença:** C (conservadora; base B) · **Confiança:** alta

### NE-08 · Crença: Title Case é obrigatório ('REGRA ABSOLUTA') — ou proibido

**Onde aparece:** volc_ads/copy/REFERENCIA-n8n-sniper.md:89; volc_ads/copy/PROMPT.md:546

**Texto conferido:** https://support.google.com/adspolicy/answer/14848295?hl=en — “Capitalization that isn't used correctly or for its intended purpose”

**O que a política diz:** A política veta caixa alta excessiva ou alternada ('FLOWERS', 'FlOwErS'); não menciona Title Case. Os 8 títulos atuais em Title Case estão APPROVED.

**Caso Senac:** Viola: Título: CURSOS GRÁTIS SENAC · Não viola: Título: Cursos Senac por Estado · Não viola: Título: Cursos Senac por estado

**Classe da crença:** C · **Confiança:** alta

### NE-09 · Crença: o formato '<Marca/Órgão>: <promessa>' é 'o template literal de afiliação oficial falsa' (atribuído a 6020955 + 13156083)

**Onde aparece:** volc_ads/copy/PROMPT.md:268-273

**Texto conferido:** https://support.google.com/adspolicy/answer/15936666?hl=en — “Implying affiliation with or endorsement by another organization, brand, or private citizen without their knowledge or consent”

**O que a política diz:** Nenhuma das duas páginas trata de sintaxe; vetam a implicação de afiliação. 'Cursos Senac: Guia Informativo' está APPROVED. A política de documentos de governo (13156083) não se aplica ao Senac (ADS-ORB-GOV). O risco depende do lado direito: 'Senac: Inscrições Abertas' implica que o anunciante é o Senac.

**Caso Senac:** Viola: Título: Senac: Inscrições Abertas · Não viola: Título: Cursos Senac: Guia Informativo

**Classe da crença:** C (a atribuição a 13156083 é D) · **Confiança:** alta

### NE-10 · Crença: 'nenhuma palavra de 4+ letras em mais de 4 títulos' é a política de repetição (14848296)

**Onde aparece:** volc_ads/copy/PROMPT.md:552-553

**Texto conferido:** https://support.google.com/adspolicy/answer/14848296?hl=en — “Asset text that repeats words or phrases within the same asset or another asset in the same ad group, campaign, or account”

**O que a política diz:** A política não tem limiar numérico nem fala de Ad Strength; o Ad Strength não define elegibilidade (NE-11). O limite '4 em 4' é heurística interna.

**Caso Senac:** Viola: Título: Senac Cursos Senac Grátis · Não viola: 'Cursos' em 5 dos 8 títulos atuais (acima do teto interno de 4) — APPROVED em 30/09

**Classe da crença:** C · **Confiança:** alta

### NE-11 · Crença: Ad Strength 'Média/Ruim' reprova ou limita a veiculação

**Onde aparece:** crença comum (baseline: ad strength AVERAGE)

**Texto conferido:** https://support.google.com/google-ads/answer/9921843?hl=en — “Ad Strength doesn’t determine whether your ad is eligible to serve.”

**O que a política diz:** A Ajuda diz que o Ad Strength não determina elegibilidade e não entra no cálculo de Ad Rank, Índice de Qualidade ou leilão.

**Caso Senac:** Viola: n/a · Não viola: Fixar a ressalva em D1 mesmo que o Ad Strength caia.

**Classe da crença:** D · **Confiança:** alta

### NE-12 · Crença: termos como 'garantido', '100%', 'crédito', 'empréstimo' causam 'suspensão imediata'

**Onde aparece:** volc_ads/copy/REFERENCIA-n8n-sniper.md:67-68; volc_ads/campanha/limites.yaml:88-105 ('evitam o strike')

**Texto conferido:** https://support.google.com/adspolicy/answer/15938075?hl=en — “Accounts aren't suspended under this policy for having ad disapprovals related to editorial issues like formatting or misspelled words.”

**O que a política diz:** Quase todas as páginas consultadas avisam ≥7 dias antes de suspender. Suspensão sem aviso, entre as consultadas: Unacceptable business practices, Coordinated deceptive practices, Malicious software, Circumventing systems. Atenção: afiliação falsa com o Senac é desse grupo. Termos financeiros não foram verificados nesta etapa (fora do caso Senac); o próprio repo mediu 'crédito' em 54 títulos aprovados (volc_ads/README.md:118-123).

**Caso Senac:** Viola: Título: Vaga Garantida no Senac — reprovação provável (Unreliable claims), não suspensão imediata · Não viola: Descrição: A disponibilidade e os requisitos variam por oferta. — texto atual, APPROVED

**Classe da crença:** D (para 'suspensão imediata' por palavra) · **Confiança:** alta

### NE-13 · Crença: urgência/prazo é proibido — ou 'seguro por hedge' ('prazo pode expirar', 'use agressivamente')

**Onde aparece:** funnelforge-migracao/engine/src/funnelforge/pipeline/doctrine.py:23-33 (BANNED_FEAR); volc_ads/copy/PROMPT.md:290; volc_ads/copy/REFERENCIA-n8n-sniper.md:77-80

**Texto conferido:** https://support.google.com/adspolicy/answer/15936667?hl=en — “Ads that use negative life events such as death, accidents, illness, arrests or bankruptcy to induce fear, guilt or other strong negative emotions”

**O que a política diz:** Prazo verdadeiro não é vetado. Vetados: pressão por medo com evento negativo (A) e promessa/urgência falsa (Unreliable claims, B). O modal ('pode expirar') não torna a frase segura se o prazo não existir na oferta.

**Caso Senac:** Viola: Título: Últimas Vagas Grátis no Senac — sem prazo real verificado · Não viola: Título: Inscrições Até 10/10 em SP — só se a oferta regional disser isso

**Classe da crença:** C (listas internas); o 'use agressivamente' é C com risco B · **Confiança:** alta

### NE-14 · Crença: aviso 'sem vínculo' + âncoras 'google adsense' / 'não temos relação com facebook ou google' são exigidos pela política

**Onde aparece:** funnelforge-migracao/engine/src/funnelforge/pipeline/doctrine.py:119-130 (REQUIRED_COMPLIANCE_ANCHORS)

**Texto conferido:** https://support.google.com/adspolicy/answer/15938071?hl=en — “If you reference another brand but you're not an official or authorized partner, consider a disclaimer on your website and in your ads.”

**O que a política diz:** O aviso de não afiliação é recomendado ('consider'), não exigido; o exigido é não implicar afiliação. As âncoras sobre AdSense/Google/Facebook não vêm de política consultada; o que o Publisher Policies exige é política de privacidade que divulgue cookies/beacons de terceiros.

**Caso Senac:** Viola: n/a · Não viola: Aviso curto 'Guia independente, sem vínculo com o Senac' no topo — suficiente e recomendado

**Classe da crença:** C (boa prática) · **Confiança:** alta

### NE-15 · Crença: link para o site oficial é exigido pela política

**Onde aparece:** funnelforge-migracao/engine/src/funnelforge/prompts/interior_editorial.jinja:20-21; funnelforge-migracao/engine/config.yaml:63 (gate falha fechado sem canal oficial)

**Texto conferido:** https://support.google.com/adspolicy/answer/6368711?hl=en — “you must disclose this and provide a link to the official government site”

**O que a política diz:** A exigência literal de link oficial existe só em Government documents, para quem cobra por serviço de governo — não se aplica ao Senac. Para o caso é boa prática (ajuda ADS-MIS-05/06 e confiança).

**Caso Senac:** Viola: n/a · Não viola: Interna com link para o regional do Senac na etapa de inscrição (como a 2309 faz)

**Classe da crença:** C · **Confiança:** alta

### NE-16 · Crença: interstitial é proibido no destino de Google Ads

**Onde aparece:** crença comum

**Texto conferido:** https://support.google.com/adspolicy/answer/16427615?hl=en — “Google Ads allows interstitials if they don't make it difficult for a user to leave a site.”

**O que a política diz:** Permitido com condições. Vetado: impedir ver o conteúdo pedido, dificultar a saída, prestitial com contagem regressiva, e (egregious) cobrir a maior parte do conteúdo a ponto de o Google não avaliar o destino.

**Caso Senac:** Viola: Vinheta ao chegar do anúncio, cobrindo a LP. · Não viola: Vinheta do formato Google no clique entre páginas.

**Classe da crença:** D · **Confiança:** alta

### NE-17 · Crença: arbitragem (comprar clique e monetizar com anúncios) é proibida — ou está liberada se a página tiver aviso

**Onde aparece:** crença comum na operação de publisher

**Texto conferido:** https://support.google.com/adspolicy/answer/16427718?hl=en — “Driving traffic through "arbitrage" or other methods to destinations with more ads than original content, little or no original content, or excessive advertising”

**O que a política diz:** Nenhum texto proíbe a arbitragem em si; vetam o destino de baixo valor (mais anúncios que conteúdo, pouco conteúdo, feito para exibir anúncios). O AdSense aceita tráfego pago se a LP cumprir o espírito das diretrizes de qualidade. Aviso não substitui conteúdo.

**Caso Senac:** Viola: LP-menu com anúncios. · Não viola: LP que responde por si com anúncios proporcionais.

**Classe da crença:** D (nas duas versões) · **Confiança:** alta

### NE-18 · Crença: dividir a resposta em várias páginas é proibido — ou é neutro

**Onde aparece:** pergunta da tarefa (risco B)

**Texto conferido:** https://developers.google.com/search/docs/essentials/spam-policies — “Generating pages to funnel visitors into the actual usable or relevant portion of a site”

**O que a política diz:** Não há veto a múltiplas páginas. Há vetos a doorway (orgânico), página-ponte (Ads), pretexto falso para interação e tela usada para navegação (Publisher). Dividir para multiplicar pageviews/vinhetas cruza esses quatro.

**Caso Senac:** Viola: LP → interna 1 (resumo) → interna 2 (a resposta) sem necessidade. · Não viola: Páginas por dúvida distinta, cada uma completa.

**Classe da crença:** B · **Confiança:** media

### NE-19 · Crença: usar a marca 'Senac' no texto do anúncio é proibido para quem não é o Senac

**Onde aparece:** crença comum

**Texto conferido:** https://support.google.com/adspolicy/answer/6118?hl=en — “Ads using the trademark where the primary purpose of the landing page is to provide informative details about products or services corresponding to the trademark”

**O que a política diz:** Não é proibido: o Google só restringe após reclamação do titular e não restringe uso informativo; restringe uso confuso/enganoso. Riscos: reclamação futura (não verificada) e Limited ad serving.

**Caso Senac:** Viola: Título: Senac: Site de Inscrição · Não viola: Título: Cursos Senac: Guia Informativo

**Classe da crença:** D · **Confiança:** alta

### NE-20 · Crença: o separador '|' é proibido

**Onde aparece:** volc_ads/copy/PROMPT.md:651-652

**Texto conferido:** https://support.google.com/adspolicy/answer/14847994?hl=en — “Non-standard symbols or characters like bullet points or asterisks, like "*flowers*"”

**O que a política diz:** O pipe não é citado; a regra geral de símbolo fora do propósito pode alcançá-lo. Não encontrado ≠ permitido.

**Caso Senac:** Viola: Título: Cursos | Senac | Grátis · Não viola: Título: Cursos Senac: Guia Informativo

**Classe da crença:** C (conservadora; base B) · **Confiança:** media

### NE-21 · Crença: pedir isenção de política resolve a reprovação

**Onde aparece:** crença comum; o repo já a rejeita (volc_ads/isencao.py:13-20)

**Texto conferido:** https://developers.google.com/google-ads/api/reference/rpc/v25/PolicyValidationParameter — “Resources that violate these policies will be saved, but will not be eligible to serve.”

**O que a política diz:** Isenção salva o recurso para re-revisão; não o torna elegível.

**Caso Senac:** Viola: n/a · Não viola: n/a

**Classe da crença:** D (a crença); o repo está correto · **Confiança:** alta

### NE-22 · Crença: validate_only sem erro = anúncio aprovado

**Onde aparece:** crença comum; o repo já a rejeita (volc_ads/campanha/validacao.py:1-9)

**Texto conferido:** https://developers.google.com/google-ads/api/reference/rpc/v25/MutateAdsRequest — “If true, the request is validated but not executed. Only errors are returned, not results.”

**O que a política diz:** validate_only pega violações comuns detectáveis na requisição; a revisão pós-envio (inclui destino) é outra etapa (ADS-REV-01).

**Caso Senac:** Viola: n/a · Não viola: n/a

**Classe da crença:** D (a crença); o repo está correto · **Confiança:** alta

## Crenças da operação que a política sustenta

| ID | Crença | Onde aparece | Sustentada por |
|---|---|---|---|
| SUS-01 | Emoji é proibido em anúncios | volc_ads/copy/PROMPT.md:651 | ADS-EDI-01 (Invalid or unsupported characters: Emoji) |
| SUS-02 | Pontuação repetida, caixa alta em palavra comum, letras separadas por ponto e troca de letra por número são proibidas | volc_ads/copy/PROMPT.md:651-654 | ADS-EDI-01, ADS-EDI-02 |
| SUS-03 | Sensacionalismo fere a política do Google | funnelforge-migracao/engine/src/funnelforge/prompts/redator_p1.jinja:3 | ADS-MIS-03 |
| SUS-04 | Falsa oficialidade/afiliação é proibida (lista BANNED_OFFICIAL) | funnelforge-migracao/engine/src/funnelforge/pipeline/doctrine.py:37-46 | ADS-MIS-01 (egregious), PUB-01 — as frases específicas são implementação interna |
| SUS-05 | Não oferecer 'Inscreva-se' quando o clique só abre outra página editorial | funnelforge-migracao/engine/src/funnelforge/prompts/interior_editorial.jinja:35 | ADS-MIS-06, PUB-02 |
| SUS-06 | Isento não é aprovado | volc_ads/isencao.py:13-20 | API-08 |
| SUS-07 | validate_only não substitui a revisão do Google | volc_ads/campanha/validacao.py:1-9 | API-07, ADS-REV-01 |
| SUS-08 | Limites 30/90 e 3–15/2–4 do RSA | volc_ads/campanha/limites.yaml:5-6 | API-02 |

## Fatos de contexto sobre o Senac (fontes oficiais)

- **FATO-01 · Natureza jurídica do Senac (Regulamento, Decreto nº 61.843/1967, art. 4º)** — “O Serviço Nacional de Aprendizagem Comercial é uma instituição de direito privado, nos têrmos da Lei civil” — https://www.planalto.gov.br/ccivil_03/decreto/1950-1969/d61843.htm (HTTP 200; sem redirecionamento). Uso: Base para afirmar que o Senac não é órgão de governo (ADS-ORB-GOV).
- **FATO-02 · Criação: Decreto-Lei nº 8.621/1946, arts. 1º e 2º (CNC organiza e cria o SENAC)** — “Fica atribuído à Confederação Nacional do Comércio o encargo de organizar e administrar, no território nacional, escolas de aprendizagem comercial.” — https://www.planalto.gov.br/ccivil_03/decreto-lei/1937-1946/del8621.htm (HTTP 200; sem redirecionamento). Uso: Contexto institucional (Sistema S / Sistema Comércio).
- **FATO-03 · Administração pela CNC (senac.br/sobre)** — “O Senac é administrado pela Confederação Nacional do Comércio de Bens, Serviços e Turismo (CNC)” — https://www.senac.br/sobre/ (HTTP 200; sem redirecionamento). Uso: Quem é o titular de fato da marca/instituição citada.
- **FATO-04 · Programa Senac de Gratuidade — critério de renda (senac.br)** — “Apenas pessoas com renda familiar per capita até 2 salários-mínimos podem participar.” — https://www.senac.br/ (Accept-Language pt-BR; com en-US redireciona para https://www.senac.br/en/) (HTTP 200; sem redirecionamento). Uso: Limita a copy 'grátis': gratuidade condicionada (ADS-MIS-04, NE-05). O mesmo site usa o rótulo 'Cursos Grátis'.

## Mudanças recentes e pendentes (changelog oficial de 2026)

| ID | Mudança | Citação | Efeito no caso |
|---|---|---|---|
| CHG-01 | [Government documents and services — critérios de 'authorized provider' (vigência 05/10/2026)](https://support.google.com/adspolicy/answer/17260489?hl=en) | “We will begin enforcing the policy update on October 5, 2026.” | Endurece quem pode ser provedor autorizado; não altera a lista de categorias; sem efeito sobre cursos do Senac. Relevante para outros funis da operação. |
| CHG-02 | [Ad format requirements — 'Text ad requirements' descontinuada (17/03/2026)](https://support.google.com/adspolicy/answer/16971215?hl=en) | “the Form ad requirements, Image quality requirements, Responsive ad requirements, and the Text ad requirements policies have been discontinued.” | Regras que só existiam em 'Text ad requirements' são candidatas à classe D; as vigentes estão em Editorial e nos requisitos de formato. |
| CHG-03 | [Limited ad serving — ampliação (jun/2026 Search; ago/2026 todos os anúncios; gradual até 2028)](https://support.google.com/adspolicy/answer/17344822?hl=en) | “Implementation will begin gradually and will be completed by 2028.” | Aumenta a importância de marca própria visível e de não parecer o Senac (ADS-LAS-01). |
| CHG-04 | [Destination mismatch — redirecionamento para outro domínio só com aprovação prévia (jun/2026)](https://support.google.com/adspolicy/answer/17140995?hl=en) | “redirects from an ad’s final URL that take the user to a different domain are allowed in certain circumstances, with prior approval.” | Sem efeito prático no caso (não há redirecionamento para senac.br). |
| CHG-05 | [Limite de recurso: decisões com mais de 6 meses não podem ser contestadas pela conta (21/07/2026)](https://support.google.com/adspolicy/answer/17251522?hl=en) | “will not be available for policy decisions made more than 6 months prior.” | Reprovações precisam ser contestadas dentro de 6 meses. |
| CHG-06 | [Misleading ad design — artigo reescrito sem mudança de aplicação (ago/2026)](https://support.google.com/adspolicy/answer/17600038?hl=en) | “This does not change enforcement of the policy.” | Nenhum. |

## Registro de consultas

90 URLs citadas neste ledger, todas consultadas em 30/09/2026. Status na checagem final:

- https://developers.google.com/google-ads/api/docs/ads/ad-types — HTTP 200; sem redirecionamento
- https://developers.google.com/google-ads/api/docs/ads/mutate-ads — HTTP 200; sem redirecionamento
- https://developers.google.com/google-ads/api/docs/concepts/api-structure — HTTP 200; sem redirecionamento
- https://developers.google.com/google-ads/api/docs/sunset-dates — HTTP 200; sem redirecionamento
- https://developers.google.com/google-ads/api/reference/rpc/v25/Ad — HTTP 200; sem redirecionamento
- https://developers.google.com/google-ads/api/reference/rpc/v25/AdGroupCriterionOperation — HTTP 200; sem redirecionamento
- https://developers.google.com/google-ads/api/reference/rpc/v25/AdTextAsset — HTTP 200; sem redirecionamento
- https://developers.google.com/google-ads/api/reference/rpc/v25/CalloutAsset — HTTP 200; sem redirecionamento
- https://developers.google.com/google-ads/api/reference/rpc/v25/MutateAdsRequest — HTTP 200; sem redirecionamento
- https://developers.google.com/google-ads/api/reference/rpc/v25/PolicyFindingErrorEnum.PolicyFindingError — HTTP 200; sem redirecionamento
- https://developers.google.com/google-ads/api/reference/rpc/v25/PolicyValidationParameter — HTTP 200; sem redirecionamento
- https://developers.google.com/google-ads/api/reference/rpc/v25/PolicyViolationDetails — HTTP 200; sem redirecionamento
- https://developers.google.com/google-ads/api/reference/rpc/v25/PolicyViolationKey — HTTP 200; sem redirecionamento
- https://developers.google.com/google-ads/api/reference/rpc/v25/ResponsiveSearchAdInfo — HTTP 200; sem redirecionamento
- https://developers.google.com/google-ads/api/reference/rpc/v25/SitelinkAsset — HTTP 200; sem redirecionamento
- https://developers.google.com/google-ads/api/reference/rpc/v25/StructuredSnippetAsset — HTTP 200; sem redirecionamento
- https://developers.google.com/search/docs/appearance/avoid-intrusive-interstitials — HTTP 200; sem redirecionamento
- https://developers.google.com/search/docs/essentials/spam-policies — HTTP 200; sem redirecionamento
- https://support.google.com/admanager/answer/7496282?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/admanager/answer/9059370?hl=en&ref_topic=28145&rd=1 — HTTP 200; sem redirecionamento
- https://support.google.com/admanager/answer/9840201?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adsense/answer/1346295?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adsense/answer/1346295?hl=pt-BR — HTTP 200; sem redirecionamento
- https://support.google.com/adsense/answer/16531962?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adsense/answer/16737?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adsense/answer/48182?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/1054210?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/13156083?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/13889491?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/14847686?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/14847993?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/14847994?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/14848295?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/14848296?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/14848297?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/14848399?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/14848500?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/15936666?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/15936667?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/15936768?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/15936769?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/15936857?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/15936964?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/15937063?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/15937463?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/15938071?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/15938075?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/15938375?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/16427615?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/16427718?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/16428019?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/16428020?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/16700443?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/16700847?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/16971215?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/17140995?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/1722120?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/17251522?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/17260489?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/17344822?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/17600038?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/6020955?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/6021546?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/6084196?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/6118?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/6283300?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/6368661?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/adspolicy/answer/6368711?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/google-ads/answer/2375416?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/google-ads/answer/7502216?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/google-ads/answer/7684791?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/google-ads/answer/9921843?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/platformspolicy/answer/3013851?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/publisherpolicies/answer/10437795?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/publisherpolicies/answer/10502938?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/publisherpolicies/answer/11035030?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/publisherpolicies/answer/11035931?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/publisherpolicies/answer/11112688?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/publisherpolicies/answer/11127388?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/publisherpolicies/answer/11127848?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/publisherpolicies/answer/11128079?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/publisherpolicies/answer/11169917?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/publisherpolicies/answer/11185754?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/publisherpolicies/answer/11185755?hl=en — HTTP 200; sem redirecionamento
- https://support.google.com/publisherpolicies/answer/11190248?hl=en — HTTP 200; sem redirecionamento
- https://www.betterads.org/standards/ — HTTP 200; sem redirecionamento
- https://www.planalto.gov.br/ccivil_03/decreto-lei/1937-1946/del8621.htm — HTTP 200; sem redirecionamento
- https://www.planalto.gov.br/ccivil_03/decreto/1950-1969/d61843.htm — HTTP 200; sem redirecionamento
- https://www.senac.br/ (Accept-Language pt-BR; com en-US redireciona para https://www.senac.br/en/) — HTTP 200; sem redirecionamento
- https://www.senac.br/sobre/ — HTTP 200; sem redirecionamento

Outras páginas baixadas e não citadas (sem regra pertinente ao caso, ou usadas só para localizar links): Technical requirements (answer/6088505), Abusing the ad network (answer/6020954), Evasive ad content (answer/15938074), Disallowed interstitial implementations do Ad Manager (answer/6309309, norma de apps), Out of context ads (answer/11190357), Creating helpful content (Search Central), About text ads (answer/1704389), About callout assets (answer/6079510), About structured snippet assets (answer/6280012), Edit your text ads (answer/2375287), lista de headers de snippet (https://developers.google.com/google-ads/api/data/structured-snippet-headers — a URL /reference/data/... redireciona para ela), títulos pt-BR de 29 páginas de política.

**Falhas e desvios de consulta:**
- FAIL-01: https://developers.google.com/google-ads/api/docs/ads/change-ads → HTTP 404. URL deduzida; substituída por docs/ads/mutate-ads e docs/ads/ad-types, localizadas por busca oficial.
- FAIL-02: https://developers.google.com/google-ads/api/docs/best-practices/validation → HTTP 404. URL deduzida; substituída por docs/concepts/api-structure (seção validate_only) e pela referência MutateAdsRequest.
- FAIL-03: https://support.google.com/adspolicy/answer/6079556?hl=en → HTTP 404. URL deduzida para callouts; a correta é answer/6084196 (link da página de tópico 'Ad format requirements').
- FAIL-04: https://www.senac.br/ (Accept-Language en-US) → redirecionou para https://www.senac.br/en/. refeito com Accept-Language pt-BR: https://www.senac.br/ 200.
- FAIL-05: https://support.google.com/adspolicy/answer/15938375?hl=pt-BR → HTTP 200, <title> vazio na extração. título pt-BR obtido da página 6020955 em pt-BR: 'Práticas desonestas de preço'.

## Lacunas — não verificado nesta etapa

- Se a versão anterior de um RSA editado continua servindo enquanto a nova é revisada (a documentação não diz).
- Se `path1`/`path2` aceitam update in-place (campo não marcado *Immutable*; não testado).
- Se existe reclamação de marca do Senac; legislação brasileira de marcas e concorrência desleal (fora do escopo).
- Proporção anúncio/conteúdo e densidade de anúncios no mobile das páginas 2306–2318; rótulo exibido pelos blocos JoinAds/AdSense; frequência e gatilhos das vinhetas configurados; se há rewarded nessas páginas.
- Se a conta está sob Limited ad serving (nada no baseline) e se o site tem ação manual no Search Console.
- Se o AdsBot recebe HTTP 200 na LP e nas internas (não testado com o user agent do AdsBot).
- Se o creditoup monetiza no Ad Manager por MCM (parceiro JoinAds) ou por conta própria.
- Como a restrição "ads obscuring content" convive com o formato oficial de interstitial (as páginas não dizem).
- Se alguma oferta gratuita do PSG tem custos acessórios.
- Política de Financial products and services (fora do caso Senac): não consultada.
