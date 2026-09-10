# Galeria dos packs

## Entrega local

- Biblioteca: `/trafego/meta/packs`.
- Detalhe recarregável: `/trafego/meta/packs/:packId`.
- Packs salvos no Assistente agora têm capa e link para o detalhe.
- Detalhe apresenta imagem, seletor de peças, prévia ilustrativa do anúncio com copy preservada, zoom, download, copiar texto e preparar campanha.
- A leitura do pack é autenticada e filtrada por proprietário. A imagem é resolvida pelo job, master e hash salvos; outra rendition não substitui o master do pack.
- Nenhuma migration, geração ou chamada Meta é necessária para visualizar o pack existente.

## Provas

- 18 testes backend passaram, incluindo isolamento do detalhe por proprietário e autenticação.
- 4 testes frontend passaram, incluindo deep link, troca de imagem/copy e recusa de outro master.
- TypeScript: 76 erros existentes; nenhum nos arquivos desta mudança na execução inicial.
- Nova rota local respondeu 401 sem sessão; módulo da página respondeu 200 no Vite.
- Build global encontrou JSX incompleto em `DataStatus.tsx` durante edição do executor de redesign. Não modificar ou reverter o arquivo daquele executor para concluir esta tarefa.
- Nova execução do build completo passou em 11,41 s após a correção paralela. `git diff --check` passou.
- QA hermético com Chrome real: seis capturas em `/private/tmp/pack-{375,768,1440}-{light,dark}.png`; sem erro JavaScript nem overflow horizontal; troca de peça, zoom e Escape exercitados. Capturas usam o screenshot fornecido como fixture visual, não a API autenticada de imagens.
- `--check` do grafo confirmou insumos desatualizados durante o redesign concorrente. Rebuild final é responsabilidade do integrador único dessa rodada; não declarar `current` antes dele.

## Integração com o redesign em andamento

O executor de redesign está escrevendo nesta mesma branch. Não há nova branch ou worktree. Preservar as adições de rotas em `src/App.tsx` e os componentes desta entrega. Não fazer commit abrangente a partir deste handoff.

Curadoria a incorporar pelo integrador único ao encerrar a rodada:

- Tasks P11-T02 e P11-T04: acrescentar a biblioteca e detalhe local dos packs às evidências, mantendo `partial` para as demais lacunas operacionais.
- Nó `cap_bancada_criativa`: acrescentar navegação por pack, preview e reuso de referências sem geração.
- Reconstruir o grafo com `scripts/atualizar_grafo_volc_os.py` depois de integrar todas as mudanças de frontend e executar `--check`. Um build durante edições concorrentes não prova o frescor final.

Os screenshots herméticos usam fixture e não comprovam leitura autenticada do pack do operador. A inspeção final com a sessão do usuário permanece necessária.
