# Mapa Mestre do VOLC O.S.

Snapshot gerado em **22/08/2026** para impedir que roadmap, documentação e implementação se percam entre camadas.

## Artefatos

- `index.html` — grafo navegável, sem dependências externas.
- `volc-os-graph.json` — fonte de verdade legível por máquina.
- `volc-os-graph.graphml` — importável em Gephi, yEd e ferramentas compatíveis.
- `nodes.csv` / `edges.csv` — análise tabular.
- `visao-executiva.mmd` — recorte Mermaid das capacidades.

## Tamanho medido

- **455 nós** e **701 relações**.
- Tipos: backend_module=4, business_component=8, capability=40, concept=132, database_function=67, document=43, edge_function=1, external_system=16, frontend_service=14, table_or_view=64, task=11, ui_surface=22, workflow=33.
- Estados: decision=10, declared_active=24, empty=31, historical=34, implemented=140, inactive=11, live=14, partial=72, reference=66, risk=9, todo=44.

## Regra de confiança

- Contagens do Supabase: `count=exact` pelo PostgREST em 22/08/2026.
- Datas: menor/maior valor da coluna temporal selecionada.
- n8n: `ativo` significa **estado declarado no inventário**, não execução bem-sucedida.
- Relações de código: extraídas de imports, `.from(...)`, `.rpc(...)`, rotas e URLs PostgREST.
- Relações de negócio: marcadas como modeladas quando não vêm de uma FK ou chamada direta.

## Correção mais importante em relação ao workbook v0.1

O monitoramento por campanha **já existe** e é robusto em `/dashboard/campaign/:campaignId`.
A prioridade correta não é criar outro monitoramento, e sim ligar a nova jornada de Tráfego a esse cockpit,
restabelecer frescor/reconciliação e fechar os elos de atribuição e conversão.
