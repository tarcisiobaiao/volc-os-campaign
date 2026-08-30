# Graphify no VOLC O.S.

## Decisão

O Graphify passa a ser a camada profunda do Mapa Mestre, mas não substitui o
nosso inventário operacional.

O motivo é simples: ele enxerga muito bem código, SQL, chamadas e dependências;
porém não sabe sozinho quais workflows estão realmente ativos, qual banco é a
fonte oficial, quais tabelas estão vazias, quais decisões são prioridade e qual
é a história de negócio por trás de cada módulo.

Por isso, a arquitetura adotada é híbrida:

```text
Código + SQL ──Graphify local──┐
                              ├── grafo híbrido consultável
Supabase + n8n + ClickUp +     │   fato / hipótese / caminho / impacto
documentos ──Mapa Mestre───────┘
```

## O que foi comprovado

Snapshot de 22/08/2026, usando Graphify `0.9.48`, commit upstream
`b2cd36267456c166788c95be6e68574064a92a42`:

- 846 arquivos de código analisados localmente;
- 121 arquivos SQL incluídos com o extrator opcional;
- 8.892 nós e 20.690 relações na camada técnica;
- 269 nós e 442 relações na camada operacional curada;
- 98 pontes automáticas entre negócio e implementação;
- 9.161 nós, 21.230 relações e 493 comunidades no grafo final;
- zero chamadas de LLM e zero envio de conteúdo para fora da máquina.

As 483 comunidades técnicas detectadas pelo Graphify foram preservadas. Os 269
nós operacionais permaneceram nos 10 clusters curados do Mapa Mestre. Essa
combinação evita que uma pequena alteração de código embaralhe os domínios de
negócio e mantém o resultado reproduzível.

## O que muda na prática

Antes, o Mapa Mestre respondia principalmente “o que temos?” e “o que vem
primeiro?”. Agora também responde:

- qual arquivo implementa uma tela, serviço ou API;
- qual é o caminho entre duas capacidades;
- o que pode ser impactado por uma tabela, classe ou serviço;
- quais elementos concentram dependências;
- quais relações são fatos extraídos e quais são hipóteses modeladas.

Exemplo validado:

```text
Hub de Tráfego
  ──organiza──> Nascimento de campanha Search
  ──deve_retornar_para──> Cockpit de campanha
```

O caminho prova por que o curto prazo continua sendo construir a ponte entre a
nova camada de Tráfego e o cockpit existente, e não criar outro monitoramento.

## Regra de honestidade

- `EXTRACTED`: apareceu diretamente no código, banco, rota ou inventário medido;
- `INFERRED`: foi resolvido por nome ou modelado como relação de negócio;
- `AMBIGUOUS`: não há evidência suficiente e precisa de revisão humana.

Essa separação é a contribuição mais valiosa da metodologia do Graphify para o
VOLC: hipótese útil continua útil, mas nunca se apresenta como fato comprovado.

## Artefatos

- `graphify-out/graph.json`: fonte integral consultável;
- `graphify-out/graph.html`: visão agregada das comunidades;
- `graphify-out/GRAPH_REPORT.md`: relatório estrutural do Graphify;
- `graphify-out/README.md`: guia curto de uso e atualização;
- `scripts/gerar_graphify_volc_os.py`: adaptador VOLC reproduzível;
- `docs/volc-os-graph/graphify-upstream.lock.json`: versão upstream fixada;
- `entregaveis/Mapa_Mestre_VOLC_OS.html`: porta de entrada executiva;
- `docs/volc-os-graph/volc-os-graph.json`: camada operacional curada.

## Próxima evolução

O próximo workbook deve usar três níveis de leitura:

1. **Respirar e decidir:** capacidades, prioridades e dependências críticas;
2. **Navegar:** Mapa Mestre executivo com estados e evidências;
3. **Investigar:** Graphify híbrido para caminho, impacto e implementação.

Não é necessário despejar 9 mil nós no documento. O workbook deve mostrar os
recortes que ajudam uma decisão; o grafo profundo permanece disponível para
provar e investigar cada recorte.
