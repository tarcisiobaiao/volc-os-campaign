# PRENSA: direção tipográfica v2, não substituição do motor

## Estado

Em prova visual. Base inspecionada: `2cb33f2`. Sem mudança de Chrome, plataforma ou geração paga.

## Diagnóstico anterior à prova de render

Referências de linha abaixo pertencem à base `2cb33f2`.

- `real_documento_cadunico_4x5`: título Inter grande, apoio/CTA pequenos e âncora quebrada no hífen. `prensa_tradutor.py:673` impõe ritmo único; `render.py:259` recebe papéis sem variação óptica; o fitter reduz papéis simultaneamente.
- `real_cartaz_consulta_fluxo_4x5`: checklist claro sobre mesa clara; título amarelo sobre faixa preta, embora o plano prometa zona clara. `prensa_tradutor.py:693` emite colunas sem superfície; `render.py:422` não usa `data-verify` nessas letras.
- Cenas da IA mostram pessoas, enquanto cenas PRENSA incluem documentos/objetos. Copy e cena diferem entre as duas pastas: essa comparação NÃO isola tipografia. O replay antes/depois usa os mesmos oito fundos e textos da PRENSA.
- A hipótese óptica é parcialmente correta: `render.py:212` só aplica `variacao` à segunda fonte do run. O papel principal ignora o campo. Declarar o token sozinho não resolve.
- A colocação automática atual só reposiciona `slides`; não governa o post de `layers`. Escolhi inicialmente medir o recorte efetivamente visível do frame aprovado, não deslocá-lo automaticamente para uma zona possivelmente incompatível com a cena. Isso não equivale a ligar o solver de composição.
- O scrim antigo mede percentil da foto e não os pixels dos glifos. A nova medição também é estatística, declarada como tal; não se deve chamar isso de pixel gate ou prometer garantia por glifo.
- Efeitos e dez fontes não devem ser usados todos numa peça. O catálogo inteiro pode estar disponível; cada registro escolhe vozes com intenção. Gráficos exigem dados: não serão inventados para ornamentação.

## Decisão

Direção versionada, replays antigos preservados. Papéis distintos por registro, prioridade explícita de redução do título antes do apoio, âncora não quebrável, contraste local medido em sRGB após object-fit, sem grão/vinheta globais obrigatórios. Tamanho de apoio parte de 16px a 540px de apresentação; CTA de 18px. São critérios declarados de design, não previsão de CTR.

## Limites

Texto CSS não produz oclusão pelo sujeito, perspectiva física ou letreiro inventado. Aprovação DOM não prova beleza nem contraste de todos os glifos. O aceite visual do operador permanece pendente até comparar o lote. O tradutor e o replay não equivalem à integração automática do endpoint HTTP: `/render` continua recebendo uma spec resolvida.

## Refinamento após revisão do Claude — 11/09/2026

Base desta rodada: `678d5d8`, incluindo os consertos do Claude para opt-in da skin e scrim legado com dimensões percentuais.

- A medição local deriva de uma única camada `image`, imediatamente abaixo do selo, e de seu `object_position`. O campo duplicado no scrim não é autoridade. Imagens transparentes, filtro CSS, origem ambígua ou pintura interposta não são medidas como foto isolada: exigem outro caminho de composição, ainda não implementado. O algoritmo continua aproximando o recorte cover com Pillow; não é a rasterização do Chrome nem garantia por glifo.
- O véu v2 dissolve apenas **fora** da zona medida, com máscara separável e patamar opaco dentro dela. Isso elimina a descontinuidade de background + box-shadow sem diminuir o alpha que fundamenta o recibo. Não se deve confundir suavizar a borda com descobrir a posição do sujeito. Ligar `colocacao.auto`, por si só, não corrige a forma da máscara.
- O recibo do DOM lê `wght` de `font-variation-settings` quando existe, incluindo runs, e carrega fontes também pelo estilo. A poda de fontes vale para a direção v2: família, faixa de pesos e estilo devem cobrir os papéis efetivamente usados; segunda voz de run preserva seus defaults itálicos. A validação SHA do catálogo permanece antes da poda.
- Sangria pinta acima da sombra difusa. CTA passa a ter piso32px, distinguindo-se do apoio24px no banner; corpos finais dependem do fitter e estão nos recibos.
- Precisão do vocabulário: Archivo e Barlow usados como display **não têm `opsz`**. O renderer agora respeita variações no papel principal, mas o eixo óptico se aplica aos papéis Inter/Source Serif que o declaram. Cinco registros nomeados não equivalem a cinco famílias ou cinco vozes tipográficas independentes; foto_crua e cartaz compartilham a combinação.

Prova comportamental em `tools/prensa/provar_chrome.py`, executada pelo replay offline no Chrome original. Evidências e limites: `docs/closure/prensa-refino-20260911/HANDOFF.md`. Sem alteração do endpoint, ativação padrão, banco, provider ou serviço em execução.
