# VOLC O.S. — Workbook Vivo

Esta pasta é a sala editorial do livro da operação. Ela existe para transformar o
grafo, o sistema e as decisões do dono em uma leitura simples, ordenada e acionável.

## Comece aqui

1. Leia `LIVRO-FONTE.md` para entender a operação sem linguagem técnica.
2. Abra `ROADMAP-VIVO.json` quando precisar auditar tarefas, estados e provas.
3. Gere o DOCX com `backend/.venv/bin/python volc-os-workbook/build.py`.
4. Leia o resultado em `entregaveis/Workbook_VOLC_OS_Livro_Vivo_v1.0.docx`.

## O que é fonte de verdade

| assunto | fonte |
| --- | --- |
| capacidades, estados e relações | `docs/volc-os-graph/curadoria-operacional.json` |
| mapa operacional gerado | `docs/volc-os-graph/volc-os-graph.json` |
| tarefas editoriais do livro | `volc-os-workbook/ROADMAP-VIVO.json` |
| explicação simples | `volc-os-workbook/LIVRO-FONTE.md` |
| navegação profunda | `graphify-out/graph.json` |

O JSON de tarefas é a fonte compartilhada desta etapa. O QG Agêntico lê esse
arquivo pelo endpoint autenticado `/api/work-road`, sem seed ou cópia em
`localStorage`. Uma futura escrita pela interface exigirá autoria, evidência e
auditoria antes de substituir a edição versionada do arquivo.

## Como interpretar o percentual

O workbook calcula um **índice editorial de fechamento**:

- concluído = 100% do peso da tarefa;
- parcial = 50%;
- existe com risco = 25%;
- a fazer = 0%;
- reservado = fora do denominador.

Esse índice não mede qualidade, faturamento, esforço restante ou prazo. Ele serve
somente para dar visibilidade ao escopo aceito e impedir que itens reservados
derrubem artificialmente o progresso.

## Regra de atualização

1. Novo material entra primeiro na inbox estratégica.
2. Fatos e hipóteses são separados numa nota de ingestão.
3. Capacidades e relações aceitas entram na curadoria humana.
4. Tarefas novas ou alteradas entram no `ROADMAP-VIVO.json`.
5. O DOCX é regenerado; nunca é editado como fonte.
6. Depois de mudança material, o grafo híbrido é atualizado pelo pipeline oficial.

## Limites

- Nunca colocar senha, token ou chave no livro, JSON ou grafo.
- “Existe arquivo” não significa “opera”.
- “Ativo declarado” não significa “propriedade comprovada”.
- Projeção de documento antigo não vira meta atual sem decisão.
- Ferramenta citada não vira integração prioritária automaticamente.
- Toda automação sensível continua sujeita a autorização, recibo e rollback.
