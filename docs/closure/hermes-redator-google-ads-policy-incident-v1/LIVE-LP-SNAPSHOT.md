# LIVE LP SNAPSHOT — initial public preservation

Captured at: 2026-09-03T00:51:32.267526+00:00

Requested URL: `https://creditoup.com.br/r/fgts-saque-aniversario/`

Raw sanitized JSON: `evidence-public/public-lp-snapshot.json`

## Variant: common_desktop
- Status: `200`
- Final URL: `https://creditoup.com.br/r/fgts-saque-aniversario/`
- HTML SHA256: `7c674d1d7daf896eb7992f9e61f8d8b598b6a28c9acaaeeb29037be6958dcd59`
- HTML bytes: `174243`
- Canonical: `['https://creditoup.com.br/r/fgts-saque-aniversario/']`
- Links captured: `25`
- Forms captured: `1`
- Inputs captured: `1`
- Scripts captured: `37`
- Iframes captured: `1`

## Variant: common_mobile
- Status: `200`
- Final URL: `https://creditoup.com.br/r/fgts-saque-aniversario/`
- HTML SHA256: `4077b30e43900f88cdbf6a529527dbb0a8526897abf4b9182471e533b95e30a1`
- HTML bytes: `174216`
- Canonical: `['https://creditoup.com.br/r/fgts-saque-aniversario/']`
- Links captured: `25`
- Forms captured: `1`
- Inputs captured: `1`
- Scripts captured: `37`
- Iframes captured: `1`

## Variant: googlebot
- Status: `200`
- Final URL: `https://creditoup.com.br/r/fgts-saque-aniversario/`
- HTML SHA256: `7c674d1d7daf896eb7992f9e61f8d8b598b6a28c9acaaeeb29037be6958dcd59`
- HTML bytes: `174243`
- Canonical: `['https://creditoup.com.br/r/fgts-saque-aniversario/']`
- Links captured: `25`
- Forms captured: `1`
- Inputs captured: `1`
- Scripts captured: `37`
- Iframes captured: `1`

## Browser visual observation — desktop snapshot

Observed via sandboxed browser after network/HTML preservation. The visible page showed:

- Branding: `Crédito Up` logo/name in the header, not Caixa/Gov logo.
- Hero title: `Saque-Aniversário do FGTS`.
- Subtitle: `Regras, prazos e simulação para 2026 — toque abaixo e veja como avaliar as vantagens ou ativar a modalidade`.
- Primary visible CTAs/buttons:
  - `Comparar as Vantagens e Desvantagens para ver qual é o seu caso` (orange).
  - `Ver o passo a passo para Ativar o Saque-Aniversário no Aplicativo` (bright green).
  - `Entender como funciona a Antecipação do Saque-Aniversário` (green).
- Government/Caixa visual elements: no official Caixa logo was visible in the initial desktop viewport, but the text repeatedly references `Caixa` / `Caixa Econômica Federal` as the administering institution.
- Form evidence: HTML parser captured one form and one input; visual desktop viewport did not show an above-the-fold data collection form.
- Footer identity/navigation links visible: `Sobre Nós`, `Contato`, `Política de Privacidade`, `Termos`, plus `2026 © Crédito Up!`.

This observation is descriptive evidence only; it does not confirm the Google suspension cause.

---

## Correção e complemento — 2026-09-03, releitura ao vivo

### A cadeia de redirecionamento NÃO tinha sido capturada

O JSON acima registra, nas três variantes, `redirect_chain: [{ "error":
"TypeError: OpenerDirector.open() got an unexpected keyword argument 'context'" }]`.
Ou seja: o campo existia, mas **nenhum salto foi medido** — a leitura falhou.
Isso foi refeito com `fetch_public_https_chain`, que preserva a cadeia:

| leitura | user-agent | status | saltos | sha256 | bytes |
|---|---|---:|---:|---|---:|
| `live_user` | Chrome 124 desktop | `200` | **0** | `7c674d1d7daf896e…` | 174 243 |
| `live_googlebot` | `Googlebot/2.1` | `200` | **0** | `7c674d1d7daf896e…` | 174 243 |

**Zero redirecionamentos**, e o HTML servido ao Googlebot é **byte a byte
idêntico** ao servido ao usuário — e idêntico ao preservado ~30 min antes.

### Cabeçalhos de resposta

`server: nginx/1.24.0 (Ubuntu)` · `content-type: text/html; charset=UTF-8` ·
`x-content-type-options: nosniff` · `referrer-policy: strict-origin-when-cross-origin`.
**Sem** HSTS e **sem** CSP — endurecimento recomendado, não exigido por política.

### DNS e TLS (checagem pública, sem credencial)

| host | A/AAAA | TLS | emissor | validade | SAN |
|---|---|---|---|---|---|
| `creditoup.com.br` | `5.161.111.86` | TLSv1.3 | Let's Encrypt | 01/08/2026 → 30/10/2026 | `creditoup.com.br`, `www.creditoup.com.br` |
| `portalmundomais.com` | Cloudflare (4 IPs) | TLSv1.3 | Google Trust Services | 15/07/2026 → 13/10/2026 | `portalmundomais.com`, `*.portalmundomais.com` |

`https://portalmundomais.com/` e `https://portalmundomais.com/sitemap_index.xml`
responderam **HTTP 410 Gone**.

### Safe Browsing

**Não consultado.** A leitura autoritativa exige chave de API, e o relatório de
transparência depende de JavaScript. Registrado como `unavailable`, não como
"limpo" — a missão permite consulta pública apenas se não exigir credencial.

### Diferença desktop × mobile — o que ela é, e o que não é

Desktop e mobile diferem em **27 bytes**, em dois pontos:
o token rotativo `AI_WEB_PUSH_PID` e o comentário de cache do WP Rocket.
**Isso não é cloaking.** Cloaking é divergência entre rastreador e usuário, e
nessa dimensão a evidência mostra igualdade exata. Ver `ENGINE-CHANGES.md` §5.

### Destinos `/r/` adicionais preservados no mesmo dia

| destino | sha256 | bytes | palavras visíveis |
|---|---|---:|---:|
| `/r/antecipacao-saque-aniversario-fgts/` | `0dbafa0dd1e4…` | 165 134 | 763 |
| `/r/maquininha-de-cartao-menor-taxa/` | `c1cfcab72d7a…` | 174 355 | 840 |
| `/r/nova-carteira-identidade-nacional-2026/` | `7e0f296129e5…` | 172 462 | 875 |

Os recibos do portão para todos estão em `GATE-RECEIPTS.json`.
