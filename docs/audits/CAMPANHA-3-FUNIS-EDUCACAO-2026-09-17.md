# Três funis editoriais em rascunho — creditoup.com.br

**Data**: 2026-09-17 · **Executor**: Claude Opus 5 (1M) via Claude Code
**Para**: revisão de Tarcísio + Codex · **Nada foi publicado publicamente.**

Manifesto JSON, índice privado e ledger de fontes:
`funnelforge-migracao/engine/.perfil-run-creditoup-20260917/entrega/`
(diretório fora do versionamento, por conter artefatos de execução).

---

## 1. Veredito por funil

| Funil | Status | Por quê |
|---|---|---|
| Cursos SENAC | `DRAFT_WITH_GAPS` | 5/5 rascunhos criados, todos os gates verdes, leitura de volta autenticada OK. Falta **prova visual real do Elementor** (P1) |
| Cursos SENAI | `DRAFT_WITH_GAPS` | idem |
| Aprenda Mais MEC | `DRAFT_WITH_GAPS` | 5/5 rascunhos criados, todos os gates verdes, leitura de volta OK. Falta a mesma prova visual (P1) |

`DRAFT_READY_FOR_REVIEW` exige ver a página renderizada. Não foi possível nesta sessão por dois
motivos independentes e ambos verificados: a extensão do Chrome não está conectada nesta máquina,
e o Application Password do WordPress vale só para REST/XML-RPC — não autentica o formulário de
login do wp-admin, então nem o Playwright instalado entra sozinho. Rascunho não abre anonimamente
(testado: 404), e isso **não** autoriza publicar para testar. Logo, o teto honesto é
`DRAFT_WITH_GAPS`.

## 2. Entrega

| # | papel | H1 | slug real | post ID | tipo | status | edicao |
|---|---|---|---|---|---|---|---|
| **Cursos SENAC** | | run `guia-cursos-senac-20260917-220001` | | | | | |
| p1 | LP | Cursos Senac: entenda a estrutura antes de procura | `guia-cursos-senac` | 2306 | `r` | `draft` | [editar](https://creditoup.com.br/wp-admin/post.php?post=2306&action=edit) |
| p2 | PRESELL | Por onde comecar no Senac: qual e a sua situacao h | `por-onde-comecar-senac-pr` | 2309 | `rec` | `draft` | [editar](https://creditoup.com.br/wp-admin/post.php?post=2309&action=edit) |
| p3 | SOLUTION | Tipos de curso do Senac: livre, tecnico e superior | `tipos-de-curso-senac-p1` | 2312 | `rec` | `draft` | [editar](https://creditoup.com.br/wp-admin/post.php?post=2312&action=edit) |
| p4 | SOLUTION | Bolsas de estudo do Senac: onde cada estado public | `bolsas-de-estudo-senac-p2` | 2315 | `rec` | `draft` | [editar](https://creditoup.com.br/wp-admin/post.php?post=2315&action=edit) |
| p5 | SOLUTION | Portal do Senac do seu estado: como confirmar que  | `portal-do-senac-do-seu-estado-p3` | 2318 | `rec` | `draft` | [editar](https://creditoup.com.br/wp-admin/post.php?post=2318&action=edit) |
| **Cursos SENAI** | | run `guia-gratuidade-senai-20260917-230001` | | | | | |
| p1 | LP | Senai: como a oferta gratuita funciona e onde ela  | `guia-gratuidade-senai` | 2321 | `r` | `draft` | [editar](https://creditoup.com.br/wp-admin/post.php?post=2321&action=edit) |
| p2 | PRESELL | Senai: qual duvida esta travando a sua decisao ago | `qual-caminho-senai-pr` | 2324 | `rec` | `draft` | [editar](https://creditoup.com.br/wp-admin/post.php?post=2324&action=edit) |
| p3 | SOLUTION | Cursos gratuitos do Senai: o que entra na conta e  | `cursos-gratuitos-senai-p1` | 2327 | `rec` | `draft` | [editar](https://creditoup.com.br/wp-admin/post.php?post=2327&action=edit) |
| p4 | SOLUTION | Edital do Senai: como ler antes de contar com a va | `edital-senai-como-ler-p2` | 2330 | `rec` | `draft` | [editar](https://creditoup.com.br/wp-admin/post.php?post=2330&action=edit) |
| p5 | SOLUTION | Certificado e diploma do Senai: o que cada documen | `certificado-diploma-senai-p3` | 2333 | `rec` | `draft` | [editar](https://creditoup.com.br/wp-admin/post.php?post=2333&action=edit) |
| **Aprenda Mais MEC** | | run `guia-aprenda-mais-mec-20260918-030001` | | | | | |
| p1 | LP | Aprenda Mais: o que e a plataforma do MEC e o que  | `guia-aprenda-mais-mec` | 2336 | `r` | `draft` | [editar](https://creditoup.com.br/wp-admin/post.php?post=2336&action=edit) |
| p2 | PRESELL | Aprenda Mais: qual e a sua duvida antes de comecar | `como-usar-aprenda-mais-pr` | 2339 | `rec` | `draft` | [editar](https://creditoup.com.br/wp-admin/post.php?post=2339&action=edit) |
| p3 | SOLUTION | Catalogo do Aprenda Mais: quem oferta cada curso e | `catalogo-aprenda-mais-p1` | 2342 | `rec` | `draft` | [editar](https://creditoup.com.br/wp-admin/post.php?post=2342&action=edit) |
| p4 | SOLUTION | Acesso ao Aprenda Mais: como e o cadastro e quem p | `acesso-cadastro-aprenda-mais-p2` | 2345 | `rec` | `draft` | [editar](https://creditoup.com.br/wp-admin/post.php?post=2345&action=edit) |
| p5 | SOLUTION | Certificado do Aprenda Mais: as regras da platafor | `certificado-aprenda-mais-p3` | 2348 | `rec` | `draft` | [editar](https://creditoup.com.br/wp-admin/post.php?post=2348&action=edit) |

Slugs reais **idênticos** aos planejados nos 15 — nenhum sufixo `-2`, nenhuma colisão com os 8
`rec` publicados, os 2 rascunhos de terceiros, as 9 LPs na lixeira ou a rota em 410.

## 3. Custo

| Funil | Custo real (US$) | Teto | Runs |
|---|---|---|---|
| Cursos SENAC | 4.2621 | 6,00 | 3 |
| Cursos SENAI | 1.6065 | 6,00 | 1 |
| Aprenda Mais MEC | 6.6145 | 6,00 (+1,50 autorizados) | 4 |
| **Total** | **12.4830** | **18,00** | 8 |

**Como foi medido**: `soma de cost_usd em runs/<id>/log.jsonl` + `image_gen_pN` do `state.json`.
O total do `report.md` **subestima**, porque um passo reexecutado sobrescreve o `StepResult`
anterior e o custo da rodada morta some do ledger — medido nesta sessão: o resume da p4 do MEC
fez o ledger do run *cair* de US$ 1,5849 para US$ 1,5162.

**Incertezas registradas**:
- O freio de orçamento usa o **preço declarado** da imagem (US$ 0,06), não o medido. O ledger usa
  preço por token do litellm; `gpt-image-2` está na tabela
  (`output_cost_per_image_token = 3e-05`, fonte `developers.openai.com/api/docs/pricing`).
  Medido: **US$ 0,0430–0,0433 por imagem**, consistente entre todas as páginas.
- O `Orcamento` não é persistido: cada invocação do CLI recomeça o teto do zero. Por isso o teto
  de cada run foi passado no perfil e **descontado à mão** do limite por funil.
- Pesquisa, verificação adversarial e revisão feitas por subagentes Claude consomem créditos de
  uso do Claude Code — pool diferente, **não** contabilizado nos US$ 18. Volume: 38 agentes,
  ~4,8 milhões de tokens de subagente.

## 4. Pesquisa: fonte por alegação

657 alegações levantadas em fontes oficiais, cada uma submetida a **verificação adversarial** —
um segundo agente reabriu a URL e tentou refutar.

| Instituição | Sustentadas | Derrubadas | Hosts oficiais distintos |
|---|---|---|---|
| SENAC | 198 | 51 | 29 |
| SENAI | 180 | 40 | 29 |
| Aprenda Mais MEC | 163 | 25 | 7 |
| **Total** | **541 (82%)** | **116** | **65** |

Todas as URLs sustentadas responderam vivas na releitura. Ledger completo em
`entrega/ledger-fontes.json` (alegação, URL, trecho de apoio, data de consulta, data de
atualização quando declarada, abrangência, tipo de curso, veredicto); as derrubadas com motivo e
correção em `entrega/ledger-derrubadas.json`; a varredura bruta em `entrega/pesquisa-bruta.json`.

As derrubadas são quase todas **exagero, não invenção**: exclusividade ("um único ponto da rede"),
generalização ("se limita a"), troca de nomenclatura (curso "profissionalizante" virando "curso
livre"), enumeração incompleta de filtros e "deve ser" onde a fonte diz "priorizando-se".

### Armadilhas que a pesquisa encontrou e o conteúdo teve de evitar

**SENAC** — `senac.br` e `dn.senac.br` são do Departamento Nacional; quem matricula e abre vaga é
o Regional. `rs.senac.br` **não existe** (o RS usa `senacrs.com.br`); **`senacrj.com.br` estava
estacionado à venda em 17/09/2026**. O arquivo oficial do próprio DN registra um endereço de PSG
por regional. Só o ensino superior tem registro e-MEC.

**SENAI** — a gratuidade **não** se chama PSG (isso é Senac): é Gratuidade Regimental, e não
alcança graduação nem pós. Jovem Aprendiz é contrato de trabalho, não "um curso". Não existe
buscador nacional nem matrícula única. Idade mínima, nota de corte e taxa variam **por edital**.
Aprovação no técnico não gera diploma sozinha. `senai.br` serve uma página de redirecionamento de
2020 com certificado TLS que não cobre o nome.

**Aprenda Mais MEC** — "reconhecido pelo MEC" é falso e a própria FAQ responde "Não": são cursos
livres/MOOC. Quem assina o certificado é a instituição da Rede Federal, não o MEC. Não há tutoria.
O acesso **não** é por conta gov.br. O direito ao certificado **caduca com a turma**. Nenhum
benefício estudantil.

## 5. Papéis das páginas

A hipótese do briefing foi ajustada com a pesquisa, como ele mesmo pediu. Dois ajustes, com motivo:

1. **A última solução não pode citar canal oficial.** `config.yaml → SOLUTION_TERMINAL` proíbe
   `external_official` e `official_link_density` isenta a terminal (`checks.py:790`). O "como
   proceder no portal" ficou nas soluções do miolo, que têm link oficial verificado; a terminal
   fecha com certificado/cuidados e recircula.
2. **O funil SENAI mudou de eixo.** O site já publicou em 15/09/2026 três páginas `/rec` de SENAI
   (`quem-pode-fazer-senai`, `lista-cursos-senai-vagas`, `unidades-senai-telefone-endereco`) que
   cobrem requisitos, modalidades/EAD/bolsas e unidades por estado. Repetir isso seria duplicata.
   O funil desta missão ataca o que **não** está coberto: o mecanismo da oferta, a leitura do
   edital e o que cada documento de conclusão comprova.

| Funil | p1 LP | p2 pré-sell | p3 solução | p4 solução | p5 solução terminal |
|---|---|---|---|---|---|
| SENAC | estrutura federativa antes de procurar | qual é a sua situação hoje | tipos de curso: livre/técnico/superior | bolsas de estudo: onde cada estado publica | portal do seu estado: confirmar que é o certo |
| SENAI | como a oferta gratuita funciona | qual dúvida trava a decisão | cursos gratuitos: o que entra e o que fica de fora | edital: como ler antes de contar com a vaga | certificado × diploma: o que cada um comprova |
| MEC | o que a plataforma é e o que não é | qual é a sua dúvida | catálogo: quem oferta e como as turmas funcionam | acesso: cadastro e quem pode estudar | certificado: as regras para emitir o seu |

## 6. Auditoria de hrefs, aviso e coleta de dados

- **Aviso determinístico**: presente como **primeiro container** do `_elementor_data` em cada LP
  (conferido por leitura de volta: `volc-editorial-notice` na posição 257 do JSON, antes dos dois
  heróis) e no início de cada interna (conferido no `content.raw` salvo).
- **Nota de utilidade pública** no corpo de todas as internas.
- **Links externos**: todos institucionais. Vários são **deep links** verificados ao vivo —
  `sp.senac.br/programa-senac-de-gratuidade`, `senacrs.com.br/hotsite/psg/`,
  `sp.senai.br/cursos/0/0?gratuito=1`, `sp.senai.br/processo-seletivo/...`,
  `sp.senai.br/consulta-certificado`, `pe.senai.br/editais/`.
- **Links internos**: só para slugs deste funil, sem self-loop, sem `-2`, sem rota em 410.
- **Saída cross-funnel**: alvo real do sitemap, conferido HTTP 200. A regra de diversidade do
  motor manda para um guia de **tema diferente** — na prática, guias de crédito do próprio site.
  É o comportamento projetado (`cross[page.ordinal % len(cross)]`), não defeito; testei cinco
  variações de H1 e nenhuma leva a um guia de educação, porque só existem 3–4 no site e eles
  ocupam sempre os índices 0–2.
- **Coleta de dados**: varredura dos artefatos por `<form>`, `<input type=text|email|tel|password>`,
  `<textarea>`, `<iframe>`, pixel/tracker e `<script src=>` → **nenhuma ocorrência**. As afirmações
  do aviso ("não pedimos senhas, CPF ou dados bancários") são verdadeiras na página final.
- **Imagens**: todas com recibo SHA-256 conferindo contra os bytes em disco e `accepted=true` na
  revisão visual. Conferência **manual** feita também: cena genérica de leitura, sem logo, selo,
  uniforme, documento oficial, QR, tela de login ou marca de aprovação.

## 7. Achados do motor — o que o Codex precisa olhar

Ver `CAMPANHA-3-FUNIS-ACHADOS-MOTOR-2026-09-17.md`, ao lado deste arquivo. Resumo dos que mudaram
o resultado:

- **A1 (corrigido, com sua autorização)** — `redator_presell.jinja:93` e `redator_pages.jinja:173`
  mandavam usar `<u>`; a allowlist de `editorial_safety.py` (criada hoje) não aceita `u`. Matou uma
  página depois de tudo pago. Retirada a instrução dos dois prompts; o gate **não** foi tocado;
  760 testes seguem passando.
- **A10** — `emotional_objective` é **copy visível** ao leitor no bloco qualificador da pré-sell
  (`steps.py:190`). Objetivos escritos como instrução vazaram literalmente para a página. Reescrevi
  os 15 como "o caso do leitor". Não está documentado no contrato do card.
- **A13** — os canais mais autoritativos são inverificáveis desta máquina: `planalto.gov.br`
  responde 200 com UA de navegador e dá **timeout com o UA honesto do motor**; `ead.senac.br`
  negocia TLS com **chave Diffie-Hellman fraca**; `senac.br`/`dn.senac.br` devolvem **403 de WAF**.
- **A14** — `target_keywords` do card **não** chega à pesquisa (`steps.py:534`): só H1 e H2 viram
  consulta. Trocar keyword não muda nada.
- **A15** — armadilha de ambiente: o `.pth` do editable install parou de ser honrado pelo `site`
  no meio da sessão, duas vezes. Runs já iniciados seguiam funcionando; invocações novas falhavam.
  Contornado com `PYTHONPATH`.

## 8. Pendências, fatos não confirmados e dependências manuais

### P1. Prova visual real do Elementor — PENDENTE
Extensão do Chrome não conectada; Application Password não autentica wp-admin. **O que fazer**
(humano, com sessão): abrir o link de edição de cada post no `INDICE-PRIVADO.md` e usar
**Visualizar**. Na LP conferir: aviso antes do herói, um H1 só, botões com os destinos certos,
imagem carregando, sem overflow em 375px e 1440px. Nas internas: aviso no início, tabela/accordion
legíveis, links oficiais abrindo. O link de preview carrega nonce da sessão de quem abre — por
isso **não** está registrado em lugar nenhum, e nenhum href de produção foi trocado por nonce.

### P2. Card no Pautador — NÃO CRIADO
Todas as rotas de `/api/pautador` e `/api/publicacao` exigem JWT de sessão do Supabase com papel
admin, e a `VOLC_SERVICE_KEY` não está configurada no `backend/.env` (`exigir_servico` responde
503 por construção). Escrever direto nas tabelas seria contornar o serviço, não usá-lo — então não
foi feito. Rastreabilidade preservada por `project_id = 2`, arquiteturas versionadas em
`.perfil-run-creditoup-20260917/arquiteturas/`, `run_id` e `post_id` no manifesto.

### P3. Achados editoriais para o seu olho (não bloqueantes, todos em rascunho)
- **SENAC p4**: "Por força de lei, o equivalente a 66,67 % da receita de contribuição compulsória
  líquida é revertido em vagas gratuitas desde 2014." Está ancorado — a `fonte_primaria` é
  `sp.senac.br/programa-senac-de-gratuidade`, que está no conteúdo — mas número, data e "por força
  de lei" na mesma frase, com o link noutro ponto da página, merecem sua leitura.
- **SENAI p2**: "o candidato precisa ter a idade mínima de 14 anos". É a armadilha que a pesquisa
  mapeou: 14 é o piso em SP e na qualificação gratuita do PR, mas o edital do SENAI-RJ Tijuca fixa
  16 em dois cursos e 18 em outro. A frase hedgeia com "dependendo da modalidade", não com
  "dependendo do regional/edital". **Correção sugerida**: "a idade mínima varia por edital e por
  Departamento Regional".

### P4. Links oficiais em domínio-raiz em parte das páginas
`canal_profundo.aprofundar` roda (Playwright instalado) mas é fail-safe: quando o portal barra o
navegador automatizado, devolve a raiz. Parte dos `official_links` saiu como `https://www.sp.senac.br`.
A raiz abre e é honesta, mas o leitor ainda navega. Limite de coleta, não defeito de conteúdo.

### P5. Grafo do VOLC O.S. defasado
`atualizar_grafo_volc_os.py --check` → `current: false` (build em `a539dbd`, HEAD `9f70f65`).
Toda decisão desta missão veio do código atual, não do snapshot.

### P6. O que NÃO foi tocado, por decisão
Nginx, DNS, Cloudflare, SSH, usuários, plugins, temas, formulários existentes, GTM, consentimento,
anúncios, GAM/AdX/Ad Inserter, campanhas do Google Ads, caches globais, sitemap, páginas publicadas
e rotas em 410. Nenhuma contestação, nenhum teste de clique em anúncio, nenhum deploy do motor,
nenhuma alteração global. Os dois rascunhos `rec` de terceiros (1937, 1931) e as 9 LPs na lixeira
permanecem intactos. O `config.yaml` global do motor segue com `official_screenshots: true` e mtime
anterior à sessão — a execução usou um **perfil isolado** com `config.yaml` próprio e symlinks para
`.env` e `runs/` (mesmo inode do `_phrase_registry.json` confirmado, então o registro anti-duplicata
compartilhado continuou valendo entre os três funis).

### P7. Segredo
Nenhuma credencial foi impressa, copiada para relatório ou versionada. O perfil com a senha
decifrada foi gerado pelo gerador existente (`backend/app/redator/perfil.montar_perfil`) em arquivo
`0600` sob diretório `0700` **fora da árvore do repositório**; o diretório de execução inteiro está
em `.gitignore`. Conferido: nenhum JSON no repositório contém `app_token`.

## 9. Protocolo de fechamento

- **Tarefa**: `P10-T17` (Reforcar identidade editorial e artefatos do Redator), em
  `volc-os-workbook/ROADMAP-VIVO.json`. Mantida **`partial`** — nao promovida, porque a
  prova visual do layout Elementor, que a propria aceitacao da tarefa exige, nao foi
  obtida. A prova adicionada e a que faltava e foi conseguida: imagem real aprovada com
  recibo SHA-256, ambiente do worker e rascunho Elementor no WordPress.
- **Curadoria operacional**: nao alterada. Nenhum estado, evidencia ou relacao de
  negocio mudou materialmente — esta missao exercitou capacidade existente, nao criou
  nem aposentou nenhuma.
- **Grafo**: `atualizar_grafo_volc_os.py --check` -> `current: false` (build em
  `a539dbd`, HEAD `9f70f65`). O rebuild oficial foi **tentado** e falhou no detector de
  segredos (`scripts/verificar_segredos.py` -> `.env_webgo: jwt`, preexistente). O
  detector **nao** foi contornado e o `.env_webgo` **nao** foi lido nem alterado.
- **Nos do grafo afetados**: `cap_funnel` (via P10-T17).
