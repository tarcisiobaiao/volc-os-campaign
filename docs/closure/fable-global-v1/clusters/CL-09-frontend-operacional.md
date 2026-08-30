# CL-09 · Frontend operacional

**Horizonte**: A · **Resultado**: decisão e evidência visíveis no cockpit; a
interface nunca afirma saúde que não mediu.

## Estado factual (F008, F024, F025, F032)

- ~40 rotas; contrato visual canônico aplicado (P01-T09 done com 48
  combinações provadas); baseline tsc = 76.
- Diagnóstico: frontend completo aguardando backend (CL-03).
- Decision Lab L6: superfície provada (44 testes) com 12 lacunas de contrato
  declaradas; selo "SHADOW READ · DADOS REAIS" reservado por contrato.
- Cofre de Ativos: rota implementada, não persiste (P03-T06 partial).
- Órfãos confirmados: CampaignDashboard.tsx, import morto de Index.
- No deploy Vercel, tudo que depende do FastAPI fica inoperante (premissa:
  Horizonte A opera em localhost; deploy do FastAPI é D12).

## Missões

| ID | O quê | Onda |
|---|---|---|
| M-W2-01 | (compartilhada) diagnóstico ganha dados reais na tela existente | 2 |
| M-W2-04 | (compartilhada) contrato L6 fechado → estados explícitos renderizáveis | 2 |
| M-W3-02/03 | (compartilhadas) recibo de lançamento e ledger no cockpit | 3 |
| M-W4-11 | Persistência do Cofre (schema privado + RLS + API adm; recusa payload sensível) | 4 |
| M-W1-09 | (compartilhada) órfãos entram no inventário de candidatos | 1 |

## Regra dura

Estado de ausência renderizado explicitamente; baseline 76 não piora; build
Vite verde; degradação 404/501 continua explícita (padrão do hook de
diagnóstico é o modelo a seguir).
