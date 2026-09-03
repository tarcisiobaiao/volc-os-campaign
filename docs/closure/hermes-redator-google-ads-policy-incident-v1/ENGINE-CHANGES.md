# ENGINE CHANGES — o que foi implementado localmente

Branch `sprint/hermes-redator-google-ads-policy-incident-v1`, base `382c5d4`.
**Nenhum deploy. Nenhuma escrita em WordPress, Google Ads, Supabase ou Search
Console.** Todo o efeito desta entrega é local ao repositório.

---

## 1 · Novo pacote — `backend/app/landing_policy/`

Clean Architecture pragmática, como pede o `CLAUDE.md`: domínio puro, aplicação,
e nenhum I/O dentro do pacote (a leitura de rede vive no adaptador de
`publisher_quality`).

| arquivo | camada | o que é |
|---|---|---|
| `contrato.py` | domínio | papéis, pontos de portão, vocabulário de evidência, tabela de severidade por papel, exigências por ponto, versão da política por hash |
| `varredura.py` | domínio | nove varreduras PURAS sobre HTML — identidade, links, formulários, alegações, governo, conteúdo, segurança, redirecionamento/cloaking, deriva |
| `portao.py` | aplicação | junta as varreduras, classifica por papel, fecha por ausência, decide o veredito |
| `recibo.py` | aplicação | monta o `LandingPolicyGateReceipt` determinístico |
| `fontes_politica.json` | dado canônico | 33 regras × 8 campos, todas com URL oficial do Google |
| `__init__.py` | fachada | ponto de entrada único do pacote |

### Decisões que valem registro

- **Status é parte do resultado.** `Verificacao` carrega `status` além de
  `achados`, com o mesmo vocabulário de `publisher_quality.snapshot`. Dois
  vocabulários de "não sei" seriam dois jeitos de esconder a mesma ausência.
- **Varredura que explode vira `failed`, não silêncio.** A exceção é capturada no
  portão e transformada em `desconhecido`, que reprova. Coberto por teste com
  `monkeypatch`.
- **Versão da política é hash, não número.** Número manual mente quando alguém
  edita a matriz e esquece de incrementá-lo.
- **`elegibilidade_de_destino_de_campanha()` força o papel.** O portão não é
  desligável por configuração do chamador.

## 2 · Extensão — `backend/app/publisher_quality/fetch.py`

Duas adições, **sem tocar** no que existia:

- `USER_AGENT_PADRAO` — extraído para constante nomeada. A comparação
  rastreador × usuário precisa pedir a mesma página com user-agents diferentes e
  conhecidos; um literal repetido em dois arquivos é como as duas leituras
  deixam de ser comparáveis.
- `fetch_public_https_chain()` — leitura pública que **preserva a cadeia de
  redirecionamento**, aceita `user_agent`, devolve status/headers/sha256, e
  tolera resposta de erro HTTP (um destino que devolve 404 ao AdsBot é
  justamente o que a política descreve; levantar exceção apagaria a evidência).
  Reusa `validate_public_https_target` **inalterada** — mesma validação
  fail-closed na URL inicial, em cada salto e na URL final.
- `_RecordingRedirectHandler` valida **antes** de anotar. Anotar antes
  transformaria a cadeia em registro do que foi TENTADO; ela precisa ser registro
  do que foi permitido. Coberto por teste.

`fetch_public_https_once` continua com assinatura e comportamento idênticos —
`test_publisher_quality_snapshot.py` passa sem alteração.

## 3 · Testes — 78 novos, todos herméticos

| arquivo | testes | o que prova |
|---|---:|---|
| `test_landing_policy_contraprovas.py` | 27 | as 24 contraprovas A–X + 3 sobre a fronteira de papel |
| `test_landing_policy_portao.py` | 26 | contrato, fecha-por-ausência, papel, fonte oficial, recibo |
| `test_landing_policy_regressao_fgts.py` | 8 | a regressão permanente do funil FGTS |
| `test_publisher_quality_fetch_seguro.py` | 17 | SSRF, redirecionamento, normalização, teto de bytes |

Nenhum abre socket. Nenhum lê conta do Google. Nenhum escreve em site.

## 4 · Scripts

- `scripts/inventariar_landing_r.py` — inventário `/r/*` de três fontes
  independentes (conta sanitizada, artefatos do repositório, sitemap público).
  Offline por padrão; `--ao-vivo` lê `robots.txt` e os sitemaps declarados com
  pausa de 2 s. **Não rasteja, não abre página, não envia formulário.**
- `scripts/auditar_landing_policy.py` — roda o portão sobre a evidência
  preservada e emite `GATE-RECEIPTS.json`; `--matriz` regenera a cópia da matriz
  no pacote de fechamento; `--ao-vivo <url>` faz duas leituras públicas
  (usuário + rastreador) com pausa de 3 s. Nenhum modo escreve fora de
  `docs/closure/`.

## 5 · Um defeito real encontrado E CORRIGIDO durante a implementação

A primeira versão de `varrer_redirecionamento` acusava cloaking sempre que duas
variantes quaisquer divergissem. Rodando sobre a preservação real, ela acusou
`/r/fgts-saque-aniversario/` — porque desktop e mobile diferem em 27 bytes (um
token rotativo de push), enquanto **o Googlebot devolveu HTML byte a byte igual
ao do desktop**. A evidência dizia o contrário da acusação.

Num pacote de apelação isso seria pior que inútil: seria uma **admissão falsa**.
A regra que ficou exige uma variante rotulada como rastreador e compara o hash
dela contra os hashes humanos; divergência entre variantes humanas vai para o
inventário como observação de dispositivo, sem virar achado. Duas contraprovas
travam o conserto nos dois sentidos.

## 6 · O que NÃO foi tocado

- `backend/app/routers/publicacao.py` — colisão com Terminal 2. O ponto de
  portão 2 vai como patch exato em `HANDOFF-PATCH-PUBLICACAO.md`.
- `funnelforge-migracao/engine/**` — o motor não foi alterado nesta entrega. O
  contrato novo consome artefato do motor; a integração dentro do pipeline é
  trabalho seguinte, descrito em `LIVE-REMEDIATION-PLAN.md`.
- Roadmap, curadoria e grafo — apenas `CURATION-HANDOFF.json`, como manda o
  protocolo de trabalho paralelo do `CLAUDE.md`.
- Frontend — nenhuma superfície de UI foi exigida por esta missão; nada em
  `src/` foi alterado, e por isso nenhum gate de TypeScript/build é aplicável.
