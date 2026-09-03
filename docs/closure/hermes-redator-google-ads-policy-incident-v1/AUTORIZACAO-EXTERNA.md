# AUTORIZAÇÃO EXTERNA — o que exige decisão humana antes de acontecer

Este pacote é **inteiramente local**. Nenhum ato abaixo foi executado. A lista
existe para que o operador autorize item a item, com o custo e o risco à vista —
e para que ninguém "resolva" o incidente de um jeito que o agrave.

---

## 1 · O que este trabalho NÃO fez

| ato | estado | prova |
|---|---|---|
| Mutação no Google Ads (campanha, anúncio, tracking, orçamento) | **não executado** | `scripts/gate_sem_mutacao_google.py` 3/3, com sentinela no executor |
| Reativação/retomada de campanha | **não executado** | nenhuma chamada de mutação existe no código escrito |
| Criação de conta Google Ads | **não executado** | — |
| Envio de apelação | **não executado** | `APPEAL-DRAFT.md` é rascunho e diz isso no cabeçalho |
| Escrita ou publicação no WordPress | **não executado** | só requisições GET públicas, sem cookie e sem autenticação |
| Alteração do destino ao vivo | **não executado** | os hashes de 2026-09-03 batem entre a preservação e a releitura |
| Deploy | **não executado** | nada em `src/`, `api/` ou `vercel.json` foi tocado |
| Escrita/migração no Supabase | **não executado** | nenhuma conexão aberta |
| Mutação no Search Console | **não executado** | não acessado |
| Postiz / AdsPower / n8n | **não executado** | não acessados |
| Edição de Roadmap / curadoria / grafo | **não executado** | delta em `CURATION-HANDOFF.json` |

Leituras públicas feitas, todas GET e com pausa entre requisições:
`robots.txt` e sitemaps de `creditoup.com.br`; a raiz e o sitemap de
`portalmundomais.com` (ambos HTTP 410); quatro páginas `/r/`; duas releituras da
LP com user-agents diferentes; consulta DNS e handshake TLS. **Sem rastejamento,
sem envio de formulário, sem acesso autenticado.**

---

## 2 · Autorizações pedidas, por prioridade

### P0 — obter a notificação literal de suspensão
**Quem:** operador, na conta suspensa (in-account + e-mail).
**Por quê:** sem ela, toda conclusão sobre a causa é inferência, e a apelação
responde à política errada.
**Risco de fazer:** nenhum. É leitura.
**Risco de não fazer:** a apelação vira chute; `ROOT-CAUSE-ANALYSIS.md`
permanece em `HYPOTHESIS_PARTIALLY_SUPPORTED`.

### P1 — executar a Fase A da remediação no WordPress
**Quem:** operador ou integrador com credencial de publicação.
**Escopo exato:** `LIVE-REMEDIATION-PLAN.md`, Fases A e B.
**Risco de fazer:** baixo — a evidência já está preservada com hash, então
corrigir agora não destrói prova.
**Risco de não fazer:** os destinos seguem com bloqueio; qualquer campanha nova
aponta para página que o portão reprova.
**Condição:** reauditar cada página corrigida e **gravar o hash aprovado**, sem
o que `DERIVA_AO_VIVO` continua immensurável.

### P2 — aplicar o patch do ponto de portão 2
**Quem:** integrador (arquivo em colisão com o Terminal 2).
**Escopo:** `HANDOFF-PATCH-PUBLICACAO.md`, incluindo as duas correções que o
próprio documento aponta.
**Risco de fazer:** publicação de LP com bloqueio passa a devolver 409 — é o
efeito pretendido, mas muda comportamento visível ao operador.

### P3 — decidir o destino de `portalmundomais.com`
**Quem:** operador.
**Fato:** o domínio responde **HTTP 410** na raiz e no sitemap; 4 rotas `/r/` só
existem na evidência da conta. As campanhas correspondentes estão
`PAUSED`/`REMOVED` em `CUST_010`, que está `ENABLED`.
**Opções:** restaurar o domínio, ou remover as campanhas.
**Proibido:** republicar essas rotas em outro domínio — é a "variação de domínio
ou conteúdo" que a política de *Circumventing systems* nomeia.

### P4 — revisar e enviar a apelação
**Quem:** operador, após P0 e P1.
**Condição:** checklist ao fim de `APPEAL-DRAFT.md` inteiramente marcado.
**Limite:** **uma apelação por vez**; apelações repetidas para a mesma suspensão
podem não ser processadas.

### P5 — decidir sobre as rotas de documento de governo
**Quem:** operador.
**Fato:** a política *Government documents and services* foi atualizada com
efeito em **05/10/2026**: provedor autorizado precisa ter o domínio **linkado a
partir de site oficial de governo**; contrato comercial, licença ou registro
empresarial **não** contam.
**Recomendação:** não anunciar `nova-carteira-identidade-nacional-2026` nem
`guia-pis-pasep-2026` enquanto esse link não existir.

---

## 3 · Proibições que continuam valendo, independentemente de autorização

Estas não são cautela deste pacote; são texto publicado da política, e violá-las
transforma um problema recuperável em um permanente.

1. **Não criar conta nova.** *"After a previous suspension decision, attempting
   to use the Google Ads system again by creating new accounts to re-enter the
   system"* é violação de *Circumventing systems*.
2. **Não republicar rota reprovada em segundo domínio.** *"Bypassing enforcement
   mechanisms and detection by creating variations of ads, domains or content
   that have been disapproved."*
3. **Não afirmar parceria, licença ou autorização que não exista** — nem no site,
   nem na apelação. É o defeito que originou o achado
   `MARCA_TERCEIRA_SEM_LASTRO`, e repeti-lo numa apelação seria pior que
   mantê-lo no site.
4. **Não coletar dado pessoal em destino pago** sem declarar o papel
   `conversion_page`, com divulgação e política de privacidade.

---

## 4 · Nota de higiene sobre leitura de conta

A tentativa read-only anterior do Hermes produziu **stderr verboso do SDK do
Google Ads no console do operador**. Os artefatos do repositório foram
sanitizados imediatamente e não guardam ID cru.

**Condição para qualquer leitura futura de conta:** suprimir o logging de
requisição/stderr do cliente antes de executar, e persistir apenas campos
pseudonimizados. Nesta sessão **nenhuma leitura de conta foi feita** — a
evidência usada é a do passo anterior, já sanitizada.
