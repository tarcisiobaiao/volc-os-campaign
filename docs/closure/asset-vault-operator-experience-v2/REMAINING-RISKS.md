# REMAINING-RISKS

1. **Nenhum ativo real cadastrado.** A tela opera contra API ou doubles. Produção continua sem patrimônio persistido até autorização de escrita no Supabase.
2. **1Password / AdsPower reais não foram tocados.** Referência composta no POST não prova resolução. Broker continua no host isolado.
3. **Duas prontidões no inspetor.** União obrigatória do merge (`prontidao` + `prontidao-visual`). Carga cognitiva residual; não colapsar sem contrato.
4. **Rascunho em sessionStorage.** Identidade e metadados da credencial (provider, nome lógico, finalidade, responsável) podem permanecer entre Fechar/reabrir. Cofre, item, campo e o localizador são efêmeros: Fechar, Concluir, recarregar e cancelar os descartam, e o storage é varrido para não os serializar. Aba anônima isola o rascunho de identidade.
5. **Hatch de captura não existe no app.** Screenshots after usam aliases Vite **fora do git**. Risco: alguém copiar o double para produção — GATES exige ausência de fallback de fixture; `cofreApi.ts` não lê `fixtures.ts`.
6. **TypeScript baseline herdado** do monorepo (erros fora de `asset-vault`). Não “limpo o repo”.
7. **Toasts de recibo.** Falhas e efeitos invisíveis (idempotência) ainda usam toast; sucesso visível no inventário após invalidate.
8. **Grafo / Mapa Vivo.** Relações continuam texto/arestas do Cofre, não curadoria. Esta missão não reconstrói o grafo.
9. **localhost:8080 / 8010 do operador.** Não exercitamos mutação contra eles. Double de captura recusa persistir.
10. **merge-tree não era limpo.** Cinco arquivos com CONFLICT no `merge-tree` dos pais `207e91f1` + `5f54d25c`; oito caminhos envolvidos na resolução da união (os cinco CONFLICT mais `prontidaoOperacao.ts`, `prontidao-operacao.test.ts` e `ProntidaoDeOperacao.tsx`). Um rebase futuro reabriria o mesmo conflito.

Nada disto autoriza inventar endpoint, revelar segredo, ou promover P03-T* para done.
