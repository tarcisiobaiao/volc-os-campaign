# Meta: tracking visível e preparação de gestão

Data: 08/09/2026. Estado: **LOCAL_PARTIAL**, sem aceite de produção.

## Resultado local

- Na criação, a etapa Campanha pede o destino antes do orçamento; a revisão também mostra o tracking. Os parâmetros vêm do template canônico do compilador, não de uma segunda constante no frontend.
- `utm_campaign={{adset.id}}` atribui receita GAM ao conjunto; a campanha soma seus conjuntos no mesmo período. `campaign_id={{campaign.id}}` leva contexto, não substitui a chave de atribuição. Não há receita individual por anúncio neste contrato.
- URL com parâmetro reservado, inclusive codificado ou em caixa diferente, é recusada. Parâmetros não reservados e fragmento são preservados. Removida a instrução contraditória para preencher tracking manualmente.
- O detalhe financeiro permite abrir os anúncios de um conjunto. Hierarquia incompleta não vira lista vazia presumida como completa.
- Gestão permite PREPARAR propostas de pausa, orçamento diário, lance e duplicação de conjunto com anúncios. O servidor confere conta/campanha/conjunto; valores não observados continuam NULL; valores propostos são selados em BRL, sujeitos à confirmação da moeda da conta.
- Proposta não é aprovação, não é salva, não é payload executável e não dispara Meta. Sua identidade inclui pedido, ator, estado observado e alteração. A interface invalida respostas antigas ao mudar a intenção ou leitura.

## Rotas

- GET `/api/trafego/meta/local/criacao/tracking`: prévia pura, autenticada, host local, sem token Meta.
- POST `/api/trafego/meta/local/gestao/planejar`: consulta somente o read model e devolve `PROPOSTA_LOCAL_NAO_EXECUTAVEL`, `executavel=false`, `persistida=false`.
- Não foi criada rota de execução de gestão nem de ativação.

## Evidências

- Backend: 73 testes passaram em `test_meta_gestao_tracking_ux.py`, `test_meta_tracking_gam.py` e `test_meta_rotas_v2.py`. Incluem zero acesso ao resolvedor de token, escopo cruzado recusado, ausência preservada, valores estritos, moeda proposta e conflito de tracking.
- UI: 67 testes passaram nos quatro arquivos focais de tracking/gestão, read view, rascunho V2 e financeiro por conjunto.
- `npm run build` passou antes da última correção de rótulo/moeda. TypeScript avaliado no projeto `tsconfig.app.json`, não no alvo raiz vazio; erros globais não são escondidos.
- TypeScript final: exit 2, 76 erros globais, nenhum nos arquivos de produção tocados por esta lane. Não foi repetido baseline em checkout separado e não se declara delta formal contra a base.
- Browser: componentes reais isolados, usando respostas fictícias explícitas, em 375/768/1440 e claro/escuro. Seis cenários sem overflow horizontal nem erros de página. Inspeção humana dos screenshots desktop claro e mobile escuro nesta rodada. O harness temporário foi removido.
- Isso NÃO prova página autenticada completa, clique de anúncio real, expansão das macros, persistência GAM ou capacidade de mutação Meta.
- Grafo reconstruído pela cadeia oficial, sem refresh de fontes externas: 34.266 nós, 79.482 arestas. P11-T05/P11-T06 e os nós cap_meta_ads/concept:meta_direct_traffic mantêm estado partial; gestão remota explicitamente pendente. Scanner sem padrões fortes; diff check limpo.
- 8080 conferido com HTTP 200 e cwd operacional. As novas rotas protegidas devolvem 401 sem sessão, não 404; nenhuma credencial foi lida para esta conferência.

## Fontes e limites da revisão

Contrato local: `backend/app/trafego/meta_execucao/compilador.py`, `contrato.py`, read model e rotas existentes. A navegação inicial usou grafo e curadoria; a memória é reconciliada mantendo P11-T05/P11-T06 em partial.

Referências consultadas do SDK oficial Meta (branch main, não prova de aceitação v26):

- https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/adobjects/adset.py
- https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/adobjects/adcreative.py

Páginas de documentação Meta responderam 429 ou exigiram login. Não foram preenchidas lacunas por suposição. As opções de gestão são intenções; compatibilidade de objetivo, otimização, orçamento, lance e cópia precisa ser confirmada antes de qualquer executor remoto.

## O que falta para operar

1. Ingerir valores correntes de orçamento/lance/moeda e distinguir autoridade ABO/CBO. Não inferir zero a partir de campo ausente.
2. Implementar aprovação, ledger e executor específico de gestão, com comparação do estado anterior e read-back. Um hash de proposta não autoriza execução.
3. Duplicar com nova identidade e tracking dinâmico, preservando histórico na origem, sem retry automático após despacho ambíguo.
4. Provar compilação/validação do plano atual e canário PAUSED sob autorização própria. A interface V2 não comprova execução V2 completa.
5. Provar clique até LP/GAM e atribuição por conjunto, soma da campanha sem somar também métricas campaign-level, e QA autenticado das páginas completas.

## Isolamento

Sem nova branch ou worktree. Nenhuma alteração deliberada no Assistente Criativo, engine de imagens ou suas migrations. O terminal paralelo criou `5a0ee63572fa55daeefd63dc443db2da2ef6e274` incluindo os arquivos desta lane que estavam no mesmo diretório; depois, `957af61f0de42d8db68a44830ca458dc836fe88c` também incluiu sua correção de moeda e memória durante as verificações. Essa história foi preservada, sem amend/rebase. O fechamento documental final não reescreve os commits alheios. Evitar novos commits amplos enquanto outro executor escreve no mesmo diretório.

Zero push, deploy, chamada Meta, Supabase oficial, migration, n8n, Google Ads ou geração paga nesta rodada. A proposta de gestão não altera o status das campanhas.
