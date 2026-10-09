# A/B real — JEV v2 + arquiteto GPT vs Gemini grounded

Data: 08/10/2026. Tema congelado: Gás do Povo. Escopo: somente arquitetura; nenhuma redação, imagem, publicação ou escrita em WordPress, Supabase ou Ads.

## Pergunta

O `gemini-3.8-flash` com Google Search, combinado ao perfil e à revisão de arestas do JEV v2, consegue substituir o `gpt-6.1-sol` como arquiteto com mais velocidade e qualidade igual ou superior?

## Desenho

- Mesmo `brief_jev_v2.json` e mesmo contrato para os dois lados.
- JEV v2 pré-arquitetura compartilhado e JEV v2 pós-arquitetura em ambos.
- GPT: uma chamada no plano ChatGPT.
- Gemini: pesquisa grounded e arquitetura JSON em duas fases internas.
- Dois julgamentos cegos com `gpt-6-astra`, invertendo X/Y.
- Ambos resultaram em 5 páginas (`LP`, `PRESELL`, 3 `SOLUTION`), 7 CTAs distintos e nenhum bloqueio estrutural fatal.

## Resultado

| Critério | GPT-6.1-sol | Gemini 3.8 Flash grounded |
|---|---:|---:|
| Tempo do arquiteto | ~239–247 s | 178,12 s (28,97 + 149,15) |
| Julgamento cego — ordem 1 | 86/100 | 63/100 |
| Julgamento cego — ordem 2 | 83/100 | 63/100 |
| Search | não | 4 consultas, 15 chunks grounded |
| Normalização | válida, 0 aviso | válida, 1 campo fora do vocabulário descartado |
| Revisor estrutural | 1 aviso | 2 avisos |
| JEV pós | sem fallback | sem fallback |

O Gemini foi cerca de 26% mais rápido, mas perdeu com confiança alta nas duas ordens. Seu ganho real foi a concretude da primeira dobra e o apelo imediato dos CTAs. As perdas foram mais importantes para o negócio:

- transformou detalhes operacionais variáveis em regras fechadas;
- classificou como prematuras saídas oficiais necessárias para consulta, validação e revenda;
- presumiu uma sequência única para leitores em estados diferentes;
- teve notas 4/10 em progressão, 4/10 em realidade atual, 5/10 em compatibilidade de monetização e 6/10 em segurança de política nos dois julgamentos.

O GPT foi menos concreto na primeira dobra, mas separou enquadramento, seleção individual, validação, revenda/cobranças e pendência cadastral; permitiu saída oficial quando ela resolvia a tarefa e tratou procedimentos incertos como requisitos a verificar.

## Leitura do JEV

O JEV v2 trouxe sinal útil e barato para os dois lados, principalmente em motivação e congruência CTA→destino. Porém, aprovou arestas de um plano que os juízes consideraram estruturalmente inferior. Logo:

- JEV é adequado como sensor de emoção e lint consultivo de arestas/CTAs;
- JEV não deve decidir o grafo, verdade factual, momento da saída oficial ou promoção do modelo;
- `jev_enabled=false` deve permanecer como padrão até existir coorte com sinal real.

## Decisão 80/20

Não promover o Gemini grounded a arquiteto padrão. A composição mais promissora para uma eventual próxima rodada é: Gemini Search produz um pacote curto de atualidade; JEV v2 produz o perfil e revisa as arestas; GPT-6.1-sol continua responsável pelo grafo tipado; portões determinísticos decidem schema, evidência, saída oficial e segurança.

Essa composição ainda não foi testada e não deve ser tratada como melhoria comprovada. Antes disso, a alavanca mais barata é corrigir no prompt GPT a resposta imediata abstrata, pois os juízes deram ao Gemini vantagem apenas nessa dimensão e em CTAs mais concretos.

## Integração do SDK

Duas tentativas descartadas foram preservadas como diagnóstico:

- `models.generate_content` com Search + JSON estruturado retornou arquitetura vazia;
- `interactions.create` devolveu `requires_action` com `google:search`, sem executar a busca no servidor.

O caminho confiável no SDK instalado foi pesquisa grounded e arquitetura JSON em duas fases. Isso prova a integração, não a superioridade do modelo.

## Artefatos sanitizados

Fora do repositório, em `/Users/mac/Desktop/VOLC-OS-CAMPAIGN/canarios/jev-gemini-architect-ab-20261008/`: `brief_jev_v2.json`, `gemini_research_v3.txt`, `raw_gpt_v2.json`, `raw_gemini_v3.json`, `plan_gpt_final.json`, `plan_gemini_final.json`, `jev_post_gpt_final.json`, `jev_post_gemini_final.json` e `receipt_final.json`.

## Estado honesto

P10-T22 permanece `partial`. Houve melhora de latência, mas não equivalência de qualidade nem prova de CTR, progressão, receita por sessão ou ROI. Nada foi publicado.

Referências: [Gemini 3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash), [Grounding with Google Search](https://ai.google.dev/gemini-api/docs/google-search/), [Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output).
