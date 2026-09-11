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
