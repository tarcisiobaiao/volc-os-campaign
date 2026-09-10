# Inspeção de marcas autorizada

08/09/2026. Incremento sobre OFFICIAL-FOLLOWUP.md: a lacuna de detector visual
Meta neste Mac foi atendida. A operação Meta completa continua **partial**.

## Escopo e privacidade

Autorização explícita do usuário para enviar imagens selecionadas ao
`gemini-3.8-flash`, com custo, somente para inspeção de marcas/logotipos.
Implementação no Gemini Developer API existente, sem migração para Vertex.
Chave exclusivamente no header de autenticação do provedor. Payload contém
somente pixels e instrução genérica fixa. Sem código, campos da campanha,
identificadores de proprietário/conta, nomes de arquivo, URLs privadas ou
tokens Meta. Raster recomposto sem EXIF/XMP/texto PNG, com orientação preservada.
Não usa upload Files API, pesquisa web nem ferramentas externas do modelo.

O detector NÃO é registrado globalmente: é injetado apenas na revisão das
peças selecionadas no fluxo Meta, após checar dono, arquivamento e hash.
Listagem de capacidades não envia imagem. Geração do Estúdio, importação e
fluxos Google não herdam saída de pixels. Revisão imediatamente anterior ao
registro da mídia usa o mesmo caminho.

Configuração local em `backend/.env`, ignorada pelo git:
`CRIATIVO_POLICY_GEMINI_VISION_ENABLED=true`. A chave já existente é resolvida
por `Settings.resolved_gemini_key`; nenhum segredo novo foi copiado/versionado.
Default do código é false, exigindo autorização em cada nova instalação.

## Contrato de execução

- Modelo fixo `gemini-3.8-flash`; `thinkingLevel=MEDIUM`; até 4096 tokens de
  saída/raciocínio. Sem fallback, retry automático ou redirecionamento HTTP.
- Exige resposta HTTP 200, modelVersion exato, conclusão STOP e JSON válido.
  Ausência de conclusão, recusa, truncamento e erro nunca viram imagem limpa.
- Imagens PNG/JPEG/WebP estáticas, até 12 MiB e 30 milhões de pixels;
  re-encoding acima do limite é recusado sem rede. Nenhum resize silencioso.
- Cache em memória por hash dos bytes + MIME, no detector versionado, 10 minutos,
  até 128 conclusões. Serialização evita cobrança duplicada por cliques
  concorrentes; falhas não são guardadas. Cache não contém pixels.
- OCR local continua separado de reconhecimento visual. Confiança do modelo
  é heurística não calibrada, não prova de infração ou licença. Suspeitas abaixo
  de 0,70 ficam nos motivos do recibo, sem bloquear; achados fortes seguem o
  portão de direitos existente. Aprovação humana não apaga um achado.

## Provas

Disponibilidade do modelo conferida por GET models/gemini-3.8-flash: HTTP 200.
Três chamadas pagas reais de inspeção, com fixtures sintéticas e sem dados de
cliente; em todas o adapter conferiu o modelo exato e conclusão válida:

| Imagem | Resultado |
| --- | --- |
| Texto neutro “Ideias para hoje” | Nenhuma marca detectada |
| Wordmark “Google” | Google, confiança reportada 0,99 |
| Símbolo de quatro quadrados coloridos, sem texto | Microsoft, confiança reportada 0,99 |

Não equivalem a benchmark de precisão nem inspeção dos packs reais do usuário.
As duas primeiras chamadas retornaram 1327 e 1308 tokens totais; a terceira
não teve medição de uso registrada. Não há valor monetário afirmado.

110 testes passaram, 1 skipped (canário OCR opt-in já exercitado na rodada
anterior). Cobrem saída só de pixels, remoção de metadados, formato/modelo,
respostas inválidas, erros de API, cache/concorrência, isolamento do detector,
escopo de proprietário, aprovação humana e registro de mídia. Testes herméticos
não herdam consentimento pago do `.env`.

Backend local reiniciado em 8010; health ok, nenhum router/rotina ausente,
Supabase configurado. Frontend 8080 HTTP 200. Nenhuma alteração visual nesta
rodada; nenhum aceite visual autenticado afirmado.

## Próximo teste do operador

Reabrir a criação Meta, selecionar o pack no conjunto, conferir imagens e
registrar aprovação. A revisão agora inclui OCR local e Gemini de marcas.
Somente depois, o botão de envio registra mídia na conta; esta inspeção não
cria nem ativa anúncio. Se houver bloqueio, ler o recibo e resolver o achado,
sem trocar erro por liberação.

Nenhuma migration adicional, upload Meta, criação/ativação, geração de imagem,
push ou deploy nesta rodada. OCR macOS ainda exige substituto real para Linux.
P11-T02/P11-T05 e nós cap_meta_ads/cap_bancada_criativa mantêm estado partial
até QA autenticado, envio do pack e canário PAUSED.

Referências consultadas: [imagens](https://ai.google.dev/gemini-api/docs/image-understanding)
e [raciocínio](https://ai.google.dev/gemini-api/docs/thinking). O endpoint
generateContent foi mantido e comprovado por chamadas reais, sem assumir
equivalência automática com os exemplos novos de Interactions.
