# Contexto revisável da landing page no Assistente Meta

Status: implementado; testes locais, sem nova migration.

## Contexto

O briefing manual perdia o conteúdo real da página. O leitor de publisher
quality existente valida endereços públicos, mas seu transporte urllib resolve
novamente o hostname depois da validação. Esse padrão não prova resistência a
DNS rebinding para uma URL arbitrária enviada pelo usuário.

## Decisão

`POST /api/criativos/meta/agente/contexto-pagina` exige a sessão do operador,
lê uma URL pública HTTPS e retorna `creative_lp_context.v1`. Usa o predicado
de IP público existente, mas fixa o IP aprovado na conexão TCP e verifica TLS
contra o hostname original. Revalida cada redirect, rejeita respostas DNS
mistas, credenciais na URL, portas não padrão, hosts locais e IPs reservados.
Não envia cookies/tokens, não herda proxies, não executa JS nem subrequests.
Limites: três redirects, 1 MB, 24 mil caracteres úteis, janela de leitura de
15 segundos e deadline assíncrono de 16 segundos; sugestão do modelo até 35s.
Um DNS bloqueado pelo resolver do sistema pode durar além do deadline da API
na thread; ao retornar, o worker verifica deadline antes de abrir conexão.

O HTML é dado não confiável, separado das instruções do agente. Scripts,
navegação, elementos ocultos por atributo/inline style e linhas com tentativas
explícitas de instrução são descartados. Isto não substitui isolamento do
modelo: a chamada não recebe ferramentas nem segredos. Texto oculto por CSS
externo não pode ser identificado sem browser, e não se promete renderização
equivalente à página visual.

O modelo seleciona índices de trechos extraídos: não escreve as declarações
fatuais. Cada `declaracao` retornada é literalmente seu `trecho`, com URL de
origem. Ainda assim, prova apenas o que a página declara, não a veracidade.
Assunto, proposta, público, momento e ângulos são sugestões para revisão, nunca
certificado de política. Falha do modelo conserva trechos e avisa que a
inferência não foi produzida; sem texto legível, permite preenchimento manual.

O frontend aplica sugestões por ação explícita. Campos finais revisados
continuam em `fatos_da_oferta`/`contexto_do_publico`; o snapshot analisado não
sobrescreve essas decisões. `url_destino` e `contexto_da_pagina` viajam no
`input` JSONB já existente da operação e da run. O contrato exige que o
snapshot pertença à URL escolhida. Não há DDL nem alteração de RLS. Snapshots
enviados pelo cliente são contexto revisável, não autoridade de aprovação.

## Provas e limites

- Testes: `backend/tests/test_criativo_contexto_pagina.py` cobre SSRF,
  IP fixado/SNI, redirects, conteúdo/tamanho, extração, erros, autenticação,
  persistência simulada e retomada pelo endpoint da operação.
- Leitura pública real de `https://apps.technewsbrasil.com.br/` concluída:
  título “TechNews Brasil - Tecnologia na palma da sua mão”, 37 trechos.
- Persistência aqui testada com repositório dublê; integração com o banco
  oficial deve ser registrada pelo integrador. Nenhuma chamada paga nesta prova.

## Referências

- [OWASP SSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- [Python HTTP client e TLS](https://docs.python.org/3/library/http.client.html)
