# Contexto de copy e revisão Meta — 10/09/2026

## Estado

**Atualização posterior, 10/09/2026:** autorização recebida, POST conectado e canário real de copy aprovado. Consulte [o fechamento da integração](../meta-copy-context-live-20260910/HANDOFF.md). O relato abaixo preserva a primeira rodada; sua pendência de consentimento foi resolvida. A pesquisa Meta ampla continua parcial.

**PARTIAL — P11-T19.** A varinha de um clique e o resolvedor local foram implementados. O envio de LP, briefing, motivações e estratégia persistidos ao modelo ainda NÃO está conectado: a checagem de autorização solicitou confirmação específica para ampliar o contexto textual anterior. A pergunta foi enviada ao operador; nenhuma autorização foi presumida.

Não houve nova publicação, ativação, chamada Meta, alteração de permissões, migration ou alteração Webgo nesta rodada. A revisão externa recebeu apenas resumos técnicos sanitizados e exemplos sintéticos.

## Implementado

- Varinha: um clique salva o rascunho e pede sugestões, sem novo campo de briefing. Quantidade opcional, loading, prévia e aplicação explícita; troca de conta, conjunto, destino, textos ou origem do pack invalida a sugestão. Nada sobrescreve a copy silenciosamente.
- Direção de copy: assunto central cedo, benefício da leitura, curiosidade específica, objeções e próximos passos; frases curtas e ângulos distintos. Não promete CTR, aprovação de benefício ou resultado comercial.
- `GET /api/trafego/meta/drafts/{ref}/copy-context?adset_key=...`: leitura local autenticada, sem dependência do modelo, sem LP fetch e sem inspeção de imagem. Retorna somente versão do rascunho, fontes, quantidade de fatos e avisos.
- Resolvedor: seleção persistida → revisão exata do pack → master/job do dono → run concluída original. Valida hash, origem, destino (preservando query semântica), dono e conjunto. Não usa a última geração do projeto nem busca global entre campanhas. Contexto truncado ou sem origem gera aviso, não ficção.
- Consultas automáticas de anunciante coalescidas por conta na instância da página. Cache somente em voo; troca de sessão invalida respostas antigas. Não há cache global compartilhado entre usuários.

O POST de sugestões continua transmitindo APENAS o contexto textual anteriormente autorizado. O resolvedor novo não está conectado ao POST. A interface não declara que todas as fontes foram utilizadas.

## Revisão Gemini executada

Orquestrador: `scripts/meta_gemini_review.py`. Master prompt e feedback estão nesta pasta. Recibos: `.claude-ads/runs/meta-context-review-20260910/ROUND-1.json` e `ROUND-2.json`.

- Três chamadas reais, duas rodadas; concorrência máxima dois, nenhuma repetição automática.
- Todas retornaram `modelVersion=gemini-3.8-flash`; `thinkingLevel=high` e `google_search` foram solicitados.
- Total informado pelo provider: **46.898 tokens**, incluindo thinking. Não equivale a uma estimativa monetária.
- Rodada 1, criativos: sete queries/sete fontes, mas saída JSON inválida. Não aceita para execução automática.
- Rodada 1, lançamento: JSON válido sem grounding verificável.
- Rodada 2, mensuração e contraprova: JSON válido sem grounding verificável.
- Resultado da pesquisa: **incompleto**, não “auditoria final aprovada”. A tentativa independente de abrir documentação Meta retornou HTTP 429; buscas adicionais não trouxeram resultados.

## Adjudicação do integrador

| Proposta externa | Decisão |
| --- | --- |
| Flexível limitado aos objetivos suportados, cinco textos por tipo e CTA uniforme | Já representado no contrato local; nenhuma nova trava. O material oficial previamente fornecido pelo operador distingue esses requisitos. |
| Reduzir primary_text flexível para 1.024 caracteres com base em asset_feed_spec | Não aplicado: extrapola um contrato para outro sem fonte exata. |
| Exigir Instagram vinculado universalmente | Não aplicado: depende de identidade e posicionamento; não demonstrado como requisito universal. |
| Repetir criação após busca retornar zero objetos | Não aplicado: ausência na leitura não prova ausência de efeito remoto. Preservada reconciliação de estado ambíguo. |
| Colocar creative_asset_groups_spec no AdCreative | Não aplicado: contradiz o contrato local e o exemplo documental fornecido, que o coloca no anúncio. |
| Proibir VALUE/MIN_ROAS globalmente | Não aplicado: não há prova de elegibilidade específica; receita editorial por conjunto não é automaticamente valor de conversão Meta. |

Inspeção local confirmou que revisão automática já compila/valida o plano; executor V2 valida filhos depois de obter IDs dos pais, registra IDs antes do readback e mantém estados parciais. Isso NÃO prova que uma nova campanha completa será aceita pela Meta. Botões de retry após erro e a aprovação final continuam necessários; não foi criada etapa adicional de confirmação.

## Testes e lacunas

- Backend focal: **111 testes passaram**, incluindo 44 do resolvedor e 26 da sugestão existente, revisão externa e contratos flexíveis.
- Frontend focal: **30 testes passaram** (varinha/nomenclatura, consultas compartilhadas e retomada da página real).
- Build passou. TypeScript global: **76 erros fora dos arquivos afetados**, mantida a quantidade anterior; não é uma compilação TypeScript global limpa.
- Chrome com fixture isolada: 375/1440, claro/escuro, uma chamada por Enter, zero aplicação sem clique, zero textareas, zero overflow e zero erro JS. API simulada no navegador; não é QA autenticado real. Capturas temporárias em `/private/tmp/meta-context-{375,1440}-{light,dark}.png` e variantes `-loading.png`.
- Front8080 e API8010/health responderam200; verificador de autoridade confirmou o Supabase oficial.

A revisão local encontrou e corrigiu quatro problemas: snapshot de LP antiga validado pela URL nova do briefing; asset trocado mantendo origem antiga do pack; estruturas legadas causando500; edição concorrente do contexto após salvar. A imagem agora precisa corresponder ao registro de envio do dono/conta/master/hash quando já está montada. A correlação de conta usa IDs internos do read model, com limite de leitura e sem exportá-los ao modelo. Ausência de prova exclui somente esse contexto e exibe aviso.

Resultados registrados na tarefa P11-T19. Testes locais não equivalem a execução autenticada, aprovação remota nem ganho de CTR.

Pendências de fechamento:

1. Consentimento específico para enviar o contexto salvo ampliado; depois conectar resolver ao POST e verificar versão da seleção após o modelo responder.
2. Provar recuperação com um pack/rascunho autenticado real, sem misturar contexto de destinos diferentes.
3. Repetir pesquisa documental somente quando houver fonte acessível; não executar novas chamadas pagas em loop por falha de grounding.
4. Criação completa PAUSED com recibos/readback e qualidade comercial dependem de teste operacional separado, não ocorrido nesta rodada.

## Como retomar

Não executar o orquestrador novamente sobre recibos existentes para obter um parecer “verde”. Uma nova rodada exige escopo, teto e feedback explícitos. Nunca executar shell ou SQL recebido do modelo. As sugestões são propostas; fonte oficial e evidência local decidem a implementação.
