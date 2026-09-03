# CONTRAPROVAS — as 30 do briefing, e onde cada uma é provada

Regra de escrita, aplicada a todas: **VERMELHO → CORREÇÃO → VERDE**. Cada prova
foi escrita para falhar antes do conserto e exige o **código certo**, não um
veredito vermelho qualquer — um teste que só confere `ready is False` passaria
por acidente de outro achado e não provaria nada sobre a regra que diz testar.

Todas herméticas: nenhuma abre socket, nenhuma lê conta do Google, nenhuma
escreve em site nenhum. As que precisam de leitura ao vivo usam `monkeypatch`
sobre `fetch_public_https_chain`.

Arquivos:

| sigla | arquivo |
|---|---|
| **V2** | `backend/tests/test_landing_policy_espinha_v2.py` |
| **AX** | `backend/tests/test_landing_policy_contraprovas.py` (as A–X herdadas) |
| **PT** | `backend/tests/test_landing_policy_portao.py` |
| **B2** | `backend/tests/test_barreira2_publicacao.py` |
| **B3** | `backend/tests/test_barreira3_destino_de_campanha.py` |
| **MT** | `funnelforge-migracao/engine/tests/test_portao_destino_pago.py` |
| **FE** | `src/lib/landing-policy/__tests__/` + `src/components/trafego/__tests__/` |

---

## O quadro

| # | contraprova | onde | prova |
|---|---|---|---|
| 1 | `paid_destination` recusa hyperlink externo clicável | **V2** | `test_cp01_destino_pago_recusa_todo_hyperlink_externo_clicavel` — 3 casos: governo com âncora descritiva, fonte de pesquisa declarada, protocol-relative. **Os três passavam na v1.** |
| 2 | a mesma regra não se aplica a editorial | **V2** | `test_cp02_a_mesma_regra_nao_se_aplica_a_pagina_editorial` — o achado é REGISTRADO e não bloqueia |
| 3 | referência oficial evidence-backed aceita em `editorial_solution` | **V2** | `test_cp03_referencia_oficial_com_lastro_e_aceita_em_editorial_solution` |
| 4 | link externo desconhecido bloqueia | **V2** | `test_cp04_link_externo_desconhecido_bloqueia_por_dois_motivos` — por não-classificado E por externo |
| 5 | link interno do mesmo domínio passa | **V2** | `test_cp05_link_interno_e_caminho_de_contato_passam` (5 casos) + `test_cp05b_recurso_tecnico_nao_e_link_editorial_de_saida` |
| 6 | ausência de link externo não salva copy com falsa afiliação | **V2** | `test_cp06_ausencia_de_link_externo_nao_salva_copy_com_falsa_afiliacao` — e observado na página real, ver `LIVE-READ-SUMMARY.json` |
| 7 | ausência de identidade/disclosure bloqueia | **V2** | `test_cp07_identidade_e_disclosure_ausentes_bloqueiam_separadamente` + `test_cp07b_texto_escondido_nao_satisfaz_identidade_nem_disclosure` |
| 8 | missing evidence não vira verde | **V2** | `test_cp08_evidencia_ausente_nao_vira_verde` — varredura que EXPLODE reprova mesmo onde não é exigida |
| 9 | H1 perigoso capturado antes da publicação | **V2**, **MT** | `test_cp09_h1_perigoso_e_capturado_no_plano_antes_de_existir_corpo`, `test_cp09b_o_title_tambem_e_manchete_mesmo_com_h1_calmo`, `test_lp_com_h1_de_falsa_oficialidade_e_reprovada_no_gate_de_conteudo` |
| 10 | claim numérico sem fonte não passa em silêncio | **V2** | `test_cp10_alegacao_financeira_sem_divulgacao_nao_passa_em_silencio` |
| 11 | moeda brasileira malformada bloqueia | **V2** | `test_cp11_moeda_brasileira_malformada_bloqueia_no_pago_e_registra_no_organico` — **mudança de contrato**: era risco em toda parte |
| 12 | CTA externo ou incongruente bloqueia | **V2** | `test_cp12_cta_externo_e_cta_incongruente_bloqueiam` |
| 13 | gate vermelho impede a chamada ao adaptador WordPress | **MT**, **B2** | `test_publicacao_reprovada_nao_chama_o_publisher`, `test_sem_o_contrato_a_publicacao_nao_toca_o_wordpress` — **sentinela**: publisher falso que chama `pytest.fail` se invocado |
| 14 | publicação aceita gera recibo e fingerprint | **MT**, **B2** | `test_publicacao_aceita_grava_recibo_e_impressao` |
| 15 | alteração após aprovação invalida elegibilidade | **V2**, **B3** | `test_cp15_alteracao_apos_a_aprovacao_invalida_a_elegibilidade`, `test_cp15c_repontar_um_cta_interno_e_deriva`, `test_alteracao_depois_da_aprovacao_invalida_a_elegibilidade` |
| 16 | recibo de versão antiga não é reusado em silêncio | **V2**, **B3** | `test_cp16_recibo_de_versao_antiga_nao_e_reaproveitado_em_silencio`, `test_recibo_de_politica_antiga_nao_e_reusado_em_silencio` |
| 17 | leitura ao vivo indisponível falha fechada | **V2**, **B3** | `test_cp17_leitura_ao_vivo_indisponivel_falha_fechada`, `test_leitura_ao_vivo_indisponivel_falha_fechada` |
| 18 | redirect cross-domain bloqueia | **V2**, **B3** | `test_cp18_redirect_cross_domain_bloqueia`, `test_redirect_cross_domain_bloqueia` |
| 19 | cadeia excessiva ou destino divergente bloqueia | **V2**, **B3** | `test_cp19_cadeia_excessiva_bloqueia_e_um_salto_de_rotina_nao`, `test_cadeia_de_redirecionamento_excessiva_bloqueia`, `test_destino_que_nao_serve_a_pagina_nao_e_destino` |
| 20 | conteúdo diferente por user-agent é sinalizado | **V2**, **B3** | `test_cp20_conteudo_diferente_por_user_agent_e_sinalizado`, `test_conteudo_diferente_para_o_rastreador_e_sinalizado` |
| 21 | diferença só de dispositivo não é falso positivo | **V2**, **B3** | `test_cp21_diferenca_apenas_de_dispositivo_nao_e_falso_positivo`, `test_diferenca_so_de_dispositivo_nao_e_falso_positivo` |
| 22 | `/provar` recusa landing inelegível | **B3** | `test_destino_conforme_deixa_o_selo_sair` (simétrico) + as recusas |
| 23 | `/subir` revalida e não confia só no `/provar` | **B3** | `test_subir_revalida_ao_vivo_e_nao_confia_no_provar` |
| 24 | cliente não envia papel menos rigoroso | **V2**, **B3** | `test_cp24*` (4 provas), `test_o_papel_avaliado_e_sempre_o_do_servidor`, `test_url_manual_do_cliente_nao_desarma_nada` |
| 25 | nenhum bloqueio executa Google Ads mutate | **B3** | `test_nenhum_bloqueio_alcanca_o_mutate`, `test_subir_recusa_antes_de_abrir_o_ledger_quando_a_leitura_falha` — **sentinela** no executor |
| 26 | testes herméticos, sem rede real | todos | `test_gate_da_lp_e_hermetico` + `monkeypatch` de `fetch_public_https_chain` em toda **B3** |
| 27 | scanner trata HTML, Markdown e campo estruturado | **V2** | `test_cp27_o_scanner_trata_html_markdown_e_url_nua` (4 formatos) + `test_cp27b_campo_estruturado_entra_na_varredura_como_o_corpo` |
| 28 | fonte registrada não vira hyperlink | **V2**, **MT** | `test_cp28_fonte_registrada_nao_vira_hyperlink_automaticamente`, `test_fonte_de_pesquisa_linkada_no_corpo_da_lp_reprova` |
| 29 | página-ponte sem valor original é recusada | **V2**, **MT** | `test_cp29_pagina_ponte_sem_valor_original_e_recusada` + `test_cp29b` (o simétrico), `test_lp_ponte_sem_conteudo_e_reprovada` |
| 30 | página útil, coerente e interna alcança verde | **V2**, **MT** | `test_cp30_pagina_util_coerente_e_interna_alcanca_verde`, `test_lp_util_e_interna_alcanca_verde` |

---

## Os cinco vermelhos que mais custaram

Cada um foi **medido**, não suposto, e cada um transformava ausência em
aprovação.

### V1 · o falso verde do `not_applicable`

**VERMELHO.** Com evidência de redirecionamento completa e **zero leitura ao
vivo**, `elegibilidade_de_destino_de_campanha` devolvia
`paid_destination_ready = True`. `not_applicable` está em `STATUS_CONCLUSIVOS`,
e `varrer_deriva` e `varrer_recibo` o devolviam quando não havia HTML observado.
O verde saía de **duas ausências**.

**CORREÇÃO.** `NAO_APLICAVEL_E_DESCONHECIDO_EM` — uma página que está no ar
sempre tem hash observável; "não se aplica" ali é impossível de boa-fé.

**VERDE.** `V2::test_cp17_leitura_ao_vivo_indisponivel_falha_fechada`.

### V2 · a varredura que explodia em silêncio

**VERMELHO.** `failed` só virava desconhecido quando o nome estava em
`EXIGENCIAS_POR_PONTO[ponto]`. No portão de pré-publicação, quatro verificações
não são exigidas: elas podiam quebrar inteiras e a publicação seguia autorizada.

**CORREÇÃO.** `failed` vira desconhecido em qualquer ponto. *"Não é exigível
aqui"* é decisão do contrato; *"quebrou"* é defeito do software.

**VERDE.** `V2::test_cp08_evidencia_ausente_nao_vira_verde`.

### V3 · a LP isenta do portão de conteúdo

**VERMELHO.** `pipeline/steps.py::step_content_gate` começava com
`if page.page_type == "LANDING PAGE": … status=OK; return`. A página que recebe
o clique comprado era a **única** do sistema marcada aprovada sem rodar
validador nenhum.

**CORREÇÃO.** A isenção foi apagada; a LP passa pelo contrato como qualquer
página, e o portão é a **primeira** instrução de `step_publish` — antes dos três
`upload_media`, senão uma página recusada já deixou mídia órfã no site ao vivo.

**VERDE.** `MT::test_lp_com_h1_de_falsa_oficialidade_e_reprovada_no_gate_de_conteudo`,
`MT::test_publicacao_reprovada_nao_chama_o_publisher`.

### V4 · a identidade aprovada por `OU`

**VERMELHO.** `not cnpjs and not (tem_sobre and tem_contato)` — uma página **sem
CNPJ nenhum** passava como operador identificado por conter as palavras "Sobre"
e "Contato". É a mesma forma do `adsense OU utilidade pública` que o
`ROOT-CAUSE-ANALYSIS.md` nomeia.

**CORREÇÃO.** Dois requisitos, dois achados: QUEM responde (registro) e COMO se
chega até ele.

**VERDE.** `V2::test_cp07_identidade_e_disclosure_ausentes_bloqueiam_separadamente`.

### V5 · o bloqueio FALSO fabricado pelo contador de botões

**VERMELHO.** `</a>` caía num `elif` da mesma cadeia e **nunca** decrementava a
profundidade: depois do primeiro `wp-block-button` da página, **todo** link
seguinte era marcado `em_botao`, fabricando `PAGINA_PONTE` e
`BOTAO_PARA_TERCEIRO_NAO_AUTORIZADO` em páginas corretas. O comentário afirmava
que a heurística errava "para MENOS botão"; ela errava para mais.

**CORREÇÃO.** O decremento saiu da cadeia `elif`.

**VERDE.** `V2::test_cp29b_pagina_longa_com_muitos_ctas_nao_e_ponte`.

Este é o único da lista que produzia **falso vermelho**, e ele é tão grave
quanto os outros quatro: bloqueio falso é como a operação desliga o portão, e um
portão desligado não protege nada.

---

## O que NÃO tem contraprova, e por quê

- **A invocação por terminal do motor** (`funnelforge run … --publish`) não passa
  por nenhuma das barreiras. Não é testável como contraprova porque não é um
  caminho do produto: é um humano com shell na máquina que tem a credencial.
  Declarado em `REMAINING-RISKS.md` §1.1.
- **CSS de folha externa escondendo conteúdo.** `texto_visivel` descarta bloco
  escondido por CSS **inline** e por atributo; resolver cascata exige motor de
  renderização. Declarado em `REMAINING-RISKS.md` §1.2.
- **Conteúdo móvel varrido como conteúdo.** A comparação móvel × desktop é por
  hash de variante. Declarado em `REMAINING-RISKS.md` §1.3.
