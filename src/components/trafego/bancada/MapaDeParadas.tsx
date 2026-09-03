/**
 * O mapa das paradas do lançamento — onde o operador está e para onde pode ir.
 *
 * ## Por que é `<nav><ol>` e não um `Tabs`
 *
 * Aba troca a VISTA do mesmo objeto; parada é um lugar no caminho, e o caminho
 * tem ordem causal (`src/types/trafego.ts:252-261`: destino vem antes de
 * política porque a copy é escrita sob a vertical). Uma lista ordenada diz isso
 * ao leitor de tela sem que ninguém precise escrever a frase.
 *
 * ## ⚠️ Parada bloqueada NÃO é `<button disabled>`
 *
 * Botão desabilitado sai da ordem de foco. Quem navega por teclado nunca chega
 * nele, e a causa — que é a única informação útil de uma parada bloqueada —
 * desaparece junto. O contrato de tela é explícito
 * (`SCREEN-CONTRACTS.md:139`): `<span aria-disabled="true">` com a causa ligada
 * por `aria-describedby`. Um link que não leva a lugar nenhum também não deve
 * PARECER clicável, e por isso não há `<a>` sem `href` aqui.
 *
 * ## ⚠️ `nao_se_aplica` sai do denominador
 *
 * Um canal sem construtor de anúncio não tem parada de anúncio. Contá-la faria
 * a tela escrever "parada 3 de 6" num lançamento que tem cinco — e o operador
 * passaria o resto da sessão procurando a sexta. A lei está no tipo
 * (`src/types/trafego.ts:250`) e é medida em `__tests__/mapa-de-paradas.test.tsx`.
 *
 * ## O marcador
 *
 * ⚠️ `bg-primary`, e não aurora. `design.md:104` diz que a aurora nunca é
 * status operacional; marcar em que degrau de trabalho o operador está É
 * operacional. A aurora fica no `aurora-rule w-16` sob o H1, que é identidade.
 *
 * ⚠️ Só `transform` transiciona. A largura entra por `style`, fora da lista de
 * propriedades animadas, porque `design.md:122` proíbe animar `width` — animar
 * largura roda layout a cada quadro e é o defeito que `MOTION-AND-INTERACTION.md §8.2`
 * manda contar como zero. Sob `prefers-reduced-motion` o marcador salta: a
 * regra universal de `src/index.css:567-583` zera a duração com `!important`,
 * então não há utilitário `motion-reduce:` aqui — ele seria decoração morta.
 */
import React, { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { Circle, CircleCheck, CircleDot, CircleHelp, Lock, Minus } from 'lucide-react';
import { Link } from 'react-router-dom';

import { cn } from '@/lib/utils';
import type { EstadoDaParada, ParadaDaBancada, ParadaProjetada } from '@/types/trafego';

/**
 * Glifo, palavra e tinta por estado.
 *
 * A correspondência de bloqueio/indeterminação é a que `VISUAL-DIRECTION.md §5`
 * fixou para acabar com a divergência medida entre `canais/PortoesDoCanal.tsx:55-79`
 * (bloqueado em âmbar) e `canais/PainelDaMensuracao.tsx:67-74` (bloqueado em
 * vermelho): bloqueado é `destructive` com cadeado, "não se sabe" é `warning`
 * com interrogação, "não se aplica" é neutro com traço.
 */
const DESENHO: Record<
  EstadoDaParada,
  { Glifo: React.ComponentType<{ className?: string }>; palavra: string; tinta: string }
> = {
  confirmada: { Glifo: CircleCheck, palavra: 'confirmada', tinta: 'text-success' },
  atual: { Glifo: CircleDot, palavra: 'onde você está', tinta: 'text-primary' },
  pendente: { Glifo: Circle, palavra: 'pendente', tinta: 'text-muted-foreground' },
  bloqueada: { Glifo: Lock, palavra: 'bloqueada', tinta: 'text-destructive' },
  indeterminada: { Glifo: CircleHelp, palavra: 'não se sabe', tinta: 'text-warning' },
  nao_se_aplica: { Glifo: Minus, palavra: 'não se aplica', tinta: 'text-muted-foreground' },
};

/** O reserva para um estado que o servidor emita antes deste bundle existir.
 *  Uma navegação que some porque encontrou uma palavra nova é pior que uma que
 *  declara não reconhecer a palavra — é a mesma lei de `Selos.tsx:151-165`. */
const RESERVA = { Glifo: CircleHelp, palavra: 'estado não reconhecido', tinta: 'text-warning' };

/** Quem NÃO é alcançável. Bloqueada e "não se aplica" não têm para onde levar. */
function alcancavel(estado: EstadoDaParada): boolean {
  return estado !== 'bloqueada' && estado !== 'nao_se_aplica';
}

export const MapaDeParadas: React.FC<{
  paradas: ParadaProjetada[];
  atual: ParadaDaBancada;
  /** O integrador monta a URL: este componente não conhece rota. */
  hrefDaParada: (p: ParadaDaBancada) => string;
}> = ({ paradas, atual, hrefDaParada }) => {
  const semente = useId();
  const listaRef = useRef<HTMLOListElement | null>(null);
  const atualRef = useRef<HTMLLIElement | null>(null);
  const [marca, setMarca] = useState<{ x: number; largura: number } | null>(null);

  // A medida do marcador. `offsetLeft` é relativo ao `<ol>` porque ele é
  // `relative` — e é ele que rola na horizontal, então o marcador rola junto.
  useLayoutEffect(() => {
    const medir = () => {
      const li = atualRef.current;
      if (!li) {
        setMarca(null);
        return;
      }
      const x = li.offsetLeft;
      const largura = li.offsetWidth;
      // Comparar antes de gravar: o `ResizeObserver` dispara na observação
      // inicial, e um objeto novo a cada disparo renderizaria à toa.
      setMarca((antes) => (antes && antes.x === x && antes.largura === largura ? antes : { x, largura }));
    };
    medir();
    if (typeof ResizeObserver === 'undefined') return;
    const observador = new ResizeObserver(medir);
    if (listaRef.current) observador.observe(listaRef.current);
    return () => observador.disconnect();
  }, [atual, paradas]);

  // Telefone: a faixa rola dentro de si e a parada atual é trazida à vista
  // (`RESPONSIVE-AND-A11Y.md:71`). `block: 'nearest'` para não arrastar a
  // página na vertical. O `typeof` existe porque jsdom não implementa isto.
  useEffect(() => {
    const li = atualRef.current;
    if (!li || typeof li.scrollIntoView !== 'function') return;
    li.scrollIntoView({ block: 'nearest', inline: 'center' });
  }, [atual]);

  const aplicaveis = paradas.filter((p) => p.estado !== 'nao_se_aplica');
  const posicao = aplicaveis.findIndex((p) => p.parada === atual);
  const progresso =
    posicao >= 0
      ? `parada ${posicao + 1} de ${aplicaveis.length}`
      : `${aplicaveis.length} paradas neste lançamento`;

  return (
    <nav
      aria-label="paradas do lançamento"
      className="sticky top-0 z-20 border-b border-border bg-card"
    >
      <ol
        ref={listaRef}
        className="relative flex items-stretch gap-1 overflow-x-auto px-2"
      >
        {paradas.map((p) => {
          const desenho = DESENHO[p.estado] ?? RESERVA;
          const { Glifo } = desenho;
          const ehAtual = p.parada === atual;
          const idCausa = `causa-${semente}-${p.parada}`;
          // A causa acompanha o que não se pode visitar. Ela existe no DOM
          // (leitor de tela) e no `title` (mouse) — a faixa tem 48px de altura
          // e não comporta o parágrafo sem virar outra coisa.
          const causa =
            p.causa ??
            (p.estado === 'nao_se_aplica' ? 'não se aplica a este lançamento' : null);

          // ⚠️ `indeterminada` também tem causa (`src/types/trafego.ts:280`), e
          // ela é ALCANÇÁVEL — não passa pelo ramo do `aria-describedby`. Sem
          // esta linha, "não consegui ler o destino" viraria um rótulo cinza
          // sem motivo, que é exatamente o achatamento entre "não sei" e "falta
          // fazer" que o tipo proíbe.
          const complementoAudivel = alcancavel(p.estado) && causa ? `: ${causa}` : '';

          const miolo = (
            <>
              <Glifo className={cn('h-4 w-4 shrink-0', desenho.tinta)} aria-hidden />
              <span className="truncate">{p.rotulo}</span>
              {/* Cor e glifo não bastam: a palavra do estado vai para quem ouve. */}
              <span className="sr-only">
                {' '}
                — {desenho.palavra}
                {complementoAudivel}
              </span>
            </>
          );

          const base =
            'inline-flex min-h-11 items-center gap-2 rounded-md px-3 text-sm md:min-h-10';

          return (
            <li
              key={p.parada}
              ref={ehAtual ? atualRef : undefined}
              className="relative shrink-0 py-1"
            >
              {alcancavel(p.estado) ? (
                <Link
                  to={hrefDaParada(p.parada)}
                  aria-current={ehAtual ? 'step' : undefined}
                  title={causa ?? undefined}
                  className={cn(
                    base,
                    'transition-colors duration-150 ease-[cubic-bezier(0.22,1,0.36,1)]',
                    'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
                    ehAtual
                      ? 'font-semibold text-foreground'
                      : 'text-muted-foreground hover:bg-muted/40 hover:text-foreground',
                  )}
                >
                  {miolo}
                </Link>
              ) : (
                <>
                  <span
                    aria-disabled="true"
                    aria-describedby={causa ? idCausa : undefined}
                    title={causa ?? undefined}
                    className={cn(base, 'cursor-not-allowed text-muted-foreground')}
                  >
                    {miolo}
                  </span>
                  {causa && (
                    <span id={idCausa} className="sr-only">
                      {causa}
                    </span>
                  )}
                </>
              )}
            </li>
          );
        })}

        {/* O marcador. `transition-transform` e mais nada: a largura troca sem
            transição de propósito. */}
        {marca && (
          <span
            aria-hidden
            className="pointer-events-none absolute bottom-0 left-0 h-[3px] rounded-full bg-primary transition-transform duration-200 ease-[cubic-bezier(0.22,1,0.36,1)]"
            style={{ width: `${marca.largura}px`, transform: `translateX(${marca.x}px)` }}
          />
        )}
      </ol>

      {/* ⚠️ Não é `aria-live`. O orçamento de regiões vivas da Bancada é de três
          (`RESPONSIVE-AND-A11Y.md:220-226`) e o anúncio da troca de parada é da
          página, que sabe quando a troca aconteceu. Duas regiões dizendo a
          mesma frase falam por cima uma da outra. */}
      <p className="px-3 pb-1 text-[0.8125rem] text-muted-foreground">{progresso}</p>
    </nav>
  );
};
