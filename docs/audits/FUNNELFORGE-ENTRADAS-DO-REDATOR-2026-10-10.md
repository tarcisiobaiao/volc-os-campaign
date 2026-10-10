# FunnelForge: entradas melhores para o redator, sem travas mecânicas (10/10, 3ª rodada)

Base: `main` @ b5e50d9e. Escritor único. Nada publicado: nenhum WordPress,
Supabase (só leitura de um card), Ads, deploy ou push.

Direção do operador: implementar o 80/20 da auditoria estratégica (M1 → M4 →
M3 → M5; M2 como orientação editorial; M6 só como repasse de dado existente),
sem reintroduzir validação semântica mecânica. Nenhuma das mudanças abaixo é
veto de palavra, contagem, similaridade lexical, heurística de negrito ou
bloqueio editorial: são entradas melhores para arquiteto, redator, sniper e
gerador de ferramenta, no caminho canônico (`run-volc` com card →
`congelar_pacotes` → `prompt_do_pacote` → `revisar_lote`).

## 1. Mudanças no motor

| Id | Mudança | Onde (caminho ativo) | Prova |
|---|---|---|---|
| M1 | O arquiteto recebe que `resposta_imediata` é a resposta ao leitor, afirmativa e nas palavras de quem busca, com a condição que decide; o limite do portal ("não consulta, não cadastra, não confirma") o sistema aplica uma vez no aviso editorial e não entra em `resposta_imediata`, `useful_delivery`, `emotional_objective`, hook ou cta. Um limite que É a resposta ("não existe pedido online") fica. Botões do plano pela entrega do destino, sem forma obrigatória. | `backend/app/n8n_prompts/funnel_builder.py` (`<criterios>`, `<jornada>`), carregado pelo motor em `inteligencia.mensagens_do_arquiteto` | `test_arquiteto_separa_resposta_imediata_do_limite_do_portal` |
| M1 | A jornada da página diz ao redator (e ao revisor, que inclui o mesmo template) que a resposta imediata declarada não é o aviso do portal: se ela trouxer esse limite, escreve-se a resposta e as condições e o limite fica para o aviso, salvo quando é a própria resposta. Vale para esqueletos aprovados antes desta rodada. | `prompts/jornada_da_pagina.jinja` | `test_jornada_interior_e_sniper_orientam_sem_vetar` |
| M2 (orientação) | O primeiro parágrafo das internas é a resposta imediata, com a condição que decide em `<strong>`; a situação do leitor, se entrar, é a segunda frase; pergunta sem resposta não abre a página. Nenhuma heurística no código: a navegação continua após o 1º parágrafo e a meta description continua sendo o 1º parágrafo. | `prompts/interior_editorial_v2.jinja` (Navegação do topo) | idem |
| M4 | Sniper: a forma do rótulo segue a entrega do destino (dúvida → dúvida; passo ou conferência → resultado; perfis → situação); pergunta, verbo ou primeira pessoa não são obrigatórios nem proibidos; o conjunto não precisa da mesma forma; "trocar Saiba por Descubra não é melhora"; escrever como quem busca no país e idioma do funil. Exemplos do operador como direção de linguagem. | `prompts/ctas_do_funil.jinja` | idem; `test_sniper_mostra_contraste_resposta_tema_sem_proibir_verbo` continua |
| M4 | Transição: a frase antes do botão principal nomeia a dúvida concreta que ficou aberta (tensão residual) ou a consequência da resposta; não descreve o site nem a navegação; "continua neste site" só quando há, por perto, um passo em outro site. | `prompts/interior_editorial_v2.jinja` (`<conexoes>`) | idem |
| M3 | O redator recebe a peça pronta como o leitor a lê: pergunta com opções e, por cenário, chip, título, passos ou itens e rodapé (`peca_em_texto`), com a instrução de explicar o porquê e o que a peça não cobre, sem repetir os cenários em lista, passos ou tabela. O JSON e o HTML continuam fora do prompt; o pacote congelado segue inteiro para a correção localizada do revisor. | `inteligencia.peca_em_texto`, `inteligencia.prompt_do_pacote` | `test_redator_recebe_os_cenarios_da_peca_em_texto_e_nao_o_json` |
| M3 | O gerador da peça recebe as seções (H2 do plano) e os blocos planejados da página, com a instrução de complementar (ramificação por situação) em vez de repetir, de devolver NONE quando os blocos já fazem a divisão, e de não repetir o aviso que o sistema imprime no topo da peça. | `inteligencia.preparar_widgets_de_orientacao`, `prompts/widgets_do_funil.jinja` | `test_gerador_da_peca_ve_as_secoes_e_blocos_que_o_texto_ja_entrega` |
| M5 | A legenda do print reaproveita a proveniência que o motor já gravava e descartava: o título da página capturada (lido pelo Chromium na captura) e o trecho que essa fonte sustenta no texto. Sem título ou trecho, a legenda fica como era. O alt descreve a imagem (site e página), sem keyword. | `steps.legenda_do_print`, `steps._insert_official_screenshot`, `steps._embed_official_screenshots`, `steps.proveniencia_do_print` | `test_legenda_do_print_*`, `test_figcaption_*`, `test_alt_do_print_*` |
| M6 (repasse) | A promessa e a profundidade que o arquiteto já declara por coorte (`funnel_strategy.jornada.coortes`) chegam ao prompt da página de entrada daquela coorte ("quem chega por paid_search espera: …, resposta direta na dobra"). Só repasse; nenhuma personalização ou infraestrutura nova. | `jornada/contexto.contexto_de_jornada` (`coortes_detalhadas`), `prompts/jornada_da_pagina.jinja` | `test_coortes_detalhadas_sao_so_as_que_entram_na_pagina` |

Não feito, de propósito (direção do operador): nenhuma seleção de parágrafo
por `<strong>`, nenhuma obrigação de variar botões, nenhuma contagem de
ressalvas, nenhuma regra sobre meta description, nenhum grep de palavra como
critério, nenhuma similaridade lexical entre widget e texto, nenhuma
classificação de resposta por conter negação. As verificações técnicas
(Gutenberg/HTML, widgets, cálculos, URLs, proveniência, gate) ficaram como
estavam.

## 2. Canário: outro contexto, mesmo idioma

Consulta somente leitura ao Pautador (`pautador_entity_opportunities`,
`pautador_entities`): 45 cards, todos com `country_code = BR`; nenhum card de
outro país ou idioma existe para um canário real. Escolhido o card 65 (FGTS
Saque-Aniversário, status `ready`, arquitetura de agosto sem jornada, 20 termos
reais), montado pelo mesmo `card_do_motor`/`_termos_do_card` do backend, com
contextos de busca e anúncio ausentes (sem campanha vinculada). O arquiteto
replaneja o funil com a pesquisa em mãos: é o teste real de M1.

Entrada canônica: `run-volc arquitetura.json --perfil perfil.json
--card-pre-arquitetura card.json --timestamp 20261010-fgts-canario --canario`,
sessão ChatGPT (`chatgpt_plan`), sem fallback faturado. Teto de 16 chamadas
registrado em `teto.json` antes da primeira chamada.

**Resultado: o canário não fechou.** O arquiteto planejou 9 páginas (a
referência de agosto tinha 5) e o teto de 16 chamadas caiu antes da 9ª redação
e da revisão em lote. Nenhuma página foi aprovada; nada foi composto pelo
caminho de publicação. Chamadas: inteligência 2 + arquiteto 1 + dossiê 2 +
ferramentas 1 + sniper 1 + redações 9 (p3 em 2 tentativas) = 16, em 12 min
(19:10 → 19:22), US$ 0, `chatgpt_plan`. Sem segunda geração, como autorizado.

| Etapa | O que saiu | Relação com a rodada |
|---|---|---|
| Arquiteto (M1) | 9 páginas; `resposta_imediata` afirmativa em todas, sem "não consulta/não cadastra/não confirma"; LP → pré-sell → 7 soluções; coortes com promessa e profundidade | M1 ativo. Limite: p4 e p8 trouxeram nota de verificação na resposta ("só deve ser publicado após confirmar…"); o prompt ganhou a regra "dúvida de vigência vai em requisitos" depois desta chamada |
| Dossiê | 41 fatos, 1 complementação; 4 páginas `ready`, 5 `review` (promessa central sem lastro) | igual ao canário anterior |
| Ferramentas (M3) | 5 candidatas; 3 peças (p3 navegador, p4 e p9 diagnóstico) e **2 NONE com motivo** ("o checklist, os passos no App FGTS e a seção sobre o mês de aniversário já cobrem as decisões que um navegador apresentaria") | é o comportamento pedido: a peça complementa ou não existe |
| Sniper (M4) | 22 rótulos, 0 recusas; dobra "Saque-aniversário: retire parte do FGTS"; saídas oficiais nomeadas ("CAIXA: onde aderir ao saque-aniversário") | formas mistas (situação "Já optei: …", dúvida, resultado); a entrega ajustada ainda saiu como descrição da página ("Compara…"); o prompt ganhou a regra "escreva-a como resposta ao leitor" depois desta chamada |
| Redação | 8 rascunhos (p1–p8); p9 não redigida (teto); **p2 e p3 FAILED em `duplicate_content`** (limiar 0,35; o guarda mediu 0,389 p2×p1 e 0,358 p3×p2 — os 0,346/0,353 citados antes vinham de texto limpo à mão, não da entrada do guarda; correção na seção 5) | validador lexical pré-existente, não alterado: a própria `UniquenessConfig` diz que funil de tema único ("all-FGTS") fica ~0,4 e só eleva o limiar para hub×hub |
| Revisão em lote | não executada (seria a 17ª chamada) | — |

Observável nos 8 rascunhos (sem revisão), comparado ao canário Tarifa Social:

| Sinal | Tarifa Social (b5e50d9e) | FGTS (esta rodada) |
|---|---|---|
| "não consulta / não confirma / não cadastra / isoladamente" no corpo | 1 a 3 por página | 0 em 8 páginas ("não substitui" ×3) |
| frases que descrevem o site ("o próximo guia deste site…") | 5 | 0 |
| 1º parágrafo com a resposta e a condição em negrito | p2 sim; p3 era pergunta sem resposta | p2–p8 sim; a intro da LP ainda abre com pergunta (template da LP, fora do prompt das internas) |
| `<strong>` por página | 8–16 | 6–17 |
| peça de orientação repetindo lista/tabela | p3 e p6 (triplicata) | gerador recusou 2 de 5 por esse motivo; nas 3 peças, texto e peça não puderam ser comparados na página (a injeção da peça acontece no acabamento, que não rodou) |

## 3. Validação

- **Motor:** 1765 testes passaram, 0 falharam, 0 pulados, com `FF_VISUAL_BROWSER=1`; 9 testes novos em `tests/test_entradas_do_redator.py`.
- **Prompts reais do canário** (`producao/funil-canario-fgts-20261010/prompts/`): as instruções novas estão nos prompts emitidos (arquiteto, widgets com "Seções e blocos que o texto já entrega", sniper, redator com "O que a peça já diz ao leitor", "não o aviso do portal", "o primeiro parágrafo é a resposta imediata", "Ela não descreve o site", coortes detalhadas na p4).
- **Previews dos rascunhos não revisados** (`roteiros/preview_rascunhos.py`: LP pelo `step_build` sem imagem; internas com o corpo do `step_write` e os prints do `step_screenshot` canônico, embutidos por `_embed_official_screenshots`, sem modelo): http://127.0.0.1:8094/index.html, capturas em `visual/`.
  - Auditoria visual do motor a 390/1440: 7 de 8 páginas passam; a p2 (pré-sell) reprova em `links_plan_and_verified_sources` (página que também reprovou na redação).
  - Chromium funcional: 0 erros JS, 0 rolagem lateral, 0 link interno quebrado; navegação do topo na dobra, antes do 1º H2, em p2 (7 botões), p3 (3), p4, p5 e p7; p6 sem navegação (único link do plano caiu no roteamento) e p8 terminal.
  - Prints com a legenda nova em p3, p4 e p7: "Reprodução: site oficial (www.fgts.gov.br), capturada em 10/10/2026 — página “Saque Aniversário”. O que esta fonte sustenta no texto: …".
  - Tabelas de 3 colunas rolam dentro do bloco a 390 px em p3, p4 e p5 (mesmo limite do canário anterior).
- **Não provado:** revisão contextual, publicação, WordPress real, anúncios, tráfego, CTR, receita.

## 4. Pendências

1. **Teto × número de páginas.** 9 páginas não cabem em 16 chamadas (mínimo 16 sem retentativa). Para fechar um canário de card novo, o operador decide: teto maior, ou pedir ao arquiteto menos páginas para o canário, ou aceitar canário só de esqueleto aprovado.
2. **`duplicate_content` em funil de tema único.** p2 (hub) e p3 reprovaram por 0,389/0,358 contra 0,35. **Resolvido na seção 5**: o operador decidiu que similaridade lexical não bloqueia (sem mexer no limiar).
3. **Revisar os 8 rascunhos** (1 chamada da revisão em lote) ou aprovar manualmente antes de qualquer composição final; p9 (antecipação) não foi redigida.
4. **LP:** a intro ainda abre com pergunta-gancho; a orientação de M2 entrou só no prompt das internas. Levar a mesma frase ao `redator_p1_v2` é uma linha, mas fica para a próxima rodada com canário.
5. **Legenda do print:** o trecho sustentado pode ser longo (cortado em 200 caracteres); conferir legibilidade no tema real.
6. **Entrega ajustada como descrição da página** e **nota de verificação na resposta imediata**: os dois prompts já foram corrigidos depois do canário; só o próximo run prova.
7. Nenhum card de outro país/idioma existe no Pautador: a generalização de idioma está só na redação dos prompts, não em canário.

## 5. Reavaliação: similaridade lexical deixa de bloquear (10/10, rodada curta)

Decisão do operador: palavras parecidas entre páginas do mesmo tema não
bloqueiam redação, revisão, composição nem publicação; não se eleva limiar nem
se cria exceção por tema, hub ou canário. Redundância material de entrega é do
revisor contextual. Nenhuma chamada de modelo nesta rodada; o funil não foi
regenerado; recibos históricos do canário ficam como estão.

**Pontos bloqueantes corrigidos (caminho canônico):**

| Consumidor | Antes | Agora |
|---|---|---|
| `steps.uniqueness_state_guard` (serial, depois do `step_write`, e consolidação do lote paralelo em `pipeline.py`) | `write_pN` FAILED + `duplicate_content` → `blocked_pN`, sem revisão nem build; retomada redige de novo | observação `similaridade_lexical` no `write_pN` (par mais parecido, idempotente), status intacto |
| `steps.presell_hub_distinction_guard` (mesmos dois pontos) | `write_pN` FAILED + `hub_not_distinct` | mesma observação; `_fail_hub` removido (sem consumidor) |
| `retry_policy.CODIGOS_PATCHAVEIS` | `duplicate_content` era estrutural | `similaridade_lexical`, `duplicate_content`, `hub_not_distinct` são localizadores (nenhuma retentativa) |
| revisor contextual (`steps._contexto_da_revisao`) | não via a métrica | recebe a observação como localizador: "Observação, não defeito… aponte só repetição material de entrega" |

Já não bloqueavam no canônico e ficaram como estavam: o validador `uniqueness`
e `opening_line_unique` (saem do V2 em `validadores_tecnicos`; continuam no V1
arquivado). Verificações técnicas (HTML/Gutenberg, JS dos widgets, cálculos,
links, segurança, recibo) inalteradas.

**Replay de p2/p3 sem modelo** (`producao/funil-canario-fgts-20261010/roteiros/replay_similaridade_p2_p3.py`,
recibo em `reavaliacao-similaridade/recibo-replay-similaridade.json`), numa
cópia do run; o `state.json` original ficou com o mesmo sha256:

| | p2 (pré-sell) | p3 (vale a pena) |
|---|---|---|
| Histórico do run (não alterado) | FAILED, `duplicate_content` contra p1 | FAILED, `duplicate_content` contra p2 |
| Veredito do próprio passo de redação | aprovado na 1ª tentativa | aprovado na 2ª (1ª caiu em `bloco_sem_fechamento`, retentativa técnica legítima) |
| Jaccard do guarda | 0,389 com p1 | 0,343 com p1; 0,358 com p2 |
| Consolidação com o código novo | `write_p2` OK + observação | `write_p3` OK + observação |
| Laço redigiria de novo / condena / bloqueia antes do build | não / não / não | não / não / não |
| `revisar_lote` canônico (coletor no lugar do modelo) | entra no lote, observação no prompt como localizador | idem |
| HTML/Gutenberg no rascunho real / com um bloco sem fechamento | nenhum / `unbalanced` estrutural | nenhum / `unbalanced` estrutural |

Isso não aprova nada: o coletor levanta erro de propósito, e na cópia p2/p3
ficariam em revisão humana. **Continuam pendentes:** p9 não redigida; revisão
contextual final das 8 páginas (1 chamada); decisão sobre teto × número de
páginas para fechar um canário de card novo.

**Testes focados:** `test_similaridade_nao_bloqueia.py` (4 novos),
`test_bloqueios_editoriais_v2.py`, `test_steps_prompt_routing.py` (hubs),
`test_paginas_paralelas.py::test_15` (serial e paralelo com o mesmo veredito,
0 condenadas, 4 observadas), uniqueness, smoke, sniper, widgets, revisor:
250 passaram. `git diff --check` limpo.
