# ADR — Distribuição orgânica e prova visual publicada

**Data:** 28/08/2026
**Estado:** decisão aceita; implementação pendente

## Resultado

O VOLC O.S. continuará sendo a autoridade sobre pauta, peça, aprovação, ativo, versão, destino e aprendizado. Ferramentas externas executarão partes delimitadas do fluxo:

1. **Postiz será o núcleo oficial de calendário e publicação multicanal.** Ele ficará isolado como serviço e será acessado por uma porta VOLC, sem transformar o banco ou a interface do Postiz em fonte de verdade do produto.
2. **MultiPost será um fallback experimental.** A extensão pode cobrir destinos sem integração estável no Postiz, mas publicação por sessão de navegador não será o caminho principal nem a autoridade de recibo.
3. **AdsPower MCP será o executor isolado de navegação e QA visual pós-publicação.** Ele abre o perfil correto, visita a URL publicada, coleta evidência e devolve o resultado ao portão do Redator. Não é cofre de credenciais, scheduler editorial ou prova automática de que a página está correta.
4. **Blotato deixa de ser o candidato principal.** Permanece apenas como referência histórica até existir razão factual para reabrir a comparação.

## Por que essa divisão

### Postiz

O projeto oferece instalação self-hosted, API pública, OAuth2, SDK, CLI e integração n8n. O contrato de criação distingue `draft`, `schedule` e `now`, aceita posts específicos por integração e devolve IDs de publicação. Isso se encaixa no fluxo VOLC de produzir, aprovar, agendar, publicar e reconciliar.

O repositório usa **AGPL-3.0**. Por isso o VOLC não deve copiar partes internas para dentro do core sem revisão de licença. A integração preferida é por processo e API, com o Postiz operando como serviço separável. Esta nota não substitui aconselhamento jurídico.

### MultiPost

O projeto é uma extensão de navegador Apache-2.0 que publica texto, imagem e vídeo em mais de dez plataformas usando sessões já autenticadas. Também declara API da extensão e API REST. É útil quando uma rede não possui API disponível, quando a integração oficial está bloqueada ou num piloto assistido.

O preço dessa cobertura é depender do navegador, do DOM e da sessão ativa. Isso torna a solução mais frágil para agendamento, idempotência, reconciliação e operação autônoma. Por isso ela fica fora do caminho principal.

### AdsPower MCP

O projeto oficial atual oferece skill, CLI e servidor MCP para a Local API, com suporte a Claude, Codex e Cursor. O cliente pode rodar headless e o MCP usa a porta local, normalmente `50325`, com API key. A versão do cliente limita quais endpoints estão disponíveis.

O artigo antigo sugere desabilitar a verificação da API. O projeto oficial atual já aceita `API_KEY`; a implementação VOLC deve manter autenticação ligada, restringir o listener à máquina ou rede autorizada e nunca registrar a chave no grafo, no Roadmap ou nos recibos.

## Fluxo pretendido

```text
Pauta VOLC
  → job criativo versionado
  → aprovação humana
  → PublicationGateway VOLC
  → Postiz draft/schedule/now
  → recibo inicial
  → URL publicada reconciliada
  → AdsPower abre o perfil isolado correto
  → inspeção de DOM + screenshot + análise visual
  → aprovado | corrigir | indeterminado
  → métricas e aprendizado retornam ao VOLC
```

O MultiPost entra apenas como rota alternativa explícita:

```text
PublicationGateway
  → destino sem adapter confiável
  → proposta MultiPost
  → confirmação humana
  → publicação browser-assisted
  → mesma reconciliação e QA visual
```

## Contratos que precisam existir

### PublicationJob

- `job_id` e chave de idempotência;
- ativo e canal de destino;
- conteúdo e assets por plataforma;
- versão e linhagem dos arquivos;
- estado de aprovação;
- estratégia `draft`, `schedule` ou `now`;
- horário e timezone;
- executor escolhido e motivo;
- tentativas, resposta sanitizada e recibo;
- URL e ID externos reconciliados.

### VisualProofJob

- `publication_job_id`;
- referência do perfil AdsPower no Cofre, nunca cookies ou senha;
- URL esperada e URL efetivamente aberta;
- viewport, horário e versão do navegador;
- screenshot e hash;
- verificações de carregamento, console, HTTP e layout;
- regras específicas para Gutenberg, slots de anúncio, clipping, sobreposição e conteúdo ausente;
- resultado `aprovado`, `corrigir` ou `indeterminado`;
- observações e aprovação humana quando necessária.

## Guardas

- Nenhuma ferramenta externa decide a pauta ou altera o ativo sem contrato VOLC.
- Publicação e QA são jobs diferentes: screenshot não é recibo de publicação.
- Falha do AdsPower não transforma a página em reprovada; o resultado é indeterminado.
- MultiPost nunca mascara a ausência de adapter oficial.
- Postiz não recebe a `service_role` do Supabase.
- AdsPower não expõe Local API sem API key e restrição de rede.
- Perfil de navegador entra no Cofre como referência operacional, sem segredo bruto.
- Toda ação externa precisa de owner, horário, idempotência e recibo.

## Piloto de aceite

O primeiro piloto usa uma única página real e uma única vertical:

1. cadastrar página e perfil AdsPower no Cofre;
2. produzir e aprovar uma peça;
3. criar draft no Postiz;
4. promover o draft para publicação aprovada;
5. reconciliar ID, URL, versão e horário;
6. abrir a URL no AdsPower;
7. gerar screenshot e verificações sanitizadas;
8. registrar decisão humana;
9. colher as primeiras métricas;
10. decidir manter, corrigir ou interromper.

## Fontes oficiais consultadas

- AdsPower Local API MCP: https://github.com/AdsPower/adspower-browser
- Artigo AdsPower MCP: https://www.adspower.com/pt/blog/adspower-local-api-mcp-server
- Postiz: https://github.com/gitroomhq/postiz-app
- API Postiz: https://docs.postiz.com/public-api/introduction
- Criação de posts Postiz: https://docs.postiz.com/public-api/posts/create
- MultiPost: https://github.com/leaperone/MultiPost-Extension
- Site MultiPost: https://multipost.app/
