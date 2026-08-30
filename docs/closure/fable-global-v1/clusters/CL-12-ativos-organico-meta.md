# CL-12 · Ativos, orgânico e Meta (Horizonte B)

**Resultado**: Cofre com ativos reais e referências seguras; um piloto orgânico
real; Meta Ads nascendo como vertical do Hub.

## Estado factual (F039)

- Cofre: contrato público v1 estrito done; tela sem persistência; página
  Facebook monetizada não inventariada; broker 1Password↔AdsPower é ADR
  aceito sem implementação (P03-T09/T10/T11 todo).
- Orgânico: Postiz escolhido (ADR 28/08), não implantado; nenhuma peça real
  percorreu publicação; MultiPost reservado a fallback.
- Meta: contrato de briefing parcial (Estúdio integrado ajuda); system user,
  criação segura e página canônica todo.
- Engines de imagem/vídeo catalogadas (P03-T04 done) e externas ao runtime.

## Ordem de saída do estacionamento (sem datas; por pré-requisito)

1. M-W4-11 (CL-09): persistência do Cofre — pré-requisito de P03-T02/T07/T10.
2. Onboard da página real no Cofre (P12-T02) — ação humana + registro.
3. Smoke 1Password MCP local (P03-T09) → broker AdsPower (P03-T11).
4. Postiz self-hosted isolado (P12-T08) → porta VOLC de publicação (P12-T09).
5. Piloto orgânico de uma semana (P12-T03/T12) com QA visual AdsPower.
6. Meta: briefing por jornada (P11-T02) → system user (P11-T03) → criação
   segura (P11-T05), sempre reutilizando o chassi de prova do Search.

## Regra dura

Nenhum segredo bruto no Cofre/grafo/API (contrato já recusa); publicação só
com recibo de URL/versão/horário; nada aqui entra no caminho crítico do
Horizonte A.
