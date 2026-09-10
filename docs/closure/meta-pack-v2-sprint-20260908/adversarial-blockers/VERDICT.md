# Adversarial review: pixels e conferência de imagens

## Intent

Listar pixels realmente acessíveis, explicar progresso/resultado da inspeção de imagem e impedir envio baseado em seleção, aprovação ou autorização obsoletas. Não ampliar autorização de um rascunho para toda a conta.

## Verdict: CONTESTED

Três revisores Claude CLI retornaram críticas; achados úteis foram corrigidos e hipóteses que dependiam de código omitido foram adjudicadas localmente. Não é certificação de prontidão produtiva: autorização de upload restrita ao rascunho e canário real continuam pendentes.

## Execução e limitações

- CLI: claude -p, ferramentas vazias, MCP vazio/estrito, hooks desabilitados, sem persistência de sessão. Três respostas completas e não vazias, exit 0, em skeptic.md, architect.md e minimalist.md.
- Usuário autorizou envio de trechos de código ao Claude. Uma tentativa com arquivos completos foi rejeitada pelo controle de envio e não executou; rodada final enviou somente trechos necessários dos controles assíncronos e revisão. Nenhum dado de campanha, credencial, arquivo .env ou imagem foi enviado nessa revisão de código.
- A skill instalada não contém brain/principles.md. Essa ausência foi informada aos revisores; foram usadas as definições de lentes disponíveis, sem inventar conteúdo dos princípios.
- Revisores não executaram testes nem leram o restante do repositório. Suas marcações de “verified” não substituem adjudicação no contexto completo. Patches finais posteriores à revisão foram verificados por testes locais, não por uma nova rodada externa.

## Findings e Lead Judgment

1. **Medium: conferência final incompleta apresentada como sucesso.** Skeptic #3. Aceito. A segunda resposta agora também exige o conjunto exato; erro visível, sem sucesso nem upload.
2. **Medium: aprovação parcial pode deixar estado visual antigo.** Três lentes. Aceito parcialmente. Falha durante aprovação limpa revisão, identifica imagem e conta aprovações já registradas. Troca de contexto descarta respostas e interrompe os próximos writes; aprovações já concluídas são duráveis e reencontradas na próxima conferência. Não são desfeitas silenciosamente. Isso não constitui transação atômica do lote.
3. **Medium: progresso some se atualização de capacidades falha.** Skeptic #4. Aceita a falha de comunicação: feedback é publicado antes do refresh. Rejeitada recomendação de conservar capacidade antiga: erro mantém envio desabilitado e revisão visível. Teste prova isso.
4. **Medium: erro de custódia deve identificar a imagem.** Três lentes, classificado high pelos revisores. Aceita identificação por índice. Rejeitada continuação do lote após master alheio/arquivado/hash divergente: a fronteira de custódia é fail-closed; o código de domínio retorna 409, não erro opaco. Teste de master arquivado confirma contrato. Não gastar em outras inspeções depois de custódia inválida.
5. **High condicional: backend confiaria no recibo do navegador.** Rejeitado por fonte: registrar recarrega bytes do dono, recalcula política e aprovação e compara hashes; cliente envia apenas referências/hash, não um veredito autorizador. Testes de aprovação revogada, conjunto divergente e segunda peça recusada existem e passam.
6. **High: aprovação antes de visualizar imagens.** Architect #1. Rejeitado: trechos omitiram a galeria, que renderiza CapaPack antes do checkbox; valid exige pack/manifests/seleção carregados. Aprovação humana é explicitamente das imagens finais, não do resultado automatizado. Peça com política recusada não recebe nova aprovação nesse fluxo.
7. **High condicional: versão mudaria entre preview e aprovação.** Não comprovado: masters são imutáveis; API resolve versão do master. Arquivamento/revogação são conferidos novamente antes do upload. Não adicionar uma segunda autoridade de versão no browser.
8. **Low: eliminar revisão exata, epochs e invalidar menos capacidades.** Minimalist #3–6. Rejeitado. Guardas cobrem resposta final distinta, render anterior ao efeito, A→B→A e falha de refresh. Testes adversariais cobrem os casos. Sobreposição não é prova de redundância.
9. **Medium: origem desconhecida aceita como upload humano.** Rejeitado como liberação: HUMAN_UPLOAD sem licença já é recusado pelo gate; teste prova. Nenhuma origem nova foi autorizada.
10. **Low: normalizar hash permissivamente.** Rejeitado: hash canônico é calculado dos bytes sob custódia, não entrada livre. Não aceitar representações diferentes para maquiar divergência.
11. **Medium: falta de idempotência no upload / erro de mídia vira 500.** Hipóteses da primeira rodada refutadas: reserva durável/CAS e estados incertos já existem; ErroDeRegistroDeMidia é subclasse de ErroDeNascimentoMeta e mantém 409 tipado.

## What went well

- Backend revalida custódia, propriedade, aprovação e inspeção antes de upload; ausência de autorização permanece fechada.
- Falha real de pixels foi isolada por campo e corrigida com leitura real completa, não presumindo falta de permissão geral.
- A imagem real selecionada passou inspeção; autorização do envio é explicitamente separada desse resultado.

## Remaining gaps

Envio autorizado apenas para o rascunho ainda não está implementado na configuração atual por conta. Nenhum upload, criação de campanha ou read-back PAUSED foi provado nesta rodada. Frontend foi exercitado com respostas simuladas em Chrome; diagnóstico de dados foi real, mas não substitui QA autenticado ponta a ponta.
