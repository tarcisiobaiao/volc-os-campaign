# Meta + GAM — fechamento local de 07/09/2026

Estado: **LOCAL_IMPLEMENTED — produção continua PARTIAL**.
Base: `8697bf7fb1b3b6bc79cbc5dfe7669c5b08f4a349`.
Mesma branch `execution/volc-os-operacao-80-20`; sem outra worktree operacional.

## Entregue

- `backend/app/trafego/meta/financeiro.py`: endpoint financeiro somente leitura
  por conta opaca, campanha e período. Resolve o ID externo no servidor, usa
  `vw_trafego_meta_insight_latest` em grão campaign/dia/default/impression/none,
  e **GAM.utm_campaign_value = Meta campaign_id**, conforme decisão do dono.
- Receita escopada pelo vínculo ativo Meta → projeto → única conta GAM.
  Catálogo indisponível, colisão Google/Meta ou múltiplas contas com o mesmo ID
  impedem atribuição. Não usa a tabela financeira legada Google como fallback.
- Cards reais de investimento, receita, retorno excedente e lucro bruto ligados
  ao servidor. Datas explícitas (padrão D-1 no fuso da conta), fontes e carimbos.
  Resposta antiga não aparece em outra campanha, conta ou período.
- Moeda/fuso diferentes, dias ausentes, duplicatas e valores NULL não viram
  totais. Zero explícito permanece zero; divisão por zero permanece NULL.
  Decimal permanece string no JSON. Receita de compras atribuída pela Meta
  **não** é receita GAM. Reach não é somado; CTR/CPC usam razões das somas.
- Novos criativos compilam `url_tags` com `utm_campaign={{campaign.id}}` e
  `campaign_id={{campaign.id}}`, mais source/medium. Tracking entra no hash,
  snapshot e revisão. URL com parâmetros conflitantes recusa localmente.
  Read-back cobra o tracking; omissão/divergência para a saga sem reenviar.
  Planos históricos congelados não são reescritos. Recompilar/revalidar antes
  de uma nova aprovação: os roots antigos não cobrem esse payload.
- Startup do backend não reconcilia nem escreve runs sem opt-in
  `VOLC_RECONCILIAR_RUNS_NO_STARTUP=1`; health expõe esse estado. Abrir a bancada
  não lê contas Meta; o operador aciona **Ler contas na Meta**.
- Leitor de catálogo funciona sem tabelas e sem `service_role`, provado em
  PostgreSQL vazio. Gate TypeScript agora aponta para `tsconfig.app.json`.

## Configuração do relatório GAM (não é segredo)

O legado tem `gam_accounts.project_id`, `gam_metrics.gam_accounts_id`,
`utm_campaign_value`, `date`, `revenue` e `revenue_converted`. Não há evidência
local de metadados completos de moeda/fuso do relatório. Não supor USD/BRL/UTC.
Após confirmação do relatório e da conversão utilizada, configurar no servidor:

```json
{
  "ID_DA_CONTA_GAM": {
    "currency": "BRL",
    "timezone": "America/Sao_Paulo",
    "revenue_column": "revenue_converted"
  }
}
```

Variável: `META_GAM_REPORTING_CONTRACT_JSON`. O exemplo não confirma que uma
conta real usa esses valores. Colunas aceitas: `revenue` ou `revenue_converted`.
Não há câmbio automático nem uso de percentual universal de imposto/revshare.
Sem configuração o gasto continua legível e a receita explica o bloqueio.
Sem vínculo de projeto confirmado não existe fallback por nome de campanha.

## Evidência de API e limites

O [SDK oficial Meta](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adcreative.py)
declara `AdCreative.url_tags` como string legível em 07/09/2026. A referência
AdCreative retornou 429; o Help Center de parâmetros dinâmicos exigiu login.
Portanto **não** declaramos a expansão de `{{campaign.id}}` remotamente provada.
O código e os fakes demonstram emissão, hash e read-back, não a aceitação do
payload na conta nem a chegada do ID ao GAM. Isso integra CP3/CP4 e a prova
posterior da instrumentação da LP. Canário PAUSED não gera receita nem prova
entrega/clique real. Não foi usada recomendação de blog como prova de API.

## Verificação local

- 355 testes backend Meta/relatórios/startup, com TCP bloqueado, verdes.
- 75 testes UI focais verdes (nova leitura, revisão, nascimento e roteamento).
- PostgreSQL 17 descartável: 152 asserções, apply/uso/rollback/reapply e
  catálogo vazio. O cluster criado pelo teste foi removido pelo seu teardown.
- TypeScript: **77 erros herdados**, saída idêntica à base exportada por
  `git archive`, sem stash ou worktree. A afirmação antiga “tsc 0” não é aceite
  do app: o alvo vazio do gate não verificava o projeto correto.
- Build Vite passou. Inspeção visual autenticada não realizada.
- Perfis de schema mantidos; nenhuma migration adicional criada nesta rodada.

## Próximos atos, sem nova auditoria ampla

1. **CP2 — catálogo e schema oficial:** autorização específica para ler catálogo,
   conferir backups/checksums e aplicar os perfis CREATE_ONLY e META_READ_MODEL
   do manifesto existente. Nunca executar glob de migrations (inclui rollbacks).
2. **CP3 — plano atual:** conta/Page/destino/peça confirmados; recompilar com
   tracking e validar roots por clique. Falta prova dependente de AdSet/Ad.
3. **CP4 — canário:** autorização limitada a um nascimento PAUSED com aprovação,
   ledger e read-back. Sem retry ambíguo, sem ativação, sem segunda campanha.
4. **Dados reais:** autorização de primeira sincronização/persistência; confirmar
   vínculo de projeto, conta GAM, moeda/fuso/coluna e instrumentação da LP que
   traduz o campaign_id recebido para a dimensão coletada no GAM.
5. **n8n:** provisionar credencial no servidor (Keychain do Mac não é credencial
   do n8n), importar inativo, execução manual D-1, replay idempotente e carimbo
   do dashboard. Só então autorizar uma agenda. Fluxo existente não foi alterado.

P11-T05/P11-T06/P06-T04/P10-T16 continuam partial, cada qual com a sua lacuna.
Vídeo/flexível, múltiplos conjuntos/CBO, Instagram, Sales/Leads, regras fiscais
versionadas e ativação ampla não foram promovidos a capacidades prontas.

Limitação de segurança herdada: o gerador/JSON JoinAds legado contém um Bearer
hardcoded previamente identificado. Não foi usado nem reproduzido aqui; requer
remoção local e rotação pelo responsável antes de publicar/usar aquele fluxo.
Não certificar o repositório inteiro livre de segredos só pelo scanner genérico.

## Ambiente e autorizações

Frontend continua em localhost:8080. Backend local reiniciado sem autoreload,
reconciliação de startup desligada, criação/ledger/persistência desligados.
Validar continua ato explícito do operador. Não alteramos configurações oficiais.
Nenhuma chamada Meta/Google autenticada, escrita Supabase oficial, migration
oficial, n8n, WordPress, deploy ou push foi executada nesta rodada. Ler o
dashboard autenticado futuramente consulta o read model oficial por desenho;
esta afirmação não proíbe nem certifica ações independentes do operador.
