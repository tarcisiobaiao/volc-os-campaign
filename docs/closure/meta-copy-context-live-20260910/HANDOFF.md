# Copy contextual Meta — integração autorizada

## Resultado

Em 10/09/2026, a varinha passou a enviar ao modelo o contexto textual comprovado das peças selecionadas: fatos da LP salva, briefing, motivações editoriais, estratégia e copy de origem. Não exige escrever outro briefing. A autorização ampliada foi recebida nesta conversa; a pendência de consentimento da rodada anterior está resolvida.

O envio é uma projeção textual, não um upload do projeto: credenciais, arquivos `.env`, IDs internos, listas de público e bytes de imagem ficam fora. Não houve migration, criação de anúncio, ativação ou mudança no Webgo.

## Uso

1. Na etapa Criativos, escolha o conjunto e vincule seu pack pelo fluxo existente.
2. Use **Sugerir copies com IA**. A varinha salva antes de gerar e usa a seleção exata daquele conjunto.
3. Confira a prévia e aplique as sugestões desejadas. Nada sobrescreve seus textos automaticamente.

Se não houver pack vinculado, a geração continua com o assunto e os textos atuais e informa a ausência das fontes. A consulta administrativa ao Supabase oficial encontrou quatro rascunhos ativos do dono consultado, todos sem seleção persistida de pack. Não foi criado vínculo artificial com outro projeto para contornar isso.

## Integridade

- Resolução por dono, conjunto, destino, revisão de pack, master, job e run original; sem usar a geração mais recente por conveniência.
- Após o modelo responder, releitura do rascunho e das testemunhas da seleção. Mudança invalida a resposta, mesmo sem mudar a versão do rascunho.
- Deadline total de 70 segundos, com reserva de tempo para rechecagem; sem retry pago automático.
- Resumo tipado das fontes usado pela prévia; estruturas antigas/incompatíveis geram avisos, não contexto inventado.
- Motivações são hipóteses editoriais. Snapshot de LP não é verificação atual nem inspeção dos pixels.

## Evidências

- **123 testes backend**: resolvedor, POST, copy, orquestrador e contratos flexíveis.
- **25 testes frontend**: varinha/nomenclatura e retomada.
- **3 testes adicionais** do runner de revisão: allowlist, scan, high/search e ausência de retry.
- **Canário pago real**: uma chamada, modelo `gemini-3.8-flash`, HTTP200 em aproximadamente4,3s; três sugestões por tipo. Rota real com grafo e repositório sintéticos, quatro tipos de fonte e rechecagem do rascunho. Não é prova de um pack real autenticado. Recibo em [CANARY.json](CANARY.json).
- Leitura administrativa no Supabase oficial sem alteração de dados; verificador de autoridade aprovado. Backend `/health` respondeu200.
- QA visual da varinha ocorreu na rodada anterior com fixtures em 375/1440, claro/escuro. Frontend não foi alterado nesta atualização; não houve nova inspeção autenticada.

## Limites do fechamento

Revisão adicional: uma chamada autorizada enviou somente quatro arquivos de integração, após scan de segredos. Solicitados `gemini-3.8-flash`, thinking high e Google Search. Não houve resposta verificável (`transport_or_response_error`); não há parecer, modelo servido, grounding ou uso de tokens comprováveis nessa tentativa. Cobrança pode ter ocorrido e é desconhecida. Nenhuma repetição foi feita. [Recibo da tentativa](CODE-REVIEW.json). O canário de copy acima é uma chamada diferente, bem-sucedida.

**P11-T19 continua partial.** Integração e canário estão comprovados, mas recuperação com pack real autenticado, pesquisa documental Meta ampla e criação PAUSED completa não foram provadas nesta rodada. Nenhum teste demonstra aumento de CTR. A pesquisa anterior continua documentada em [meta-context-review](../meta-context-review-20260910/HANDOFF.md); não repetir chamadas pagas até obter um parecer favorável.

Memória operacional: tarefa `P11-T19`, nó `doc:meta-context-review-20260910`. Reconstruir e conferir o grafo após concluir a adjudicação da revisão de código.
