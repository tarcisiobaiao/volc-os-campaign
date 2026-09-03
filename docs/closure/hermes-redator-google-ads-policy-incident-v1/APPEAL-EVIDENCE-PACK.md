# APPEAL EVIDENCE PACK — o que existe, e o que não existe

Montado em **2026-09-03**. Serve a duas leituras: a interna (o que sabemos) e a
externa (o que dá para citar numa apelação sem afirmar mais do que se mediu).

> **Nada aqui foi enviado ao Google.** A apelação não foi submetida.

---

## 1 · Peças de evidência

| # | peça | arquivo | o que prova |
|---|---|---|---|
| E1 | Snapshot público do destino, 3 user-agents | `evidence-public/public-lp-snapshot.json` + 3 `.html` | conteúdo servido em 2026-09-03T00:51Z, com sha256 por variante |
| E2 | Três destinos `/r/` adicionais preservados | `evidence-public/r-*.html` | estado dos outros destinos pagos no mesmo dia |
| E3 | Evidência de conta sanitizada | `account-evidence-sanitized.json` | `CUST_013` = `SUSPENDED`; 14 anúncios; status de política por anúncio. Sem ID cru |
| E4 | Inventário de rotas `/r` | `ROUTE-R-INVENTORY.json` | 14 destinos pagos, 3 fontes independentes, `portalmundomais.com` em 410 |
| E5 | Matriz de política | `GOOGLE-POLICY-MATRIX.json` | 33 regras, todas com URL oficial do Google, consultadas em 2026-09-03 |
| E6 | Recibos do portão | `GATE-RECEIPTS.json` | 5 recibos, todos `blocked`, com hash de conteúdo e de inventário |
| E7 | Análise de causa | `ROOT-CAUSE-ANALYSIS.md` | o que a evidência sustenta e o que ela refuta |
| E8 | Mudanças de engenharia | `ENGINE-CHANGES.md` + `GATES.md` | o que foi implementado e provado localmente |

---

## 2 · O que a evidência AFIRMA sobre o destino

Medições, não impressões. Cada uma é reproduzível a partir dos artefatos.

1. **Sem cloaking.** Googlebot e usuário receberam HTML **byte a byte idêntico**
   (`sha256 7c674d1d7daf896e…`, 174 243 bytes) em duas leituras separadas no
   mesmo dia. A variação desktop↔mobile é de 27 bytes, num token rotativo de
   notificação push.
2. **Sem redirecionamento.** Zero saltos na cadeia; a URL final é a declarada.
3. **Sem coleta de dado pessoal.** O único formulário nas quatro páginas
   preservadas é a busca do WordPress (`<input type="text" name="s">`). Nenhum
   campo de senha, cartão, CPF, RG, renda ou upload de documento.
4. **Sem conteúdo misto.** As 12 ocorrências de `http://` são todas o namespace
   SVG do W3C. TLS 1.3 válido (Let's Encrypt; SAN `creditoup.com.br`,
   `www.creditoup.com.br`).
5. **Código dinâmico atribuído.** `String.fromCharCode` e oito `atob(` pertencem
   ao plugin de rotação de anúncio (namespace `ai_*`), decodificando os próprios
   atributos `data-info`/`data-shares`/`data-time`. Nenhuma exfiltração observada.
6. **Identidade do operador presente em 3 das 4 páginas**: razão social, CNPJ
   `42.724.548/0001-24`, aviso de não-vínculo com órgãos públicos e divulgação de
   AdSense — inclusive na página que a conta suspensa anunciava.
7. **Anúncios aprovados.** 11 dos 14 anúncios de Busca estão
   `APPROVED`/`REVIEWED`; a suspensão é de conta.

## 3 · O que a evidência mostra CONTRA nós

Está aqui por decisão explícita: uma apelação que só lista o que ajuda é uma
apelação que o revisor desmonta em cinco minutos.

1. **Sete links para `caixa.gov.br` com âncora numérica** em
   `/r/fgts-saque-aniversario/` — `40 %`, `90 dias`, `5 %`, `50 %`, `2900.00 R$`,
   `5 saques anuais`. Estruturalmente, isso faz o leitor atribuir cada número ao
   banco público.
2. **`/r/antecipacao-saque-aniversario-fgts/` sem identidade nenhuma**: sem CNPJ,
   sem sobre, sem contato, sem privacidade, com 19 menções a órgão público e
   nenhum aviso de não-vínculo.
3. **Marcas de terceiros como parceiras** na mesma página: "autorizar um banco
   parceiro, como o Banco Bmg ou o Santander".
4. **Promessas de resultado**: "não realizam consultas… SPC e Serasa",
   "liberação do dinheiro… em poucos minutos".
5. **`2900.00 R$`** — cifra malformada, dentro de um link para a Caixa.
6. **`APPROVED_LIMITED`** nos anúncios de documento de identidade nacional.
7. **Host de adtech não declarado** (`script.joinads.me`) enquanto a divulgação
   na página nomeia Google AdSense.
8. **Slugs repetidos entre dois domínios** do mesmo operador (igualdade de
   conteúdo não verificada — o outro domínio está em 410).

## 4 · O que NÃO existe, e é preciso pedir ao operador

Sem estes itens, a apelação é um chute educado.

| # | falta | por que é indispensável | quem obtém |
|---|---|---|---|
| F1 | **Texto literal da notificação de suspensão** (in-account + e-mail), com a(s) política(s) nomeada(s) | a apelação precisa responder à política CITADA, não à que inferimos | operador, na conta suspensa |
| F2 | Data da suspensão | permite comparar com o `lastmod` das páginas | operador |
| F3 | Histórico de avisos anteriores | Google pergunta sobre mudanças recentes | operador |
| F4 | Estado de verificação de anunciante | algumas suspensões só admitem apelação após verificação concluída | operador |
| F5 | Snapshot que o Google revisou | hoje não existe hash aprovado; `DERIVA_AO_VIVO` é immensurável | conserto no motor (Fase D5) |
| F6 | Se há relação comercial documentada com as instituições citadas | decide se o texto é corrigido ou comprovado | operador |

## 5 · Pontos de política pertinentes, com a fonte

Todos consultados em 2026-09-03, hosts oficiais do Google.

| política | URL | por que importa aqui |
|---|---|---|
| Unacceptable business practices | `support.google.com/adspolicy/answer/15938071` | "Make it seem like you're affiliated with another brand, organization or government entity when you're not" |
| Phishing (FAQ de suspensão) | `support.google.com/google-ads/answer/15936970` | define phishing como obter dado pessoal fingindo ser entidade confiável; pede branding autêntico, contato atualizado e página "sobre" |
| Misrepresentation | `support.google.com/adspolicy/answer/6020955` | misleading representation, unreliable claims, dishonest pricing, unclear relevance |
| Government documents and services | `support.google.com/adspolicy/answer/13156083` | só governo certificado ou provedor autorizado; disclosure "Not a government website" |
| Atualização de out/2026 | `support.google.com/adspolicy/answer/17260489` | a partir de 05/10/2026, autorização exige link a partir de site oficial de governo |
| Circumventing systems | `support.google.com/adspolicy/answer/15938075` | cloaking, redirect abuse, conta nova após suspensão, variação de domínio/conteúdo |
| Destination requirements | `support.google.com/adspolicy/answer/6368661` | destination mismatch, bridge pages, insufficient original content |
| Account suspensions overview | `support.google.com/google-ads/answer/9841640` | onde ler o motivo literal; como apelar; uma apelação por vez |

## 6 · Uma advertência sobre `Circumventing systems`

A política diz, literalmente, que criar contas novas após uma suspensão é
violação, e que contas suspensas por prática inaceitável **não voltam a
anunciar**. Duas consequências operacionais, registradas para que ninguém
"resolva" o problema do jeito errado:

- **não criar conta nova**;
- **não republicar as mesmas rotas num segundo domínio** — é exatamente a
  "variação de domínio ou conteúdo" que a política nomeia.

Ver `AUTORIZACAO-EXTERNA.md`.
