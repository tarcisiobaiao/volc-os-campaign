# GATES — o que foi rodado, com que saída

Executado em **2026-09-03**, worktree
`/root/work/volc-runs/hermes-redator-google-ads-policy-incident-v1`,
branch `sprint/hermes-redator-google-ads-policy-incident-v1`, base `382c5d4`.

---

## 1 · Resultado, em uma tabela

| gate | comando | saída |
|---|---|---|
| Bateria focal do backend (redator + publisher quality + landing policy + publicação) | `python3 -m pytest backend/tests/{11 arquivos} -q` | **154 passed, 31 skipped** |
| Contraprovas A–X | `pytest backend/tests/test_landing_policy_contraprovas.py -q` | **52 passed** |
| Portão / contrato / recibo | `pytest backend/tests/test_landing_policy_portao.py -q` | **26 passed** |
| Regressão permanente FGTS | `pytest backend/tests/test_landing_policy_regressao_fgts.py -q` | **7 passed** |
| SSRF / redirecionamento / leitura pública | `pytest backend/tests/test_publisher_quality_fetch_seguro.py -q` | **17 passed** |
| Validadores do FunnelForge (linha de base, não tocados) | `PYTHONPATH=src pytest tests/test_{identity_compliance,gate_fail_closed,route_validators,validators,doctrine,doctrine_validators}.py -q` | **158 passed** |
| Inventário `/r` | `python3 scripts/inventariar_landing_r.py --ao-vivo` | 58 rotas · 14 destinos pagos · 7 com anúncio |
| Varredura de link/formulário/alegação + recibos | `python3 scripts/auditar_landing_policy.py` | 33 regras na matriz · **5 recibos · 5 `blocked` · 0 `paid_destination_ready`** |
| Comparação rastreador × usuário | leitura pública dupla, 2026-09-03 | HTML **byte a byte idêntico** (`7c674d1d7daf…`, 174 243 B) |
| Ausência de mutação no Google Ads | `python3 scripts/gate_sem_mutacao_google.py` | **3/3 ok**, 5 contraprovas focais com sentinela no executor |
| Whitespace do diff | `git diff --check` | limpo |
| Varredura de segredos | `python3 scripts/verificar_segredos.py` | "nenhum padrão forte encontrado" |
| Varredura de ID cru do Google Ads | regex sobre os 32 arquivos novos/alterados | **0 identificadores reais** (7 candidatos, todos atribuídos — ver §4) |
| TypeScript / build | — | **não aplicável**: nenhum arquivo em `src/` foi alterado |

Nenhum gate falhou. Nenhum gate foi pulado sem motivo declarado.

### Nota sobre `PYTHONPATH=src`

Os testes do FunnelForge não coletam com `pytest` direto: o pacote é instalado
via `pip install -e` no `.venv` do motor, que não existe neste worktree.
`PYTHONPATH=src` é o equivalente honesto — sem ele o resultado é
`ModuleNotFoundError`, e "6 errors during collection" seria lido como falha de
código quando é falha de ambiente. Registrado aqui para não virar mistério.

---

## 2 · As contraprovas A–X

O briefing enumera "contraprovas A–X" literalmente. O arquivo de testes guarda
as 24 provas originais por requisito e, após a revisão adversarial da Bia, uma
segunda camada com a nomenclatura explícita do incidente (`test_brief_a_*` até
`test_brief_x_*`). Cada uma monta uma página sintética que um humano razoável
reprovaria, e exige que o portão reprove **pelo código certo** — não por acidente
de outro achado. Todas em
`backend/tests/test_landing_policy_contraprovas.py`.

| # | contraprova | código exigido | requisito |
|---|---|---|---|
| A | destino pago sem identidade de operador | `IDENTIDADE_OPERADOR_AUSENTE` | identidade |
| B | CNPJ da página diverge do CNPJ do operador | `IDENTIDADE_CNPJ_DIVERGENTE` | não inventar CNPJ |
| C | credencial inventada ("licenciados pelo Banco Central") | `IDENTIDADE_CREDENCIAL_NAO_COMPROVADA` | não inventar licença |
| D | marca de terceiro como parceira, sem lastro | `MARCA_TERCEIRA_SEM_LASTRO` | não inventar parceria |
| E | órgão público citado sem aviso de não-vínculo | `AVISO_NAO_OFICIAL_AUSENTE` + `AFILIACAO_GOVERNAMENTAL_IMPLICITA` | serviço governamental |
| F | link de governo com âncora de valor | `LINK_GOVERNO_COM_ANCORA_DE_VALOR` | serviço governamental |
| G | botão principal apontando para site de governo | `AFILIACAO_GOVERNAMENTAL_IMPLICITA` | serviço governamental |
| H | oferta de aquisição de documento restrito | `SERVICO_GOVERNAMENTAL_RESTRITO` | serviço governamental |
| I | host externo sem lastro | `LINK_EXTERNO_NAO_CLASSIFICADO` | classes de link externo |
| **J** | **host declarado pela evidência PASSA** | ausência do código | classes de link externo |
| K | botão para terceiro não autorizado | `BOTAO_PARA_TERCEIRO_NAO_AUTORIZADO` | classes de link externo |
| L | campo de senha no destino | `CAMPO_CREDENCIAL_OBSERVADO` | dado sensível |
| M | coleta de CPF no destino pago | `FORMULARIO_DADO_SENSIVEL` | dado sensível |
| **N** | **busca do WordPress NÃO é coleta** | ausência do código | dado sensível |
| O | promessa de resultado improvável | `ALEGACAO_DE_RESULTADO_IMPROVAVEL` | alegação financeira |
| **P** | sem divulgação reprova / **com divulgação passa** | `ALEGACAO_FINANCEIRA_SEM_DIVULGACAO` (dos dois lados) | divulgação |
| Q | valor monetário malformado vira risco | `VALOR_MONETARIO_MALFORMADO` | alegação financeira |
| R | conteúdo original insuficiente | `CONTEUDO_ORIGINAL_INSUFICIENTE` | originalidade |
| S | página-ponte | `PAGINA_PONTE` | bridge page |
| T | destino incongruente com a promessa do anúncio | `DESTINO_INCONGRUENTE_COM_ANUNCIO` | congruência |
| U | redirecionamento para fora do domínio | `REDIRECIONAMENTO_CROSS_DOMAIN` | redirecionamento |
| V | HTML diferente para rastreador e usuário | `DIVERGENCIA_RASTREADOR_USUARIO` | cloaking |
| **V₂** | **desktop ≠ mobile NÃO é cloaking** | ausência do código | cloaking |
| **V₃** | sem variante de rastreador, cloaking é `desconhecido` | entrada em `desconhecidos` | fecha por ausência |
| W | deriva do que foi aprovado | `DERIVA_AO_VIVO` | deriva ao vivo |
| X | conteúdo misto reprova / **namespace SVG não conta** | `CONTEUDO_MISTO` (dos dois lados) | segurança do destino |

As cinco em **negrito** são o simétrico: cenários legítimos que um portão
apressado reprovaria. Sem elas o portão seria só "tudo reprova", e a operação o
desligaria na primeira semana — que é a pior falha possível num portão.

### As contraprovas de "fecha por ausência"

Em `test_landing_policy_portao.py`, porque testam o portão e não uma página:

- verificação exigida `unavailable` impede o verde;
- sem hash aprovado, a deriva é desconhecida e **não** limpa;
- varredura que levanta exceção vira `failed` e reprova (com `monkeypatch`);
- antes de publicar, redirecionamento **não** é exigido (ausência estrutural
  não é buraco);
- código novo sem classificação bloqueia no papel estrito;
- papel não-pago nunca declara `paid_destination_ready`;
- `elegibilidade_de_destino_de_campanha` **força** o papel pago.

### A regressão permanente FGTS

`test_landing_policy_regressao_fgts.py`, 7 testes. Roda por dois caminhos:

1. **Excerto sanitizado embutido** — trechos literais de
   `funnelforge-migracao/referencia/run-fgts-producao` e `funil-no-ar`, reduzidos
   ao mínimo que carrega os defeitos. Vale mesmo se a pasta `referencia/` for
   arquivada. Um teste prova que o excerto não carrega segredo.
2. **Artefatos reais**, quando presentes: `funnel_plan.json`,
   `*.lp_content.json`, `texto/LP.md`, `INVENTARIO.md`.

Os quatro defeitos que o portão de hoje precisa nomear no funil de ontem:
`ALEGACAO_DE_RESULTADO_IMPROVAVEL`, `MARCA_TERCEIRA_SEM_LASTRO`,
`AVISO_NAO_OFICIAL_AUSENTE`, `AFILIACAO_GOVERNAMENTAL_IMPLICITA`.

---

## 3 · Recibos emitidos sobre a evidência preservada

`GATE-RECEIPTS.json`, versão de política `df252bc25e636d78`.

| destino | veredito | bloqueios | desconhecidos |
|---|---|---|---|
| `/r/antecipacao-saque-aniversario-fgts/` | `blocked` | 7 códigos | `live_drift`, `redirect_and_cloaking` |
| `/r/fgts-saque-aniversario/` (desktop/googlebot) | `blocked` | `LINK_EXTERNO_NAO_CLASSIFICADO`, `LINK_GOVERNO_COM_ANCORA_DE_VALOR` | `live_drift` |
| `/r/fgts-saque-aniversario/` (mobile) | `blocked` | idem | `live_drift` |
| `/r/maquininha-de-cartao-menor-taxa/` | `blocked` | `LINK_EXTERNO_NAO_CLASSIFICADO` | `live_drift`, `redirect_and_cloaking` |
| `/r/nova-carteira-identidade-nacional-2026/` | `blocked` | `LINK_EXTERNO_NAO_CLASSIFICADO`, `SERVICO_GOVERNAMENTAL_RESTRITO` | `live_drift` |

`live_drift` é `unavailable` em todos porque **nenhum hash aprovado foi gravado
na publicação**. Essa lacuna é ela própria um achado — ver
`LIVE-REMEDIATION-PLAN.md`, item 5.

---

## 4 · Prova de contenção externa

| ato proibido | prova |
|---|---|
| mutação no Google Ads | `scripts/gate_sem_mutacao_google.py` 3/3 ok, com sentinela que falha o teste se o executor for chamado. Nenhuma leitura de conta foi feita nesta sessão de execução — a evidência sanitizada vem do passo anterior do Hermes. |
| escrita/publicação no WordPress | nenhuma requisição não-GET saiu deste worktree. As leituras públicas usam `fetch_public_https_chain`, que só monta `Request(..., method="GET")` sem cookie e sem autenticação. |
| deploy | nenhum comando de deploy executado; nada em `src/`, `api/` ou `vercel.json` foi alterado. |
| escrita/migração no Supabase | nenhuma conexão ao Supabase foi aberta. |
| mutação no Search Console | não acessado. |
| Postiz / AdsPower / n8n | não acessados. |
| apelação enviada | **não enviada.** `APPEAL-DRAFT.md` é rascunho local, e diz isso no próprio cabeçalho. |
| roadmap / curadoria / grafo | não editados; o delta vai em `CURATION-HANDOFF.json`. |

Cada recibo emitido carrega `external_mutation` com os quatro `false` — a prova
viaja no artefato, não numa frase de relatório.

### Varredura de ID cru do Google Ads

Regex sobre os arquivos novos/alterados, procurando `NNN-NNN-NNNN`,
10 dígitos consecutivos, e nomes de credencial (`developer_token`,
`refresh_token`, `client_secret`, `login_customer_id`). **7 candidatos, todos
atribuídos e nenhum real:**

| candidato | arquivo | o que é de fato |
|---|---|---|
| `8878636057` | `COORDINATION-LOG.md` | pedaço de `proc_0e8878636057`, id de processo do Hermes |
| `6234542683` (×4) | `GATE-RECEIPTS.json` | substring de dígitos dentro de um sha256 de inventário |
| `1837582566` | `GATE-RECEIPTS.json` | idem |
| `0863450300` | `ROOT-CAUSE-ANALYSIS.md` | pedaço de `df252bc25e636d78`, a versão da política |

`account-evidence-sanitized.json` usa apenas pseudônimos (`CUST_001`…`CUST_013`,
`CUST_010_CAMP_001`…). Nenhum ID de cliente, campanha, grupo ou anúncio real
está versionado.

---

## 5 · Limitações destes gates, ditas antes que alguém conclua sozinho

- **Não são inspeção de rede.** Provam ausência de chamada de mutação na rota
  testada e ausência de método não-GET no código escrito; não provam o que
  outro processo desta máquina fez.
- **O portão lê HTML, não a intenção do revisor.** `paid_destination_ready` é a
  afirmação estreita descrita em `REDATOR-POLICY-CONTRACT.md` §8.
- **Nenhum gate confirma a causa da suspensão.** Isso exige a notificação
  literal; ver `ACCOUNT-EVIDENCE.md`.
- **O ponto de portão 2 não está ligado.** `publicacao.py` é reservado nesta
  missão; o patch exato está em `HANDOFF-PATCH-PUBLICACAO.md` e ainda não foi
  aplicado por ninguém.
