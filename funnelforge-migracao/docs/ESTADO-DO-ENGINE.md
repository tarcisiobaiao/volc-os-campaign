# Estado real do engine redator — 11/08/2026

Levantado lendo o código, rodando a suíte e testando validadores contra entradas
reais. Nada aqui é lembrança.

```
funnel-forge/            15.860 linhas · 505 testes passando (PYTHONPATH=src)
```

## As 9 etapas

```
extract → research → write(+judge) → seo → image → screenshot → build → widget → publish
```

`pipeline.py` valida o **grafo do funil duas vezes**: uma no `step_extract`
(sobre o plano descartável) e outra no plano FINAL, depois do
`expand_presell_hubs`. Falha de grafo é **fail-closed** — órfã, terminal sem
saída ou `bare_rec` derrubam a página. Página que falha não aborta o run: vira
`FAILED` no `step_status` e as outras seguem.

## O que já está certo e não pode ser destruído

**Grafo.** `presell_hubs=1`, `lp_direct_solutions=2` — exatamente o desenho que
validamos hoje na mão. `_BUTTON_HREF` do `lp_template.py` mapeia
`mobile [hub, sol1] · desktop [hub, sol1, sol2] · corpo sol2`, que é o que a LP
2064 tem em produção.

**Autorização de domínio vem da PESQUISA**, não de allowlist estática:
`research_hosts(facts)` alimenta o `same_domain`. Foi a remoção da regra hard-coded.

**31 validadores públicos, 46 códigos de issue.** Os gates de segurança do
`sanitize_widget_block` cobrem: script externo, handler inline, `<form>`,
listener global de clique, credencial falsa, HTML dinâmico, `&` cru em script.

**9 arquétipos de widget** derivados do nível de engajamento da página, não
sorteados.

**`step_screenshot` existe e é bom**: captura os destinos oficiais que o próprio
`step_write` citou, revalida o host contra a allowlist no adapter, converte para
webp, e embute depois do link correspondente. Best-effort por contrato — nunca
derruba a página.

**`phrase_registry`** garante unicidade de frase entre páginas do mesmo funil.

## As lacunas que o dia 11/08 expôs

### 1 · A pesquisa é best-effort e o fato é pobre

O docstring é explícito: *"research is best-effort grounding, not a hard
dependency"*. Qualquer falha vira `ResearchFacts(sparse=True)` e **nunca levanta**.

E o modelo do fato tem cinco campos:

```python
resumo: str · dados_validados: list[dict] · passo_a_passo: list[str]
fontes: list[str] · sparse: bool
```

**Não tem unidade, dispositivo, vigência nem data de verificação.** Hoje a gente
descobriu na pele que o que separa um número publicável de um número inventado é
exatamente isso: `R$ 100` sozinho é ruído; `R$ 100 · por saque anual cedido ·
Resolução CCFGTS 1.130/2025 art. 1º § 4º · DOU 20/10/2025 · verificado em
11/08/2026` é fato.

Foi essa pobreza que deixou "Resolução CCFGTS nº 1.130/2025" ser citada seis
vezes sem link no funil antigo — e que deixaria de novo.

### 2 · Vocabulário Gutenberg pobre

O enhancer emite:

```
paragraph 19 · separator 4 · html 4 · list-item 3 · group 3 · buttons 3
spacer 1 · pullquote 1
```

**Não emite `details`, `columns`, `image` nem `table`.** Foram exatamente os
quatro que eu precisei escrever à mão hoje para as páginas pararem de ser parede
de texto. Sem eles não existe "cara de interface".

### 3 · Nenhuma regra sobre os defeitos de hoje

Nada no engine detecta:

```
<p> dentro de wp:html ................. matou os 3 widgets
parágrafo colado num widget ........... indução de clique em anúncio
is-style-outline ...................... botão fantasma
wp:buttons consecutivas sem respiro ... botões colados
margem zero entre wp:group irmãos ..... callouts colados
```

### 4 · O CTA enganoso passa

Testei o validador real contra o rótulo que quebrou hoje:

```python
cta_style('Consultar modalidade no App FGTS' → /rec/…-p1/)  →  passa
cta_style('Conferir saldo no App FGTS'       → /rec/…-p1/)  →  passa
```

`BANNED_CTA_EXECUTION` tem 7 termos (`agendar, solicitar, emitir, cadastrar,
consultar meu cpf, garantir minha consulta, garantir meu acesso`) e nenhum cobre
a classe: **verbo de ação + menção a destino externo + href interno**.

### 5 · Config desalinhada com a operação

```yaml
allowed_external: [gov.br/susep, consumidor.gov.br]    ← do funil de seguro
cnpj: "00.000.000/0001-00"                             ← placeholder
official_screenshots: true                             ← mas playwright não
                                                          estava instalado
steps.widget.validators: []                            ← nenhum
steps.write_p1.validators: []                          ← a LP não é validada
steps.judge.validators: []
```

Com essa allowlist, um funil de FGTS teria **todo link oficial e todo screenshot
barrado** — o `same_domain` e o adapter de screenshot revalidam contra ela.

### 6 · O engine não sabe que a posição do anúncio depende do texto

`post-banners.php:34–85` divide o conteúdo por `</p>` para inserir banner.
**A densidade de parágrafos do nosso texto move o slot de anúncio.** Isso é
entrada de projeto do redator e hoje não existe em lugar nenhum do engine.

## Resumo em uma linha

O esqueleto está sólido — grafo, fail-closed, unicidade, arquétipos, screenshots.
O que falta é tudo que o dia de hoje ensinou: **fato com procedência, vocabulário
visual, e as regras que impedem os cinco defeitos que chegaram ao ar.**
