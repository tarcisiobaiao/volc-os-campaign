# VOLC Agent Gateway: catálogo de capacidades (V1)

Fonte: `backend/app/agente_bia/gateway/`. Publicado em `GET /api/agent/tools`.

| Capacidade | Efeito | Papel | Quem invoca | Estado |
|---|---|---|---|---|
| `volc_get_campaign_context` | leitura | ADMIN | o backend, em nome do usuário autenticado | implementada, prova hermética |
| (registrar proposta) | escrita de intenção | ADMIN | — | **não existe**: o catálogo recusa efeito diferente de `leitura` |
| (mutações: verba, lance, status, GTM, WordPress) | mutação | — | — | **proibidas na V1**; só o execution plane futuro, com aprovação |

## Regras do catálogo

1. Só registra capacidade com `efeito="leitura"` e entrada com `extra="forbid"`. Qualquer outra coisa levanta `CapacidadeProibida` no registro.
2. O papel é conferido no servidor antes de validar a entrada: um 403 não ensina o schema.
3. A saída é revalidada pelo modelo de saída antes de sair.
4. Nenhuma entrada aceita SQL, nome de tabela, URL, tenant ou dono. Nenhuma capacidade chama URL arbitrária ou o Google Ads.
5. O Hermes **não** recebe a capacidade como ferramenta na V1. O backend a invoca e manda o resultado como bloco de **dado** delimitado e marcado como não confiável.

## `volc_get_campaign_context`

### Entrada (estrita)

| Campo | Tipo | Regra |
|---|---|---|
| `campaign_ref` | string | `volc_campaign_id`, a identidade interna; regex `^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$`. O id externo cru não é aceito. |
| `janela` | enum | `ultimos_7_dias` (padrão), `ultimos_14_dias` ou `ultimos_30_dias`: dias fechados até ontem em America/Sao_Paulo. Data livre não é aceita. |

### Saída (estrita, todos os campos obrigatórios)

| Campo | Conteúdo | Origem canônica |
|---|---|---|
| `identificacao` | `campaign_ref_mascarado`, `nome` (cortado em 120, sem controle), `plataforma`, `conta_mascarada`, `id_externo_mascarado` (`••••1234`) | `FonteDeReconciliacao.uma_campanha` + `inventario.campanha_projetada`, a mesma leitura de `GET /api/trafego/campanhas/{id}` |
| `situacao` | `canal`, `estado_externo`, `veiculacao` | idem |
| `janela` | `nome`, `inicio`, `fim`, `dias` | `custo_canonico.periodo_padrao` |
| `custo` | `valor` (só quando **todo** dia está fechado), `valor_coberto`, `verdade` (real, parcial ou indisponivel), `unidade` com a moeda | `custo_canonico.montar_custo` sobre `google_ads_campanha_dia` filtrado pela campanha, com o ledger lido **antes** do fato |
| `conversoes_oficiais` | mesma régua do custo: total só com todos os dias fechados | coluna `conversoes` (Google `metrics.conversions`, ações primárias) do mesmo fato |
| `receita` | **sempre** `{valor: null, estado: "nao_reconciliada", motivo}` | não há serviço aplicado que reconcilie receita por campanha (v17_04 não aplicada) |
| `lucro` | **sempre** `{valor: null, estado: "nao_calculado", motivo}` | falta receita reconciliada; a granularidade válida é a coorte (ADR-CICLO-ECONOMICO) |
| `frescor` | **obrigatório**: `avaliado_em`, `estado` (fresco, defasado ou desconhecido), `snapshot_inventario`, `fato_ultima_colhida_em`, `fato_ultimo_fechamento_em`, `fato_idade_horas` | `inventario.frescor_da_conta` + `montar_custo` |
| `cobertura` | `dias_total`, `dias_fechados`, `dias_por_estado` | `custo_canonico.cobertura` |
| `fontes` | lista fixa das três fontes | — |
| `limitacoes` | lista fixa: receita, lucro, natureza das conversões, alertas parciais | — |
| `alertas` | derivados desta leitura: snapshot não recente, custo parcial ou indisponível, motivos do custo, frescor desconhecido | — |

### Garantias provadas

- campo extra, janela livre, URL, SQL ou id malformado dão 422, sem nenhuma leitura de fonte (`test_ferramenta_rejeita_parametro_extra_e_janela_livre`);
- OPERATOR recebe 403 sem leitura (`test_ferramenta_exige_admin_no_servidor`);
- a ordem de leitura é snapshot → ledger → fato (`FonteDeContextoFalsa` levanta se o fato vier antes do ledger);
- janela fechada mostra total; janela parcial deixa `valor` nulo e preenche só `valor_coberto` (`test_contexto_parcial_nao_inventa_total`);
- frescor ausente torna a saída inválida pelo schema (`test_frescor_e_obrigatorio_*`);
- receita e lucro são sempre nulos com motivo.

### Limitações declaradas

- Alertas do quadro operacional completo (`alertas.montar_quadro`) ficaram de fora: é uma leitura do quadro inteiro, pesada demais para uma campanha.
- A conta inteira não é lida, só as linhas desta campanha no fato. A verdade é calculada para a campanha.
- O id externo e a conta saem mascarados. O nome da campanha sai, por ser necessário à conversa, e é tratado como dado não confiável.
