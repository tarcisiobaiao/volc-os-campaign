# Meta Measurement + Advantage Control Plane v1

Status: `SPEC_CANDIDATE_PARTIAL_WITH_REAL_READ_PROOF`. Esta especificação não autoriza migration, Meta
mutate, criação, ativação ou deploy.

## Veredito

O VOLC já possui leitura real Meta v26, credencial local protegida no Keychain,
read model da hierarquia Campaign → AdSet → Ad → Creative e uma espinha de
intenção/lote/ledger reutilizável. Ainda não possui o executor Meta completo,
inventário persistido de fontes de evento/conversões personalizadas, compilador
de `promoted_object` ou read-back canônico de Advantage+.

| Capacidade | Estado | Evidência |
|---|---|---|
| Ler contas Meta | pronta localmente | leitura real e `meta_local.py` |
| Ler hierarquia | pronta localmente | `adaptador.py` + `sincronizador.py` |
| Ler pixels/custom conversions | integrado e provado localmente | preflight v26, 4 contas reais, zero erro |
| CAPI geral | parcial | roteador v21, dois eventos |
| Compilar mensuração no AdSet | ausente | nenhum compilador de `promoted_object` |
| Advantage+ control plane | ausente | UI demonstrativa; read-back não canônico |
| `validate_only` Meta | suporte visível no SDK, não ligado | SDK oficial |
| Criar tudo PAUSED | ausente | sem executor Meta de escrita |
| Ledger/recibo Meta | parcial | espinha existente ainda Google-shaped |

## Correções aplicadas ao output dos modelos

- Não está provado que `/datasets` substitua ou deva priorizar `/adspixels`.
  O inventário deverá suportar a terminologia Pixel/Dataset sem afirmar
  equivalência não documentada.
- Não está provado que `pixel_id` e `custom_conversion_id` sejam mutuamente
  exclusivos em `promoted_object`. O compilador mantém receitas versionadas e
  a validação remota adjudica a combinação.
- Não foram aceitas janelas temporais de CAPI/deduplicação, orçamento mínimo,
  remoção de placements/polls ou obrigatoriedade de Advantage Audience em
  categorias especiais sem confirmação oficial atual.
- `advantage_state_info` é resultado de leitura. Não é um botão mágico de input.
- Custom Conversion é uma mutação administrativa separada; nunca nasce como
  efeito colateral de criar campanha.

## Evidência real incorporada em 04/09/2026

O adaptador integrado percorreu quatro contas acessíveis pelo system user e leu,
somente por GET, a hierarquia Campaign → AdSet → Ad → Creative, Pages,
Instagram, pixels/datasets, Custom Conversions e Insights do dia. As quatro
provas terminaram sem erro; uma Custom Conversion foi observada em uma das
contas. O token foi resolvido do Keychain apenas no processo backend e nenhum
ID bruto foi gravado no pacote de fechamento.

Essa evidência promove a descoberta/inventário local, não a operação Meta:
Insights ainda não foram persistidos, nenhuma migration foi aplicada e não há
executor de criação, edição ou ativação.

## Contratos que precisam existir

### 1. Inventário de mensuração

Novo serviço proposto: `backend/app/trafego/meta/mensuracao.py`.

Input:

- referência opaca da credencial;
- conta Meta canônica;
- versão Graph fixada.

Output:

- fontes de evento visíveis à conta;
- conversões personalizadas com ID, nome, tipo, fonte, regra resumida,
  `is_archived`, `is_unavailable`, `first_fired_time`, `last_fired_time`;
- frescor da leitura e paginação completa;
- estado separado: `AVAILABLE_FIRED`, `AVAILABLE_NEVER_FIRED`, `ARCHIVED`,
  `UNAVAILABLE`, `STALE`, `UNKNOWN`.

Invariantes:

- IDs externos nunca são confundidos entre contas;
- ausência nunca vira lista vazia sem recibo de leitura completa;
- token nunca cruza a fronteira do backend;
- Custom Conversion criada em outro ato não entra automaticamente num plano.

Endpoints propostos:

- `GET /api/trafego/meta/accounts/{account_ref}/event-sources`
- `GET /api/trafego/meta/accounts/{account_ref}/custom-conversions`
- `POST /api/trafego/meta/custom-conversions/plan`
- `POST /api/trafego/meta/custom-conversions/create` — mutação separada e
  desabilitada até autorização específica.

### 2. Compilador de `promoted_object`

Novo módulo proposto: `backend/app/trafego/meta/promoted_object.py`.

Entrada canônica:

```text
account_ref
objective
conversion_location
optimization_goal
billing_event
destination_type
measurement_kind = STANDARD_EVENT | CUSTOM_EVENT | CUSTOM_CONVERSION | NONE
event_source_ref?
event_name?
custom_conversion_ref?
```

Saída:

- payload Meta mínimo;
- campos omitidos explicitamente;
- receita/versionamento utilizado;
- hash da impressão;
- evidência e advertências.

O compilador nunca inventa ID, evento ou conversão. Receitas que ainda não têm
fonte oficial ficam `NEEDS_OFFICIAL_CONFIRMATION` e não chegam à escrita real.

### 3. Matriz de compatibilidade

A matriz local é uma guarda estrutural, não uma cópia pretendidamente completa
da lógica dinâmica da Meta.

| Família | Estrutura local permitida | Autoridade final |
|---|---|---|
| Tráfego para website | destino web; otimização de tráfego compatível; mensuração opcional claramente marcada | `validate_only`/resposta Meta |
| Leads no website | destino web; fonte de evento disponível; evento/conversão selecionado | `validate_only`/resposta Meta |
| Vendas no website | destino web; fonte de evento; evento padrão/custom ou conversão selecionada | `validate_only`/resposta Meta |
| Instant Form/Messaging/App | compilador próprio; não reutilizar receita de website | documentação + validação Meta |
| Awareness/Engagement | não exigir `promoted_object` web por conveniência | documentação + validação Meta |

Estados de erro estáveis:

- `META_ACCOUNT_SCOPE_MISMATCH`
- `META_EVENT_SOURCE_UNAVAILABLE`
- `META_CUSTOM_CONVERSION_UNAVAILABLE`
- `META_CUSTOM_CONVERSION_NEVER_FIRED`
- `META_MEASUREMENT_RECIPE_UNPROVEN`
- `META_PROMOTED_OBJECT_INVALID`
- `META_REMOTE_VALIDATION_FAILED`
- `META_REMOTE_RESULT_AMBIGUOUS`
- `META_READBACK_DIVERGENT`

### 4. Advantage+ control plane

Expor quatro controles independentes:

1. Orçamento: Campaign budget versus AdSet budget.
2. Audiência: `targeting_automation.advantage_audience`, quando suportado.
3. Posicionamentos: automático versus manual, com allowlist versionada.
4. Criativo: enhancements/automação criativa somente após campos oficiais
   específicos serem confirmados.

Cada controle mostra:

- escolha do operador;
- payload compilado;
- campos que a Meta ignorou ou ajustou;
- estado lido após validação/criação;
- overall e componentes de `advantage_state_info` sem inferência.

O preset recomendado pode sugerir uma configuração, mas nunca ocultar os quatro
eixos nem alterar o payload depois da aprovação.

### 5. CAPI e eventos

O roteador atual em `supabase/functions/capi-router/index.ts` permanece legado
até migração explícita. O novo contrato deve:

- aceitar catálogo versionado de eventos em vez de dois nomes hardcoded;
- usar `event_time` da ocorrência, não a hora de processamento da fila;
- gerar uma identidade única por ocorrência e reutilizar o mesmo `event_name`
  + `event_id` nas cópias browser/server;
- tratar hashing por campo: e-mail/telefone e outros campos definidos pela Meta
  seguem normalização/hash; IP, User-Agent, `fbc` e `fbp` não podem ser
  hasheados indiscriminadamente;
- preservar consentimento, finalidade, origem, dataset/pixel, resposta e erro;
- distinguir aceite HTTP de evento saudável/atribuível;
- impedir que teste de evento contamine produção.

Não aposentar o v21 até existir reconciliação sem duplicar eventos.

## Fluxo 80/20

### P0 — primeiro canário Meta PAUSED

1. Integrar leitura paginada de fontes e Custom Conversions.
2. Implementar estados de disponibilidade/frescor.
3. Criar compilador mínimo para uma única receita autorizada.
4. Acrescentar validação local e `validate_only` remoto.
5. Adaptar lote/ledger para identidade Meta sem reutilizar ID Google.
6. Criar Campaign → AdSet → Creative → Ad como `PAUSED`.
7. Fazer read-back de status, orçamento, objetivo, mensuração e Advantage.
8. Fechar recibo apenas após equivalência; ativação fica fora do P0.

### P1 — mensuração confiável

1. Persistir inventário Pixel/Dataset e Custom Conversion.
2. Generalizar CAPI com event lineage/deduplicação.
3. Expor diagnóstico de último disparo e disponibilidade.
4. Persistir Insights e ações por data/objeto/conta.

### P2 — experimentação governada

1. Presets Advantage+ por objetivo com versão.
2. Experimentos de budget/audience/placements/creative isolados.
3. Ativação separada com teto, aprovação e rollback operacional.
4. Comparação incremental sem atribuir causalidade ao dashboard sozinho.

## UX mínima completa

Na etapa Mensuração:

- seletor de conta;
- Pixel/Dataset com estado e última atividade;
- tipo: evento padrão, evento personalizado ou Custom Conversion;
- nome/ID mascarado e regra resumida;
- alertas `never fired`, indisponível, arquivado, stale e desconhecido;
- preview exato do `promoted_object`.

Na etapa Advantage+:

- quatro cards independentes para budget, audience, placements e creative;
- solicitado versus observado;
- explicação do impacto e possibilidade real de opt-out;
- nenhum rótulo geral “Advantage+ ativo” antes do read-back.

Na revisão:

- impressão/hash congelado;
- hierarquia que será criada;
- orçamento e status `PAUSED` destacados;
- validação local separada da validação Meta;
- botão `Validar na Meta` sem criação;
- botão posterior `Criar pausada`, sujeito a autorização própria;
- recibo e read-back visíveis.

## Contraprovas de maior valor

1. `ACTIVE` injetado pelo cliente é recusado antes da rede.
2. ID de fonte/conversão pertencente a outra conta é recusado.
3. Arquivado, indisponível, nunca disparou, stale e ausente não viram zero.
4. Custom Conversion não é criada implicitamente.
5. Evento customizado não é serializado como evento padrão.
6. Payload aprovado e payload enviado têm o mesmo hash.
7. `validate_only` falho nunca promove ledger para criado.
8. Timeout ambíguo entra em reconciliação e não dispara segunda criação.
9. Retry da mesma chave não cria uma segunda hierarquia.
10. Read-back divergente fecha como conflito, não sucesso.
11. Componentes Advantage habilitados não forçam overall habilitado na UI.
12. Orçamento de Campaign e AdSet não ficam simultaneamente autoritativos.
13. Browser/server usam a mesma identidade somente para a mesma ocorrência.
14. `event_time` preserva a ocorrência original em processamento tardio.
15. Token e PII bruta não aparecem em DOM, logs, erros ou recibos.

## Delta de arquivos

Alterar:

- `backend/app/trafego/meta/dominio.py`
- `backend/app/trafego/meta/adaptador.py`
- `backend/app/trafego/meta/sincronizador.py`
- `backend/app/trafego/meta/persistencia.py`
- `backend/app/trafego/ledger.py` somente para neutralizar identidade Google
- `src/pages/trafego/MetaCriacaoPage.tsx`
- contratos TypeScript da área Meta

Adicionar:

- `backend/app/trafego/meta/mensuracao.py`
- `backend/app/trafego/meta/promoted_object.py`
- `backend/app/trafego/meta/compatibilidade.py`
- router autenticado de planejamento/validação/criação Meta
- migration posterior para event sources, Custom Conversions e Insights

Não tocar nesta fase:

- campanhas existentes;
- ativação Meta;
- n8n/WordPress;
- CAPI v21 em produção até plano de migração;
- tabelas Google ou IDs Google como identidade Meta;
- Roadmap/grafo operacional compartilhado antes da integração e prova.

## Fontes

- [SDK oficial Meta Business](https://github.com/facebook/facebook-python-business-sdk)
- [CustomConversion oficial](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/customconversion.py)
- [Evento CAPI oficial](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/serverside/event.py)
- [Exemplo CAPI oficial](https://github.com/facebook/facebook-python-business-sdk/blob/main/examples/AdsPixelEventsPostCustom.py)
- [AdPromotedObject oficial](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adpromotedobject.py)
- [Campaign oficial](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/campaign.py)
- [AdSet oficial](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adset.py)
- [TargetingAutomation oficial](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/targetingautomation.py)

Limitação: `developers.facebook.com` respondeu 429 e a busca web interna do
Gemini respondeu 500. Regras dinâmicas de compatibilidade, placements, creative
enhancements, permissões e limites permanecem `NEEDS_OFFICIAL_CONFIRMATION`
antes de implementar escrita real.
