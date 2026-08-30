# ADR-002 — Integrar o Motor de Vídeo por adapter e runtime separável

**Status:** aceita como direção arquitetural · implementação pendente  
**Data:** 26/08/2026

## Contexto

O parque auditado possui contrato, 15 skins, 17 formatos e 38 MP4s finais na
fábrica externa. A raiz organizada, porém, não contém o workspace completo de
execução e ainda referencia caminhos e ferramentas da máquina do autor. O VOLC
O.S. já possui a porta interna `MotorDeCriativo`, mas nenhum adapter de vídeo.

## Decisão

Preservar o Motor de Vídeo como patrimônio próprio e extrair um runtime
separável, chamado pelo backend por uma implementação da porta
`MotorDeCriativo` para `VIDEO`.

O primeiro corte não move a fábrica inteira e não tenta atender Google, Meta e
orgânico ao mesmo tempo. Ele torna uma vertical 1080×1920 reproduzível,
idempotente e auditável, porque esse é o envelope comprovado pelos renders.

O runtime deverá:

- receber um `CreativeJob` versionado;
- resolver contrato, skin, voz, idioma, hook e destino;
- trabalhar em diretório isolado por job;
- emitir progresso e permitir cancelamento;
- persistir MP4, props, timings, ledger e relatórios;
- falhar fechado nos gates;
- nunca publicar nem mutar plataforma por conta própria.

## Separação obrigatória

`skin` responde como contar e apresentar. `destination_pack` responde o que a
plataforma aceita. Uma skin não deve codificar tamanho, peso ou política de um
canal publicitário.

## Alternativas rejeitadas

### Copiar `/Users/mac/volc-factory` para o backend

Rejeitada: preserva paths locais, dependências implícitas, arquivos de trabalho
e responsabilidades demais dentro da API principal.

### Chamar scripts externos diretamente pelo Hub

Rejeitada: o navegador não deve conhecer path, chave, provider nem processo de
render.

### Reescrever o motor do zero

Rejeitada: perderia contrato, skins, provas, regras de licenciamento e gates já
desenvolvidos.

### Começar pelos cinco destinos publicitários

Rejeitada: a evidência atual cobre 9:16 orgânico. Adaptar tudo antes de provar o
runtime recriaria o overengineering que o inventário busca evitar.

## Consequências

O motor continua evoluindo sem acoplar o Hub ao filesystem. O custo é uma etapa
de portabilidade, containerização e paridade antes de haver botão funcional no
produto. Google e Meta passam a consumir o mesmo ativo, mas cada um recebe seu
próprio pacote de destino e aprovação.
