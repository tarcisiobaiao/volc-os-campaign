# Revisão localizada no motor canônico (10/10/2026)

Tarefa: P10-T22 (`partial`). Nó: `cap_funnel`. Mesmo funil da Tarifa Social,
reaproveitando pesquisa, dossiê, rascunhos e mídias de 09/10.

## Bloqueios editoriais ativos (inventário do caminho V2)

| Código | Protege | Agora |
|---|---|---|
| `cta_generic`, `cta_editorial_execution`, `cta_external_channel` (listas de palavras) | preferência / julgamento que depende do destino | localizador para o revisor |
| `official_links_few` (cota de links oficiais) | preferência | localizador |
| nota 4–6 em `compliance`/`destination_relevance` | opinião numérica | aviso; segura só nota de falha (< 4) sem achado, que é resposta incoerente |
| `revisao_humana` do modelo sem bloqueante nem afirmação sem fato | cautela | vira ajuste/aprovação |
| patch recusado por forma (âncora ambígua, revalidação, texto de link) | integridade do patch | texto revisado segue; pendência registrada |
| `unbalanced`, `has_script`, `lp_schema`, `lp_sections`, `ad_slot_inseguro`, `cross_domain`, `unplanned_external_link`, `critical_claim_without_citation`, `ungrounded_critical_claim`, identidade/CNPJ, `duplicate_content`, `self_loop`, patch com URL/link/tag/número novo | técnica ou fato | continua bloqueando |

## Defeitos reais corrigidos

- Calculadora pronta nunca entrava na página no caminho com pacotes (widget
  pulado antes da revisão e depois do build). Agora entra antes do revisor.
- Ferramenta pronta apagava os rótulos de todos os botões ligados à página e
  trocava a promessa dela; só ferramenta indisponível faz isso agora.
- Cálculo puro (renda ÷ moradores) era desativado por falta do salário-mínimo
  vigente; agora segue, e o texto fica proibido de afirmar o limite em reais.
- Entrada de contagem aceitava "1,5 integrante" (achado do revisor global);
  `inteiros` validado no gabarito e no navegador.
- Card rearquitetava o plano aprovado; agora o plano aprovado com jornada é
  usado sem chamar o arquiteto, e plano refeito registra delta e suspende a
  publicação.
- Retomada usa o `config_snapshot.json` do run, não inferência por autenticação.
- Resposta truncada (`finish_reason` de corte) reprova na hora.
- Print mobile rola até o título, desconta cabeçalho fixo e tenta de novo uma
  vez quando a navegação cai; tabela de 2 colunas empilha no celular (CSS do
  MU-plugin, versionado, sem deploy); rótulo de saída oficial sem "site externo".
- `pydantic>=2.12` declarado (o código já usava `exclude_if`).

## Validação real (sem publicar)

Uma revisão global (gpt-6.1-sol, sessão ChatGPT, 295 s, sem fallback) sobre
as 7 páginas; 3 imagens novas (Gemini, US$ 0,2846; revisão servida por
`gemini-3.6-flash` no lugar de `3.5-flash`, marcada FALLBACK pelo motor).

- Aprovadas: LP, p3, p4, p5, p6, p7 (p4/p5/p7 estavam retidas em 09/10).
- p2 (pré-sell): retida por achado material do revisor na calculadora
  (fração de integrante). Defeito corrigido por código e provado no Chromium;
  a página espera `funnelforge decidir` (achado em widget exige pessoa).
- Patches aplicados: subtítulo da LP, duas frases com escopo factual, rótulo de
  saída oficial da p7. CTAs internos não foram alterados (notas 8–9).
- 5 prints oficiais mobile; calculadora: 1518 ÷ 4 = 379,50; "1,5" recusado.
- Chromium 390 px e 1440 px: 7 páginas sem bloqueio. Preview não executa tema,
  plugins, Elementor nativo nem anúncios; o CSS do MU-plugin não está no site.

Artefatos: `producao/recuperacao-motor-20261010/` (fora do Git).

## Limites

- Rota HTTP `/redator/disparar` sempre publica rascunho: não foi executada.
  Prova disponível: teste com rota real → worker real → motor dublê.
- p4 sem saída oficial verificada (aviso da revisão global).
- Falha restante na suíte do motor: `test_lp_ponte_sem_conteudo_e_reprovada`,
  lacuna real aberta pelo commit `19c0e14` (outra sessão): LP só de ponte passa
  no portão de destino pago sem `PAGINA_PONTE`.
