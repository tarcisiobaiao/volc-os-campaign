/**
 * O painel que diz por que este lançamento não anda.
 *
 * ## ⚠️ Ele NÃO recalcula prontidão
 *
 * A régua do veredito é do servidor. `Cockpit.bloqueios` já é o subconjunto de
 * `avisos` que IMPEDE avançar (`src/types/trafego.ts:203`), e o comentário
 * daquele campo registra o defeito que esta regra existe para não repetir: até
 * 03/09/2026 o engine barrava só `bloqueio` e a tela barrava tudo que não fosse
 * `informacao`/`atencao` — duas réguas para o mesmo veredito, divergindo na
 * primeira severidade nova. Este componente recebe a lista JÁ FILTRADA e
 * projeta. Não há `filter(severidade === ...)` aqui, e não pode haver.
 *
 * A contagem que ele mostra é do tamanho da lista recebida, não de uma
 * reclassificação — contar itens de uma lista pronta é projeção; reclassificar
 * severidade seria uma segunda régua com outro nome.
 *
 * ## ⚠️ Zero animação, no primeiro quadro
 *
 * `MOTION-AND-INTERACTION.md §2` é literal: "Bloqueio — nada. O bloqueio
 * aparece no primeiro quadro." Um impedimento que entra suave sugere que
 * chegou depois e que talvez saia sozinho. Não há classe de transição neste
 * arquivo, e a ausência é a especificação.
 *
 * ## Por que não é `role="alert"`
 *
 * O orçamento de regiões vivas da Bancada é de exatamente três, e nenhuma é
 * esta (`RESPONSIVE-AND-A11Y.md:218-226`): troca de parada, escada da ignição e
 * erro de operação. O bloqueio é estado da tela, não evento — ele está no fluxo
 * de leitura, com título próprio, e ser lido na ordem é melhor do que ser
 * gritado por cima da parada que o operador estava lendo.
 */
import React, { useId } from 'react';
import { Lock } from 'lucide-react';

import { horaDeLeitura } from '../inventario/formato';

import type { AvisoDoCockpit } from '@/types/trafego';

export const PainelDeBloqueio: React.FC<{
  /** JÁ FILTRADOS pelo servidor. Ver o ⚠️ do topo. */
  bloqueios: AvisoDoCockpit[];
  titulo?: string;
  /** ISO-8601. `null` = sem carimbo de leitura — nunca um relógio local. */
  lidoEm?: string | null;
}> = ({ bloqueios, titulo = 'Bloqueado', lidoEm }) => {
  const semente = useId();
  const idTitulo = `bloqueio-${semente}`;

  // Lista vazia não é "tudo certo": é ausência de bloqueio, e quem afirma que
  // está tudo certo é a parada, com a evidência dela. Um painel vazio dizendo
  // "nenhum bloqueio" ocuparia o lugar mais alto da tela com uma não-notícia.
  if (!bloqueios || bloqueios.length === 0) return null;

  const quantos =
    bloqueios.length === 1 ? '1 impedimento' : `${bloqueios.length} impedimentos`;
  const carimbo = (lidoEm && horaDeLeitura(lidoEm)) || null;

  return (
    <section
      aria-labelledby={idTitulo}
      className="shadow-card relative overflow-hidden rounded-lg border border-destructive/25 bg-destructive/[0.045] p-4 before:absolute before:left-0 before:top-0 before:h-[2px] before:w-full before:bg-destructive before:content-['']"
    >
      <div className="grid grid-cols-[24px_minmax(0,1fr)] gap-x-2 gap-y-3">
        <div className="flex h-6 items-center justify-center">
          <Lock className="h-4 w-4 text-destructive" aria-hidden />
        </div>
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 id={idTitulo} className="text-[0.9375rem] font-semibold leading-6 text-foreground">
            {titulo}
          </h3>
          <span className="text-[0.8125rem] text-muted-foreground">{quantos}</span>
        </div>

        <ul className="col-start-2 space-y-2">
          {bloqueios.map((b, i) => (
            <li
              key={`${b.codigo}-${i}`}
              className="border-t border-destructive/15 pt-2 first:border-0 first:pt-0"
            >
              {/* 14px: é texto que decide (`design.md:172`). O detalhe fica na
                  mesma frase do título porque separá-los em duas linhas fazia o
                  operador ler o rótulo e parar antes do motivo. */}
              <p className="text-sm leading-relaxed text-pretty text-foreground">
                <span className="font-medium">{b.titulo}</span>
                {b.detalhe ? <span className="text-muted-foreground"> — {b.detalhe}</span> : null}
              </p>
              {/* O código é o que o operador COPIA quando pede ajuda. Metadado,
                  13px, e nunca no lugar da frase. */}
              <p className="mt-1 text-[0.8125rem] text-muted-foreground">código {b.codigo}</p>
            </li>
          ))}
        </ul>

        {/* ⚠️ Sem carimbo, a tela DIZ que não tem carimbo. `new Date()` aqui
            mediria a hora de quem olha, não a idade do dado
            (`src/types/trafego.ts:206-213`). */}
        <p className="col-start-2 text-[0.8125rem] text-muted-foreground">
          {carimbo ? `lido em ${carimbo}` : 'sem carimbo de leitura'}
        </p>
      </div>
    </section>
  );
};
