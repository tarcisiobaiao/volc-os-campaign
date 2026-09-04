/**
 * Um par rótulo/valor em que o valor pode legitimamente ser desconhecido.
 *
 * ## Por que ele saiu de dentro dos painéis
 *
 * Este componente estava TRIPLICADO, byte a byte, em três arquivos do cockpit
 * de canais: `PainelDeCanais.tsx:52-74`, `PainelDaMensuracao.tsx:106-128` e
 * `PlanoDeMensuracao.tsx:33-55`. As três cópias foram conferidas por `diff`
 * antes da consolidação e eram idênticas — nenhuma divergência de comportamento
 * precisou ser preservada.
 *
 * Três cópias de um mesmo par rótulo/valor divergem no primeiro ajuste de
 * tipografia, e a que diverge é justamente a do painel que ninguém abre todo
 * dia. Como este é o átomo que carrega TODO fato do cockpit — meta efetiva,
 * frescor, destino de conversão —, uma divergência aqui vira três hierarquias
 * de leitura diferentes para a mesma classe de informação.
 *
 * ## As duas correções de contrato que vieram junto
 *
 * 1. **A ressalva subiu de 11px para 14px.** `design.md:172` diz que "essential
 *    actions and explanatory text never drop below 14 pixels", e
 *    `VISUAL-DIRECTION.md §3` repete em regra dura: "Nenhum texto que sustenta
 *    decisão abaixo de 14px. Causa de bloqueio, exigência de portão, ressalva
 *    (…): 14px". A ressalva é exatamente isso — é ela que impede o operador de
 *    ler "resolvido" como "a ingestão offline funciona".
 * 2. **O rótulo deixou a caixa alta de 11px.** `VISUAL-DIRECTION.md §3` fixa o
 *    piso em 12px e manda "rótulo de coluna repetido" em CAIXA DE SENTENÇA;
 *    `design.md:174` diz que caixa alta é auxílio de navegação, não textura —
 *    e um `<dl>` com oito rótulos em versalete é textura.
 *
 * A cor saiu da paleta crua de ardósia — escrita duas vezes por linha, uma para
 * cada tema — e passou a ser `text-muted-foreground`, o token que o claro e o
 * escuro já calibram para contraste (`src/index.css:46,188`).
 */
import React from 'react';

export function Fato({
  rotulo,
  valor,
  ressalva,
}: {
  rotulo: string;
  valor: React.ReactNode;
  /** O que o valor NÃO afirma. `null` = não há ressalva, e não "está tudo bem". */
  ressalva?: string | null;
}) {
  return (
    <div>
      <dt className="text-xs font-medium leading-5 text-muted-foreground">
        {rotulo}
      </dt>
      <dd className="text-sm font-medium text-foreground">{valor}</dd>
      {ressalva ? (
        <p className="mt-0.5 text-sm leading-snug text-muted-foreground text-pretty">
          {ressalva}
        </p>
      ) : null}
    </div>
  );
}

export default Fato;
