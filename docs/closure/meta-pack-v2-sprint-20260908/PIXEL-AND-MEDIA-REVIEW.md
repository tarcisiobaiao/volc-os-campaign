# Pixels compartilhados e resultado da conferência de mídia

Estado: PARTIAL. Correções locais verificadas; nenhum upload ou nascimento Meta executado nesta rodada.

## Diagnóstico real

- Consulta do System User, na conta do rascunho solicitado: `adspixels` com `id,name` retornou HTTP 200 e dois pixels. Os campos `is_unavailable`, `last_fired_time` e `creation_time` também passaram individualmente.
- Acrescentar apenas `owner_ad_account` produziu HTTP 403 / Graph code 200. O token já possui ads_read e ads_management. O campo opcional consulta a conta proprietária do pixel compartilhado e não deve impedir a listagem da conta selecionada.
- Removida essa projeção opcional. Catálogo real corrigido: completo, dois itens PIXEL, ambos AVAILABLE_FIRED. Propriedade ausente continua desconhecida, não é convertida em permissão.
- Inspeção real da única imagem selecionada, após registrar OCR como no startup: aprovação humana vigente, utilizável, política CLEAR, léxico/OCR Apple Vision/Gemini sem restrição. Somente bytes da imagem autorizada foram enviados ao detector; nenhum token, código ou dado de campanha.
- A autorização de upload dessa conta no servidor está desligada. Esse é um bloqueio independente de pixel e aprovação. Não foi ampliada uma autorização restrita ao rascunho para toda a conta.

## Correções

- Catálogo indisponível não afirma zero itens nem mostra selo verde de leitura vigente; mensagem de permissão inclui vínculo e campos solicitados.
- Conferência de pack informa andamento, resultado por imagem, aprovação registrada, motivos e detector indisponível. Inspeção concluída não é confundida com autorização de upload.
- Respostas antigas são descartadas ao mudar conta, conjunto, pack, versão, manifesto ou seleção. Consentimento, recibo e revisão são limpos; uploads permanecem associados ao contexto de origem, nunca anexados a outra seleção.
- Exige conjunto exato de imagens revisadas, manifesto presente e referências pertencentes ao pack. Falha ao atualizar capacidades invalida autorização antiga.
- Não duplica aprovação já vigente nem reinspeciona sem necessidade no mesmo clique. Peça recusada pela política não recebe aprovação nova nesse fluxo.
- Backend recusa referências duplicadas antes da inspeção, resolve detector uma vez por lote e não chama inspeção paga parcial quando falta capacidade obrigatória. Custódia e aprovação continuam verificadas; revisão é recalculada antes de upload.

## Provas

- Backend: 113 testes passando em catálogos selecionáveis, revisão e registro de mídia.
- Frontend: 22 testes passando em conferência de pack e catálogo. Incluem corrida de mudança de conjunto, revisão vazia/incompleta, aprovação interrompida, autorização velha e motivo de política.
- Build passou; TypeScript permanece com 76 erros globais preexistentes, nenhum em PrepararPackMeta, CatalogoDaConta ou pautadorApi.
- Chrome: componentes reais isolados com respostas simuladas, 375/768/1440, claro/escuro, teclado, carregamento, resultado, upload bloqueado, sem overflow nem erro JS. Não equivale ao fluxo autenticado completo. Capturas temporárias: `/private/tmp/meta-review-feedback-{width}-{theme}.png`.
- Frontend 8080 e backend 8010 retornam HTTP 200. Autoridade Supabase validada: database.agenciavolc.com.br.
- Claude CLI recebeu trechos de código após autorização explícita, sem ferramentas, MCP ou hooks. Revisão não autoriza mutações. Achados condicionais foram conferidos contra a fonte: ErroDeRegistroDeMidia já herda ErroDeNascimentoMeta; registrador já tem reserva durável/idempotência e reconciliação de resultado incerto. Não foram removidas essas proteções.
- Síntese adversarial, respostas completas e decisões locais: adversarial-blockers/VERDICT.md. Estado CONTESTED; não houve declaração de prontidão produtiva.

## Pendências verdadeiras

- Implementar/verificar liberação de upload vinculada ao rascunho autorizado, proprietário, conta e peças persistidas; a configuração atual permite conta inteira. Não habilitar flag global/por conta como substituto.
- Escolher fonte e evento elegíveis no rascunho, concluir validação e executar o canário PAUSED com confirmação do operador.
- Upload real, vínculo retornado pela Meta, criação/read-back e QA autenticado ponta a ponta não comprovados nesta rodada.

P11-T02 e P11-T05 permanecem partial. Nós: cap_meta_ads e cap_bancada_criativa.
