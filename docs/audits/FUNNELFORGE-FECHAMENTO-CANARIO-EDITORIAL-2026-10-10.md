# FunnelForge: fechamento com canário editorial real (Tarifa Social)

Data: 10/10/2026. Base: `main` @ fdb6488e, com a limpeza de vetos mecânicos
(`FUNNELFORGE-SEM-VETOS-MECANICOS-2026-10-10.md`) ainda local, revisada e
mantida. Nada foi publicado: nenhum WordPress, Supabase, Ads, deploy ou push.

## 1. Caminho real conferido

- **Disparo.** `POST /redator/disparar` (perfil `completo`) monta o perfil com
  `preset=completo_chatgpt`. O worker roda
  `run-volc <arq> --perfil <p> --timestamp <t> --card-pre-arquitetura <card>`
  no diretório do motor, com `src` à frente do `PYTHONPATH`.
- **Configuração.** O preset liga `editorial_v2`, o dossiê, 3 workers, os
  widgets e os prints. O texto fica no plano ChatGPT, sem fallback faturado.
  O backend só manda `editorial_v2` quando é `true`, então nada desliga o V2
  no caminho. O `config.yaml` agora também traz o V2 ligado.
- **Canário.** É o mesmo comando, com `--canario` (sem publicador e sem
  imagem). A configuração efetiva foi gravada antes da primeira chamada
  (`recibos/config_efetiva.json`).
- **Redator e revisor leem o mesmo bucket.** Os ids de fatos são idênticos nas
  7 páginas. Os destinos, porém, divergiam (ver o defeito 2).

## 2. Defeitos demonstrados e corrigidos

| # | Defeito (evidência) | Correção | Contraprova |
|---|---|---|---|
| 1 | `prompt_do_pacote` passava `next_solutions=[]`, e o bloco `<entregas_dos_destinos>` saía vazio para a pré-sell e as soluções. A pré-sell é instruída a dizer "a promessa daquele destino" sem recebê-la. | Entrega confirmada de cada destino (com o fallback, quando a ferramenta não ficou pronta) | `test_presell_e_solucoes_recebem_a_entrega_confirmada_de_cada_destino` |
| 2 | O revisor conferia os botões contra a entrega do PLANO (`destinos_da_pagina`), não contra a do pacote que o redator leu | Com pacote congelado, os destinos vêm do pacote | `test_revisor_confere_os_botoes_contra_a_entrega_do_pacote_nao_a_do_plano` |
| 3 | `redator_p1_v2` ainda listava frases "conferidas" ("não perca o prazo", "sistema oficial"…) e pedia 650 palavras "para o portão de destino pago", que não roda mais no V2 | Orientação pelo sentido; profundidade sem meta | `test_lp_v2_sem_meta_de_palavras…`; o teste antigo dos 650 foi trocado |
| 4 | `escrita_natural.jinja` (redator e revisor V2) proibia expressões de oficialidade isoladas, o que impedia identificar a saída oficial com naturalidade | Oficialidade pelo sentido, canal nomeado pelo dono | `test_escrita_natural_julga_oficialidade_pelo_sentido_sem_lista` |
| 5 | **Canário:** na p2, o patch do revisor dizia "até meio salário-mínimo", "até três salários-mínimos", texto literal do fato da ANEEL citado como evidência. O patcher recusou ("numero_novo") e a página foi para decisão humana sem necessidade. | Número por extenso presente em fato citável passa, como os dígitos; o inventado continua recusado | `test_numero_por_extenso_do_fato_citavel_passa…` |
| 6 | **Canário:** contraste de 4,49:1 no botão selecionado do widget de orientação (p6/p7). A auditoria visual do motor reprovou. | Texto do estado selecionado em `#0b5f75` (6,28:1), tom que o widget já usa | auditoria visual 7/7 OK |
| 7 | **Canário:** a pesquisa nova trouxe outra vez o FAQ do MME com `?_authenticator=…` (token de sessão), defeito que a rodada anterior tinha corrigido à mão | `canonica` tira também parâmetros de sessão (`_authenticator`, `doAsUserId`, `jsessionid`, `phpsessid`) e mantém query funcional (`?id=53&origem=servico`) | `test_canonica_tira_token_de_sessao…` |
| 8 | **Canário:** sem a frase de contraste (removida junto com a recusa por código), o sniper abriu 6 dos 12 rótulos com "Entender…/Conhecer…" | Contraste resposta × tema com exemplo neutro; nenhum verbo proibido | `test_sniper_mostra_contraste…` |

Nenhum veto lexical foi restaurado. Os contratos técnicos seguem como
estavam: recibo/hash da revisão, patch sem URL ou número fora do inventário,
blocos Gutenberg, HTML/JS e slots.

## 3. Canário real

Comando: o `run-volc` canônico com `--canario`
(`producao/funil-canario-editorial-20261010/roteiros/canario.py`). A única
intervenção é o teto de chamadas, fixado antes da primeira chamada:

- **24 no total:** nominal 14 + folga 10. O preset usa 60.
- **Run:** `runs-canario/tarifa-social-energia-eletrica-20261010-canario-editorial`.
- **Esqueleto:** o aprovado, do card (`historico.arquitetura_referencia`),
  sem chamada ao arquiteto.
- **Reaproveitado:** PAA (cache), documentos (bucket compartilhado), hero e
  destaques aprovados de 09–10/10.
- **Refeito:** a pesquisa do dossiê, porque o entry point com card não aceita
  dossiê congelado (`--dossie-de` é recusado).

| | Run anterior (final de 10/10) | Canário |
|---|---|---|
| Chamadas no run | 20 (13 redações, 6 retentativas lexicais) | **14** (7 redações, 0 retentativas) |
| Parede | 804 s | **630 s** |
| Retomadas | 8 chamadas | 4 chamadas |
| Total | 28 | **18** |
| Faturado | US$ 0 | US$ 0 (`chatgpt_plan`, sem fallback) |
| Revisão na 1ª passada | 7/7 | 6/7 (p2 → humano pelo defeito 5) |
| Final | 7/7 | 7/7 aprovadas, gate OK |

Concorrência: 3 workers, pico de 3 chamadas em voo; a redação paralela levou
96 s na parede.

**Retomadas por causa, cada uma só na etapa afetada:**

| Causa | Etapa retomada | Chamadas |
|---|---|---|
| Defeito 5 | Revisão da p2, com a mesma resposta | 0 |
| Defeito 6 | Widget de p6/p7 + revisão em lote, porque o recibo cobre o corpo | 1 |
| Defeito 7 | Troca de URL conferida no documento público + revisão de p6/p7 | 1 |
| Defeito 8 | Sniper só dos botões + revisão das 5 páginas cujo botão mudou | 2 |

As quatro foram descobertas uma depois da outra. Numa ordem ideal, uma única
revisão bastaria.

## 4. Revisão contextual e microajustes (prova)

- 1ª passada (`revisor_lote`, 101 mil tokens, 160 s):
  - **LP:** 1 patch de identidade, "não cadastra pessoas".
  - **p5:** 3 patches que restringem à Neoenergia uma instrução comprovada só
    para ela, no corpo e na meta description.
  - **p2:** patch recusado (defeito 5), depois reaplicado sem chamada.
  - Nenhum patch tocou link ou número fora do inventário.
- **Re-revisões:** p6 e p7 foram aprovadas sem patch, duas vezes. Na revisão
  dos rótulos, a LP recebeu 3 patches que tiraram "outras cobranças podem
  permanecer": esse fato está no inventário da p6, não no da LP. A mesma frase
  tinha passado na 1ª revisão, o que mostra variação do revisor.

## 5. Validação visual e funcional (preview local)

O que foi exercitado:

- **Composição:** local, com publicador em disco; 7/7 com o gate final pós-decoração OK.
- **Auditoria visual do motor** (`visual_gate.audit`, Chromium 390 e 1440 px):
  aprovada, sem bloqueio.
- **Checagem funcional:**
  - sem rolagem lateral, sem imagem quebrada, sem link interno quebrado e sem erro JS;
  - LP e pré-sell sem link externo;
  - calculadora da p2 com 7 casos iguais a `widgets.calculos.calcular`,
    inclusive as recusas de "2,5" pessoas, "1,518.00", "abc" e 0;
  - widgets de escolha (p3, p4, p5) e de botões (p6, p7) mudam a resposta em
    todas as opções;
  - navegação clicada LP → pré-sell → p3 → p4.

O que isso não prova: tema, plugins, anúncios, CLS com anúncio e o
WordPress real.

## 6. Pendências

1. **p4 sem saída.** A pesquisa não verificou canal oficial nem fatos de
   outras distribuidoras: a página entrega o caminho só para a Neoenergia e
   termina sem botão. A revisão global registra o problema só como aviso.
2. **Entregas ajustadas pelo motor (p2, p4, p5).** Mudam o escopo do
   esqueleto e dependem do aceite do operador. Nada foi aceito.
3. **CTAs.** Os "Entender…" saíram, mas vários viraram "Saiba/Veja/Descubra…".
   Melhorou, mas ainda não é o rótulo-resposta do lote anterior corrigido à mão.
4. **LP.** O FAQ ficou com uma resposta burocrática depois do patch, e o fato
   "outras rubricas permanecem" não é atribuído à LP.
5. **Produção.** Nenhuma prova de produção, tráfego, CTR ou ROI.
