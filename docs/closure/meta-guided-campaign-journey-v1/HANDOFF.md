# Jornada guiada Meta — 08/09/2026

Interface implementada localmente; operação ponta a ponta continua **partial**.
Base de código: `a61cd6d7965cf1b5a8ab84971de3c95af848ccd7`, branch operacional existente
`execution/volc-os-operacao-80-20`. Nenhuma branch/worktree nova.

## Conferência pelo operador

Abra `/trafego?rede=meta` e escolha **Criar campanha guiada**, ou acesse
`/trafego/meta/nova` sem parâmetros antigos. O rascunho começa sem nome nem URL
de exemplo. Preencha o destino HTTPS sem parâmetros reservados e o nome.

Sequência: destino → conta → Página → resultado → conversão, quando necessária
→ público → orçamento → conjuntos → criativos → revisão.
Voltar e o índice recolhido permitem corrigir respostas. Cmd/Ctrl+Enter avança;
não compila, valida ou cria automaticamente. Cada ato remoto continua explícito.

1. Carregar contas faz a leitura já existente por clique, não nesta entrega.
2. Vendas/Leads apresentam a mensuração antes do público. O catálogo existente
   lê fontes e conversões da conta selecionada; mudança de receita limpa a
   seleção anterior e define o propósito correspondente. Conversão personalizada
   e evento padrão não são enviados juntos pela escolha de conversão.
3. ABO/CBO, valor exato em reais, atalhos de orçamento, público amplo/personalizado
   e controles avançados continuam ligados ao mesmo rascunho. Não foi adicionado
   slider que arredonde silenciosamente o orçamento.
4. O acompanhamento usa o template canônico existente: `utm_campaign={{adset.id}}`.
   A campanha soma os conjuntos; não há soma adicional de métricas campaign-level.
5. Em Criativos, abra o Assistente integrado ou selecione ativos da conta.
   O Assistente reaproveita sua página/engine real, sem outro backend. Geração
   continua exigindo a autorização e os limites já existentes.
6. Confira o plano no servidor. Resumo, hash, recibos e permissão de criação
   continuam vindo do backend; navegação não produz um JSON de lançamento paralelo.

## Fronteiras que continuam bloqueadas

- V2 (incluindo Vendas/Leads e configurações multiconjunto/CBO) pode preparar e
  validar conforme flags, mas não ganhou executor de criação nesta entrega.
  Selecionar uma receita não prova elegibilidade da conta/evento nem libera criação.
- Selecionar uma conversão existente não instala nem configura a Conversions API.
- O Assistente está integrado na experiência, mas **peça gerada → registro na conta
  com avaliação de política → anúncio compilado** ainda não está concluído.
  Seleção de masters impede conferir um plano antigo até resolver/remover a seleção.
  Não existe upload automático nem inclusão silenciosa das peças no payload.
- Aprovar estratégia não autoriza gastar com geração nem publicar mídia.
- Dados do rascunho e seleção são locais à página: recarregar a página os perde.
  Projetos do Assistente seguem seu mecanismo durável existente. Retornar à etapa
  Criativos retoma a referência do projeto durante a mesma jornada.
- Nenhuma comprovação de migração, storage oficial, geração paga, leitura Meta,
  validação remota, criação ou ativação foi realizada nesta rodada.

## Implementação e segurança

`src/components/trafego/meta/jornada.ts` governa apenas navegação; `rascunho.ts`
e os compiladores existentes preservam os contratos V1/V2. URLs antigas com
`etapa` e referência de operação continuam interpretadas.

O Assistente é aberto em iframe same-origin, com identificação de integração.
A ponte verifica origem **e** `contentWindow`, tipo, quantidade e formato das refs.
Não aceita URLs, tokens ou payload Meta como seleção. A referência de projeto não
troca o `src` do iframe em plena geração; só é usada na próxima entrada.
Escolher novos masters invalida compilação, validação e aprovação anteriores.

A seleção não é reserva durável, recibo de política ou autorização de upload.
O bloqueio conhecido R-01 do supply chain não foi contornado para aparentar
que geração e lançamento já estão integrados de ponta a ponta.

## Evidência e limites de QA

- Vitest: **102 testes passando, oito arquivos** — navegação, rascunho,
  contratos V1/V2, recibos/duplo clique, catálogos, Assistente, galeria e ponte
  em testes herméticos. Arquivo da jornada reexecutado após ajuste de tipagem:
  17/17, sem exceções não tratadas.
- Build de produção passou. TypeScript foi executado com `tsconfig.app.json`,
  não com o projeto raiz vazio: **76 erros fora dos arquivos alterados**.
  O gate TypeScript global não está verde. Não foi executada a suíte global backend.
- Chrome real, componentes de produção isolados, fixtures e rede externa bloqueada:
  375 e 1440 px, claro/escuro; destino, resultado e orçamento; nenhum overflow
  horizontal ou erro de página. Capturas locais em `/private/tmp/meta-journey-*`.
  Isso **não é** QA autenticado nem prova real de catálogos/geração/publicação.
- Harness temporário removido do projeto após a conferência.

## Fontes e decisão de produto

A skill Impeccable orientou a hierarquia, progressão, detalhes recolhidos, foco,
movimento curto e respeito a reduced-motion. Os tokens do produto foram mantidos;
a mudança para jornada guiada atende ao pedido explícito do operador.

O backend já possui `_promoted_object_v2` em
`backend/app/trafego/meta_execucao/compilador.py`. O SDK oficial da Meta documenta
campos como `custom_conversion_id` e `pixel_id` em
[AdPromotedObject](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adpromotedobject.py).
Isso não comprova elegibilidade nem aceitação de uma combinação na conta.
A página oficial de custom conversions consultada retornou HTTP 429;
nenhum default novo foi inferido dessa indisponibilidade.

P11-T05 e P11-T06 permanecem partial. Próximo marco: conferir esta jornada na
sessão do operador e fechar separadamente a passagem governada da peça gerada
para a conta, antes de prometer campanha criada com assets do Assistente.
