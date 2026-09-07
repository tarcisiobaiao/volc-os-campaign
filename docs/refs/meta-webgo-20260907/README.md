# Meta: estado local e referências Webgo — 07/09/2026

O 8080 serve a worktree operacional `execution/volc-os-operacao-80-20`, no
código `0c2723e54683f728d97ec2b465915f7172d63c27`. Esta consolidação é local:
não importa contas, não executa planilhas e não autoriza produção.

## Onde inspecionar

- `/trafego?rede=meta`: Hub, conexão e leitura explícita.
- `/trafego/meta/nova`: bancada, plano, validação, aprovação e recibo governados.
- `/settings/campaigns?rede=meta`: lista demonstrativa. O detalhe Meta ainda
  usa `META_DEMO`/`META_INSIGHTS_DEMO`; não é um dashboard financeiro real.

Vite 8080, Node 3001 e Python 8010 foram localizados na mesma worktree.
Os health checks públicos responderam; o source map entregue pelo Vite para
`MetaCriacaoPage.tsx` contém exatamente o arquivo atual, SHA-256
`e31918ca7c57dcd9822d14ec1b068ce5b8a58ca009ee7556d5894e6f744c1c69`.
Isso prova procedência do código servido, não inspeção visual autenticada nem
recarregamento da aba já aberta do operador. Use recarregar para descartar uma
aba antiga; confira antes se há rascunho que deseja preservar.

Não foi necessário reiniciar: o backend estava saudável e a última correção
alterou SQL candidato, provas e documentação. O startup em
`backend/app/main.py::_reconciliar_runs_orfaos` pode escrever no banco oficial;
reiniciá-lo sem avaliar esse efeito não seria uma ação neutra. Nenhuma flag de
criação foi aberta e nenhum token foi resolvido nesta verificação.

## O que as planilhas acrescentam

Foram lidos dois XLSX originais, sem alteração. O manifesto JSON ao lado guarda
somente hashes e estrutura sanitizada; os arquivos brutos, IDs, URLs de mídia,
nomes de contas e linhas financeiras não foram copiados para o repositório.
Fórmulas, links e instruções de células foram tratados como dados não confiáveis.

O Publisher já descreve boas práticas: token em Script Properties, não na
planilha; `PUBLICAR=NÃO` até a decisão; nascimento PAUSED; validação por nível;
edição com preservação de status; IDs, resultados e log de publicação. Não é
correto tratá-lo como uma automação sem segurança. O XLSX não contém o Apps
Script, portanto não permite auditar sua idempotência, segredo ou transporte.
Os status históricos são registros da planilha, não read-back independente.

| Frente | Referência Webgo | VOLC conferido no código |
|---|---|---|
| Nascimento seguro | Campanha → conjunto → anúncio; PAUSED, validação e logs | Aprovação selada, ledger durável, read-back, recuperação e fencing; provas locais, canário completo ainda pendente |
| Orçamento e objetivo | ABO/CBO, Traffic/Sales, evento/dataset, meta de custo | P0 restrito a Traffic/LPV, ABO, BRL, um conjunto, compartilhamento falso |
| Público e identidade | País, idade, gênero, públicos, placements, Instagram | P0 Facebook-only; opções amplas não equivalem a receitas implementadas |
| Produção em lote | Linhas por conjunto/anúncio; mídia em três formatos, aprimoramentos e textos | Um conjunto e até dez pares estáticos; não equivale a múltiplos conjuntos nem criativo flexível/vídeo |
| Edição posterior | Preservar status, substituir criativo, editar por nível | Receita de nascimento não oferece paridade comprovada de edição/ativação |
| Nomes e marcação | Gerador CP/CJ/AN, rota/site/ADX, parâmetros URL | Destino é selado; compilador P0 não emite `url_tags` nem contrato canônico de UTM por anúncio |
| Arbitragem financeira | Meta RAW × GAM RAW, Ad ID/utm_content, FX, revshare, impostos e custos | Leitura/SQL candidatos existem; lista e detalhe financeiros Meta ainda demonstrativos |
| Operação diária | Histórico por anúncio/campanha/dia, tendência, receita sem correspondência e agenda | R2/T05–T09 ainda deve ligar fatos reais, conciliação e páginas; sem recomendar gasto a partir da demo |

Fontes locais principais: `backend/app/trafego/meta_execucao/contrato.py`
(`PlanoMetaPausado`), `compilador.py`, `backend/app/routers/trafego_meta_criacao.py`,
`src/pages/trafego/MetaCriacaoPage.tsx`,
`src/pages/settings/CampaignsSettings.tsx`,
`src/pages/settings/MetaCampaignsSettingsDemo.tsx`,
`src/pages/MetaCampaignInsightPage.tsx` e `src/utils/roasCalculations.ts`.

**Conclusão:** controles locais do VOLC são mais explícitos e testáveis, mas
superioridade global e substituição integral das planilhas não estão provadas.
A referência Webgo oferece maior amplitude operacional declarada e um fechamento
financeiro que o VOLC ainda precisa conectar de verdade.

## Checklist incorporado, sem abrir outra implementação

1. **P11-T05 / CP2:** conferir catálogo e histórico oficial, backup e perfil
   `CREATE_ONLY` exato de `docs/closure/traffic-operational-closure-v2/SCHEMA-DEPLOY-MANIFEST.json`.
   Aplicação exige autorização própria; nunca executar migrations por glob.
2. **P11-T05 / CP3–CP4:** provar conta/Page/Shop/LP/peça do plano atual; renovar
   roots validate_only; autorizar um único canário PAUSED dos quatro nós com
   read-back. Prova histórica de Campaign+Creative não cobre AdSet/Ad.
3. **P11-T06 / R2 T05–T09:** ligar Insights e dashboards reais e conciliação
   Meta×GAM por identidade estável de anúncio/data/conta. Separar janela de
   atribuição, moeda/fuso, receita atribuída e complementar; não distribuir
   receita órfã silenciosamente nem preencher ausência com zero.
4. **T09:** adjudicar fórmula antes de comparar ROAS. O helper atual do VOLC
   chama de ROAS o retorno excedente `((receita/gasto)-1)*100`; isso não é
   intercambiável com receita/gasto, ROI líquido ou ROAS de compras da Meta.
   O XLSX financeiro exporta resultados, não o código que calcula tudo: sua
   fórmula precisa ser obtida/confirmada, não inferida só pelo título da coluna.
   FX, revshare, impostos e rateio precisam de fonte e data, sem hardcode das
   taxas históricas da planilha.
5. **P11-T02/T04 e receitas posteriores:** mapear CP/CJ/AN, UTMs, multi-conjuntos,
   CBO, evento/dataset, edição segura, mídia por placement e vídeo/flexível.
   Reutilizar as specs existentes; não expor controles que o compilador recusa.

Não se exige toda essa amplitude para o primeiro canário. Exige-se para declarar
substituição completa da operação Webgo. Solicitar o Apps Script original,
sanitizado e sem Script Properties/credenciais, na futura sprint de paridade.

## Evidência e memória

Prova local anterior, não repetida neste trabalho documental: 223 testes Meta
com TCP bloqueado e 38 verificações SQL em PostgreSQL descartável. Fonte:
`docs/closure/traffic-operational-closure-v2/r0-fencing-final-v1/HANDOFF.md`.
O perfil oficial e o primeiro nascimento Meta completo continuam não comprovados.
A ressalva sobre possíveis efeitos de uma sessão anterior permanece naquele
handoff; esta consolidação não a transforma em certificado de zero efeitos.

P11-T02, P11-T05 e P11-T06 continuam `partial`; não há promoção por número de
testes ou por aparência. Nós `cap_meta_ads` e `concept:meta_direct_traffic`
passam a refletir rotas implementadas e fechadas por governança, não ausência de
rotas. Novo documento de referência: `doc:meta-webgo-operational-reference`.
O grafo foi reconstruído com extração técnica local, sem refresh de contas;
`atualizar_grafo_volc_os.py --check` retornou `current:true`, insumos idênticos.
Dois limites permanecem: o extrator advertiu sobre colisões de IDs genéricos
em schemas (`ref_label/ref_reason/ref_id`), e o endpoint
`work_road.status_do_grafo` ainda usa divergência de commit para marcar stale.
Após um commit apenas documental, o QG pode emitir aviso de commit diferente
mesmo com o digest atual. Isso é uma pendência do indicador, não razão para
reescrever o SHA do build. Não foi alterado runtime nesta consolidação para
evitar reload com efeitos de startup no banco oficial.

Sem nova branch/worktree, merge ou exclusão de trabalho paralelo histórico.
Sem push, Meta/Google Ads, Supabase oficial, migrations oficiais, deploy, n8n,
WordPress ou geração de mídia nesta rodada.
