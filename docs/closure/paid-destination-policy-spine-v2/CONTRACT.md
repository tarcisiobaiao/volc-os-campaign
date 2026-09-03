# CONTRATO — a espinha de política do destino pago, v2

Versão do contrato: `paid_destination_policy_spine.v2`
Versão da matriz de fontes: `43472d43866cbf19` (39 regras)
Implementação: `backend/app/landing_policy/**`
Base: `origin/volc-os-v2` @ `34dc7b41bce901bd8bebfdec0a01e293678cbf08`

---

## 0 · A frase que este documento existe para tornar verdadeira

> Uma página de destino pago não pode nascer sem papel operacional declarado,
> nem ser publicada sem avaliação do contrato, nem ser usada em campanha sem
> recibo válido.

Antes desta sprint, as três metades da frase eram falsas ao mesmo tempo, e por
um motivo só: **`backend/app/landing_policy` não tinha chamador nenhum.** O
pacote existia, era bem construído, tinha 61 testes — e não era chamado por
nada fora dos próprios testes e de um script de auditoria. Um portão que nunca
está no caminho não é um portão.

---

## 1 · Os cinco papéis, e o que cada um exige

O papel não é derivado do slug nem declarado pelo cliente. Ele é **apurado pelo
servidor** (`portao.papel_do_servidor`), nesta ordem:

| ordem | fato apurado | papel |
|---|---|---|
| 1 | o artefato tem campo de formulário | `conversion_page` |
| 2 | há campanha apontando para a URL | `paid_destination` |
| 3 | o papel editorial do motor (`LP`/`PRESELL`/`SOLUTION`) | `paid_destination` / `presell` / `editorial_solution` |
| 4 | nada disso | `organic_article` |

Um papel pedido pelo cliente é aceito **só quando pede MAIS rigor**. Pedir menos
levanta `PapelRelaxadoPeloCliente` — não é ignorado em silêncio, porque um
pedido desses não é ruído: é alguém tentando baixar o rigor pela borda da API.

| papel | regime | o que muda |
|---|---|---|
| `paid_destination` | **estrito** | achado classificado vira bloqueio; verificação exigida inconclusiva vira `desconhecido`, que também reprova |
| `conversion_page` | **estrito** | idem, e a presença de formulário é o que o produz |
| `presell` | frouxo | o mesmo achado é REGISTRADO com severidade menor |
| `editorial_solution` | frouxo | idem |
| `organic_article` | frouxo | idem |

**No papel frouxo o achado nunca some.** Se sumisse, a operação deixaria de
saber que o defeito existe naquela página, e ele viajaria intacto até o dia em
que a URL virasse destino de campanha.

---

## 2 · A política de links do VOLC

```
PAID_DESTINATION_EXTERNAL_CLICKABLE_LINKS = FORBIDDEN
```

**Isto é política interna do VOLC, mais restritiva que a regra do Google.** O
Google não proíbe hyperlink externo em página de destino; ele proíbe fazer
parecer que existe vínculo com outra marca, órgão ou governo, e proíbe a
página-ponte. A âncora oficial da regra é essa cláusula
(*Unacceptable business practices*, `support.google.com/adspolicy/answer/15938071`).
A matriz de fontes marca isso no campo `regime`, e nenhum artefato desta sprint
apresenta a decisão da casa como proibição da plataforma.

A regra existe porque a anterior — barrar só o host **não classificado** —
deixava passar exatamente o que foi ao ar:

- `caixa.gov.br` é host de governo: **classificado**, passava;
- uma fonte de pesquisa declarada é `fonte_declarada`: **classificada**, passava.

A v1 barrava a *ausência de classificação*. A v2 barra a *presença do link*.

### O que NÃO é bloqueado

Âncora interna (`#`), link relativo, URL do mesmo domínio canônico, links legais
internos, `mailto:`/`tel:` (explicitamente permitidos e coerentes com a exigência
de identidade), e recurso técnico — `img`, `script`, `font` não são navegação
clicável do leitor. Confundi-los com outbound editorial afogaria o achado que
importa numa lista de assets.

`javascript:`, `data:` e `blob:` são clicáveis e **não resolvíveis** lendo o
documento: entram como `LINK_EXTERNO_NAO_CLASSIFICADO`, e o que não se classifica
não aprova.

### As fontes continuam existindo

Fonte de pesquisa fica no dossiê de evidência (`PaginaObservada.fontes_de_pesquisa`,
`PlanoDaPagina.fontes_de_pesquisa`) e é citada em prosa. Ela **não vira âncora**
no corpo de um destino pago. Em `editorial_solution` e `organic_article` a
referência externa evidence-backed continua permitida — o papel decide.

---

## 3 · As dez verificações e o que é exigível em cada ponto

| verificação | geração | pré-publicação | elegibilidade de campanha |
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
| **`approval_receipt`** *(nova na v2)* | — | — | ✓ |

As dez **rodam sempre**. A tabela diz apenas onde "não deu para olhar" vira
reprova. Ausência estrutural não é buraco: antes de publicar não existe
redirecionamento nem aprovação anterior a observar.

### Três caminhos para `desconhecido`

1. verificação **exigida** naquele ponto que não concluiu;
2. verificação que saiu `not_applicable` num ponto em que "não se aplica" é
   impossível de boa-fé — uma página no ar **sempre** tem hash observável;
3. varredura que **explodiu**, em qualquer ponto, exigida ou não.

O caso 3 é o que mais custava: `failed` só virava desconhecido quando o nome
estava na lista de exigidas, então no portão de pré-publicação quatro
verificações podiam quebrar inteiras e a publicação seguia autorizada.
*"Não é exigível aqui"* é decisão do contrato; *"quebrou"* é defeito do
software, e software quebrado nunca é evidência de página limpa.

---

## 4 · As três barreiras

### BARREIRA 1 — geração

O plano é avaliado **antes** de existir corpo escrito. `landing_policy.plano`
renderiza os campos estruturados — papel, rota, título, H1, subtítulos, claims,
valores monetários, links, CTAs, formulários, identidade do operador,
disclosures, fontes — como documento canônico, e entrega esse documento às
**mesmas dez varreduras**.

Renderizar em vez de escrever regra nova é decisão deliberada: duas regras (uma
para o plano, outra para a página) divergem no primeiro mês, e aí o plano aprova
o que a página reprova. Quem lê o recibo não teria como saber qual das duas
estava certa.

Markdown, URL nua e autolink entram pela mesma porta. O redator devolve
Markdown; um scanner que só enxergasse `<a href>` daria verde para
`[40%](https://www.caixa.gov.br/)` — o defeito do incidente, escrito na sintaxe
em que ele nasce.

### BARREIRA 2 — pré-publicação

Antes de qualquer chamada externa ao publicador: monta-se o documento final
realmente publicável, confirma-se o papel apurado pelo servidor, validam-se
hyperlinks, CTAs, identidade e disclosures, gera-se a impressão canônica e o
recibo de decisão. Só depois o adaptador de publicação pode ser alcançado.

Portão vermelho ⇒ **zero chamada externa, zero publicação parcial, zero
fallback**, erro semântico e acionável, e recibo local de recusa.

**O predicado correto é `avaliacao.paid_destination_ready`, nunca
`if avaliacao.bloqueios`.** Testar só bloqueios ignora `desconhecidos`, e foi
assim que o handoff anterior deixaria publicar uma página cuja varredura falhou.

### BARREIRA 3 — campanha

A mesma landing é reavaliada em `/provar` **e outra vez** imediatamente antes de
qualquer caminho de `/subir`. Não se confia no recibo antigo nem no resultado do
`/provar`: o selo é do payload, e `url_final` está lá como string. Impressão
idêntica não prova nada sobre o que o destino serve agora.

`elegibilidade_de_destino_de_campanha()` **força** papel e ponto. Uma campanha
apontando para uma URL faz dela um destino pago, qualquer que seja o papel
cadastrado — deixar o chamador escolher seria deixar o portão ser desligado por
configuração.

Deriva, leitura falha ou evidência vencida ⇒ **não elegível, e nenhum mutate**.

---

## 5 · Deriva: a impressão canônica ao lado do byte

O recibo carrega **as duas**:

- `content_sha256` — o byte. Prova **igualdade**, e foi assim que a acusação de
  cloaking contra `/r/fgts-saque-aniversario/` foi REFUTADA: Googlebot e usuário
  devolveram 174 243 bytes idênticos.
- `content_fingerprint` — a projeção estrutural (título, cabeçalhos, texto
  visível normalizado, inventário de links clicáveis, inventário de campos).
  Mede **mudança**.

O byte não serve sozinho para medir deriva: na mesma leitura, desktop e mobile
daquele destino diferiram em 27 bytes — um token rotativo de push. Um portão que
reprovasse por deriva a cada rotação seria desligado na primeira semana. Um que
ignorasse a deriva não veria a edição manual no WordPress. São o mesmo erro com
sinais trocados.

---

## 6 · Duas versões, porque elas mudam por motivos diferentes

| campo | o que é | muda quando |
|---|---|---|
| `policy_contract_version` | a **forma** da avaliação: quais verificações existem, o que cada papel exige, em que ponto | acrescenta-se verificação, muda-se exigência ou severidade |
| `policy_source_version` | o **texto** das regras — sha256 da matriz de fontes | corrige-se a redação, a URL ou a data de consulta de uma regra |

Um recibo que carregasse só uma pareceria reaproveitável depois de uma mudança
que o invalidou. Recibo de versão diferente ⇒ `RECIBO_DE_POLITICA_DESATUALIZADO`.

**Lacuna declarada:** nenhuma das duas versões cobre o código dos detectores
(as expressões regulares e limiares de `varredura.py`). Mover um código entre as
tabelas de severidade muda o veredito enquanto as duas versões ficam idênticas.
Está registrado em `REMAINING-RISKS.md`; não foi fechado nesta sprint.

---

## 7 · Onde o recibo mora — e por que não há tabela nova

`pautador_funnel_runs.paginas_publicadas jsonb` já existe
(`src/sql/pautador/04_matriz_do_redator.sql:60`), já é o contrato declarado com o
módulo de campanha, e `worker.resumo_do_estado` a preenche com
`[p for p in state.published.values()]` — **sem filtrar chave nenhuma**. Um
recibo posto em `state.published[n]` chega ao banco inteiro.

Zero migration. Zero coluna nova. Zero segunda autoridade sobre o mesmo fato.

`url_canonica` derruba query e fragmento: um destino do Google chega com `gclid`
grudado, e um recibo só encontrável com a query exata é um recibo que nunca é
encontrado — e não encontrar reprova, então a campanha morreria sempre.

---

## 8 · Frescor

`JANELA_DE_FRESCOR_PADRAO_S = 24 h`. Página no ar muda sem avisar — plugin,
tema, rotação de anúncio, edição manual. Um recibo de duas semanas descreve um
conteúdo que pode não existir mais.

**Divergência declarada:** `app/trafego/dominio.py` usa `JANELA_RECENTE_S = 30
min` para frescor de conta. São grandezas diferentes (leitura de API × conteúdo
publicado) e a divergência é deliberada, não descuido.

Recibo sem carimbo comparável ⇒ `unavailable`, nunca "recente". Devolver
`observed` ali faria um recibo sem data parecer sempre novo.

---

## 9 · O que este contrato NÃO afirma

`paid_destination_ready: true` significa exatamente: *nesta avaliação, neste
ponto de portão, contra esta versão do contrato e desta matriz, não sobrou
bloqueio nem desconhecido*.

Não significa que o Google vai aprovar. Não significa que a conta está limpa.
Não significa que a página está correta. O portão lê HTML; ele não lê a intenção
do revisor.

O recibo carrega isso explicitamente:

```json
"readiness": {
  "volc_gate": "ready",
  "live_verified": true,
  "google_approval": "unknown",
  "google_approval_note": "Este portão lê HTML; ele não lê a decisão do revisor do Google."
}
```

Cinco estados que **não podem ser colapsados num único verde**: pronto segundo o
VOLC · publicado · verificado ao vivo · elegível para campanha · aprovação do
Google **desconhecida**. Colapsá-los foi como uma LP com sete links de governo
virou destino de campanha.
