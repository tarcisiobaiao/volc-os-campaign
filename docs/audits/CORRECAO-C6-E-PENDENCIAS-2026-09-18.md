# Correcao C6 e pendencias factuais

Data UTC: 2026-09-18. Estado: **DRAFT_WITH_GAPS**, sem publicacao.
Esta revisao sucede o handoff CORRECAO-3-FUNIS-HANDOFF-2026-09-18.md.

## Resultado verificado

- 15 posts relidos por REST autenticada antes e depois; todos continuam draft,
  com os mesmos IDs, slugs, tipos e templates.
- Seis posts existentes corrigidos, nenhum criado; nenhuma nova midia.
- Nove posts intocados, incluindo a LP SENAC editada pelo operador (2306).
- Referencias de imagens e hashes do JavaScript dos widgets inalterados.
- Zero chamadas pagas de geracao, zero publicacao, sem alteracao de anuncios,
  infraestrutura, credenciais ou configuracao de cache.
- 772 testes aprovados no engine, incluindo 12 novos testes de regressao.
  Ruff aponta cinco E501 em linhas preexistentes de steps.py fora desta
  alteracao; nenhum desses achados foi ocultado por mudanca de configuracao.

## Correcoes nos rascunhos

| Posts | Alteracao |
|---|---|
| 2318, 2333, 2348 | Retirados os dois botoes e o link de recirculacao financeira de cada terminal, suas pontes e notas de permanencia no mesmo site. A orientacao agora termina em canais oficiais relacionados ao assunto. |
| 2309 | Retirada a alegacao sem lastro sobre consulta publica de certificados do SENAC-SP, inclusive a linha correspondente da tabela. Orientacao para confirmar o atendimento da unidade. Nao afirmamos que a ferramenta inexiste. |
| 2318 | Retirada a generalizacao de requisitos de conclusao padronizados nacionalmente e de nota 6,0. O leitor deve consultar o regulamento do curso/regional. |
| 2336, 2342, 2348 | Retirada a conversao universal de carga horaria em dias minimos. O prazo passa a ser o da ficha do curso/turma, distinto da data limite da turma e da liberacao de avaliacoes. Corrigida tambem a explicacao do widget em 2348. |

Na LP MEC (2336), somente uma folha do JSON Elementor mudou:
`/3/elements/15/settings/editor`. A arvore, IDs, imagens, estilos e template
foram preservados. Na LP SENAC (2306), nenhum campo foi escrito.

Antes de cada escrita foram comparados modified_gmt, conteudo, metadados e
identidade contra o snapshot novo desta rodada. As seis respostas foram
relidas e comparadas byte a byte com o campo enviado. Foram enviados somente
`content` ou `meta._elementor_data`, sem regravar status, slug ou template.
Isso detecta mudancas anteriores a cada escrita, mas nao e um bloqueio
transacional contra edicoes simultaneas no WordPress.

## C6 no engine

Opcao explicita por perfil, sem modificar o padrao dos outros projetos:

```json
{"tema": {"terminal_exit_policy": "official"}}
```

O padrao continua `cross_funnel`. O valor e validado por tipo, sem liberar
override arbitrario de routing ou validators. Em modo official:

- Nao consulta o sitemap para escolher uma recirculacao.
- A terminal aguarda a pesquisa para receber o destino oficial da pagina.
- Remonta rotas sem conservar a recirculacao de um plano legado retomado.
- PageSpec exige external_official e proibe funnel/cross_funnel.
- Prompt pede encerramento editorial com links inline e identifica a saida
  para o site da instituicao. Nao obriga botoes nem notas de permanencia.
- Gate exige links reais no corpo; uma imagem com a mesma URL nao conta.
  Mantem densidade minima baseada nas fontes e rejeita links fora das URLs
  oficiais autorizadas daquela pagina.
- Apenas a validacao anterior a pesquisa adia a exigencia de URL oficial;
  a validacao de conteudo e a resolucao de links continuam fechadas.

Testes cobrem opcao tipada e isolada, legado preservado, fonte ausente ou
reprovada, retomada idempotente, URL inventada, caminho relativo, densidade,
prompt, avisos do grafo e paginas intermediarias inalteradas.

Nenhum run pago foi executado com essa nova opcao. O patch esta no codigo local;
nao foi feito restart/deploy de servico. As correcoes dos seis rascunhos foram
aplicadas diretamente por ID, nao reexecutando o publicador.

## Elementor 2306

Inspecao do HTML salvo encontrou seis SVGs com viewBox e paths estaticos
identicos, correspondentes aos icones; nesses SVGs nao foram encontrados
handlers, scripts, links externos ou foreignObject.

O alerta de shortcode corresponde a `su_accordion` e `su_spoiler`, usados
no FAQ. O proprio `lp_template.py::_su_accordion` gera essa estrutura.
O plugin `shortcodes-ultimate` foi confirmado **active** por WP-CLI
somente-leitura com skip-plugins/skip-themes.

Esses alertas isolados nao demonstram malware. Nao removemos o FAQ, nao
revertemos a edicao do operador e nao ampliamos a allowlist global de HTML.
Isso nao substitui a prova de renderizacao autenticada nem constitui auditoria
de seguranca completa do plugin.

## Fontes e destinos

Destinos conferidos por GET sem credenciais, todos HTTP 200 em 2026-09-18 UTC:

- [SENAC Transparencia](https://transparencia.senac.br/).
- [Registro de regionais publicado pelo SENAC](https://transparencia.senac.br/assets/settings/settings.json):
  confirmadas referencias a senacrs.com.br e rj.senac.br.
- [Consulta de certificado SENAI-SP](https://www.sp.senai.br/consulta-certificado).
- [Catalogo Aprenda Mais](https://aprendamais.mec.gov.br/course/index.php).
- [Ajuda Aprenda Mais](https://aprendamais.mec.gov.br/mod/page/view.php?id=134111).

A [categoria de Ciencias Humanas](https://aprendamais.mec.gov.br/course/index.php?categoryid=4&lang=pt_br)
exibe carga horaria e prazo de certificado por curso/turma. Exemplos pontuais
nao foram convertidos em regra universal. Remover a generalizacao nao significa
declarar falsos os prazos de cursos especificos que constam nas fichas.

## Evidencias e continuidade

Manifesto sanitizado:
`funnelforge-migracao/engine/.perfil-run-creditoup-20260917/entrega/manifesto-correcao-c6-2026-09-18.json`.
Contem hashes antes/depois, read-back, URLs finais e invariantes dos 15 posts.

Snapshots privados antes/depois e propostas:
`~/Downloads/CreditoUp-revisao-rascunhos-2026-09-18-private/snapshots/`
(diretorios 0700, arquivos 0600). Nao anexar essa pasta a repositorios publicos.
Nao contem as credenciais REST usadas na operacao.

Os runs e manifestos historicos foram preservados. **Nao retomar nem
republicar seus artefatos antigos sobre os rascunhos atuais**: o estado revisado
e o read-back desta rodada, documentado pelo novo manifesto. Uma retomada exige
conciliacao explicita com o WordPress, inclusive da edicao manual do 2306.

## Limites e veredito

C6 e as pendencias factuais acima: corrigidas e verificadas no escopo descrito.
Falta preview autenticado real desktop/mobile das LPs e internas, com
conferencia dos links entre rascunhos, FAQ, imagens, avisos e widgets.
Nao publicamos rascunhos para contornar essa falta de sessao.

**DRAFT_WITH_GAPS: nao liberar publicacao automatica.** Esta rodada nao e uma
revalidacao factual integral de todas as alegacoes dos 15 posts e nao garante
aprovacao ou recuperacao de conta no Google Ads.

Memoria operacional: P10-T17 / cap_funnel permanece partial e foi atualizada.
Rebuild executado, bloqueado pelo detector de segredo preexistente
`.env_webgo: jwt` (valor nao lido nem impresso; arquivo intocado).
O `--check` retornou `current: false`: grafo gerado em 2026-08-29,
commit construido a539dbd, HEAD 9f70f65. Nenhum bypass foi aplicado.
