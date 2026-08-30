# CL-05 · Decisão e ORAKUL (fato → recomendação → autorização → ação)

**Horizonte**: A (contrato) / B (autonomia) · **Resultado**: toda ação sensível
tem proposta, antes/depois, autorização humana, idempotência, rollback e
verificação — e o kernel ORAKUL é extraído como política pura versionada.

## Estado factual (F009, F022, F017)

- Kernel decisório na main (844+1627 linhas, 171 testes coletados), 100%
  sintético; replay dourado 8/8; fronteira raw hermética com 134 contraprovas.
- v10 não aplicada; writer inexistente; aprovação sem caller (ver CL-02).
- ORAKUL/BEAST histórico: 1.678 linhas Python com maturidade/histerese/pisos
  ainda misturadas a I/O (P09-T08 todo); constantes não publicáveis.
- Webhook de mutação legado ATIVO sem autenticação (D10) — a porta única ainda
  tem um buraco vivo.
- Decision Lab L6 declarou 12 lacunas de contrato em vez de improvisar.

## Missões

| ID | O quê | Onda | Portão |
|---|---|---|---|
| M-W2-04 | Fechar as 12 lacunas de contrato do L6 no backend (ainda sintético, estados explícitos) | 2 | nenhum |
| M-W2-05 | (compartilhada) Inventário executável de superfícies privilegiadas incl. webhook | 2 | leitura |
| M-W3-09 | Kernel ORAKUL extraído: fatos→features→políticas→árbitro→proposta puro, golden replay | 3 | após integração |
| M-W3-10 | Shadow com dado real: GoogleAdsRow real atravessa a fronteira, janela declarada | 3 | **D2** (coleta ativa) |
| M-W4+ | Budget-ROI Allocator (P09-T10..13) — replay offline primeiro | 4 | specs prontas |

## Regra dura

Nenhum T2/autonomia sem ADR próprio; propostas nunca parecem execução;
divergências de replay explicadas, não suavizadas.
