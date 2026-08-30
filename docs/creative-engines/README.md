# Inventário dos motores criativos VOLC

Este diretório transforma os motores criativos que vivem fora do VOLC O.S. em patrimônio localizável, comparável e integrável. Ele não copia os projetos nem afirma que já estão conectados ao produto.

## Fonte humana e fonte para agentes

- `INVENTARIO-MOTORES-DE-IMAGEM.md`: leitura humana, decisões e ordem de integração.
- `motores-de-imagem.json`: manifesto estruturado para agentes, QG, Workbook e grafo.
- `CATALOGO-PRENSA-E-MOTOR-IMAGEM.md`: catálogo detalhado das famílias, skins, gates e modos com e sem imagem generativa.
- `PACOTE-REUSO-MOTOR-IMAGEM.json`: mapa estruturado de extração por módulo e critérios de aceite.
- `snapshots/motor-imagem-2026-08-26.json`: fotografia reproduzível, hasheada e somente leitura do parque externo.
- `ADR-001-SERVICO-CRIATIVO-VOLC.md`: decisão sobre extração, microserviço e os seis modos criativos.
- `CATALOGO-MOTOR-DE-VIDEO.md`: leitura humana dos 17 formatos, 15 skins, providers, gates e provas de execução do vídeo.
- `motores-de-video.json`: manifesto estruturado do Motor de Vídeo.
- `PACOTE-REUSO-MOTOR-VIDEO.json`: módulos a extrair, alvo e critérios de aceite.
- `snapshots/motor-video-2026-08-26.json`: fotografia reproduzível do código organizado e dos renders da fábrica externa.
- `ADR-002-INTEGRACAO-MOTOR-VIDEO.md`: decisão de adapter + runtime separável, começando pelo envelope 9:16 comprovado.

Os projetos externos continuam sendo a autoridade do código que executam. Este diretório é a autoridade do **inventário**: qual projeto vale, o que foi observado, qual prova existe e o que ainda falta.

## Regra de atualização

Quando um motor mudar materialmente, atualizar primeiro o manifesto estruturado e a evidência factual deste inventário. Depois, atualizar `docs/volc-os-graph/curadoria-operacional.json` e reconstruir o Mapa Vivo.

Nunca guardar chaves, tokens, imagens privadas ou conteúdo de `.env` neste inventário.

O snapshot do Motor de Imagem é refeito com:

```bash
python3 scripts/inventariar_motor_imagem.py \
  --output docs/creative-engines/snapshots/motor-imagem-2026-08-26.json
```

O snapshot do Motor de Vídeo é refeito com:

```bash
python3 scripts/inventariar_motor_video.py \
  --output docs/creative-engines/snapshots/motor-video-2026-08-26.json
```
