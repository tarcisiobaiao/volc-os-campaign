# Meta: motivação, grande ideia e cena

2026-09-09 · P11-T17 · implementação local; aceite visual de imagens novas pendente.

## Decisão e fonte

O problema observado não era apenas cromático: as propostas transformavam o
sumário institucional da LP em capas explicativas. Aumentar saturação sem mudar
a ideia continuaria produzindo panfletos. A nova sequência é fato revisado →
motivação possível → pergunta relevante → grande ideia → cena → texto e spec.

Transferência conceitual, não cópia do motor Pautador Pro:

- `backend/app/motor_pautas/psique.py`: tensão mental como ponte entre informação
  e interesse; não importar seus priors numéricos ou scores históricos.
- `backend/app/motor_pautas/prompts/classificador_eixos.md`: explicitar a pergunta
  e a resposta útil, o que está em jogo e a lacuna de conhecimento.
- `backend/app/n8n_prompts/funnel_builder.py`: separar desejo superficial,
  transformação desejada e necessidade real; jornada dúvida → clareza.
- `backend/app/motor_pautas/DECISOES.md` e `backend/app/validacao/oportunidade.py`:
  calibrações e correlações históricas não autorizam previsão causal de clique
  ou lucro. Nenhum dado financeiro, cliente ou score foi copiado para o prompt.

Ads orientou a separação entre hipótese e evidência; Impeccable orientou a
prioridade das motivações e a divulgação progressiva dos fatos na interface.

## Contrato

`ContextoDaPagina.motivacoes_sugeridas` tem até oito itens: tipo (dor, desejo,
sonho, receio), hipótese, pergunta latente, entrega da página e refs de fatos.
É produzido na mesma chamada de contexto, sem segundo agente/custo adicional
por chamada. A quantidade de tokens dessa chamada pode variar. Índices só
viram refs se pertencem aos fatos extraídos selecionados; itens malformados
são descartados individualmente. Referências órfãs são recusadas pelo modelo.
Ausência de apoio não força quatro emoções inventadas.

Na montagem da missão, hipóteses apoiadas em fatos desmarcados são excluídas,
sem mutar o contexto original salvo. Contexto e fatos continuam dados, nunca
instruções. Motivação é hipótese editorial, não diagnóstico de quem verá o ad.

`PecaCriativa.big_idea` registra ideia central, pergunta latente, promessa do
clique e cena-chave. O prompt pede o objeto em cada peça nova; a contraprova
exige sua presença quando há contexto motivacional apoiado em fatos aprovados.
Legado continua aceito e peças inteiramente congeladas não ganham campos novos.
O serializer omite big_idea ausente/nula para preservar snapshots históricos.

O briefador transpõe a cena-chave e ideia para os campos de direção já
aprováveis. O renderer continua usando a spec aprovada; não injeta big_idea como
texto extra e não reinterpreta specs antigas. gpt-image-2/quality medium intactos.
Referências cromáticas seguem presentes, sem transformar uma página editorial
em representação falsa de canal oficial. Nenhuma promessa de CTR foi adicionada.

## Experiência e persistência

Após analisar a LP, “Por que alguém clicaria?” apresenta bullets agrupados pelas
motivações disponíveis antes da lista de fatos. A entrega e seu apoio são
expansíveis. Fatos mantêm seleção e proveniência; desmarcar apoio sinaliza que a
hipótese não orientará o briefing. Na estratégia, a ideia central fica visível;
pergunta, promessa e cena ficam nos detalhes, sem outra etapa de aprovação.

Contexto no input JSON e saída no output JSON existentes carregam os campos.
Nenhuma migration necessária nesta rodada. Um teste encontrou snapshot de peça
válida com 4134 caracteres, acima do teto antigo de 4000. O teto de
ElementoCongelado.valor passou a 16000, com teste de aprovação → continuação nas
rotas reais usando repositório dublê. Não é prova nova de persistência em banco vivo.

## Verificação e próximo teste

Os resultados finais de testes e QA hermético constam no manifesto desta run.
Build passou. TypeScript global mantém 76 erros herdados, nenhum no domínio
criativo. Backend 8010 e frontend 8080 responderam HTTP 200. Autoridade Supabase
oficial conferida; nenhum banco, campanha, imagem antiga ou Webgo foi alterado.

Para testar: novo briefing → analisar LP novamente → conferir assunto e
motivações → adicionar ao briefing → propor estratégia → revisar ideia/cena →
aprovar e gerar. Regerar uma peça já aprovada mantém sua spec antiga por desenho.
Não houve nova chamada paga: qualidade dos pixels, aceitação humana das big
ideas geradas e efeito sobre CTR dependem da próxima geração/experimento.
