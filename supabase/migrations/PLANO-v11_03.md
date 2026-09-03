# Plano da `v11_03` — a execução criativa vira dado

**Estado: ESCRITA COMO SQL, PROVADA EM CLUSTER DESCARTÁVEL, NÃO APLICADA EM PRODUÇÃO.**
Arquivo: `supabase/migrations/v11_03_execucao_criativa.sql` (876 linhas) ·
rollback pareado: `v11_03_rollback.sql` (136 linhas) ·
ciclo que os executa: `scripts/provar-ciclo-v11_03.sh`.
Depende de: `v11_01` e `v11_02`.

---

## ⚠️ Aviso de procedência: este plano divergiu do que foi construído

A primeira versão deste arquivo, de 28/08/2026, descrevia **outra `v11_03`** —
templates, perfis de legenda e áudio, e uma trava de finalidade no gatilho de
entrega — e abria com a frase *"NÃO ESCRITA COMO SQL. NÃO APLICADA."* enquanto o
`.sql` completo já existia na mesma pasta, com 5 tabelas, 9 funções e 7 gatilhos
sobre um assunto inteiramente diferente: a **execução** de um render.

Isso não é detalhe de documentação. Um plano que descreve um código que não é o
código ao lado é pior do que nenhum plano: quem abrir a pasta para decidir se
aplica lê um arquivo que se declara não-escrito e um `.sql` pronto para rodar, e
não tem como saber qual dos dois mente. O que aconteceu, factualmente, é que o
rótulo `v11_03` foi reutilizado quando a prioridade mudou de *catálogo de
receitas* para *execução*, e este arquivo não acompanhou.

**Nada da proposta original foi implementado.** Ela não foi descartada por estar
errada — continua de pé, e está preservada integralmente na seção
[NÃO IMPLEMENTADA](#nao-implementada) abaixo. O que mudou foi a ordem: o gap G4
(execução fire-and-forget em função serverless) foi julgado bloqueante, e sem
executor com dono não havia por que criar tabela de template.

---

## 1. O que a `v11_03` que EXISTE faz

Ela persiste o contrato que a bancada local já provava só em memória: um render
tem fila, dono, prazo, tentativa, recibo, artefato e veredito de qualidade — e
cada um desses vira linha, não log.

**Medido no cluster descartável, com as três migrations aplicadas em ordem:**

| Objeto | Quantidade |
|---|---|
| tabelas `criativo_render_*` | **5** |
| funções (7 de gatilho + 2 de chave de storage) | **9** |
| gatilhos | **7** |
| índices sobre as 5 tabelas (inclui PK e unique) | **14** |
| constraints `CHECK` | **27** |

### As 5 tabelas

| Tabela | Colunas | O que ela guarda |
|---|---|---|
| `criativo_render_job` | 26 | a fila: estado, dono, lease, batimento, tentativa, `retry_of`, tenant, `idempotency_key`, encomenda |
| `criativo_render_transicao` | 7 | a trilha **append-only** de quem mudou o quê e quando |
| `criativo_render_recibo` | 19 | a prova de produção: motor, versão, seed, versões, parâmetros, assinatura, custo e as **4 medidas de áudio** |
| `criativo_render_artefato` | 12 | o arquivo: slot, mime, bytes, sha256, chave de storage e o estado da conferência |
| `criativo_render_validacao` | 6 | o veredito de cada gate sobre o artefato |

Estados do job, por `CHECK`:
`queued → claimed → running → validating → rendered`, com `failed` e `cancelled`
como saídas. `rendered` é terminal e exige recibo.

### As 7 invariantes que o schema defende

1. **Lease não é renovado por transição.** Renovar lease é trabalho do batimento,
   que confere dono. Sem isso, passar de `claimed` para `running` ressuscitava um
   lease vencido e o trabalho abandonado nunca voltava para a fila.
2. **Só o dono bate o coração.**
3. **`rendered` é terminal e exige recibo.** "Concluído" sem prova é opinião.
4. **`failed` só volta por gesto explícito**, e o gesto nasce um job novo com
   `retry_of` — não se reabre um terminal, porque o `failed` guarda por que falhou.
5. **Artefato é imutável depois de `rendered`**, com `bytes`/`sha256` NOT NULL.
6. **Tenant entra na identidade.** A chave única é `(tenant, idempotency_key)`.
7. **Mensagem de erro não carrega caminho, stack nem drive do Windows** — por
   `CHECK`, porque documentação não impede ninguém de gravar `/var/folders/...`.

Somam-se a essas quatro guardas que a revisão adversarial de 29/08/2026
acrescentou: recibo concluído é imutável; veredito de gate de job concluído não
muda nem cresce; a chave de storage é construída por **uma** função só, usada
pelos dois lados; e a conferência de storage é atômica (carimbo e veredito
andam juntos).

### Segurança

RLS **habilitada e forçada** nas 5, **zero policies**, `REVOKE` de `public`,
`anon`, `authenticated` **e** `service_role` — porque o ACL padrão do schema
`public` concede `arwdDxt` a todos eles em toda tabela nova — seguido de
`GRANT select, insert, update` só ao `service_role`. Sem `DELETE` e sem
`TRUNCATE`: apagar job é apagar auditoria. A trilha `criativo_render_transicao`
não é nem atualizável pelo `service_role`.

⚠️ Esse desenho **depende de o `service_role` ter `BYPASSRLS`**. Com RLS forçada
e zero policies, um `service_role` sem bypass lê zero linhas e não insere — a
migration aplicaria limpa e o produto pararia em silêncio. É a primeira coisa que
`scripts/preflight-v11_03.sh` confere.

---

## 2. Como ela é provada

```bash
bash scripts/provar-ciclo-v11_03.sh      # 151 provas, 0 falhas
bash scripts/v11_03-provar-preflight.sh  #  17 provas, 0 falhas
bash scripts/v11_03-provar-plano.sh      #  12 provas, 0 falhas — este arquivo
```

O terceiro confere ESTE documento contra o `.sql` ao lado: linha de estado, os
nomes das 5 tabelas, a marcação da proposta não implementada e os ponteiros para
ciclo e rollback. Contra a versão anterior deste plano ele dá 1 passou / 11
falharam — que é a medida do quanto ele descrevia outra coisa.

O primeiro sobe um Postgres do zero com `initdb` em `mktemp -d`, aplica
v11_01 + v11_02 + v11_03, roda as provas de comportamento e de papéis, **executa
o rollback**, reaplica, e então roda as contraprovas dos defeitos fechados em
02/09/2026. Não usa Docker e nunca fala com banco de produção.

As contraprovas merecem nome próprio, porque são o que impede estes três defeitos
de voltarem:

- **os 7 gatilhos, por igualdade.** O bloco `do $verifica$` é **extraído do
  próprio `.sql`** e executado contra o banco íntegro, depois com um gatilho
  removido de propósito, depois recomposto. A verificação antiga aceitava `>= 6`
  e sairia verde com 6.
- **as 9 funções, não 7.** Um leftover é fabricado — uma sobrecarga de
  `criativo_storage_chave` que os `drop function` por assinatura não alcançam — e
  o rollback tem de **acusar**. A conferência antiga contava só o prefixo
  `criativo_render_%` e não via as duas funções de storage.
- **as 21 tabelas por nome, não por contagem.** Uma tabela `criativo_*` a mais
  (uma v11_04 futura) não pode impedir reverter a v11_03; e uma das 21 renomeada
  — contagem ainda 21 — tem de ser acusada.

---

## 3. O que falta antes de aplicar em produção

1. **`scripts/preflight-v11_03.sh` contra o banco real**, com DSN passado por
   argumento. Ele é fail-closed: o que não conseguiu conferir sai como
   `NAO CONFERIDO` e reprova.
2. **Backup conferido por restauração**, não por data de arquivo.
3. O roteiro executável está em
   `docs/closure/creative-factory-production-last-mile-v1/braco-a/PACOTE-v11_03.md`.

Enquanto isso não acontecer, o estado honesto é: **provada, não aplicada.**

---

<a id="nao-implementada"></a>

# NÃO IMPLEMENTADA — a proposta original de 28/08/2026

> ⚠️ **Tudo desta seção em diante é proposta, não código.** Não existe `.sql`
> correspondente, nada foi aplicado, e nenhuma das tabelas abaixo existe em
> lugar nenhum. Está preservado porque continua sendo trabalho válido a fazer —
> e porque apagar uma proposta ao renomear o rótulo foi como este arquivo passou
> a mentir sobre o próprio código. Se algum destes itens for construído, ele
> precisa de um número de migration **próprio**, não deste.

## O que era proposto

A `v11_02` entrou porque o parque **já existia** em quatro cópias e só precisava
de dono. As tabelas abaixo não descrevem nada que exista: descrevem um produto
que está sendo desenhado. Aplicar schema antes do consumidor é como
`criativo_pacote` e `criativo_entrega` nasceram vazios — o que ali foi deliberado
(para que C2 não migrasse tabela povoada), aqui seria só pressa.

### Tabelas novas propostas

| Tabela | Guarda | Consumidor que a justifica |
|---|---|---|
| `criativo_template` | identidade da receita: slug, nome, finalidade, canal, dono | Laboratório (existe, hoje só em memória) |
| `criativo_template_versao` | corpo versionado e **imutável** da receita (jsonb), com hash | comparação de versões |
| `criativo_template_preset` | conjunto nomeado de valores sobre uma versão | nível Guiado |
| `criativo_perfil_de_legenda` | tipografia, stroke, safe area, karaokê, `hideDuring`, densidade | **lacuna maior do vídeo** — hoje não há onde guardar |
| `criativo_perfil_de_audio` | LUFS alvo, true peak, ducking, trim, silêncio máximo | hoje o número vira PASS/FAIL e se perde |
| `criativo_template_variante` | variante experimental sobre uma versão | experimento A/B |

> Nota de 02/09/2026: a linha de `criativo_perfil_de_audio` dizia que "o número
> vira PASS/FAIL e se perde". Isso deixou de ser verdade para o **recibo**: a
> `v11_03` que existe guarda `lufs_integrado`, `true_peak_dbtp`, `alvo_lufs` e
> `tolerancia_lufs` como números, exatamente as quatro medidas de `MedidaDeAudio`
> em `backend/app/criativo/bancada/contrato.py`. O que continua sem lugar é o
> **perfil** — o alvo declarado antes da produção, reutilizável entre jobs. Medida
> e alvo-por-execução estão resolvidos; alvo-como-política, não.

### O que **não** entrava, e por quê

- **`criativo_voz` não ganha `pitch`, `apresentacao` nem `hash_da_geracao`.**
  Esses campos não existem no legado: `motor/core.py` não grava hash de geração
  de voz, e não há campo de gênero em nenhum cluster do contrato. **Criar coluna
  para um dado que ninguém produz é criar um `null` permanente que parece lacuna
  de preenchimento.**
- **Nada de tabela para Postiz, TikTok, Pinterest ou YouTube.** Não há
  integração, não há exigência medida, não há número com fonte.
  `criativo_finalidade.classe` já separa `paid` de `organic`.

## A trava de finalidade — o item mais importante da proposta, e ainda aberto

O gatilho `criativo_entrega_autorizada` (v11_02) já exige aprovação **vigente,
positiva e do próprio pacote**. Falta uma condição:

```
a finalidade da aprovação precisa ser a finalidade do pacote
```

Sem ela, uma aprovação dada para `instagram_organic` autoriza uma entrega de um
pacote `google_display`. Isso muda obrigação de disclosure, de direito de uso e
de política de plataforma — **entregar peça orgânica como anúncio é o defeito de
negócio mais caro desta área**, e o banco não o impede hoje.

É ALTERAÇÃO DE GATILHO EXISTENTE, não tabela nova, e não depende de nenhuma
decisão de produto. **Continua sem migration própria.**

## Os 13 índices de chave estrangeira — também ainda abertos

Medido em 28/08/2026: **13 das 23 FKs de `criativo_*` estão sem índice.**

```
criativo_aprovacao.finalidade_id     criativo_master.brand_pack_id
criativo_briefing.brand_pack_id      criativo_master.substitui_id
criativo_briefing.modo_id            criativo_pacote.projeto_id
criativo_entrega.autorizacao_id      criativo_projeto.brand_pack_id
criativo_entrega.pacote_id           criativo_skin.motor_id
criativo_gate.motor_id               criativo_voz.motor_id
criativo_job.motor_id
```

`criativo_master.substitui_id` é a mais urgente: é a cadeia de versões que a tela
de ativo percorre para montar o histórico. Com as tabelas vazias nada disso dói;
dói no primeiro projeto com volume. São `CREATE INDEX CONCURRENTLY`, sem lock de
escrita, e não dependem de decisão de produto.

## Os índices GIN que NÃO entravam

Há 16 colunas `jsonb` sem GIN, e nenhum índice foi proposto para elas. Sem padrão
de consulta conhecido, GIN em tudo é custo de escrita sem benefício provado — e
as tabelas têm zero linha, então não há nem por onde medir. Decisão adiada com
gatilho explícito: **quando o Laboratório definir quais campos do contrato são
filtráveis, o índice nasce junto com a consulta que o justifica.**

## Ordem sugerida na proposta original

1. **13 índices de FK.** Zero risco, zero decisão de produto.
2. **Trava de finalidade no gatilho de entrega.** Corrige um furo real.
3. **`criativo_perfil_de_legenda` e `criativo_perfil_de_audio`.**
4. **`criativo_template` + `criativo_template_versao`.** Só depois de o executor
   ter dono (G4).
5. **`criativo_template_preset` e `criativo_template_variante`.** Só quando
   houver segundo consumidor real.

> Dos cinco, o item 4 é o único cujo bloqueio a `v11_03` que existe começou a
> levantar: ela é justamente o executor com dono, prazo e recibo. Os itens 1 e 2
> nunca dependeram de nada e seguem parados.

## Regras herdadas da v11_02 — estas a `v11_03` que existe cumpriu

- transacional, com rollback pareado, **rodado** por `scripts/provar-ciclo-v11_03.sh`;
- RLS habilitada **e** forçada, zero policies, `REVOKE` inclusive de `service_role`;
- ausência é `null`, nunca `0`;
- toda medida carimbada com o momento em que foi medida;
- declarado e observado nunca dividem coluna;
- `CHECK` que possa abortar em linha histórica entra como `NOT VALID` com
  diagnóstico, nunca como `ALTER` que derruba a migration inteira.
