# Correção cirúrgica dos 3 funis — preflight e achado bloqueante

**Data**: 2026-09-18 · **Rodada**: reparo editorial sobre o parecer do Codex
**Estado**: **NENHUMA ESCRITA FOI FEITA.** Preflight concluído, correções mapeadas, execução
interrompida por decisão do operador (contexto do executor esgotado) e por um achado que exige
conciliação.

**Custo desta rodada: US$ 0,00** — nenhuma chamada paga de texto, pesquisa, imagem ou visão.
Só leitura REST autenticada e leitura de arquivos locais.

---

## 1. Achado bloqueante: o post 2306 foi editado por outra pessoa e perdeu o aviso

A LP do SENAC (`2306`, tipo `r`, slug `guia-cursos-senac`) **não está mais como foi publicada**.

| Evidência | Publicação (2026-09-17 22:58 GMT) | Estado lido agora (2026-09-18 00:19 GMT) |
|---|---|---|
| `modified_gmt` | 2026-09-17T22:58:41 | **2026-09-18T00:19:29** |
| `date_gmt` | — | **2026-09-18T00:19:29** (também alterado) |
| `post_content` | 0 bytes | **7.927 bytes de HTML renderizado** |
| `_elementor_data` | 22.070 chars | **19.914 chars** |
| `volc-editorial-notice` | presente, primeiro container | **AUSENTE** |
| H1 do herói | "Guia de Cursos Senac 2026" | "Cursos Senac em 2026" |

O padrão é inequívoco: alguém abriu o post no **editor do Elementor e salvou**. O Elementor grava
o HTML renderizado em `post_content` (daí os 7.927 bytes num tipo que antes tinha zero) e reescreve
`_elementor_data`. Nesse salvamento **o container do aviso de identidade editorial foi removido**.

**Não escrevi nada no 2306.** Re-renderizar o template a partir do `lp_content.json` apagaria a
edição humana — e o prompt desta rodada é explícito: divergência material de autoria exige
conciliação antes da escrita afetada.

### O que precisa ser decidido antes de mexer no 2306

1. **Repor só o aviso**, preservando a edição humana: injetar o container `volc-editorial-notice`
   como primeiro elemento do `_elementor_data` atual, sem tocar no resto. Mantém o trabalho de
   quem editou e devolve a identidade editorial. **É a opção recomendada.**
2. **Descartar a edição humana** e re-renderizar a partir da origem — só se quem editou confirmar
   que a alteração não deve ser preservada.
3. Em qualquer caso, C7 e parte de C1 tocam a LP do MEC (2336), não o 2306; as demais correções do
   SENAC (C3, C6, C8) são nas internas 2309/2312/2318, que **estão intactas**.

### As outras 14 páginas estão íntegras

`modified_gmt` coerente com a publicação, aviso presente, `draft`, slugs idênticos, nenhuma mídia
nova. As LPs 2321 e 2336 têm `post_content` vazio e o aviso dentro do `_elementor_data`, como
esperado.

## 2. Preflight — o que foi conferido

| Item | Resultado |
|---|---|
| Leitura REST autenticada, contexto `edit` | **15/15** posts lidos |
| Status | **15/15 `draft`** |
| Slugs remoto × `state.published` | **15/15 idênticos**, nenhum `-2` |
| Aviso editorial | presente em 14; **ausente no 2306** (ver §1) |
| `_elementor_data` nas 3 LPs | presente nas 3 |
| Yoast (`_yoast_wpseo_title`) | presente nas 15 |
| Mídias novas | nenhuma criada |
| Snapshot recuperável | 15 JSONs + resumo em pasta `0700` **fora da document root e fora do repositório** |

Snapshot: `<scratchpad>/snapshot-antes/` (`2306.json` … `2348.json`, `_resumo.json`), com
`sha256` de `post_content` e de `_elementor_data` por post. **O manifesto original não foi
tocado** — a evidência anterior está preservada.

Inventário dos 15 (tema · página · ID · tipo · bytes · `modified_gmt`):

```
SENAC  p1 2306 r    7927   2026-09-18T00:19:29   <-- EDITADO POR TERCEIRO
SENAC  p2 2309 rec  10813  2026-09-17T22:58:44
SENAC  p3 2312 rec  11438  2026-09-17T22:58:47
SENAC  p4 2315 rec  10458  2026-09-17T22:58:51
SENAC  p5 2318 rec  22437  2026-09-17T22:58:53
SENAI  p1 2321 r    0      2026-09-17T23:11:54
SENAI  p2 2324 rec  11612  2026-09-17T23:11:57
SENAI  p3 2327 rec  24419  2026-09-17T23:12:00
SENAI  p4 2330 rec  22776  2026-09-17T23:12:02
SENAI  p5 2333 rec  23575  2026-09-17T23:12:05
MEC    p1 2336 r    0      2026-09-18T00:12:06
MEC    p2 2339 rec  11015  2026-09-18T00:12:08
MEC    p3 2342 rec  13050  2026-09-18T00:12:09
MEC    p4 2345 rec  20170  2026-09-18T00:12:11
MEC    p5 2348 rec  22870  2026-09-18T00:12:13
```

## 3. C1–C8 — alvos localizados e confirmados nos artefatos

Cada linha foi verificada lendo o arquivo local. Nenhuma foi alterada.

| # | Post | Arquivo:linha | Trecho atual (resumido) |
|---|---|---|---|
| C1 | 2336 | `p1.guia-aprenda-mais-mec.lp_content.json:1` | FAQ afirma acesso "integrado utilizando a conta oficial do Gov.br" |
| C1 | 2345 | `p4.acesso-cadastro-aprenda-mais-p2.gutenberg.html:24` e tabela ~:52 | acesso por outros portais federais como opcional |
| C2 | 2327 | `p3.cursos-gratuitos-senai-p1.gutenberg.html:133` | "Valide os requisitos no cadastro federal … perfil escolar … sistema de validação do MEC no portal gov.br" |
| C3 | 2309 | `p2.por-onde-comecar-senac-pr.gutenberg.html:96` | tabela "Canal Seguro = endereço terminado em `.senac.br`" |
| C3 | 2318 | `p5.portal-do-senac-do-seu-estado-p3.gutenberg.html:70` | "confirme se o endereço termina **estritamente** em `.senac.br`" |
| C4 | 2321 | `p1.guia-gratuidade-senai.lp_content.json:1` | FAQ com renda "geralmente até 1,5 salário mínimo" |
| C4 | 2324 | `p2.qual-caminho-senai-pr.gutenberg.html:46` | "renda familiar per capita … até 2 salários mínimos" como regra |
| C4 | 2327 | `p3.cursos-gratuitos-senai-p1.gutenberg.html:99` | idem, em FAQ |
| C4 | 2330 | `p4.edital-senai-como-ler-p2.gutenberg.html:73` | "prova objetiva … costuma apresentar 60 questões"; conferir também datas e idade |
| C5 | 2342 | `p3.catalogo-aprenda-mais-p1.gutenberg.html:80` | passo de certificação com link para curso técnico integrado do IFRS Canoas |
| C6 | 2318 | `p5.portal-do-senac-do-seu-estado-p3.gutenberg.html:9` | CTA de topo "Ver o guia de crédito do trabalhador no aplicativo »" |
| C6 | 2333 | `p5.certificado-diploma-senai-p3.gutenberg.html:9` | CTA de topo "Ver o guia de crédito do trabalhador no app »" |
| C6 | 2348 | `p5.certificado-aprenda-mais-p3.gutenberg.html:9` | CTA de topo "Ver o guia de aumento de limite e planejamento financeiro »" |
| C7 | 2336 | `p1.guia-aprenda-mais-mec.lp_content.json:1` | FAQ "não há limite de vagas ou turmas fechadas" |
| C8 | 2312 | `p3.tipos-de-curso-senac-p1.gutenberg.html:34` e FAQ ~:126 | "habilitação profissional reconhecida pelo MEC" sem distinguir nível |
| C8 | 2348 | `p5.certificado-aprenda-mais-p3.gutenberg.html:~29, ~105` | validade, horas complementares e progressão |

Status de todas: **NÃO APLICADA** (nenhuma escrita nesta rodada).

## 4. C6 — provável bloqueio estrutural, a confirmar antes de aplicar

`config.yaml → routing.SOLUTION_TERMINAL` tem `forbidden_targets: [self, funnel,
external_official, bare_rec]` e `required_targets: [cross_funnel]`, e
`validators/checks.py:790` isenta a terminal do gate de densidade de link oficial. Ou seja: pela
regra vigente, a página terminal **não pode** ter saída para canal oficial e **precisa** de
cross-funnel.

`config/perfil.py:aplicar_perfil` sobrepõe apenas `site.*`, `wordpress.*`, `tema.*` e os tetos —
**não** sobrepõe `routing`. Não há, portanto, override por run que resolva C6 sem tocar no motor.

Conforme o prompt, **C6 deve ser registrada como BLOQUEADA**, com o patch mínimo apresentado e
**não aplicado**. Esboço do patch mínimo, para o Codex avaliar depois:

1. `config.yaml`: em `SOLUTION_TERMINAL`, mover `external_official` de `forbidden_targets` para
   `allowed_targets` e acrescentá-lo a `required_targets`; manter `cross_funnel` como permitido,
   porém não obrigatório, e elevar `cta_max`.
2. `routing.py:bind_official_route`: remover a condição `or is_terminal` que hoje impede ligar a
   aresta oficial na terminal.
3. `validators/checks.py:official_link_density`: retirar a isenção `ctx.get("is_terminal")`.
4. `prompts/redator_pages.jinja`, bloco `{% elif is_terminal %}`: trocar a instrução de
   recirculação exclusiva por "entregue o canal oficial primeiro; a leitura de outro tema, se
   houver, vem depois e claramente separada".
5. Testes a ajustar/criar: `test_route_validators.py`, `test_routing.py` e
   `test_gate_fail_closed.py` cobrem a regra atual e vão falhar — precisam de caso novo para
   terminal com `external_official`.

Alternativa sem tocar no motor, que **não** foi aplicada por exigir aprovação: remover apenas os
parágrafos-ponte artificiais e rebaixar o CTA financeiro para o fim da página, mantendo a aresta
cross-funnel exigida pelo gate. Isso atende parte de C6 (o desvio do caminho principal) mas não
entrega a saída oficial na terminal.

## 5. Pendências que seguem abertas

- **P1 · Prova visual real do Elementor**: continua pendente. Extensão do Chrome não conectada;
  Application Password vale só para REST e não autentica o wp-admin. Rascunho devolve 404 anônimo.
  Links de edição por ID estão no índice privado. **Não publicar para testar.**
- **P2 · Card no Pautador**: segue não criado (API exige JWT admin; `VOLC_SERVICE_KEY` ausente).
- **P3 · Conciliação do 2306**: ver §1. Bloqueia C3/C6/C8 apenas na LP do SENAC — as internas do
  SENAC estão livres para correção.
- **P4 · Grafo**: `--check` → `current: false`; rebuild continua barrado pelo detector de segredos
  (`.env_webgo: jwt`, preexistente). **Não contornado, arquivo não lido.**

## 6. Veredito

**DRAFT_WITH_GAPS** nos três funis — inalterado em relação à rodada anterior, porque nenhuma
correção foi aplicada. Os erros factuais apontados pelo Codex **continuam presentes** nos
rascunhos. Nenhum funil está pronto para publicação.

Próximo passo: executar C1–C5, C7 e C8 nas 14 páginas íntegras, tratar C6 como bloqueada com o
patch acima, e conciliar o 2306 antes de qualquer escrita nele.
