# FunnelForge — autenticação "Sign in with ChatGPT" (`auth_mode`)

Estado em 07/10/2026: **login real, catálogo real e canário real concluídos** (ver
"Prova real" abaixo). O modo `api_key` continua o padrão do `config.yaml` e não mudou.

## Modos

| `openai.auth_mode` | O que faz | Cobrança |
|---|---|---|
| `api_key` (padrão) | LiteLLM com as chaves do `.env`, como sempre | API faturada |
| `chatgpt_plan` | passos `chatgpt/<modelo>` vão à Responses API com o token do plano; o resto segue no LiteLLM | uso do plano ChatGPT (não é API faturada; limites do plano valem) |

Sem fallback silencioso: um passo do plano nunca cai para um modelo faturado
(`allow_api_key_fallback: false` remove/recusa o fallback), erro do plano não
chama o LiteLLM, e o servidor devolver outro modelo é erro. `somente_plano: true`
impede o run de começar se algum passo for faturado.

## Fonte oficial (consultada em 07/10/2026)

- Endpoints, parâmetros e escopo: https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- Inferência (`/v1/responses`, `store:false`, `stream:true`, `/v1/models`): https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
- Erros: https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery
- Tokens (1 h; refresh de 30 dias, rotativo): https://developers.openai.com/siwc/token-sharing-open-source/token-reference
- Elegibilidade: o programa é para apps **open-source e hospedados localmente**;
  app pago ou hospedado remotamente usa o formulário
  https://openai.com/form/sign-in-with-chatgpt-interest/
- `gpt-6.1-sol` (https://developers.openai.com/api/docs/models/gpt-6.1-sol):
  listado como "API only"; disponibilidade no plano só se confirma em
  `GET /v1/models` com o token. O run confere antes da primeira chamada.

Não documentado para o fluxo do plano e, por isso, recusado com erro:
busca na web (pesquisa), entrada com imagem (revisão de imagem), geração de
imagem. `reasoning.effort` e `text.format` são enviados só quando o passo pede.

## client_id

O VOLC usa o PRÓPRIO `client_id` (`oaiapp_...`), público, em `openai.client_id`.
Duas formas oficiais de obtê-lo:
1. formulário de interesse (app pago ou hospedado remotamente);
2. registro dinâmico no primeiro login (`--registrar-dinamico`), previsto para
   apps open-source/hospedados localmente: usa `client_id=dynamic_agent_client`,
   `agent_name_hint="VOLC FunnelForge"` e um `ext_agent_host_id` gerado e
   guardado por host; o callback devolve o `client_id` emitido.

## Comandos

```bash
cd funnelforge-migracao/engine
funnelforge auth login --provider chatgpt [--client-id oaiapp_...] [--registrar-dinamico]
funnelforge auth status        # modo, conexão, expiração do acesso; nunca o token
funnelforge auth logout        # apaga a sessão local
funnelforge run-volc <arquitetura.json> --canario
```

`--canario`: `publish=false`, `publish_status=draft`, publisher e gerador de
imagem desligados, imagens não exercitadas, teto de 40 chamadas (ou
`run.max_chamadas_llm`), artefatos em `runs-canario/<run_id>/` e
`recibo_canario.json` (auth_mode, modelo pedido/servido, esforço, tentativas,
tokens, portões, custo "não aplicável — uso do plano", prova de não publicação).

## Onde fica a sessão

Keychain do macOS (serviço `volc-funnelforge.chatgpt`, conta `perfil-oauth`) ou,
com `armazenamento: arquivo`, `~/Library/Application Support/volc-funnelforge/
perfil-chatgpt.json` (diretório 700, arquivo 600, escrita atômica, fora do
repositório). Renovação com trava de arquivo e releitura antes de girar o
refresh token. Limite conhecido do Keychain: o valor passa por argumento do
`security` (visível por instantes na tabela de processos do próprio usuário).

## Prova real (07/10/2026)

- Registro dinâmico oficial: `client_id=dynamic_agent_client`, `agent_name_hint=VOLC
  FunnelForge`, `ext_agent_host_id=urn:uuid:<UUID do host>` (o formato `volc-<hex>` foi
  recusado com `invalid_authorize_request`; o exemplo oficial é `urn:uuid:`), callback em
  `127.0.0.1:1455`, PKCE S256, `state` e `nonce` novos. Emitido `oaiapp_HiCdd…`, guardado
  neste host fora do repositório.
- ID token validado: assinatura RS256 pelo JWKS do emissor (via httpx; o `urllib` deste
  Python não tem pacote de CAs), `iss`, `aud` = client_id emitido, `nonce`, `exp`.
- Escopos concedidos: `openid profile email offline_access resource.invoke
  chatgpt.tokens.use.direct`. Tokens no Keychain.
- Catálogo (`GET /v1/models`, visíveis): gpt-6.1-sol, gpt-6-astra, gpt-6-sol, gpt-6-luna,
  gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna. `reasoning.effort` aceito (gpt-6.1-sol: low…ultra).
- Inferência mínima (`store:false`): gpt-6.1-sol/high e gpt-6-sol/medium, servido = pedido.
- Canário: `canarios/chatgpt-plan-20261007/` (fora do repo), 26 chamadas, todas
  `chatgpt_plan`, custo de API faturada US$ 0,00, nada publicado. Ver P10-T23.

Rodar o canário de novo (do diretório do canário, sem `.env`):

```bash
PYTHONPATH=<engine>/src python -c "from funnelforge.cli import app; app()" run-volc \
  <engine>/tests/fixtures/jornada_senac/arquitetura.json --canario \
  --fatos-de <engine>/tests/fixtures/state_run_220001.json
```
