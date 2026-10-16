# Clusters de execução — 15/10/2026

## Estado de partida

- `main` e `origin/main`: `6124c550`, limpos e sincronizados na abertura desta
  época.
- Grafo: `current: true` na abertura.
- Checkout histórico: congelado; não deve receber trabalho novo.
- Control plane anterior: preservado como evidência, porém desatualizado.
- Disco: alerta operacional; havia cerca de 15 GiB livres na auditoria.

## Mapa operacional

| Lane | Missão atual | Pode escrever | Não pode escrever |
| --- | --- | --- | --- |
| Claude Projects | Experience/QA: reconstruir W13; depois D1; auditar funil e destino | branch/worktree candidata da missão | `main`, migrations, Ads collectors, Hermes, autoridades compartilhadas |
| Terminal Codex | Google Ads + JoinAds + atribuição econômica + Decision Plane shadow | módulos de coleta, medição e testes do domínio | Bia/Hermes, FunnelForge editorial, autoridades compartilhadas |
| Terminal Claude | fechar a mesma Bia/Hermes usada no Telegram | worktree `feat/bia-hermes-volc-v1` e paths da Bia | Ads collectors, W13/D1, `main`, autoridades compartilhadas |
| Integrador | reconciliar, revisar e integrar | checkout oficial, memória operacional e arquivos compartilhados | desenvolvimento exploratório concorrente |

## Fila real

1. **Bia/Hermes — prioridade de reconciliação.** A branch atual é
   `feat/bia-hermes-volc-v1` em `3b1b142d`. Evidências locais indicam migrations
   v20/v27 no Supabase oficial, enquanto o código ainda não está no `main`.
   Fechar o handoff, revisar e reaplicar sobre `6124c550` antes de ampliar essa
   superfície.
2. **Plano econômico/Ads.** Consolidar autoridade de coleta, custo, receita,
   atribuição e recomendações shadow. Não promover automação de verba antes de
   provar frescor e reconciliação econômica.
3. **W13.** Reconstruir seletivamente os commits próprios de
   `origin/mission/w13-sombra-todas-ry1q17` sobre o W7 endurecido já integrado.
   Não mesclar a branch antiga inteira.
4. **D1.** Reaplicar apenas depois do W13, absorvendo deliberadamente os
   conflitos com `CampanhaCanonPage.tsx` e o D3 já integrado.
5. **JoinAds/GTM/Measurement drift.** Auditar runtime versus Git e portar só os
   artefatos provados; não mesclar as branches históricas completas.
6. **Convergência.** Gates acumulados, Roadmap, curadoria, rebuild do grafo e
   push controlado.

## Como Claude Projects deve usar multiagentes

- Coordenador: decompõe a missão e mantém a matriz de arquivos.
- Scout de produto: somente leitura, produz achados e evidência.
- Scout visual/browser: somente leitura, produz screenshots e regressões.
- Revisor técnico/adversarial: somente leitura sobre SHA congelado.
- Writer: exatamente um por conjunto de paths; entrega commits pequenos.
- Integrador interno: apenas monta o SHA candidato; nunca toca `main`.

Auditoria de funil pode correr em paralelo com o writer do W13, mas qualquer
correção fica em outra fase/branch. `CampanhaCanonPage.tsx` permanece zona de
escrita única.

## Próxima ordem de cada superfície

### Claude Projects

> Recomece do `main` `6124c550`. Reconstrua somente o delta W13 sobre o W7 atual,
> com scouts e revisores read-only e um único writer. Não toque D1 antes de o
> W13 virar candidato aprovado. FunnelForge/WordPress/destino pago ficam em
> auditoria read-only nesta fase. Entregue `HANDOFF.md`, `handoff.json` e SHA
> congelado; sem merge, push, deploy ou migration.

### Terminal Codex

> Continue a missão Economic Attribution & Decision Plane em worktree própria.
> Feche coleta Google Ads/JoinAds, ledger, frescor, custo→jornada→receita e
> propostas shadow. Não altere Bia/Hermes, FunnelForge ou autoridades
> compartilhadas. Qualquer migration é candidata, numerada sob reserva e não é
> aplicada pelo worker. Entregue handoff tipado e provas herméticas/read-only.

### Terminal Claude

> Finalize a mesma Bia do Telegram na branch `feat/bia-hermes-volc-v1`. Congele
> o SHA atual, registre o que já foi aplicado no Supabase/Hermes, prove Telegram
> saudável e frontend local, e produza handoff para reaplicação sobre
> `6124c550`. Não crie outra persona, não toque Ads/W13/D1 e não faça merge ou
> push.

## Critério de velocidade

Velocidade é medida por candidatos independentes prontos para integração, não
por número de chats abertos. Três writers só são paralelos quando seus conjuntos
de arquivos são disjuntos. Revisão, pesquisa e QA podem paralelizar livremente
desde que não mutem o mesmo estado.
