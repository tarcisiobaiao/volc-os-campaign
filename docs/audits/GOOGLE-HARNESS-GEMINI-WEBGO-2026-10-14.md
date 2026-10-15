# Call Webgo → melhorias do engine e prova real Gemini/Google

14/10/2026. Base inspecionada: main `fb446595`, checkout oficial
`volc-os-campaign-qg-real-20261007`. Um escritor, sem branch/worktree nova.
O checkout histórico e o canário não versionado do FunnelForge foram preservados.

## Veredito

Há um avanço técnico real, delimitado: Gemini planejou Search usando uma LP
pública e quatro keywords já existentes; o builder canônico montou três grupos,
com RSA próprio por grupo. Após quatro ajustes locais explícitos da copy, a
API v25 aceitou 30 operações em validate_only. Nada foi criado ou ativado.

Não ficou demonstrada operação autônoma sem revisão, ROI, serving, aprovação
de política ou o fluxo HTTP autenticado de criação. Meta e os outros canais
não receberam inferência nem validate_only novos nesta rodada.

## 1. O ouro da conversa e como usar

Fonte local: `Downloads/Webgo - Sistema, upgrades e funções.txt`, reunião
de 14/10, 32 minutos. Transcrição automática: termos ambíguos não viraram
requisitos. Foi usada como relato de operação, não como documentação da API.
Não acessamos o link Tactiq nela nem enviamos o trecho pessoal ao Gemini.

| Trecho | Insight aproveitável | Aplicação e cuidado |
|---|---|---|
| 02:14–06:55 | Comparar modelos de funil pela proporção de campanhas lucrativas, não só pelo campeão visível | Coortes por versão/modelo + janela + total de campanhas elegíveis + gasto + receita reconciliada. Mostrar tamanho de amostra; não inventar limiar de vencedor nem confundir prefixo de URL com versão formal. Não implementado neste delta. |
| 07:47–10:29 | Grupos e hipóteses de audiência podem oferecer mais controle do que multiplicar campanhas | Experimento, não regra universal de escala. Search usa ad group, Meta ad set, PMax asset group; não são objetos intercambiáveis. Neste delta: RSA opcional específico por grupo Search. |
| 11:30–13:00 e 23:28 | Anúncio caro pode ser o mais rentável; enxergar campanha/grupo/anúncio | CPC isolado não decide corte. Receita por anúncio só existe com atribuição comprovada nesse nível. Não dividir receita agregada proporcionalmente ao gasto e chamar isso de observação. |
| 11:30–13:00 | CPA de referência e exceção por grupo, com histórico | A API permite override de tCPA só nas estratégias compatíveis. Não ativar essa ideia numa campanha manual ou copiar suporte entre canais. Sem mudança de lances nesta rodada. |
| 14:06–18:40 | Visibilidade/exclusão de placements e YouTube poupa trabalho operacional | Reaproveitar coleta/gestão existentes e conferir suporte e escopo por canal. Nenhuma exclusão automática nem promessa de mesmo comportamento em Display, Demand Gen e PMax. |
| 19:44–23:28 | Tipo da campanha, filtro e responsável devem ficar visíveis | Quick win de cockpit futuro. Operador atribuído manualmente não comprova quem criou a campanha. Nenhuma inferência retroativa de autoria. |

A fala sobre fim do Display em abril não foi verificada e não orientou código
ou migração. Duplicar 9–17 campanhas também não virou automação nem recomendação
de gasto. Não extraí percentuais de ROI da fala truncada.

O suporte a tCPA por grupo foi confrontado com a [documentação oficial de
override](https://developers.google.com/google-ads/api/docs/campaigns/bidding/override-strategies).
Separação de estratégia, criatividade e receita é mais útil aqui do que um
LLM recebendo liberdade para mexer em dinheiro.

## 2. Stack adotado — só o delta necessário

- SDK Google Ads já instalado: 33.0.0, API v25 preservada.
- SDK nativo `google-genai==2.31.0`: schema JSON e chamada Gemini.
- Pydantic já existente: contrato de proposta, sem decisões financeiras.
- `hypothesis==6.169.2`: propriedades de partição e preservação de valores.
- Builders, classificador de erros e cliente Google atuais reutilizados.
- Sem ADK/agentes novos, JEV, nova base, fila, scheduler ou executor paralelo.

A pesquisa de bibliotecas anterior está em
`.claude-ads/runs/google-engine-research-20261014-01/RELATORIO.md`.
A [documentação Gemini de structured output](https://ai.google.dev/gemini-api/docs/structured-output)
sustenta o uso de JSON Schema; isso organiza forma, não garante veracidade
nem aprovação de anúncios.

Instalação no venv de desenvolvimento compartilhado: SDK Gemini/Hypothesis e
dependências transitivas. `websockets` passou de 17.0.1 para 16.1.1 pelo limite
do SDK. `pip check` passou. O runtime Vercel não ganhou esses requisitos;
`backend/requirements-dev.txt` inclui a dependência de desenvolvimento para
que a suíte nova seja reproduzível. A chave foi carregada em memória pelo
adapter existente, nunca exibida ou salva nos artefatos.

## 3. Prova real e os dois defeitos encontrados

1. `models.list` real confirmou a chave e o acesso a gemini-3.8-flash. O default
   do projeto continua gemini-3.5-flash; só o harness escolheu 3.8 explicitamente.
2. Captura somente leitura: LP Senac pública HTTP 200, 5.497 caracteres
   extraídos e quatro keywords ENABLED. Não é novo conjunto pago aprovado.
3. Tentativa 1: HTTP 400 antes da geração. `response_schema=Proposta` fez o SDK
   serializar `additional_properties` no Schema protobuf que o endpoint recusou.
   Corrigido para `response_json_schema=Proposta.model_json_schema()`.
4. Tentativa 2: Gemini solicitado e servido `gemini-3.8-flash`, finish STOP,
   6,126 s, 2.022 tokens de entrada + 653 de saída = 2.675.
5. A proposta agrupou acesso geral (duas keywords), requisitos (uma), e estado
   (uma). Um texto tinha 91 caracteres. A revisão local retirou só “gerais”
   nessa descrição; outras três trocas removeram “27 estados” (são 26 + DF).
   Não se alteraram keywords, organização, URL, lances ou orçamento.
6. O schema passou a declarar maxLength de 30/90/25, sem truncamento automático.
   O output original permanece intacto. O roteiro de revisão é específico deste
   run, não um corretor semântico automático do engine. Não houve terceira chamada.
7. Proposta revisada → builder atual → **30 operações aceitas pelo Google**,
   três grupos/quatro keywords. Request ID real no recibo. Validação + releitura:
   4,869 s. Payload SHA-256:
   `bc30916ac788257c8c15f4c35faa69334ab7b7f05eb1dd61a11a613897054b71`.
8. Campanhas/anúncios/status/orçamentos/estratégias relidos sem mudança. Não
   houve mutação persistente, /subir, destrava financeira, Supabase, migration,
   publicação, deploy ou chamada Meta. A comparação não cobre toda configuração
   possível da conta nem exclui mudanças concorrentes fora desse recorte.

Limites técnicos do canário: R$ 20/dia e CPC R$ 0,60 são valores de entrada
da prova, NÃO mudança na campanha ativa nem recomendação de lance. Nenhum CPC
estimado de SERP/DataForSEO/Keyword Planner participou de uma decisão financeira.
Gemini foi chamado por API; o provedor não informou custo monetário. Custo fica
null, não “US$ 0”. Duas tentativas HTTP, uma geração aproveitável.

## 4. Código e testes

- `SubIntencao.rsa: CopyRSA | None` + builder Search: valida e emite o texto
  do próprio grupo. Ausência conserva o payload/copy antigos.
- Cliente Google: captura request-id da RPC validate_only quando solicitado,
  sem registrar headers/credenciais nem alterar o executor de escrita.
- `volc_ads/harness/`: contrato, snapshot público, Gemini, builder e recibos.
  Teto de duas gerações, lock por run, gravação antes do gasto, resposta antes
  de parse e retomada de recibo completo sem nova chamada com hashes conferidos.
- Propriedades: keywords sem inventar/duplicar/omitir; orçamento/CPC chegam
  intactos ao protobuf; proposta não aceita campos financeiros/negativas.
- Contraprovas: saída incompleta/modelo divergente não chega ao Google; queda
  não retenta às cegas; artefato adulterado não é reutilizado; corpo HTTP do SDK
  contém responseJsonSchema, não o additional_properties inválido.

Provas: 488 testes no recorte de canais/harness/backend crítico passaram;
depois a suíte Ads inteira passou com **1.570 testes, zero falhas/pulos,
26 avisos, 12,62 s**, com socket de rede bloqueado. Os JUnits distinguem os
recortes; não somar as contagens, pois há sobreposição. Não é a suíte inteira
do VOLC nem teste de UI. O recorte backend tem avisos de depreciação herdados.

A suíte ampliada revelou que um teste antigo de independência de CPC tentava
renovar OAuth real. A primeira execução parou nesse ponto (1.568 passaram,
um falhou); corrigi o isolamento desse teste, sem alterar sua asserção de
payload invariável. A repetição offline passou inteira. Isso não foi registrado
como falha da API nem exigiu outra inferência.

## 5. O que falta para o negócio

- Integrar proposta assistida ao percurso HTTP autenticado e ao conjunto pago
  aprovado, sem bypass do selo, destino, ledger ou executor. Este delta é
  CLI/importável, não botão novo no cockpit.
- Atribuir custo/receita no mesmo nível antes de usar lucro de grupo/anúncio.
- Ensaiar um experimento por hipótese e medir; não promover duplicação a regra.
- Validar criativos/dados reais dos outros canais e Meta em rodadas próprias.
- Sitelinks ainda usam a URL única do builder; validate_only não provou serving
  nem navegação por destinos distintos. Não ampliar promessa do recurso.

P05-T10 permanece partial. Nó cap_search_birth recebe a evidência técnica,
sem promoção de estado. O motor não foi declarado “antierro” ou financeiramente
autônomo. A próxima entrega útil é fechar a integração do cockpit existente,
não instalar mais bibliotecas.

## Artefatos

`.claude-ads/runs/google-harness-20261014-01/`:

- manifest.json, tests.xml;
- canary/input.json, keywords-source.json, landing-source.json;
- canary/snapshot-before.json e snapshot-after.json;
- canary/proof/: journal, falha inicial, diagnóstico, resposta Gemini original;
- canary/reviewed/: proposta, quatro ajustes, payload e receipt.json;
- validar_revisao_local.py: roteiro reproduzível e sem nova inferência.

Não foi copiada a conversa pessoal nem a chave Gemini para esses arquivos.
