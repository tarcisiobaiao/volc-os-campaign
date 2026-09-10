# Meta creative closure — implementação local, validação parcial

Worktree: `/private/tmp/volc-os-operacao-80-20`, branch `execution/volc-os-operacao-80-20`, HEAD base `be4483b19f62d638909ca22ee523ec92816e1d14`. Alterações pré-existentes preservadas; sem push, deploy ou modificação do Webgo.

## Defeito que afetava a imagem

O adaptador OpenAI adicionava “Sem texto, sem letras…” depois de receber headline/complemento/CTA. Não havia compositor tipográfico posterior: o compositor existente cola fotografias. Uma rendition real antiga 4x5 foi inspecionada: calendário/botijão ilustrados, barras simulando texto e ausência da headline pedida. O master antigo tinha `insumo_sanitizado=null`: reconstruímos a contradição pelo código e briefing, não recuperamos um request histórico que nunca foi persistido.

Agora a saída estratégica pode conter `direcao_de_arte`. A ponte gera uma CreativeSpec versionada por formato, separa texto interno de copy externa e compila composição, margem, hierarquia, contraste e textos exatos. O provider continua `gpt-image-2`, `quality=medium`, sem fallback. Spec vai para `briefing.referencias`; prompt efetivo para `master.insumo_sanitizado`, não para DTO público.

Decisão: usar o suporte tipográfico do provider nesta versão, sem adicionar outro compositor de texto. Medidas no prompt são orientações, não garantia pixel a pixel. A spec permanece `humana_pendente`; HTTP200 não significa aprovação visual. Fotografia, colagem e inspiração continuam modos distintos. Não foi acrescentada visão paga.

## Interface e contexto

- URL opcional da LP, leitura segura HTTPS com limites e proteção SSRF/DNS/redirect.
- Fatos com trechos e fonte; público/momento como hipóteses. Aplicação explícita preserva textos do operador.
- Editar fato, mudar URL ou falhar numa reanálise remove a atribuição antiga de fonte, sem apagar texto humano.
- Objetivo não é perguntado no briefing standalone; criador pode herdar objetivo e URL pelo iframe.
- Estratégia mostra headline/complemento/CTA antes da geração, sem fingir uma prévia da composição final.
- Nova versão explícita preserva imagens antigas; o mesmo UUID é reutilizado em retry/reload. Alterar a seleção/formato sob a mesma versão retorna409.
- QA corrigiu compressão de títulos mobile e coluna cinza vazia para uma direção com peça única.

## Matriz Meta

| Caminho | Implementação/prova desta rodada | Limite |
|---|---|---|
| Estático novo | Fluxo existente preservado; duplicar mantém copy/conjunto e limpa mídia/aprovações | Sem nova publicação nesta rodada |
| Asset feed / variações | Descoberta diferencia origem multiasset | ID do post não é promessa de transportar todas as regras |
| Flexível | V2 até executor/readback; `creative_asset_groups_spec` em `/ads`; 1 anúncio por conjunto, grupos preservados | Imagens + Vendas; elegibilidade e `text_type=description` ainda sem validação remota |
| Post original | Identidade original mantida quando elegível | Novo arquivo/imagem não herda engajamento |
| Pack | Append/revisões e seleção existentes preservados; testes de biblioteca/reuso passam | Não é dark post por si só |

Fonte do campo flexível: [SDK oficial Meta](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/adobjects/adaccount.py) e guia oficial fornecido pelo operador. Algumas páginas Meta retornaram429; não tratamos a indisponibilidade como confirmação de elegibilidade. Contrato do motor consultado em [modelo](https://developers.openai.com/api/docs/models/gpt-image-2) e [geração de imagens](https://developers.openai.com/api/docs/guides/image-generation).

## Banco real

Migration `20260909234342_creative_generation_versions.sql` aplicada no Supabase oficial. Adiciona `geracao_ref` e `plano_sha256`, substitui unicidade por `(run_ref, creative_ref, geracao_ref)`. Quatro registros históricos preservados como `original`; RLS/FORCE RLS e grants preservados. PostgREST confirmou novas colunas. Backup e provas em `EVIDENCE.json`.

Prova LP real: criou uma operação técnica, salvou/releu input JSONB idêntico, recusou outro owner no repositório e arquivou a operação. Sem run, aprovação, imagem ou chamada paga. Esse teste prova o filtro do repositório; não equivale a login real de dois usuários.

## Testes e visual

- Root:116 testes contrato/spec/contexto/rotas e186 testes motor/execução/estúdio; scanner de segredos e diff-check passaram.
- Meta:195 backend e51 frontend focais, executados pelo subagente.
- Assistente:62 frontend. Build Vite passou; TypeScript global segue76 erros fora do escopo (nenhum em criativo/Meta tocado).
- Meta ampliado:1 teste estático pré-existente falha exigindo literal no wrapper de dashboard não alterado. Não ocultado nem atualizado para silenciar.
- Chrome isolado, componentes reais com fixtures:375/768/1440 claro/escuro, teclado, loading/erro. Zero overflow/runtime error. Fontes remotas foram bloqueadas no harness; capturas usam fallback configurado.
- Capturas antes/depois: `/private/tmp/volc-lp-browser-oA7VcR/after/`; Meta: `/private/tmp/meta-flexible-{largura}-{tema}.png`. São evidências temporárias, não uma galeria de imagens geradas.

## Ainda necessário para encerrar

Não houve canário pago nesta rodada. A matriz de duas direções já aprovadas × dois formatos está preparada, mas a criação de sessão temporária de QA aguarda consentimento específico do operador. A ferramenta recusou gerar/guardar credencial sem essa confirmação; não houve contorno nem token criado. Sem sessão, não afirmamos QA autenticado, qualidade das quatro novas imagens ou persistência de novos masters por HTTP.

Nenhuma nova campanha, anúncio, upload à Meta ou ativação foi executada. PAUSED/aprovação continuam exigidos. Estado **partial**, não production-ready. Próximo passo: sessão autorizada → plano de4 renders → geração limitada → arquivos e links → inspeção visual → readback. Nenhuma tentativa paga ilimitada.

## Como validar localmente

Abra `http://localhost:8080/trafego/meta/assistente-criativo`, analise uma LP, revise os fatos e gere uma estratégia. Em um projeto que já tem imagens, use **Preparar nova versão** em Produção, confira formatos/quantidade e autorize o custo explicitamente. Na montagem, **Duplicar e trocar imagem** deixa a nova imagem pendente sem alterar a peça original. Flexível continua sujeito à validação da Meta.

Memória: P11-T17 e `doc:meta-creative-closure-20260909`; capacidades relacionadas `cap_creative_engines`/`cap_meta_ads`. P11-T02/T04/T05/T16 não promovidas a done.
