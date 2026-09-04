# Débitos cosméticos — não bloqueiam a inspeção

Achados da rodada adversarial classificados como **não bloqueantes**. Nenhum
impede o proprietário de usar a tela nem cria risco de gasto.

1. `PortaoDePolitica.tsx:159` ainda escreve que campanha com `limitacao` "sobe com restrição" — a parada que o monta agora barra. Texto contradiz a régua.
2. `PortaoDePolitica.tsx` inteiro está em 11px, abaixo do piso de 14px que esta entrega impôs.
3. Falha de leitura da copy vira TAREFA ("escrever o anúncio") em vez de indeterminação — e a tarefa custa ~174 s de LLM pago.
4. A demoção da ação primária quando o funil já tem campanha no ar existia na tela antiga e não foi reconstruída (o fato aparece no Pedido e no `JaNoAr`, mas o botão não muda).
5. A prop `desatualizada` de `CartaoCopy` existe e ninguém a preenche: o aviso de "copy escrita para outra seleção" foi perdido.
6. Duas das três regiões `aria-live` que o contrato de acessibilidade exige não existem.
7. `keywords_fora` viaja no pedido e nada na tela escreve nele: campo morto.
8. Ocorrências de `text-white/30..45` na Ignição reprovam AA; `/45` fica na linha dos 4,5:1.
9. O botão de copiar identificador do recibo tem 32px, abaixo do piso de 44px do próprio projeto.
10. `ChipDeEstado` entrega a descrição só por `title` + `sr-only`: no telefone o motivo do estado é invisível para quem enxerga.
