/**
 * A mesa de proporções: as peças prontas de um trabalho lado a lado, na mesma
 * altura, e a moldura de Stories sobre a 9:16.
 *
 * ## Por que existe
 *
 * Um trabalho multi-proporção (Prensa `artboard.variants`, W6) entrega a mesma
 * peça em 1:1, 4:5, 9:16 e 1,91:1. A lista de peças mostra cada uma com sua
 * ficha, e é a ficha que serve para decidir sobre UMA peça. A pergunta que o
 * operador tem antes disso é outra: "a família está coerente?". Ela só se
 * responde olhando as proporções juntas, na mesma escala vertical, sem rolar.
 *
 * A moldura de Stories (EV-META-20) entra só na 9:16 e é uma régua de prévia,
 * não um veredito: ver `zonaSegura.ts`.
 */
import React from 'react';
import { Frame } from 'lucide-react';

import { cn } from '@/lib/utils';
import type { Rendition } from '@/types/criativos';
import {
  FONTE_DA_ZONA_SEGURA,
  fraseDaZonaSegura,
  proporcaoLegivel,
  zonaSeguraDeStories,
  type ZonaSegura,
} from './zonaSegura';

/**
 * A moldura sobre uma prévia 9:16. As faixas são desenhadas em % para valer
 * em qualquer escala da imagem; o contêiner abraça a `<img>` (inline-block),
 * então 100% aqui é a imagem, não a coluna.
 */
export const MolduraDeStories: React.FC<{
  zona: ZonaSegura;
  visivel: boolean;
  children: React.ReactNode;
  className?: string;
}> = ({ zona, visivel, children, className }) => {
  const { pct } = zona;
  const faixa = 'pointer-events-none absolute bg-foreground/45';
  return (
    <span className={cn('relative inline-block align-top', className)}>
      {children}
      {visivel && (
        <span aria-hidden data-moldura-stories className="absolute inset-0">
          <span className={cn(faixa, 'inset-x-0 top-0')} style={{ height: `${pct.topo}%` }} />
          <span className={cn(faixa, 'inset-x-0 bottom-0')} style={{ height: `${pct.base}%` }} />
          <span
            className={cn(faixa, 'left-0')}
            style={{ top: `${pct.topo}%`, bottom: `${pct.base}%`, width: `${pct.esquerda}%` }}
          />
          <span
            className={cn(faixa, 'right-0')}
            style={{ top: `${pct.topo}%`, bottom: `${pct.base}%`, width: `${pct.direita}%` }}
          />
          <span
            className="absolute border border-dashed border-background/90"
            style={{
              top: `${pct.topo}%`,
              bottom: `${pct.base}%`,
              left: `${pct.esquerda}%`,
              right: `${pct.direita}%`,
            }}
          />
        </span>
      )}
    </span>
  );
};

/** O botão que liga e desliga a moldura. Um só por tela: a escolha vale para todas. */
export const AlternarMoldura: React.FC<{
  ligada: boolean;
  aoAlternar: () => void;
}> = ({ ligada, aoAlternar }) => (
  <button
    type="button"
    aria-pressed={ligada}
    onClick={aoAlternar}
    className={cn(
      'inline-flex min-h-9 items-center gap-2 rounded-md border px-3 text-[13px] font-medium',
      'transition-colors duration-150 ease-out',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
      ligada
        ? 'border-primary/50 bg-primary/10 text-foreground'
        : 'border-input bg-card text-foreground hover:bg-muted/60',
    )}
  >
    <Frame className="h-4 w-4 text-primary" aria-hidden />
    {ligada ? 'Zona de Stories visível' : 'Mostrar zona de Stories'}
  </button>
);

export const MesaDeProporcoes: React.FC<{
  pecas: Rendition[];
  molduraLigada: boolean;
  aoAlternarMoldura: () => void;
}> = ({ pecas, molduraLigada, aoAlternarMoldura }) => {
  // Só o que tem arquivo entra na mesa. Peça sem prévia continua na lista,
  // com o motivo; aqui ela seria um buraco sem explicação.
  const comArquivo = pecas.filter((p) => p.estado === 'pronta' && p.previewUrl);
  if (comArquivo.length < 2) return null;

  const story = comArquivo
    .map((p) => zonaSeguraDeStories(p.larguraPedida, p.alturaPedida))
    .find((z): z is ZonaSegura => z !== null);

  return (
    <section
      aria-label="Mesa de proporções"
      className="rounded-[10px] border border-border bg-card p-3 shadow-card sm:p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="kicker">Mesa de proporções</p>
          <p className="mt-1 max-w-[70ch] text-[13px] leading-relaxed text-muted-foreground">
            {comArquivo.length} peças prontas na mesma altura, para conferir a família antes de
            decidir peça a peça.
          </p>
        </div>
        {story && <AlternarMoldura ligada={molduraLigada} aoAlternar={aoAlternarMoldura} />}
      </div>

      {/* Rola DENTRO da mesa, nunca a página: no telefone a família inteira
          não cabe, e a página não pode ganhar barra horizontal. */}
      <ul className="-mx-1 mt-3 flex gap-4 overflow-x-auto px-1 pb-2">
        {comArquivo.map((p) => {
          const zona = zonaSeguraDeStories(p.larguraPedida, p.alturaPedida);
          const img = (
            <img
              src={p.previewUrl as string}
              alt={`Peça ${p.rotulo} na proporção ${proporcaoLegivel(p.larguraPedida, p.alturaPedida)}`}
              loading="lazy"
              decoding="async"
              className="block h-36 w-auto max-w-none rounded-sm bg-muted/40 sm:h-48"
            />
          );
          return (
            <li key={p.id} className="shrink-0">
              <figure>
                <div className="overflow-hidden rounded-md border border-border">
                  {zona ? (
                    <MolduraDeStories zona={zona} visivel={molduraLigada}>
                      {img}
                    </MolduraDeStories>
                  ) : (
                    img
                  )}
                </div>
                <figcaption className="mt-2 flex flex-col">
                  <span className="font-display text-sm font-semibold text-foreground">
                    {proporcaoLegivel(p.larguraPedida, p.alturaPedida)}
                  </span>
                  <span className="text-[12px] tabular-nums text-muted-foreground">
                    {p.larguraPedida} x {p.alturaPedida}
                  </span>
                </figcaption>
              </figure>
            </li>
          );
        })}
      </ul>

      {story && molduraLigada && (
        <p className="mt-2 max-w-[78ch] text-[12px] leading-relaxed text-muted-foreground">
          {fraseDaZonaSegura(story)}
        </p>
      )}
      {story && !molduraLigada && (
        <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">
          A 9:16 vai para Stories e Reels. Ligue a moldura para ver o que a interface cobre (
          {FONTE_DA_ZONA_SEGURA}).
        </p>
      )}
    </section>
  );
};
