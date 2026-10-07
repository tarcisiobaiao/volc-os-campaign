# ADR: Editorial V2 é um superconjunto do V1 e nunca publica sozinho

**Estado:** Accepted — guarded rollout, em 30/09/2026, por decisão explícita do operador.
**Versão:** `editorial-v2-rc1`. Arquitetura aceita para rollout protegido; integração em produção e canário completo ainda pendentes.
**Dono da decisão:** Tarcisio / VOLC
**Escopo:**
- o motor de funil (`funnelforge-migracao/engine`);
- a ponte da copy Search (`volc_ads`);
- o disparo do redator (`backend/app/routers/publicacao.py`, `backend/app/redator/*`);
- a tela de disparo (`src/components/pautador-pro/entity/DispararRedatorDialog.tsx`).

## Contexto

O fluxo editorial que estava em produção (V1) escrevia páginas de funil com pesquisa, redação, juiz, SEO, widget, imagem,
screenshot oficial, build Gutenberg e envio como rascunho ao WordPress. As medições de 29 e 30/09/2026 mostraram três perdas
estruturais entre as etapas:

- **O que se sabia do leitor não chegava ao redator.**
  - O público e o tom definidos pelo arquiteto não chegavam a ele.
  - Fatos verdadeiros caíam por tipagem.
  - Os termos reais de busca e a promessa do anúncio não chegavam ao briefing.
  - A promessa da LP não chegava ao juiz da copy Search.
- **Validadores bloqueavam por palavra isolada ou por heurística de forma**, sem dependência técnica comprovada. Isso
  contraria as Diretrizes 1 e 2 do operador (30/09).
- **A composição visual era cega.** Havia uma cota por forma de pergunta ou nenhuma exigência, e as páginas saíam só com
  parágrafo, título, lista e botão.

O V2 foi construído no ramo `editorial_v2` do motor (B3a–B8, D2) e ligado de ponta a ponta no sprint de integração (S1–S4):
- a tela liga a flag;
- o backend persiste e transmite a flag;
- `contexto_de_busca` e `contexto_de_anuncio` chegam ao motor;
- a promessa da LP chega ao juiz;
- a regra de tipagem de fatos é única.

A Diretriz 3 proibiu construir uma plataforma editorial paralela. O V2 tinha de ser o motor existente, melhorado.

## Decisão

1. **O Editorial V2 é um superconjunto do V1.**
   - Toda capacidade do V1 continua no V2: pesquisa, fatos verificados, os dois usos do Chromium citados no item 2, blocos
     Gutenberg e widgets, portões factuais, estruturais, de URL, de tracking e de segurança, e o envio como rascunho.
   - O V2 **acrescenta**:
     - o briefing por página, que carrega público, tom, intenção, fatos tipados, termos de busca, anúncio e `visual_plan`;
     - a revisão contextual, com **uma** chamada e no máximo **uma** rodada de microajuste aplicada por código com as travas
       existentes;
     - o recibo sha256 do conteúdo aprovado;
     - o portão de composição.
   - O que muda de **política**, e não de capacidade: bloqueios por palavra ou heurística sem dependência comprovada viram
     aviso ou localizador para o revisor (Diretriz 2). A cota cega FF-16 não vale no V2.
2. **O V2 preserva a pesquisa com Chromium.** O Chromium continua nos mesmos dois pontos do V1:
   - a sonda anti-anúncio em `registrar_canais_oficiais`, logo depois da pesquisa, que decide os `official_links` que
     briefing, redator e revisor recebem;
   - o passo de screenshot oficial, cujas capturas o `step_publish` embute no rascunho.

   O V2 **não** remove nem contorna nenhum dos dois. Hoje as capturas **não** alimentam pesquisa, fatos, briefing nem revisão.
   É assim por desenho, tanto no V1 quanto no V2 (canário S3, item 9). Fazê-las chegar lá é trabalho novo, sujeito a decisão
   própria.
3. **O V2 preserva as capacidades Gutenberg** e as moderniza para blocos nativos:
   - table, columns, group, list e details;
   - pullquote, com a regra de mover a frase, sem duplicá-la;
   - `wp:html` só na barra de progresso, com `role="img"`.

   Os widgets do V1 continuam. A âncora do Ad Inserter (1º e 3º `<p>` contáveis, fora de `blockquote`, no fluxo principal)
   é **dependência técnica comprovada** e bloqueia (`ad_slot_inseguro`).
4. **Composição por `visual_plan` semântico.** O briefing declara, por seção, uma intenção de um vocabulário fechado
   (comparar, passo a passo, checklist, fato-chave, navegação por região, atenção, FAQ, exemplos numéricos) e o padrão nativo
   correspondente, com o motivo. A exigência de blocos vem do plano, não de cota:
   - plano ausente ⇒ aviso, sem exigência inventada;
   - plano malformado ⇒ erro do contrato do briefing;
   - plano não cumprido ⇒ localizador para o revisor, não bloqueio.
5. **O V2 nunca publica automaticamente.**
   - O máximo que o sistema faz sozinho é gravar **rascunho** no WordPress, e só com o recibo sha256 conferido.
   - `step_publish` recusa `run.publish_status` diferente de `draft` quando a página é V2.
   - Página em revisão humana, rejeitada ou alterada depois da decisão fica em `blocked_pN`: não passa por imagem, build nem
     envio, e a publicação avulsa pelo backend também a recusa.
   - Tornar uma página pública é sempre um ato humano no WordPress.
   - A ativação de anúncios segue a Diretriz 2 §10: a RSA nasce pausada, e a ativação é um lote próprio aprovado por hash.
6. **O V2 é escolhido por funil, e a escolha é persistida.**
   - A tela oferece um interruptor que nasce desligado.
   - O backend grava `pautador_funnel_runs.editorial_v2` e transmite a escolha ao motor pelo perfil do run.
   - O motor grava a escolha no `state.json`, e ela é **pegajosa**: um run que nasceu V2 é retomado V2, e nenhuma fonte desliga
     outra (`editorial_v2_do_run`).
   - Com a flag desligada, prompts e ordem de passos continuam idênticos aos do V1. O teste de ouro
     `test_editorial_v2_flag_off_identico.py` garante isso.
7. **Ausência é dita, nunca preenchida.** Termos de busca, anúncio e promessa da LP chegam sempre num estado do contrato
   (`presente`, `vazio_confirmado` ou `ausente` com o motivo).
   - Um export de termos que não cobre a janela é `ausente`, não "0 termos".
   - Falha de leitura vira `ausente` com a classe do erro, nunca com a mensagem crua.
   - A leitura de contexto nunca derruba o disparo.
8. **O gate de notas do juiz é obrigatório.** O recibo do revisor exige `trava_de_notas=trava-notas-v1`, as notas
   existenciais do papel da página e o mínimo definido no código. A retomada reconfere essas condições.
   - `ajustar` com nota insuficiente exige decisão humana sobre o conteúdo e o patch proposto; a aplicação de um patch
     não transforma notas insuficientes em aprovação automática.
   - O limite continua em uma revisão e no máximo uma rodada de microajuste. Não se repete o juiz até obter aprovação.
   - Falhas factuais, ausência de evidência e referências inventadas mantêm a página pendente, sem publicação.

## Alternativas consideradas

| alternativa | por que não |
|---|---|
| Plataforma editorial paralela (novo pipeline, novos contratos, painel próprio) | Proibida pela Diretriz 3: duplicaria o motor e perderia as capacidades já provadas do V1 (Chromium, Gutenberg, portões) |
| Substituir o V1 pelo V2 de uma vez (sem flag) | Sem comparação A/B nem ciclo real aprovado, não haveria como provar equivalência nem reverter. Contraria o "sem big bang" do guia do projeto |
| Revisor com duas ou mais rodadas de reescrita pelo modelo | Custo e deriva: a 2ª rodada tende a neutralizar o texto. A Diretriz 4 exige o menor ajuste fundamentado. Reduzido a UMA chamada na B5-redução |
| Exigência visual por cota (N blocos por página) | Produz decoração sem função. O plano semântico por seção explica cada bloco e deixa o revisor apontar o que falta |
| Publicação automática (`publish_status: publish`) com recibo | O recibo prova integridade, não aprovação editorial nem de negócio. Quem publica é a pessoa |
| Tornar o `visual_plan` obrigatório (erro quando ausente) | Não há dependência técnica comprovada (Diretriz 2). Ausente vira aviso |

## Consequências

- Os dois ramos convivem. O ouro do V1 não pode mudar enquanto o V2 não cumprir as três condições de aposentadoria do caminho
  antigo (`judge.jinja`/`_judge_page`, B8 §4):
  1. uma comparação A/B com o mesmo insumo, com teto e com decisão humana cega a favor do V2;
  2. a tela ligando a flag (feito na S2);
  3. um ciclo real de rascunho aprovado pela pessoa.
- Custo por página maior no V2, por causa do briefing e do revisor. No canário S3 (5 páginas, LLM real) o gasto foi
  US$ 1,6169 em 39 chamadas. 56% desse gasto foi em páginas que o fail-closed reteve, o que mostra que a retenção funciona e
  também que há desperdício a reduzir (prompt do briefing e grounding do redator).
- **Mais páginas vão para decisão humana** (`revisao_humana`) em vez de sair aprovadas com texto neutralizado. É o efeito
  desejado. A decisão é feita com `funnelforge decidir <run> --pagina N --decisao aprovar|rejeitar --sha256 …`.
- O pacote de políticas do revisor vale até 30/10/2026. Depois dessa data, toda página V2 recebe o alerta `policy_pack_stale`,
  que não bloqueia, até alguém regenerar o pacote com `scripts/gerar_pacote_revisor.py`.
- A migração `src/sql/pautador/06_run_editorial_v2.sql` foi aplicada no Supabase self-hosted em 30/09/2026 com
  `ON_ERROR_STOP`. A coluna é `boolean NOT NULL DEFAULT false`. O smoke ASGI da branch com PostgREST real retornou 200
  com a flag ligada e desligada, e confirmou sua persistência em nova leitura. Auth, perfil e worker foram isolados;
  não houve publicação e os registros temporários foram removidos. Isso não comprova deploy do backend ativo.
- O disparo pode fazer até duas consultas GAQL de **leitura** (termos e RSA) quando o card tem campanha Search vinculada, com
  teto de 30 s. Funil novo não chama o Google.
- A regra de tipagem de fatos de legado (fato sem `tipo`) mora num arquivo só, `funnelforge/domain/tipagem_de_fatos.py`,
  carregado pelo motor e pela ponte. A ponte exige o motor no checkout, o que o backend já exigia.
- **Pendências conhecidas, fora desta decisão:**
  - o `.env` do motor com credencial de WP faz o `build_deps` montar o publisher mesmo sem perfil com `wordpress`, e a única
    trava é a flag `publish` (recomendação: montar só com `--publish` e o bloco `wordpress`);
  - o Chromium recebe 403 do Akamai em `sp.senac.br` sem `Issue`;
  - as capturas não alimentam pesquisa nem revisão (item 2 acima).

## Rollback pela flag

O rollback não exige deploy nem reversão de código. Há quatro níveis, do mais estreito ao mais amplo:

1. **Por funil (operador):** desligue o interruptor "Fluxo editorial v2" na tela de disparo. O próximo run desse card sai V1.
2. **Por arquitetura:** tire `funnel_architecture.editorial_v2` do card, se alguém o tiver posto. Só o `true` literal liga.
3. **Global:** `run.editorial_v2` em `funnelforge-migracao/engine/config.yaml` já é `false` por padrão. Ninguém deve mudar o
   padrão sem a comparação A/B.
4. **Banco (opcional):**
   - o rollback está no cabeçalho da migração 06:
     `alter table public.pautador_funnel_runs drop column if exists editorial_v2; notify pgrst, 'reload schema';`
   - sem a coluna, a tela volta a receber 409 ao ligar, e o V1 funciona;
   - a coluna pode ficar: o padrão `false` é o que toda linha anterior foi.

**Limite do rollback:**
- Um run que **já nasceu** V2 continua V2 na retomada, porque o estado é pegajoso por segurança: um run V2 retomado como V1
  subiria sem conferir o recibo.
- Para voltar um funil em andamento, cancele o run (`/redator/runs/{id}/cancelar`) e dispare de novo com o interruptor
  desligado.
- Rascunhos já gravados no WordPress não são tocados pelo rollback, porque nunca foram públicos.

## Evidência histórica e aceite do RC1 (30/09/2026)

- **Suítes herméticas (S4):**
  - motor: 1047/0;
  - volc_ads: 682/0;
  - backend: 1430/0 com 1 pulado (4 exclusões de ambiente real);
  - `tsc -p tsconfig.app.json`: 76 erros herdados e 0 nos arquivos tocados.
- **Relatórios:**
  - `.claude-ads/runs/editorial-refactor-20260930/sprint-integracao/revisao-final.md`;
  - handoffs S1 a S3 no mesmo diretório.
- **Canário com LLM real, sem `--publish`, terminando em preview** (`sprint-integracao/canario/recibo.json`):
  - p1 e p3 tiveram os recibos originais invalidados por notas zeradas; a nova revisão do fechamento aprovou ambas
    com notas 10 nos critérios exigidos e `trava-notas-v1`, sem alteração do conteúdo;
  - p4 em revisão humana, com o fail-closed preservando o texto;
  - p2 e p5 retidas pelos portões;
  - nenhuma escrita no WordPress.
- **p2:** o `66,67%` já tinha fato tipado citável e fonte resolvida no inventário. A unidade não trazia `%`;
  corrigir apenas esse metadado fez o gate factual passar, com o texto intacto e sem chamada paga. SEO, revisão e build
  posteriores não foram executados: p2 não conta como página completa aprovada.
- **p4:** os dois patches recusados por `regiao_protegida` foram aprovados pelo operador e aplicados somente no canário.
  Explicitam que cadastro e envio da ficha acontecem no portal regional do Senac. Estrutura, URLs, números e widgets
  foram preservados; HTML e gate factual passaram. A autorização cobre os patches, sem publicação; o aceite integral
  da página permanece pendente, pois a revisão histórica tem notas zeradas.
- **p5 — limitação conhecida do RC1:** a única nova tentativa corrigiu a confusão entre IDs de fontes e de fatos, mas
  inventou referências `termo:` ausentes da amostra observada. O fail-closed funcionou e não haverá nova tentativa nesta
  etapa. Quando não houver termos observados, o briefing não pode inventá-los. Um fallback futuro deve usar apenas
  fatos, intenção e evidências realmente disponíveis; essa melhoria não foi implementada neste RC1. A resposta também
  usou uma base de hipótese proibida numa entrega e uma referência de tensão malformada, igualmente retidas.
- **Custo adicional do fechamento:** US$ 0,094324 em três chamadas (p1, p3 e a tentativa de p5). Aplicação dos patches de p4
  e formalização do RC1: zero chamadas pagas adicionais. Nenhuma publicação WordPress.
- **Evidência versionada:** `.claude-ads/runs/editorial-refactor-20260930/fechamento-sniper/editorial-v2-rc1.json`,
  `p4-patches-aplicados.json` e `migration-smoke.json`, no mesmo diretório.
- **Rollout:** `editorial_v2=false` por padrão, V1 preservado como fallback, nenhum conteúdo publicado automaticamente.
  `P10-T19` continua `partial` até integração/deploy do backend ativo e um canário completo aprovado. Esta etapa não faz
  merge em `main` nem deploy. Roadmap e curadoria registram esse estado; o grafo gerado não foi reconstruído, conforme
  a restrição do operador enquanto outra sessão trabalha no attention-engine. Nenhum frescor novo é declarado.

## Fechamento final do RC1 (30/09/2026, noite)

- **P5 corrigido.** O briefing e o revisor só oferecem `termo:` como evidência quando há termos observados, e só copiado
  literalmente da lista. Sem termos, os dois prompts dizem `termo: indisponível` e mandam declarar a ausência. A mensagem
  do contrato diz o porquê e volta na retentativa.
- **Canário, uma retomada do `run_pipeline` real** (sem publicar, sem retry nem fallback), US$ 0,162874 em 7 chamadas:
  - p1/p3 aprovadas, reconferidas pela trava, sem chamada;
  - p2 passou por SEO, revisor (aprovado), imagem e build, e o gate final a bloqueou por `ad_slot_inseguro`: o 3º `<p>`
    cai nos cartões de rota em `wp:columns`. O microajuste proposto só reordena, mas exige decisão sobre o conteúdo;
  - p4 teve uma revisão completa com a trava e segue em `revisao_humana`: dois achados de identidade, com os patches
    recusados por `regiao_protegida`;
  - p5 não inventou termo. Foi retida por `o_que_encontra` com base `fato` e ref `destino:`; o esquema do prompt foi
    corrigido, sem validação ao vivo.
- **Superconjunto provado por teste:** o screenshot oficial é capturado e embutido como decoração `print_oficial` no
  rascunho V2. Widget e Gutenberg já tinham prova.
- **Sem merge nem deploy.** O worktree principal tem sessão ativa de outra frente. Não há runbook de deploy do backend
  do Pautador. Recibo: `.claude-ads/runs/editorial-refactor-20260930/fechamento-sniper/editorial-v2-fechamento-final.json`.
- **Decisões do operador (30/09, 21:12), sem chamada paga:**
  - p2: o parágrafo "É importante destacar que as regras de ingresso…" foi movido para antes do `wp:columns`, sem
    mudar palavra; o slot do Ad Inserter ficou livre (sha `791ebf39…`). Falta a decisão sobre o novo sha;
  - p4: aprovada humanamente na íntegra, no sha `ef5734b6…`;
  - p5: correção aceita por código e testes, com uma validação real depois da integração.

  Contagem do fechamento: 7 chamadas pagas, US$ 0,162874.
- **Fechamento operacional da branch (30/09, 21:30):**
  - p2 aprovada humanamente no sha `791ebf39…`, cobrindo só a reordenação literal.
  - Validação real do p5 (1 chamada, US$ 0,029034): **reprovada**, sem termo inventado. O modelo copiou no `ref` de
    `o_que_encontra` a dica de esquema `"destino:<URL> com base briefing_do_arquiteto"`, e o contrato exige
    `destino:<URL>` exato.
  - O stack local desta worktree subiu: V2 desligado por padrão, motor em draft e rotas de publicação autenticadas.
