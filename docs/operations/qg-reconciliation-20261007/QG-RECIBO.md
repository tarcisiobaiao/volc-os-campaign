# Recibo do QG Agêntico — 07/10/2026

Branch `integration/qg-real-20261007`, roadmap no commit `5778e7b`
(sha256 `537a33be0a662980d6820b4b86205df055bd1e0a7cbc53aaa95d84a327ea704e`).

## Como foi medido

A rota `/settings/qg-agentico` e a API `/api/work-road` exigem sessão Supabase.
Nenhuma credencial foi usada. O recibo tem duas partes:

1. **API real em processo.** O router `app.routers.work_road` montado num
   FastAPI com `TestClient`, trocando só a dependência `exigir_usuario`.
   Durante a medição, `socket.connect` levantava erro: nenhuma chamada de rede
   foi possível.
2. **Página real.** `QGAgenticoPage` e `QgTaskPage` renderizadas em jsdom com
   as respostas JSON da etapa 1 (teste temporário, apagado depois).

## Resultado

| Verificação | Resultado |
|---|---|
| `GET /api/work-road` | 200, `Cache-Control: no-store` |
| Totais por status = arquivo | done 48 · partial 78 · todo 50 · risk 1 · reserved 12 (189) |
| `reserved` fora do percentual | 177 tarefas aceitas; 49,3% (done 1, partial 0,5, risk 0,25) |
| Lista e detalhe na mesma fonte | `GET /tasks/{id}` devolveu o mesmo sha256 da lista para P10-T19, P01-T12, P04-T04 e P12-T02 |
| Exportação de pendências | `GET /export?scope=open&format=json`: 129 tarefas (78 partial, 50 todo, 1 risk), nenhuma `done` ou `reserved` |
| Exportação DOCX | `GET /export?format=docx` devolve um arquivo fixo de `entregaveis/` quando ele existe (aqui, 404). Não é gerada do roadmap vivo |
| `GET /graph-status` | `stale: false`, `graph_commit` = HEAD do momento (`acaac92`) |
| Página `/settings/qg-agentico` | mostra 49.3%, 17 iniciativas, 189 tarefas, 48 concluídas e "reservado — fora do percentual" |
| Página `/settings/qg-agentico/tarefas/P01-T12` | título, status "A fazer", iniciativa P01 e "Fonte volc-os-workbook/ROADMAP-VIVO.json · hash 537a33be0a66" |
| Cópia antiga ou backend alternativo | o front só lê `/api/work-road` (`src/lib/pautadorApi.ts`); não há JSON de roadmap importado no bundle; o backend lê o arquivo a cada requisição |

## Falha herdada relacionada

`src/features/work-road/__tests__/qg-logic.test.ts` lê o roadmap real e espera
`P05-T11` como próxima tarefa recomendada. P05-T11 está `done` desde a linha v2;
a recomendação atual (`P05-T12`) é a correta. O teste já falhava em `90833f2`.
