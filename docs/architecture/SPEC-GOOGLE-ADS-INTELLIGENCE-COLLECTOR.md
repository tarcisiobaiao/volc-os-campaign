# Coletor contínuo de inteligência Google Ads

**Estado em 29/08/2026:** persistência e primeira coleta real concluídas; agendamento contínuo preparado, ainda não ativado.

## Objetivo

Ler sinais oficiais da Google Ads API de forma recorrente e somente leitura, persistindo cada tentativa no Supabase oficial `database.agenciavolc.com.br`. O contrato não permite que ausência, zero, inelegibilidade e falha virem a mesma coisa.

## Fontes coletadas

| Fonte | Cadência planejada | Escopo |
|---|---:|---|
| `DIAGNOSTICO_ENTREGA` | 4 horas | campanha |
| `RECOMENDACOES_ARMAZENADAS` | 4 horas | conta |
| `SIMULACOES_CAMPANHA` | 4 horas | campanha |
| `EXPERIMENTOS` | 4 horas | conta |
| `RECOMENDACOES_GERADAS` | diária | campanha |
| `FORECAST_KEYWORDS` | diária | campanha |

O modo `frequente` executa as quatro primeiras fontes. O modo `completa` adiciona recomendações geradas e forecast.

## Semântica obrigatória

Uma coleta possui exatamente um destes estados:

- `com_dados`: a API respondeu com um ou mais itens;
- `vazio_confirmado`: a chamada foi válida e retornou nenhum item; `quantidade = 0`;
- `parcial`: houve resposta utilizável, mas incompleta;
- `inelegivel`: o recurso não atende aos pré-requisitos;
- `nao_suportado`: a fonte/canal não é suportada pelo coletor;
- `falhou`: ocorreu erro; exige classe e código sanitizados.

`inelegivel`, `nao_suportado` e `falhou` carregam `quantidade = NULL`. Uma métrica usa contrato separado: `medido` aceita inclusive valor numérico zero; `ausente`, `nao_aplicavel` e `falhou` não aceitam valor numérico.

## Persistência oficial

A migration `v12_01_google_inteligencia_coletas.sql` cria:

- `trafego_google_inteligencia_coleta`: recibo append-only da chamada;
- `trafego_google_inteligencia_item`: itens devolvidos pela fonte;
- `trafego_google_inteligencia_metrica`: valores com unidade e estado semântico;
- RPC atômica e idempotente `volc_registrar_google_inteligencia(jsonb)`.

As tabelas têm RLS habilitada e forçada. `anon` e `authenticated` não possuem acesso. `service_role` possui leitura direta e execução da RPC, mas não `INSERT`, `UPDATE` ou `DELETE` direto. A RPC é `SECURITY DEFINER` com `search_path` fixo.

## Primeira coleta real

Conta: Crédito Up (`8017851692`). Campanhas Search operacionais: Maquininha (`24155134757`) e FGTS (`24156373085`). Coletor versão 3:

| Fonte | Maquininha | FGTS |
|---|---:|---:|
| diagnóstico | `com_dados`, 12 itens | `com_dados`, 83 itens |
| simulações | `vazio_confirmado`, 0 | `vazio_confirmado`, 0 |
| recomendações geradas | `vazio_confirmado`, 0 | `vazio_confirmado`, 0 |
| forecast | `com_dados`, 4 cenários | `com_dados`, 3 cenários |

No nível da conta, recomendações armazenadas e experimentos retornaram `vazio_confirmado`, quantidade zero. A execução v3 fechou 10 recibos e zero falhas.

O postflight read-only após a execução v3 encontrou 78 métricas: 63 `medido` e 15
`ausente`. Entre as medidas, 27 têm valor numérico zero; nenhuma das 15 ausentes
carrega valor. Portanto zero medido e ausência permanecem distinguíveis também
na persistência real, não apenas no modelo Python.

A versão 1 teve três falhas de contrato da API. Elas permanecem no ledger como `falhou` com quantidade nula; não foram apagadas nem reclassificadas como vazio. A versão 2 corrigiu os campos e criou novos recibos idempotentes. A versão 3 separa a identidade do desfecho: uma falha no intervalo não ocupa a chave do sucesso posterior, portanto retries preservam a falha e também registram a recuperação.

## Execução e segurança

Entrada:

```bash
python scripts/coletar_google_inteligencia.py --modo frequente
python scripts/coletar_google_inteligencia.py --modo completo
```

O coletor confere a trava de escrita Google Ads e não contém chamadas `mutate`. O pacote `deploy/google-intelligence/` prepara, como alternativa operacional, um serviço `oneshot` e dois timers systemd:

- frequente: a cada 4 horas;
- completo: diariamente às 06:15 em `America/Sao_Paulo`.

Os timers ainda não estão ativos e não são a arquitetura escolhida. A ingestão atual é orquestrada pelo n8n; antes de qualquer instalação, os workflows D0/D-1 devem ser confrontados com o coletor v3 e adaptados para chamar a fronteira/RPC v12, ou uma ADR deve justificar a troca pelo worker. Só uma agenda pode permanecer ativa. Se o worker for escolhido, a instalação exige copiar `/Users/mac/google-ads.yaml` para `/opt/volc-google-intelligence/google-ads.yaml` no servidor oficial, com modo `600`, e ativar units como root, mediante autorização explícita.

## Critério de pronto

- uma única autoridade de agenda ativa, sem sobreposição entre n8n e systemd;
- heartbeat/recibo por execução;
- alerta quando a cadência atrasar ou uma fonte falhar;
- primeira janela automática reconciliada no Supabase;
- QG/cockpit mostra fonte, janela, frescor e estado semântico;
- recomendações oficiais continuam sendo evidência, nunca autorização de mudança;
- zero mutação Google Ads nesta rotina.
