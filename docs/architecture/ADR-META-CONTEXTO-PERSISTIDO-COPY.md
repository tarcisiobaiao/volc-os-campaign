# ADR — Contexto persistido para sugestões de copy Meta

## Status

Aceito e conectado ao POST em 10/09/2026, após autorização explícita do operador para o contexto salvo. Complementa `ADR-META-NOMENCLATURA-E-COPY.md`. Evidência: `docs/closure/meta-copy-context-live-20260910/HANDOFF.md`.

## Contexto

O operador já fornece contexto ao produzir as peças. Pedir um novo briefing para cada banco de copy repete esforço e permite divergência. Buscar genericamente no histórico pode misturar campanhas, destinos e gerações.

## Decisão

Resolver a cadeia da seleção persistida do conjunto até a geração original, sob o mesmo dono. A revisão de pack, o hash e o vínculo master/job são parte da identidade, não apenas o nome do pack. O destino compara query semântica; parâmetros de tracking não definem uma nova LP.

Separar obtenção local do contexto e envio externo. O GET autenticado expõe somente resumo das fontes, sem custo de modelo. Com a autorização ampliada recebida, o POST envia fatos da LP salva, briefing, motivações e estratégia da seleção comprovada. Não usar imagens, listas de público, IDs ou credenciais como contexto do modelo. Acesso autorizado ao projeto não equivale a envio indiscriminado de arquivos.

Varinha de um clique com prévia; não aplicar automaticamente. Requisições e resultados desatualizados não podem substituir os textos de outro conjunto. Fonte ausente ou incompatível precisa aparecer como limitação, sem usar outra geração como substituta silenciosa.

Revisores externos recebem resumos técnicos sanitizados. Grounding solicitado não significa grounding realizado. Modelo exato, recibos, fontes e testes precisam ser verificados independentemente. Sem execução automática de código/SQL produzido pelo modelo, sem retry pago oculto.

## Alternativas

- Busca vetorial em todos os projetos: rejeitada por não preservar identidade da seleção e por poder misturar donos/assuntos.
- Última run do projeto: rejeitada porque pode não ter produzido a peça selecionada.
- Refazer leitura da LP a cada sugestão: rejeitada nesta fase; aumenta custo/latência e muda o contexto sem explicar a diferença.
- Reutilizar o snapshot exato: adotado; com checagens de dono, destino, revisão e avisos para lacunas.

## Consequências

Não exige novas tabelas para a leitura. Após a chamada, revalidar a versão do rascunho e o hash privado das testemunhas da seleção, pois o pack pode mudar independentemente do rascunho. Hash privado não é enviado ao modelo. Deadline total de 70 segundos inclui leituras, geração e rechecagem; reservar 20 segundos para a rechecagem e não repetir chamadas pagas automaticamente. Snapshots não são verificação atualizada da LP nem aprovação das afirmações publicitárias. Fonte ausente mantém o contexto dos textos atuais e assunto, com aviso explícito.
