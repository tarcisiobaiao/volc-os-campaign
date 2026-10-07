# Achados do motor — o que o Codex precisa olhar

Todos verificados no código e/ou medidos em execução real nesta sessão (2026-09-17).

## A1. Prompt do redator mandava usar uma tag que o gate novo rejeita · CORRIGIDO

`editorial_safety.py` nasceu hoje (`POLICY_VERSION = "editorial-2026-09-17"`) com uma
allowlist de 47 tags que inclui `b`, `i`, `small`, `em`, `strong`, `cite` — e **não** `u`.
Os prompts do redator, mais antigos, mandavam o contrário:

- `prompts/redator_presell.jinja:93` — "…`<em>` pra ênfase e **`<u>` pontual** num detalhe crítico"
- `prompts/redator_pages.jinja:173` — idem

**Consequência medida**: no run-piloto do SENAC, a página 2 seguiu a instrução, produziu
`<u>` e morreu em `content_gate_p2 = unsafe_editorial_html` → `blocked_p2`, **depois** de
pesquisa, redação, juiz, SEO e imagem pagos (US$ 0,26 na página).

**Por que não há retry**: a bateria de `write_page` não inclui `html_issues`. O modelo nunca
recebe esse feedback; a reprovação só aparece no gate final, que não retenta.

**Correção aplicada** (autorizada pelo operador): retirada a instrução `<u>` dos dois prompts,
com a razão escrita na própria linha. O gate **não** foi tocado. `pytest tests/ -q` → 760 passed.

**Sugestão para o Codex**: incluir `html_issues` (ou um validador equivalente de allowlist) na
bateria de `write_page`/`write_presell`, para que a reprovação vire feedback com retry em vez de
página condenada. Hoje é a única classe de erro que só aparece quando já não dá para consertar.

## A2. `identity`/`wrong_cnpj` proíbe citar o CNPJ de qualquer instituição

`validators/checks.py:885-893`: qualquer CNPJ no conteúdo que não seja o do site vira
`wrong_cnpj`. Medido: a p5 do SENAC (cujo H2 era "Sinais que ajudam a reconhecer uma página
institucional") citou o CNPJ do Senac e reprovou **três vezes**, US$ 0,2464 queimados.

Editorialmente, isso impede uma página de utilidade real: "como confirmar que este site é
mesmo da instituição" é justamente onde o CNPJ ajuda o leitor. Contornei pelo input (tirei o
convite do esqueleto e pus "cite instituições pelo nome, nunca por número de registro").

**Sugestão**: distinguir "CNPJ apresentado como sendo o do site" de "CNPJ citado como dado de
terceiro", em vez de reprovar por presença.

## A3. Canal oficial fail-closed + WAF dos portais = página condenada de graça

`build_official_links` (steps.py:1019) descarta qualquer URL que o `HttpUrlVerifier` não
confirme, e `401/403/405/429/timeout` contam como não confirmada (url_verifier_http.py:51).

Medido ao vivo em 2026-09-17:

| URL | veredito do verificador |
|---|---|
| `https://www.senac.br/` | HTTP 403 (WAF Azure Front Door) |
| `https://www.dn.senac.br/portalpsg/` | HTTP 403 |
| `https://www.ead.senac.br/` | ConnectError pelo httpx (mas 200 com UA de navegador) |
| `https://www.planalto.gov.br/ccivil_03/...` | ReadError |
| `https://www.senai.br/` | **certificado TLS não cobre o host** |
| `https://senai.br/` | **certificado expirado** |
| `https://www.portaldaindustria.com.br/senai/` | ReadTimeout |

**Consequência medida**: a p4 do SENAC (gratuidade/PSG) recebeu da pesquisa exatamente essas
quatro fontes, nenhuma passou, e o pré-voo matou a página com `official_links_none` +
`target_missing` — corretamente, e **sem gastar** a redação.

**O que funciona** (verificado, HTTP 200): `sp.senac.br` (inclusive
`/programa-senac-de-gratuidade` e `/bolsas-de-estudo`), `mg.senac.br`, `portal.sc.senac.br`,
`pe.senac.br`, `go.senac.br`, `es.senac.br`, `pr.senac.br/psg/`, `senacrs.com.br/psg`,
`pa.senac.br/psg/perguntas-frequentes`, `transparencia.senac.br`, `sic.senac.br`;
`senai.portaldaindustria.com.br/para-voce/estude-aqui-no-senai`, `sp.senai.br`, `sc.senai.br`,
`pe.senai.br`, `ms.senai.br`, `rn.senai.br`, `ap.senai.br`, `senaimg.com.br`,
`senai-ce.org.br`; `aprendamais.mec.gov.br`, `gov.br/mec/pt-br`, `escolavirtual.gov.br`.

**Correção aplicada**: reescrevi H1, H2 e keywords da p4 para apontar à **página de bolsas do
Departamento Regional** — que existe, responde 200 e é a fonte editorialmente correta, já que o
PSG é operado por regional.

**Sugestão**: o `HttpUrlVerifier` poderia registrar "bloqueado por antibot" separadamente de
"não existe" no relatório da página, para o operador distinguir pauta ruim de portal blindado.

## A4. Sonda anti-anúncio desaparece junto com os screenshots

`_verificadores` só monta `is_ad_monetized` a partir de `deps.screenshot`, que é `None` quando
`run.official_screenshots=false` — exigido por esta missão. Ou seja: **desligar as capturas
desliga também a camada 3** de `build_official_links`.

**Mitigação nesta execução**: `blocked_hosts` no perfil com 14 agregadores comerciais, dois
deles achados pela pesquisa e não por suposição — `cursosenacgratuito.com.br` (agregador que
ranqueia para "senac cursos gratuitos") e **`senacrj.com.br`, que em 2026-09-17 era domínio
estacionado à venda imitando o Senac-RJ**. Mais auditoria manual de cada href externo.

**Sugestão**: separar a sonda anti-anúncio da flag de screenshot — são decisões diferentes.

## A5. `canal_profundo` depende de Playwright de forma independente da flag

`canal_profundo.colher_links` usa `sync_playwright` (canal_profundo.py:195). Sem Playwright,
`aprofundar()` devolve a **raiz** em silêncio e o leitor cai na home do portal. A flag de
screenshot não tem nada a ver com isso, mas o README sugere que Playwright é só para prints.

**Nesta execução**: instalei `playwright` + Chromium (extra `screenshots` do pyproject) **só
por causa disto**; as capturas seguem desligadas por `official_screenshots: false`.

## A6. Exit code 0 mente, e o custo do `report.md` subestima

Confirmado em execução: o run-piloto terminou com **exit 0** tendo 3 de 5 páginas bloqueadas.
As falhas ficaram em `blocked_p2/p4/p5` e nos `write_pN`, e nada foi impresso no terminal.

O custo real deve ser lido como `soma de cost_usd em log.jsonl` + `image_gen_pN` do `state.json`.
No run-piloto: **US$ 1,1637** (26 chamadas de LLM + 3 imagens).

O `Orcamento` não é persistido: cada invocação do CLI (inclusive cada `resume`) recomeça o teto
do zero. Por isso o teto de cada run desta missão foi passado no perfil e **descontado à mão**
do limite de US$ 6 por funil.

## A7. Preço da imagem: declarado ≠ medido (e aqui o medido existe)

`budget.image_price_usd.medium = 0.06` é só o freio *antes* da chamada. O ledger usa o preço
por **token** da tabela do litellm, e `gpt-image-2` está lá
(`output_cost_per_image_token = 3e-05`, fonte `developers.openai.com/api/docs/pricing`).
Medido nesta execução: **US$ 0,0431 a 0,0432 por imagem**, consistente entre páginas.

## A8. A página terminal não pode citar canal oficial — e isso é intencional

`config.yaml` → `SOLUTION_TERMINAL.forbidden_targets` inclui `external_official`, e
`official_link_density` (checks.py:790) isenta explicitamente a terminal. Portanto a hipótese
do briefing ("P3 orienta como proceder NO PORTAL OFICIAL") não cabe na **última** página do
funil. Ajustei: o conteúdo de "como proceder no portal" vive nas soluções do miolo (que têm
link oficial verificado) e a terminal fecha com certificado/cuidados e recircula.

## A9. Registro de frases compartilhado

`runs/_phrase_registry.json` já tinha 4 aberturas de pré-sell todas no padrão
"Toque na opção certa e …". O padrão vem do próprio prompt
(`redator_presell.jinja:42`), e só o *payoff* varia. `opening_line_unique` reprova com
Jaccard ≥ 0,6. Os três funis desta missão rodaram **em sequência**, no mesmo `runs/`, de
propósito — é o que mantém a proteção anti-doorway viva entre eles.

## A10. `emotional_objective` é COPY VISÍVEL, não instrução — e isso não está no contrato do card

`steps.py:190-195` (`_qualifier_questions_for`): "Each solution's `emotional_objective`
(or its h1) becomes a neutral 'caso -> caminho' criterion". O `redator_presell.jinja:35`
renderiza cada um como `- se o seu caso é {{ q.caso }} → caminho de {{ q.solucao }}`.

**Consequência medida** (run 2 do SENAC, p2): objetivos escritos em voz de instrução
vazaram literalmente para o leitor —

> "Se o seu caso é **separar níveis de ensino que o leitor costuma tratar como a mesma
> coisa**, toque no caminho de Tipos de curso do Senac…"
> "Se o seu caso é **levar o leitor à página de bolsas do Departamento Regional, que é
> onde a vaga gratuita realmente aparece, sem prometer gratuidade universal**, toque…"

A segunda frase é a *minha* instrução ao motor, com ressalva de compliance e tudo, impressa
para o leitor. Nada reprova isso: nenhum validador olha a voz do texto.

**Correção aplicada**: reescrevi os 15 `emotional_objective` como **o caso do leitor**
("Você ainda mistura curso livre, curso técnico e curso superior e não sabe qual serve para
o seu objetivo"). Nenhuma mudança no motor.

**Sugestão para o Codex**: documentar isso no contrato do card (`briefing_volc.py` e a tela
do Pautador). Hoje `emotional_objective` parece um campo interno e é, na pré-sell, texto de
primeira pessoa para o leitor. Quem preenche o card no Pautador não tem como saber.

## A11. `critical_fact_grounding` pode arrastar fonte de notícia para dentro do artigo

Medido (run 2, p2): a pré-sell precisou do critério de renda do PSG, citou o valor do
salário mínimo, e o `critical_fact_grounding` exigiu a URL da fonte **literalmente no
corpo**. A `fonte_primaria` que a pesquisa trouxe para esse número foi
`cnnbrasil.com.br/economia/financas/governo-oficializa-salario-minimo-...` — e o link da CNN
foi parar num guia sobre o Senac.

O gate funcionou como projetado (número ancorado em fonte), mas o resultado contraria
"links externos devem identificar o portal oficial": a fonte oficial do salário mínimo é o
decreto no Planalto, que o `HttpUrlVerifier` não conseguiu abrir (`ReadError`).

**Correção aplicada**: reescrevi o H2 da pré-sell que puxava o critério de renda
("Quem procura vaga sem pagar mensalidade" → "Quem quer saber onde as vagas sem mensalidade
são anunciadas"), movendo o "quem se enquadra" para a página onde a fonte é o próprio Senac.

**Sugestão**: o contrato factual poderia ranquear `fonte_primaria` por tipo de domínio
(órgão > instituição > imprensa) antes de aceitar, ou ao menos sinalizar no relatório quando
a fonte de um número é imprensa.

## A12. Deep link cai na raiz quando o portal bloqueia o navegador automatizado

`canal_profundo.aprofundar` é chamado (steps.py:1137-1141) e é fail-safe: qualquer problema
devolve a raiz. Com Playwright instalado, os `official_links` do run 2 ainda saíram como
`https://www.sp.senac.br/` e `https://www.gov.br/mec/pt-br` — raízes.

Causa provável: os mesmos WAFs que devolvem 403 ao httpx também barram o Chromium headless,
então `colher_links` volta vazio e o fail-safe mantém a raiz. O comportamento é correto (raiz
viva > URL inventada morta), mas o leitor ainda cai na home. Vale registrar como pendência
real de qualidade de link, não como bug.

## A13. Por que os canais oficiais mais autoritativos não passam no verificador — causas medidas

Diagnóstico feito com o httpx do próprio venv do motor, variando um parâmetro por vez:

**`https://www.ead.senac.br/`** → `ConnectError: [SSL: DH_KEY_TOO_SMALL] dh key too small`
em **todas** as combinações (8s, 30s, UA de navegador, HTTP/1.1). O portal EAD do Senac
negocia TLS com uma chave Diffie-Hellman abaixo do nível de segurança padrão do OpenSSL do
Python 3.14. **Não é bug do motor** — é fraqueza real do servidor, e recusar é o comportamento
correto. O `curl` do sistema aceita porque roda com outro nível de segurança.

**`https://www.planalto.gov.br/ccivil_03/...`** → discrimina por **User-Agent**:

| tentativa | resultado |
|---|---|
| httpx 8s, UA padrão | ReadTimeout |
| httpx 30s, UA padrão | ReadTimeout |
| httpx 30s, **UA de navegador** | **200** (22.148 bytes) |
| httpx 30s, HTTP/1.1, UA de navegador | **200** |

Ou seja: o Planalto responde, mas **não** para um cliente que se identifica honestamente.
Como o `HttpUrlVerifier` usa `FunnelForge-LinkCheck/1.0` e timeout de 8s
(`url_verifier_http.py:85`), **toda fonte legal brasileira no Planalto é sistematicamente
inverificável** — e o `critical_fact_grounding` depende justamente dela para ancorar número,
prazo e dispositivo legal.

**Consequência medida**: a página de gratuidade do SENAC morreu **duas vezes** em
`official_links_none`, porque as quatro fontes que a pesquisa devolveu eram
2 decretos no Planalto (UA), o portal do DN (WAF 403) e o EAD (DH fraco).

**Não alterei o motor** (o prompt manda relatar bloqueio estrutural em vez de mexer).
Contornei pelo input, reescrevendo a página para o vocabulário que leva a pesquisa às páginas
**regionais de bolsas**, que respondem 200.

**Sugestão para o Codex**, em ordem de valor:
1. Elevar o timeout do verificador para ~20s e reservar 8s só para o primeiro salto —
   o Planalto responde em ~10-15s.
2. Manter o UA honesto, mas registrar `bloqueado_por_ua` separado de `inexistente`, para o
   operador ver que a fonte existe e o problema é de identificação.
3. Considerar `verify=ssl_context_permissivo` **somente para leitura de verificação** em
   hosts `.gov.br`/institucionais com DH fraco — decisão de segurança, não minha.

## A14. `target_keywords` do card NÃO chega à pesquisa

`steps.py:534-537`: `deps.research.research(topic=page.h1_title, structure=structure, ...)`,
onde `structure` é só `"\n".join(page.main_content_structure)`. As `target_keywords` do card
alimentam o redator e o juiz, **nunca** a busca.

Consequência prática para quem monta card: **o único jeito de dirigir a pesquisa é o H1 e os
H2**. Foi assim que a página de gratuidade do SENAC precisou ser reescrita duas vezes — trocar
as keywords não teve efeito nenhum; o que mudou o resultado foi trocar o vocabulário do H1 e
da estrutura ("Programa Senac de Gratuidade"/"edital" → "bolsas de estudo"/"lista de bolsas
do seu estado"), porque é isso que vira consulta.

**Sugestão para o Codex**: ou passar as keywords para o `topic` da pesquisa, ou documentar na
tela do Pautador que keyword não influencia a busca — hoje um operador razoável assume que
influencia.

## A15. Armadilha de ambiente: o `.pth` do editable install parou de ser honrado no meio da sessão

Em 17/09/2026, com o venv funcionando desde as 18:35, `import funnelforge` e o console script
`.venv/bin/funnelforge` passaram a falhar com `ModuleNotFoundError` — **sem** ninguém mexer no
venv. Diagnóstico passo a passo:

- `__editable__.funnelforge-1.0.0.pth` existia, 85 bytes, conteúdo correto (`…/engine/src`);
- `site` processava `.pth` normalmente (um `.pth` de teste criado na hora **foi** aplicado);
- `site.makepath` devolvia o caminho certo, `os.path.exists` → `True`, e o caminho **não** estava
  em `known_paths`. Ou seja: todas as condições de `site.addpackage` satisfeitas;
- mesmo assim `sys.path` não continha `…/engine/src`.

O arquivo carregava o xattr `com.apple.provenance`. **Reescrever o arquivo com o mesmo conteúdo
resolveu na hora** — import e CLI voltaram.

Fica registrado porque o sintoma é péssimo: um run que começou antes continua funcionando (os
módulos já estão carregados) enquanto qualquer invocação nova falha. Se acontecer de novo:
reescrever o `.pth` ou refazer `pip install -e .`, e **não** concluir que o venv sumiu.
