# Runbook operacional — coleta diária Meta no n8n

> **Estado desta entrega:** o workflow foi **gerado e validado localmente**.
> Ele **não** foi importado, **não** foi executado e **não** foi ativado em
> nenhuma instância n8n. Existir um JSON não é evidência de que um fluxo esteja
> no ar — este runbook trata os três atos como separados de propósito.

## O que existe

| artefato | papel |
|---|---|
| `n8n/gerar_flows_meta_ledger.py` | gerador determinístico do JSON (ids `uuid5`, contrato com SHA) |
| `n8n/volc_meta_insights_dia_d1.json` | o workflow, nascido com `"active": false` |
| `scripts/validar_workflows_n8n_meta.py` | validador nó a nó, espelhando o do Google Ads |
| `backend/tests/test_meta_workflows_n8n.py` | roda gerador `--check` + validador como teste |

O fluxo Google canônico (`n8n/volc_gads_campanha_dia_d1.json` e `_d0.json`) e
seu gerador **não foram tocados**, e nenhuma agenda existente foi mexida.

## A cadeia de nós, e por que ela é essa

Reproduz nó a nó a cadeia já aprovada do Google:

```
Agenda ─┐
        ├─ Config ─ Identidade da execução ─ Contas autorizadas ─ Selecionar contas
Manual ─┘                                          │
                                          Objetos conhecidos ─ Identidade VOLC por conta
                                                     │
                                            Lote de contas (batchSize 1)
                                                     │
                                          Página: preparar pedido ─ Meta Graph: insights
                                                     │                      │
                                       Juntar contexto e resposta   Juntar contexto e erro
                                                     │                      │
                                          Página: normalizar        Classificar erro da Meta
                                                     │
                                          Validar semanticamente ─ RPC: ingerir lote
                                                     │
                                          Reconciliar lote ─ Tem próxima página? ─┐
                                                     │                            └─(volta ao lote)
                                          Fechar execução ─ Limite 1 ─ RPC: fechar recibo
                                                     │
                                          Releitura do recibo ─ Batimento e saúde ─ Falha real? ─ Alerta
```

Quatro defesas herdadas do fluxo Google que **não** podem ser "simplificadas":

1. **Dois nós `Merge` por posição** em vez de `$('Nó')` dentro do laço. Dentro
   de um `splitInBatches`, `$()` lê o contexto da iteração errada.
2. **`$input.all()` no nó de fechamento** — não `$()`.
3. **`Limit 1` antes da RPC de fechamento**, para não fechar o recibo N vezes.
4. **`"active": false` no arquivo versionado.** A ativação é um ato humano.

## As regras que este fluxo carrega (e por que)

### O dia é o da conta, nunca o do servidor
`Selecionar contas` lê `trafego_meta_ad_account.timezone_name` e calcula a
janela D-1 **no fuso de cada conta**. Uma conta sem fuso, ou com um fuso que o
runtime não conhece, é **recusada com motivo** — nunca cai em UTC por padrão.

Este é o mesmo defeito que o backend acabou de corrigir: uma conta em
`America/Sao_Paulo` lida por um processo em UTC pede, por três horas toda
noite, um dia que a conta ainda não começou, e lê o vazio como ausência de
veiculação.

Consequência de projeto: **a chave da execução carrega a data do disparo, não a
janela coletada.** Cada conta tem seu fuso, então uma chave única com uma janela
única mentiria sobre metade das contas. A janela real viaja por conta, dentro do
recibo.

### A janela de atribuição nunca é carimbada sem ter sido pedida
`action_attribution_windows` só vai no fio quando há janelas configuradas — e
nunca vazio, porque a chave vazia pediria "nenhuma janela" em vez de "a janela
da conta". `Validar semanticamente` rejeita a linha com
`JANELA_CARIMBADA_SEM_PEDIDO` se o rótulo divergir do que foi pedido.

### Janelas de atribuição não são achatadas
Com janelas pedidas, a Graph devolve **uma chave por janela dentro da mesma
action** (`{action_type, 1d_click, 7d_click}`). Ler só `value` colapsaria as
duas num número irrecuperável. Cada janela vira uma linha própria.

### Marca d'água só avança sobre janela inteira E persistida
`marca_dagua` recebe `janela_fim` apenas quando `completo && persistencia_confirmada`.
Uma janela truncada pelo teto de páginas é um **resultado incompleto declarado**,
não um erro duro: as linhas lidas são preservadas, a incompletude é registrada, e
a marca d'água **não** anda.

### Erro de autorização para; erro transitório repete
`Classificar erro da Meta` separa os dois. 401/403 exigem ação humana e não
entram em retry. Repetir vale na **próxima rodada agendada**, não dentro desta.

### Nada de regra financeira em Code node
A persistência é uma chamada à RPC (`trafego_meta_persistir_snapshot`). Os nós
de código normalizam e validam forma — não recalculam dinheiro. A regra
financeira mora no serviço canônico e no schema, em um lugar só.

## ⛔ O bloqueio real: credencial da Meta no servidor

**Este fluxo não funciona ainda, e a razão é concreta.**

O fluxo Google autentica por um **tipo de credencial predefinido do n8n**
(`googleAdsOAuth2Api`, via `nodeCredentialType`). Para a Meta:

- o token operacional hoje vive no **Chaveiro do macOS** do operador, atrás de
  rotas que exigem `darwin` + `localhost` + papel ADMIN;
- um servidor n8n **não tem** esse Chaveiro, e não pode depender de sessão de
  navegador nem de endpoint administrativo em `localhost`;
- **não há evidência neste repositório** de que a instalação n8n em uso ofereça
  um tipo de credencial equivalente para a Meta.

O workflow referencia a credencial **por indireção**, sem segredo em lugar
nenhum. Ele permanece **inoperante até o provisionamento** descrito em
`AUTHORIZATION-REQUESTS.md` → *Provisionamento de credencial Meta para o
servidor*. Isso é a resposta honesta, não uma pendência escondida.

## Sequência de ativação — três atos, três autorizações

Não pule etapas e **não** trate uma autorização como se cobrisse a seguinte.

### Pré-condições (todas obrigatórias)
- [ ] Perfil de schema `META_READ_MODEL` aplicado e verificado (CP2-b), **incluindo**
      a migration incremental `20260907210000_meta_read_model_consistency.sql`.
- [ ] Credencial Meta de serviço provisionada, limitada às contas autorizadas.
- [ ] `scripts/validar_workflows_n8n_meta.py` verde.
- [ ] Gate de agenda única verde: nenhuma outra rotina coletando as mesmas contas.
- [ ] Leitura ao vivo do inventário n8n confirmando **quais** agendas estão de
      fato ligadas hoje. O inventário versionado é de 19/08/2026 e declara 23
      workflows ativos — é um retrato antigo, não o estado atual.

### Ato 1 — importar **desativado**
Importar `n8n/volc_meta_insights_dia_d1.json`. Conferir na interface que
`Active` está **desligado**. Nada dispara.

### Ato 2 — execução manual, uma conta, um dia
Usar o gatilho **Executar manualmente**, com `CONTAS_PERMITIDAS` restrito a uma
única conta e a janela de um único dia.

Conferir, nesta ordem:
1. o recibo da execução existe e traz conta opaca, período, fuso da conta,
   versão da API, parâmetros enviados, páginas, contagens, completude;
2. as linhas chegaram ao Supabase;
3. **a releitura pela API do produto** mostra os mesmos números — não basta o nó
   de releitura do próprio fluxo;
4. nenhum id bruto, token ou registro financeiro apareceu em log ou alerta.

### Ato 3 — reprocessamento idempotente
Rodar **a mesma janela outra vez**. Conferir que:
- o gasto **não** dobrou;
- a projeção `vw_trafego_meta_insight_latest` expõe **uma** linha por grão;
- a tabela base guarda as duas revisões como histórico.

Sem esta prova, não ative a agenda.

### Ato 4 — ativar a agenda (autorização própria)
Só depois dos atos 2 e 3 provados. Ao ativar:
- confirme que nenhuma rotina legada coleta as mesmas contas;
- registre no gate de agenda única que existe agora uma agenda Meta declarada.

## Reversão

| situação | o que fazer |
|---|---|
| coleta duplicando gasto | desativar a agenda; a projeção `latest` já protege a leitura; investigar a chave de idempotência antes de religar |
| janela sistematicamente incompleta | desativar a agenda; a marca d'água não avançou, então reprocessar é seguro |
| erro de autorização | desativar; o fluxo não faz retry disso de propósito |
| schema divergente | desativar; **não** rodar rollback com dados reais sem plano de preservação |

Desativar a agenda **nunca** apaga dados já persistidos.

## O que este fluxo deliberadamente NÃO faz

- não cria, edita, pausa nem ativa nada na Meta — é `GET` de Insights;
- não envia eventos pela Conversions API (coletar Insights não é enviar eventos);
- não coleta vídeo, catálogo, breakdowns fora da allowlist nem múltiplos níveis
  na mesma execução;
- não decide orçamento nem lance;
- não toca os fluxos Google existentes.
