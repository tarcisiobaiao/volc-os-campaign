# REMAINING-RISKS

1. **Nenhum ativo real cadastrado.** A tela opera contra API ou doubles. Produção continua sem patrimônio persistido até autorização de escrita no Supabase. Interface pronta **não** significa Cofre povoado.
2. **1Password / AdsPower reais não foram tocados.** Referência composta no POST não prova resolução. A autoridade canônica única é `tools/adspower-broker/` no host isolado; P03-T11 permanece `partial`.
3. **Segundo candidato de broker removido.** `backend/app/asset_vault/broker/` foi unido a partir de `5f54d25` e **removido na adjudicação**. Não transplantar `inventario_perfis` / `inventario_grupos` sem missão própria.
4. **Inventário real de perfis/grupos AdsPower não está implementado.** P03-T07 permanece `partial` conforme a linha oficial `3331c0c` (browser_profile / prontidão visual / broker hermético na linha oficial; nenhum perfil real inventariado).
5. **Duas prontidões no inspetor.** União obrigatória do merge (`prontidao` + `prontidao-visual`). Carga cognitiva residual; não colapsar sem contrato.
6. **Rascunho em sessionStorage.** Identidade e metadados da credencial (provider, nome lógico, finalidade, responsável) podem permanecer entre Fechar/reabrir. Cofre, item, campo e o localizador são efêmeros: Fechar, Concluir, recarregar e cancelar os descartam, e o storage é varrido para não os serializar. Aba anônima isola o rascunho de identidade.
7. **Hatch de captura não existe no app.** Screenshots after usam aliases Vite **fora do git**. Risco: alguém copiar o double para produção — GATES exige ausência de fallback de fixture; `cofreApi.ts` não lê `fixtures.ts`.
8. **TypeScript baseline herdado** do monorepo (erros fora de `asset-vault`). Não “limpo o repo”.
9. **Toasts de recibo.** Falhas e efeitos invisíveis (idempotência) ainda usam toast; sucesso visível no inventário após invalidate.
10. **Grafo / Mapa Vivo.** Relações continuam texto/arestas do Cofre, não curadoria. Esta missão não reconstrói o grafo.
11. **localhost:8080 / 8010 do operador.** Não exercitamos mutação contra eles. Double de captura recusa persistir.
12. **merge-tree não era limpo.** Cinco arquivos com CONFLICT no `merge-tree` dos pais `207e91f1` + `5f54d25c`; oito caminhos envolvidos na resolução da união. Um rebase futuro reabriria o mesmo conflito. Esta correção **não** rebaseia a linha oficial `3331c0c`.

Nada disto autoriza inventar endpoint, revelar segredo, ou promover P03-T* para done.
