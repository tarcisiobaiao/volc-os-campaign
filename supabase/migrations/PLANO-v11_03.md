# Plano da `v11_03` — templates, perfis e a trava de finalidade

**Estado: PLANEJADA. NÃO ESCRITA COMO SQL. NÃO APLICADA.**
Data: 28/08/2026 · Depende de: `v11_01` e `v11_02` (ambas aplicadas em produção)

Este arquivo é plano, não migration. Não existe `.sql` correspondente de propósito:
um arquivo `.sql` na pasta de migrations é um convite a ser aplicado, e três das
decisões abaixo ainda pertencem ao dono do produto.

## Por que não aplicar agora

A `v11_02` entrou porque o parque **já existia** em quatro cópias e só precisava de
dono. As tabelas abaixo não descrevem nada que exista: elas descrevem um produto
que está sendo desenhado. Aplicar schema antes do consumidor é como o `criativo_pacote`
e o `criativo_entrega` nasceram vazios — o que ali foi deliberado (para que C2 não
migrasse tabela povoada), aqui seria só pressa.

E há um bloqueio técnico à frente: **o modelo de execução está quebrado** (gap G4 —
`asyncio.create_task` fire-and-forget dentro de função serverless na Vercel). Criar
tabela de template antes de resolver quem executa é mobiliar um cômodo sem telhado.

## 1. Tabelas novas

| Tabela | Guarda | Consumidor que a justifica |
|---|---|---|
| `criativo_template` | identidade da receita: slug, nome, finalidade, canal, dono | Laboratório (existe, hoje só em memória) |
| `criativo_template_versao` | corpo versionado e **imutável** da receita (jsonb), com hash | comparação de versões |
| `criativo_template_preset` | conjunto nomeado de valores sobre uma versão | nível Guiado |
| `criativo_perfil_de_legenda` | tipografia, stroke, safe area, karaokê, `hideDuring`, densidade | **lacuna maior do vídeo** — hoje não há onde guardar |
| `criativo_perfil_de_audio` | LUFS alvo, true peak, ducking, trim, silêncio máximo | hoje o número vira PASS/FAIL e se perde |
| `criativo_template_variante` | variante experimental sobre uma versão | experimento A/B |

### O que **não** entra, e por quê

- **`criativo_voz` não ganha `pitch`, `apresentacao` nem `hash_da_geracao`.** Esses
  campos não existem no legado: `motor/core.py` não grava hash de geração de voz, e
  não há campo de gênero em nenhum cluster do contrato. **Criar coluna para um dado
  que ninguém produz é criar um `null` permanente que parece lacuna de preenchimento.**
- **Nada de tabela para Postiz, TikTok, Pinterest ou YouTube.** Não há integração,
  não há exigência medida, não há número com fonte. `criativo_finalidade.classe` já
  separa `paid` de `organic`, e é o que se sabe hoje.

## 2. A trava que falta, e que é a mais importante deste plano

O gatilho `criativo_entrega_autorizada` (v11_02) já exige aprovação **vigente,
positiva e do próprio pacote**. Falta uma condição:

```
a finalidade da aprovação precisa ser a finalidade do pacote
```

Sem ela, uma aprovação dada para `instagram_organic` autoriza uma entrega de um
pacote `google_display`. Isso muda obrigação de disclosure, de direito de uso e de
política de plataforma — **entregar peça orgânica como anúncio é o defeito de negócio
mais caro desta área**, e hoje o banco não o impede.

Isto é ALTERAÇÃO DE GATILHO EXISTENTE, não tabela nova. Pode e deve ser separada do
resto do plano, porque não depende de nenhuma decisão de produto.

## 3. Os 13 índices de chave estrangeira

Medido em produção hoje: **13 das 23 FKs de `criativo_*` estão sem índice**.

```
criativo_aprovacao.finalidade_id     criativo_master.brand_pack_id
criativo_briefing.brand_pack_id      criativo_master.substitui_id
criativo_briefing.modo_id            criativo_pacote.projeto_id
criativo_entrega.autorizacao_id      criativo_projeto.brand_pack_id
criativo_entrega.pacote_id           criativo_skin.motor_id
criativo_gate.motor_id               criativo_voz.motor_id
criativo_job.motor_id
```

`criativo_master.substitui_id` é a mais urgente: é a cadeia de versões que a tela de
ativo percorre para montar o histórico. Com as tabelas vazias nada disso dói; dói no
primeiro projeto com volume, e é o tipo de coisa que ninguém volta para consertar.

**Estes índices podem entrar sozinhos, sem nenhuma tabela nova.** São `CREATE INDEX
CONCURRENTLY`, sem lock de escrita, e não dependem de decisão de produto.

## 4. Os índices GIN que NÃO entram

Há 16 colunas `jsonb` sem GIN. Não proponho índice para nenhuma.

Sem padrão de consulta conhecido, GIN em tudo é custo de escrita sem benefício
provado — e as tabelas têm zero linha, então não há nem por onde medir. Decisão
adiada com gatilho explícito: **quando o Laboratório definir quais campos do contrato
são filtráveis, o índice nasce junto com a consulta que o justifica.**

## 5. Ordem sugerida, do mais seguro ao mais dependente de decisão

1. **13 índices de FK.** Zero risco, zero decisão de produto. Pode ir hoje.
2. **Trava de finalidade no gatilho de entrega.** Corrige um furo real. Sem tabela nova.
3. **`criativo_perfil_de_legenda` e `criativo_perfil_de_audio`.** Descrevem coisa que
   o legado já produz e o schema não representa. Baixo risco.
4. **`criativo_template` + `criativo_template_versao`.** Só depois de o executor ter
   dono (G4) — senão o Laboratório salva receita que nada consegue executar.
5. **`criativo_template_preset` e `criativo_template_variante`.** Só quando houver
   segundo consumidor real.

## 6. Regras que a v11_03 herda da v11_02, sem exceção

- transacional, com rollback pareado, **rodado** por `scripts/provar-ciclo-v11.sh`;
- RLS habilitada **e** forçada, zero policies, `REVOKE` inclusive de `service_role`
  (o ACL padrão quebrado do `public` concede `arwdDxt` a todo mundo em toda tabela
  nova — isso é real e está ativo em produção);
- ausência é `null`, nunca `0`;
- toda medida carimbada com o momento em que foi medida;
- declarado e observado nunca dividem coluna;
- CHECK que possa abortar em linha histórica entra como `NOT VALID` com diagnóstico,
  nunca como `ALTER` que derruba a migration inteira.
