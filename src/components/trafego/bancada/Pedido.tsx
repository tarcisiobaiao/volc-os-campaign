/**
 * O Pedido — a projeção persistente do que será criado.
 *
 * ## ⚠️ Projeção PURA. Ele não decide nada
 *
 * `SCREEN-CONTRACTS.md:309`: toda linha tem rótulo, valor, fonte e — quando é
 * medida — frescor; `FALTA` vem do servidor; `próximo ato` é frase, não botão.
 * Este componente não filtra, não soma, não conclui e não oferece ação. No dia
 * em que ele calcular qualquer coisa, existirão duas réguas para o mesmo
 * veredito — que é o defeito já registrado em `src/types/trafego.ts:184-200`,
 * onde o engine barrava só `bloqueio` e a tela barrava quase tudo.
 *
 * ## ⚠️ Ele NÃO é `aria-live`
 *
 * O orçamento de regiões vivas da Bancada é de três, e `RESPONSIVE-AND-A11Y.md:227`
 * exclui o Pedido por nome: "Ele muda a cada decisão e falaria o tempo todo".
 * A pista equivalente é visual — a tinta de 1200ms na linha alterada, que é da
 * página — e a associação por `aria-describedby` a partir do controle que
 * causou a mudança.
 *
 * ## ⚠️ Ausência é "—" e a companhia de quem não leu
 *
 * Nunca `0`, nunca célula vazia (`src/types/trafego.ts:289`). A palavra de
 * ausência entra por `LinhaDeFato`, que também dá o texto alternativo do
 * travessão para quem ouve (`RESPONSIVE-AND-A11Y.md §5.5`).
 */
import React, { useId } from 'react';
import { ChevronDown, ShieldCheck, TriangleAlert } from 'lucide-react';

import { horaDeLeitura } from '../inventario/formato';

import { ChipDeEstado } from './ChipDeEstado';
import { LinhaDeFato } from './BlocoDeEvidencia';

import type { LinhaDoPedido } from '@/types/trafego';

export const Pedido: React.FC<{
  linhas: LinhaDoPedido[];
  /** Vem do servidor. Esta tela não deduz falta a partir de linha vazia. */
  faltas: string[];
  /** FRASE, não botão. `null` = ninguém declarou o próximo ato. */
  proximoAto: string | null;
  lidoEm?: string | null;
}> = ({ linhas, faltas, proximoAto, lidoEm }) => {
  const semente = useId();
  const idTitulo = `pedido-${semente}`;
  const lista = faltas ?? [];
  const carimbo = (lidoEm && horaDeLeitura(lidoEm)) || null;

  return (
    <section
      aria-labelledby={idTitulo}
      className="bancada-order-card shadow-card"
    >
      <div className="bancada-order-head">
        <div>
          <span className="kicker text-muted-foreground">Resumo persistente</span>
          <h2 id={idTitulo} className="mt-1 font-display text-xl font-semibold tracking-tight text-foreground">
            O pedido
          </h2>
        </div>
        {lista.length > 0 && (
          // ⚠️ Caixa de sentença. `VISUAL-DIRECTION.md §8` proíbe caixa alta
          // fora do `.kicker`, e o chip de estado é 13px em caixa de sentença
          // por decisão de geometria (`design.md:56-58`). A palavra do servidor
          // é `FALTA`; o que muda aqui é o desenho dela, não o fato.
          <ChipDeEstado
            glifo={TriangleAlert}
            palavra={`Falta (${lista.length})`}
            descricao="o servidor recusou o pedido enquanto estas condições não forem satisfeitas"
            tom="atencao"
          />
        )}
      </div>

      <div className="bancada-order-safety">
        <ShieldCheck className="h-4 w-4 shrink-0 text-success" aria-hidden />
        <p>
          <strong>Nasce pausada.</strong> Esta bancada prepara e prova; ativar é outro ato.
        </p>
      </div>

      <details className="bancada-order-details" open={linhas.length <= 4}>
        <summary>
          <span>Decisões do pedido</span>
          <ChevronDown className="h-4 w-4" aria-hidden />
        </summary>
        <div className="divide-y divide-border/60 pb-1 pt-2">
          {linhas.length === 0 ? (
            <p className="py-2 text-sm text-muted-foreground">
              nenhuma decisão registrada ainda neste pedido
            </p>
          ) : (
            linhas.map((l, i) => (
              <LinhaDeFato
                key={`${l.rotulo}-${i}`}
                rotulo={l.rotulo}
                valor={l.valor}
                fonte={l.fonte}
                frescor={l.frescor ?? null}
                ausencia="—"
              />
            ))
          )}
        </div>
      </details>

      {lista.length > 0 && (
        <details className="bancada-order-details bancada-order-missing bg-muted/20">
          <summary>
            <span>O que ainda falta ({lista.length})</span>
            <ChevronDown className="h-4 w-4" aria-hidden />
          </summary>
          <ul className="list-disc space-y-1 pb-1 pl-5 pt-2 text-sm leading-relaxed text-pretty text-muted-foreground">
            {lista.map((f, i) => <li key={`${f}-${i}`}>{f}</li>)}
          </ul>
        </details>
      )}

      <div className="bancada-order-next">
        <p className="text-sm leading-relaxed text-pretty text-foreground">
          <span className="text-muted-foreground">Próximo ato: </span>
          {/* Ausência DECLARADA. Uma frase que some lê-se como "não há mais
              nada a fazer", que é a conclusão errada. */}
          {proximoAto ?? (
            <span className="text-muted-foreground">nenhum próximo ato declarado</span>
          )}
        </p>
        <p className="text-[0.8125rem] text-muted-foreground">
          {carimbo ? `lido em ${carimbo}` : 'sem carimbo de leitura'}
        </p>
      </div>
    </section>
  );
};
