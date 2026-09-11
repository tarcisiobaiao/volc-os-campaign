# Fila de refino Meta — converter evidência em implementação

`EXECUTION.md` é o prompt mestre; `tasks.py` é a fila **executável**. Esta página
define o roteiro das próximas missões. Roteiro não significa feature implementada.
Nenhum ticket novo é disparado só porque outra run terminou.

## Despacho do lead

Para cada área abaixo, consultar o grafo, o código operacional e testes. Selecionar
um comportamento ausente reproduzível, não uma suspeita do modelo. Registrar:

```text
TÍTULO: ação do operador que ficará melhor
ANTES: path:linha + comportamento observado + caso que falha
DEPOIS: comportamento exato para sucesso, vazio, erro e concorrência
CONTRATO: estrutura que permanece; mudança necessária e fonte oficial
ESCOPO: até quatro arquivos de implementação/teste, sem sobreposição entre tickets
PROVA: teste obrigatório e critérios de revisão; browser quando alterar layout
EXCLUÍDO: efeitos externos, mudanças de identidade/permissão e decisões humanas
```

O lead insere um `Ticket`, reduz o contexto a trechos relevantes (limite do preload),
e aprova os arquivos. Não atribuir “leia todo Meta e melhore tudo” a um executor.

## 1. Jornada e experiência

Prompt de investigação: siga conta→Página→destino→mensuração→conjuntos→anúncios→revisão.
Conte ações evitáveis e localize cargas que poderiam ser automáticas. Verifique
retomada/CAS, loading/erro/retry, seleções por conjunto e desativação de respostas
antigas. Não remova a aprovação final nem a decisão sobre categoria especial.
Entregue um caso reproduzível e arquivo/teste; se o comportamento já existir, cite-o.

## 2. Criativos, packs e copy

Prompt de investigação: siga LP/contexto→briefing→spec→imagem→pack→conjunto→anúncio.
Procure perda de contexto, preview, edição ou seleção. Confira variações por tipo,
limites já versionados e modo flexível elegível. Preserve post_id quando o contrato
de reuso o permite; não transforme imagem em social proof. Qualidade de imagem/CTR
exige prova visual/experimento, não passa por testes de string.

Tickets despachados nesta rodada: `copy_retry`, `flexible_focus`.

## 3. API e criação PAUSED

Prompt de investigação: confronte compilador, executor, ledger e readback com a
documentação oficial da versão usada. Reproduza uma falha parcial em transporte
dublê e confira reconciliação sem duplicar campanha/conjunto/anúncio. Validação
local não prova aceite remoto. Antes de propor campo novo, prove identidade, origem,
objetivo e elegibilidade; não confunda instagram_user_id com instagram_actor_id.
Não modifique payload por snippet de busca. Encontre o chamador que preenche o campo.

## 4. Mensuração e operação

Prompt de investigação: com fixtures de campanha/conjunto/anúncio, prove Meta
utm_campaign=adset_id e soma da receita GAM ao pai. Procure duplicação por joins,
paginação parcial, NULL virando zero, filtro de período ou moeda. A view por anúncio
nunca recebe rateio inventado. Webhook é sinal para revisão, não autorização para
pausar, ativar ou trocar criativo automaticamente.

## Integração e parada

Cada candidato precisa de teste pós-edição, crítica e revisão do lead. O lead aplica
o patch no ramo operacional, roda regressões ampliadas e registra o estado no
roadmap/grafo. Teste hermético, browser local, Supabase vivo e aceite remoto são
camadas distintas. Migrations ficam como proposta até backup/validação específicos.
Uma rodada sem patch útil ou com orçamento exaurido vira pendência, não “done”.
