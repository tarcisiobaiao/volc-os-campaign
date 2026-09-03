# HERMES_CODEX_REVIEW — revisão adversarial do delta

Data: 2026-09-03
Branch: `sprint/hermes-redator-google-ads-policy-incident-v1`
Base: `382c5d4c67fc521d5e6739f8e76d1c36a96fdb53`

## Resultado

**Sem bloqueante remanescente reproduzido após a rodada corretiva única.**

## Achado bloqueante reproduzido na revisão

A primeira versão do executor afirmava cobertura de contraprovas A–X, mas o teste
rotulava uma lista derivada e não a enumeração literal do briefing. A revisão da
Bia reproduziu a lacuna adicionando testes `test_brief_a_*` até `test_brief_x_*`.
Na primeira execução, 6/52 falharam:

- link visível `Caixa` apontando para outro domínio só virava `LINK_EXTERNO_NAO_CLASSIFICADO`, sem achado explícito de marca governamental com destino divergente;
- campo `token`/`OTP` não era classificado como sensível;
- redirecionamento JavaScript pós-carregamento não era detectado;
- script externo não declarado era risco, não bloqueio para `paid_destination`;
- o teste documental do appeal usava caminho incorreto;
- uma contraprova de bridge page precisava de densidade de botões suficiente para medir a razão.

## Correção aplicada

- Novo achado `MARCA_GOVERNAMENTAL_COM_DESTINO_DIVERGENTE`.
- Novo achado `SCRIPT_REDIRECIONA_CLIENT_SIDE`.
- `token`/`OTP` entram na assinatura de campo sensível.
- `SCRIPT_TERCEIRO_NAO_DECLARADO` passou a bloquear em papel estrito.
- `fontes_politica.json` atualizado para 33 regras, todas com URL oficial Google.
- Testes literais A–X corrigidos e estabilizados.
- `GOOGLE-POLICY-MATRIX.json` e `GATE-RECEIPTS.json` regenerados.

## Gates reexecutados após correção

- `backend`: **154 passed, 31 skipped**.
- `funnelforge`: **158 passed**.
- `auditar_landing_policy.py --matriz`: **33 regras**.
- `auditar_landing_policy.py --evidencia`: **5 recibos, 5 blocked, 0 ready**.
- `inventariar_landing_r.py --ao-vivo`: **58 rotas, 14 destinos pagos, 7 com anúncio**.
- `gate_sem_mutacao_google.py`: **3/3 ok**.
- `git diff --check`: limpo.
- `scripts/verificar_segredos.py`: nenhum padrão forte.
- Scan contextual de raw Google Ads IDs/credenciais: ok; candidatos restantes são hashes/process IDs/CNPJ público ou evidência pública de site, não IDs de conta.
- Scan de superfície externa não-GET em código novo: ok.

## Revisão por eixo

| eixo | veredito |
|---|---|
| falsa afiliação governo/Caixa | coberta e reforçada após correção |
| coleta de dados / credenciais / OTP | coberta após correção |
| redirect/cloaking | server-side/crawler coberto; client-side JS coberto após correção |
| bridge page / conteúdo original | coberto |
| claims financeiros/disclosures | coberto |
| governo/documentos/serviços | coberto |
| bypass por tipo de página | coberto: `paid_destination` separado de editorial e ponto de campanha força papel pago |
| falso verde / unknown | coberto: unknown impede `paid_destination_ready` |
| alteração HTML depois do gate | coberto por `live_drift`; ainda exige hash aprovado em produção |
| appeal com alegação não provada | rascunho diz não enviado e não afirma causa confirmada |

## Limitação honesta

O ponto de pré-publicação WordPress não foi ligado porque `backend/app/routers/publicacao.py` estava proibido por colisão com Terminal 2. O patch/handoff exato está em `HANDOFF-PATCH-PUBLICACAO.md`.
