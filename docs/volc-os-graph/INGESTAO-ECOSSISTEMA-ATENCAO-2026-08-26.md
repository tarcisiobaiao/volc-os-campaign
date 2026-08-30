# Ingestão do ecossistema de atenção — 26/08/2026

## Resultado

Os documentos antigos descrevem uma visão ampla e útil, mas não são uma lista de
funcionalidades prontas. A parte aproveitável foi separada em três operações e uma
fundação comum:

1. **aquisição direta** — anúncio Google ou Meta → criativo → site;
2. **conteúdo orgânico** — descobrir tema → produzir → adaptar → publicar → medir;
3. **retenção e relacionamento** — conversa consentida → segmentação → retorno;
4. **Cofre de Ativos** — páginas, perfis, contas, domínios, engines e integrações que
   pertencem à operação.

Esta classificação impede que uma projeção antiga vire tarefa obrigatória, que um
arquivo vire prova de sistema funcionando ou que a operação direta de Meta seja
misturada com a tese histórica de chat e LTV.

## Escala de evidência usada

| classe | significado |
| --- | --- |
| **Fato observado** | arquivo, código, resposta de serviço, banco, teste ou tela vistos nesta rodada |
| **Fato declarado** | informação afirmada pelo dono, ainda sem inventário independente |
| **Ativo existente, não integrado** | artefato real encontrado, mas fora do VOLC O.S. e sem operação comprovada |
| **Protótipo / engenharia** | desenho, SQL ou workflow que pode ser reaproveitado, sem eficácia operacional provada |
| **Visão / hipótese** | possibilidade futura, projeção ou modelo que exige validação |
| **Risco / descartar como regra** | ideia antiga que não deve entrar no produto sem revisão de plataforma, política ou segurança |

## Fontes analisadas

### V.OS

- `VOS PRIME.docx` — arquitetura aspiracional do ecossistema de atenção;
- `ORGANICO - ATTENTION MATRIX V.OS.docx` — desenho de autoridades, perfis
  faceless, amplificadores, portais e pilares editoriais.

### Meta

- `BLACK BOOK - META - PROGRAMMATIC.docx`;
- `VOLC - META - PROGRAMMATIC.docx`;
- `beast_mode_autopilot_complete/BEAST_MODE_AUTOPILOT_MASTER.md`;
- `beast_mode_autopilot_schema.sql`;
- quatro workflows legados e cinco workflows V2.

Os dois DOCX de Meta têm conteúdo textual idêntico. São uma fonte lógica, não dois
sistemas diferentes. Os binários têm hashes distintos por metadados internos.

## O que foi comprovado

| item | classificação | evidência e limite |
| --- | --- | --- |
| Página de Facebook monetizada | Fato declarado | O dono informa que comprou a página há mais de um mês. Nome, ID, propriedade, monetização e acessos ainda não foram inventariados. |
| ChatPion próprio | Fato observado parcial | `https://chatpion.agenciavolc.com.br/` respondeu HTTP 200 em 26/08/2026. Isso prova uma superfície publicada, não prova fluxos, páginas, permissões ou entregabilidade configurados. |
| Engines de imagem e vídeo | Fato declarado / ativo não integrado | O dono declara engines prontos e validados; contratos, paths e execuções ainda precisam entrar na curadoria. |
| Documentação V.OS e Meta | Fato observado | Os quatro DOCX e o pacote BEAST existem e foram lidos. |
| Workflows Meta | Protótipo observado | Existem 4 JSON legados e 5 JSON V2; todos trazem `active=false`. O pacote não prova execuções reais. |
| Schema BEAST | Engenharia observada | SQL define 14 tabelas e 2 views para contas, campanhas, criativos, insights, avaliações, decisões e aprendizado. Não foi provado aplicado no banco oficial. |
| Workflow de promoções | Fato declarado / não verificado | O dono aponta `hA1hLumyH33xH549`. A raiz do n8n respondeu HTTP 200; a rota direta do workflow respondeu 404 sem sessão. Conteúdo e estado operacional não foram observados. |

## O que os documentos realmente contêm

### V.OS PRIME

O documento propõe um ciclo completo:

`observar → interpretar → criar → adaptar → publicar → monetizar → proteger → aprender`

As famílias aproveitáveis são:

- sensores de pauta e tendência;
- transformação de oportunidade em briefing;
- produção de texto, imagem e vídeo;
- adaptação por canal;
- publicação assistida;
- medição e aprendizado;
- segurança de marca, conta, domínio e tráfego.

Os nomes “The Field”, “The Mind”, “The Body” e “Immune System” são uma linguagem de
visão. O VOLC O.S. não precisa reproduzi-los como módulos técnicos. O valor está no
ciclo, não na nomenclatura.

### Organic Attention Matrix

O documento organiza autoridades, perfis faceless, amplificadores e portais em
pilares editoriais. Isso é um **catálogo de estratégia**, não um inventário de ativos.
Handles, quantidades de perfis, metas de volume e projeções de receita não provam
propriedade nem operação.

O princípio reaproveitável é: uma pauta pode gerar várias peças, mas cada canal
recebe formato, texto e momento próprios. A página de Facebook comprada é o primeiro
caso real para transformar essa tese em um piloto mensurável.

### Meta Programmatic / Black Book

O documento desenha uma operação distinta de Meta direto:

`Meta/Orgânico → comentário ou mensagem → ChatPion/Typebot → identidade → retorno → site → receita`

Ele também contém schema, scripts, sete agentes conceituais e checklists. Os números
de CPL, LTV, ROI, volume e prazos são hipóteses antigas. Não entram como limites do
produto nem como política de otimização.

### BEAST Mode Autopilot

O pacote observado materializa parte de uma segunda arquitetura:

- precheck;
- observação de insights;
- avaliação;
- motor de decisão;
- rotação criativa.

O documento mestre anuncia sete módulos, mas os artefatos presentes não comprovam
Risk Sentinel, Learning Loop e Executor como workflows entregues. Mesmo os módulos
presentes estão desativados nos JSON e nunca operaram, segundo o dono. Por isso o
conjunto entra como **laboratório histórico reaproveitável**, nunca como capacidade
pronta para ligar.

## Separação canônica das operações

### 1. Meta direto — frente atual

Objetivo: usar contrato criativo, imagens e vídeos para criar e gerir campanha,
conjunto e anúncio que levam diretamente ao site.

Esta frente pertence ao Hub de Tráfego e compartilha identidade, inventário,
frescor, reconciliação, aprovação humana e recibo com Google Ads.

### 2. Conteúdo orgânico — nova frente

Objetivo: ativar ativos sociais próprios com uma cadeia editorial assistida,
começando por uma página real.

Primeiro piloto honesto:

- cadastrar a página no Cofre;
- escolher uma vertical e um objetivo;
- gerar uma pauta e suas peças;
- revisar manualmente;
- publicar em uma única página;
- registrar URL, horário e versão;
- medir alcance, interação, clique e retorno;
- decidir o próximo teste.

Não começa com dezenas de perfis, automação total ou projeções de receita.

### 3. Retenção e relacionamento — frente posterior

Objetivo: usar ChatPion e canais consentidos para manter relacionamento, devolver
conteúdo ou oferta e medir o retorno.

Pré-requisitos antes de qualquer automação de envio:

- inventário de páginas, permissões, tokens e fluxos;
- consentimento, opt-out, janelas e regras atuais por canal;
- identidade e deduplicação;
- logs de envio, entrega, bloqueio e descadastro;
- limites e circuit breaker;
- atribuição de clique e receita;
- aprovação humana para mensagens e segmentos.

### 4. Promoções e afiliados — frente reservada

Objetivo potencial: captar ofertas por API, validar disponibilidade e condição,
produzir mensagem e distribuir em grupos próprios de WhatsApp/Telegram com
atribuição.

O protótipo citado ainda precisa ser aberto e inventariado. Até lá, é capacidade
planejada, não pipeline existente.

### 5. Infoproduto low ticket — espaço reservado

Existe apenas como direção estratégica informada pelo dono. Não recebe tarefas,
prazo, percentual ou arquitetura até chegarem novos materiais.

## Cofre de Ativos

O Cofre não deve guardar senhas em texto nem virar apenas uma tela de login. Ele é o
registro operacional de tudo que a VOLC possui, opera ou depende.

Cada ativo deve responder:

- o que é e para que serve;
- plataforma, ID e URL pública;
- empresa, marca, projeto e vertical responsáveis;
- dono e operadores autorizados;
- estado: descoberto, verificado, pronto, ativo, restrito, inativo ou aposentado;
- capacidade de monetização e prova correspondente;
- integrações conectadas;
- referência segura da credencial, nunca o segredo;
- última verificação e próximo vencimento;
- dependências e ativos relacionados;
- evidências e incidentes;
- próximo uso decidido.

Famílias iniciais:

- páginas e perfis sociais;
- contas e gerenciadores de anúncio;
- pixels, datasets, apps e system users;
- domínios, sites e propriedades monetizadas;
- contas GAM, AdSense, afiliado e marketplaces;
- grupos e canais de WhatsApp/Telegram;
- engines de texto, imagem e vídeo;
- workflows, serviços e webhooks;
- cofres e referências de credencial.

## Material que não vira regra do VOLC O.S.

Ficam explicitamente fora do produto até revisão independente:

- projeções financeiras e metas de escala dos documentos;
- thresholds fixos de kill/scale, CPL, ROI, fadiga e confiança;
- criação de contas secundárias para aquecimento;
- pods artificiais, disfarce de padrão ou diversificação de IP;
- rotação de domínio para contornar bloqueio;
- alteração editorial para manipular leilão publicitário;
- disparos, comment automation ou retargeting sem política e consentimento atuais;
- “pausar tudo” ou alterar orçamento automaticamente sem autorização, recibo e rollback;
- autoajuste de thresholds sem conjunto de validação e governança.

Esses trechos são evidência histórica do pensamento, não requisitos aceitos.

## Roadmap prático extraído

### Agora — fechar o mapa e descobrir o que é real

- [x] Ler e classificar os documentos V.OS e Meta.
- [x] Distinguir Meta direto, orgânico e retenção.
- [x] Identificar duplicidade dos DOCX de Meta.
- [x] Inventariar estrutura dos workflows e schema BEAST.
- [ ] Cadastrar a página monetizada com identidade e prova mínima.
- [ ] Inventariar engines criativos com path, contrato e execução.
- [ ] Abrir e exportar o workflow de promoções citado.
- [ ] Inventariar configuração funcional do ChatPion sem copiar segredos.

### Próximo — criar a fundação comum

- [ ] Modelar a fonte compartilhada do Cofre de Ativos.
- [ ] Criar interface de inventário, relações, evidências e próximos usos.
- [ ] Ligar Cofre, Mapa Vivo, Work Road e integrações sem duplicar verdade.
- [ ] Definir referências seguras de credencial e revisão de acesso.

### Primeiro piloto orgânico

- [ ] Usar uma página real, uma vertical e uma semana de teste.
- [ ] Reaproveitar um engine de conteúdo por contrato explícito.
- [ ] Manter aprovação humana antes de publicar.
- [ ] Persistir peça, versão, publicação e métricas.
- [ ] Registrar aprendizado no Work Road e no grafo.

### Depois

- [ ] Integrar ChatPion em modo inventário/leitura.
- [ ] Validar retenção com política e consentimento atuais.
- [ ] Auditar e decidir o destino dos workflows BEAST.
- [ ] Auditar o protótipo de promoções e afiliados.
- [ ] Receber a documentação de low ticket antes de abrir backlog.

## Decisão de curadoria

- Os documentos continuam preservados como referências históricas.
- O pacote BEAST entra como laboratório histórico parcialmente materializado.
- A página monetizada entra como ativo declarado aguardando onboarding.
- ChatPion entra como sistema publicado com operação não verificada.
- O Cofre de Ativos entra como capacidade planejada e fundação transversal.
- Organic Content Matrix entra como capacidade parcial, não como rede pronta.
- Retenção/chat e promoções/afiliados entram como frentes separadas e posteriores.
- Low ticket entra apenas como conceito reservado.
