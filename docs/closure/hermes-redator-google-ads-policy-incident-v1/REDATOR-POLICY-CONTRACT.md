# CONTRATO DE POLÍTICA DO REDATOR — `paid_destination` explícito

Implementação: `backend/app/landing_policy/**`
Fonte canônica de política: `backend/app/landing_policy/fontes_politica.json`
(cópia gerada em `GOOGLE-POLICY-MATRIX.json`)

---

## 1 · O problema que este contrato resolve

O motor de funil tem papéis **editoriais**: `LP`, `PRESELL`, `SOLUTION`
(`funnelforge.domain.models.PageRole`, derivados do slug). Eles dizem onde a
página está no funil. Não dizem se ela recebe clique comprado.

Isso é ambíguo em duas direções, e as duas custaram:

- uma `LP` pode nunca ter campanha — e era avaliada como se tivesse;
- um artigo orgânico pode virar destino de campanha amanhã — e não era avaliado
  como tal em momento nenhum.

O contrato novo é **declarado, não derivado**, e vive ao lado do papel editorial
em vez de substituí-lo.

## 2 · Os cinco papéis

| papel | o que é | regime |
|---|---|---|
| `paid_destination` | URL que um anúncio do Google Ads aponta | **estrito — fecha por ausência** |
| `conversion_page` | página que COLETA dado do visitante | **estrito** |
| `presell` | pré-venda interior do funil, sem clique comprado direto | frouxo |
| `editorial_solution` | página-solução interior do funil | frouxo |
| `organic_article` | artigo orgânico do portal | frouxo |

**Regime estrito** = achado classificado vira bloqueio, e verificação exigida que
não pôde ser concluída vira `desconhecido`, que também reprova.
**Regime frouxo** = o mesmo achado é REGISTRADO com severidade menor. Ele nunca
some — se sumisse, a operação deixaria de saber que o defeito existe naquela
página, e ele viajaria intacto até o dia em que a URL virasse destino de campanha.
Prova: `test_landing_policy_contraprovas.py::test_o_mesmo_defeito_e_registrado_no_artigo_organico_sem_reprovar`.

## 3 · As duas regras que decidem tudo

### 3.1 Fecha por ausência

Uma `Verificacao` carrega **status** além de achados:
`observed` · `absent_confirmed` · `unavailable` · `not_applicable` · `failed`
(o mesmo vocabulário de `publisher_quality.snapshot`, de propósito).

No `paid_destination`, verificação **exigida** naquele ponto de portão cujo
status não é conclusivo vira entrada em `desconhecidos`. Ela **não** vira "sem
achados" — que é como software costuma mentir. Uma varredura que levanta exceção
vira `failed` e reprova, em vez de sumir num `except` silencioso.

`paid_destination_ready = papel é paid_destination AND sem bloqueios AND sem desconhecidos`

### 3.2 Código não classificado bloqueia

`contrato.severidade()` devolve `blocker` para qualquer código desconhecido nos
papéis estritos. Um achado novo que ninguém classificou não entra em produção
valendo "observação" só porque a tabela não foi atualizada.

## 4 · O que é exigido em cada ponto de portão

Ausência estrutural não é buraco: antes de publicar não existe redirecionamento
para observar. Exigi-lo ali reprovaria toda página por uma impossibilidade.

| verificação | artefato de geração | pré-publicação WP | elegibilidade de campanha |
|---|:--:|:--:|:--:|
| `identity` | ✓ | ✓ | ✓ |
| `external_links` | ✓ | ✓ | ✓ |
| `forms_and_sensitive_data` | ✓ | ✓ | ✓ |
| `claims_and_disclosures` | ✓ | ✓ | ✓ |
| `government_services` | ✓ | ✓ | ✓ |
| `content_originality_and_congruence` | ✓ | ✓ | ✓ |
| `destination_security_signals` | — | — | ✓ |
| `redirect_and_cloaking` | — | — | ✓ |
| `live_drift` | — | — | ✓ |

Todas as nove **rodam sempre**; a tabela diz apenas quais transformam
"não deu para olhar" em reprova.

`elegibilidade_de_destino_de_campanha()` **força** o papel `paid_destination`.
Uma campanha apontando para uma URL faz dela um destino pago, qualquer que seja
o papel cadastrado — deixar o chamador escolher seria deixar o portão ser
desligado por configuração.

## 5 · As 33 regras e suas fontes

Cada código emitido tem entrada em `fontes_politica.json` com `policy`, `url`,
`consulted_at`, `applicability`, `evidence`, `result`, `confidence`, `correction`.
Três testes protegem isso:

- todo código que o portão pode emitir tem fonte;
- toda fonte tem regra correspondente (matriz não mente sobre cobertura);
- toda URL de fonte é host oficial do Google.

Doutrina herdada de `volc_ads/policy/spec.py`: **regra sem fonte não entra.**

### Fronteira com `volc_ads/policy` — sem duplicação

| | `volc_ads/policy/spec.py` | `backend/app/landing_policy` |
|---|---|---|
| superfície | o **anúncio** (headline, description, sitelink) | a **página de destino** |
| destino | só `http_ok` (status HTTP aceito) | identidade, links, formulário, alegação, governo, originalidade, redirecionamento, cloaking, deriva |
| eixo | país × vertical × idioma | papel × ponto de portão |
| habilitação | certificação por vertical/país | — |

Nenhuma regra aparece nos dois. `http_ok` continua só lá; nada aqui reavalia
texto de anúncio.

## 6 · Autorização vem de EVIDÊNCIA, nunca de allowlist

Um host externo é classificado como `fonte_declarada` quando quem chamou o
portão trouxe a evidência daquela página. Sem lastro ele é
`terceiro_desconhecido` — e desconhecido reprova destino pago.

É a mesma doutrina de `funnelforge...checks.same_domain`, pelo mesmo motivo:
lista estática bloqueia o canal oficial de que a página precisa e deixa passar o
que entrou pela prosa. Contraprovas I (sem lastro reprova) e J (com lastro passa)
provam os dois lados.

## 7 · O recibo

Todo veredito emite um `LandingPolicyGateReceipt` com URL, `content_sha256`,
carimbo, `policy_source_version` (hash da matriz — ninguém edita a regra e mantém
o recibo antigo parecendo válido), hash de cada inventário, resultado de
identidade e de segurança, veredito, bloqueios com a fonte oficial de cada um,
desconhecidos, referências de evidência e `paid_destination_ready`.

O recibo carrega também `external_mutation` com quatro `false` — a prova de
contenção viaja no artefato, não numa frase de relatório.

## 8 · O que este contrato NÃO afirma

`paid_destination_ready: true` significa exatamente: *nesta avaliação, neste
ponto de portão, contra esta versão da política, não sobrou bloqueio nem
desconhecido*. Não significa que o Google vai aprovar, nem que a conta está
limpa, nem que a página está correta. O portão lê HTML; ele não lê a intenção do
revisor. Um portão que prometesse mais seria a mesma alegação forte sem evidência
que ele existe para impedir.
