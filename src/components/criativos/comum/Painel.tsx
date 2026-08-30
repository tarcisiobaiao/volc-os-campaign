/**
 * A moldura das telas do Estúdio: cabeçalho de página e seção de trabalho.
 *
 * ## Por que o cabeçalho é um componente e não JSX solto
 *
 * Porque o DESIGN.md dá a ele um ORÇAMENTO: 220 a 280px no desktop, para que a
 * primeira linha operacional apareça sem rolar. Um cabeçalho por página, cada
 * um com seu espaçamento, estoura o orçamento sem ninguém perceber. Aqui a
 * altura é uma decisão só, e o `min-h`/`max-w` guardam a promessa.
 *
 * ## Por que `Secao` não é `Card`
 *
 * Porque o DESIGN.md proíbe cartão dentro de cartão. `Secao` é uma superfície
 * de trabalho com borda e fundo, não uma pilha de elevação: dentro dela vão
 * linhas e listas, nunca outra `Secao`.
 *
 * ## Os três planos desta área, e qual fundo cada um usa
 *
 * 1. **Canvas** (`bg-background`): a página.
 * 2. **Superfície de trabalho** (`bg-card`): `CabecalhoDoEstudio` e `Secao`, e
 *    também os cartões da biblioteca, que vivem direto no canvas.
 * 3. **Região dentro da superfície** (`bg-muted/30`): peça do job, item de
 *    fila, opção de escolha. Fundo sutil e hairline, nunca um segundo `bg-card`
 *    com sombra, que é o que produz a pilha de cartões que o DESIGN.md recusa.
 *
 * Nenhum dos três usa sombra em estado normal.
 */
import React from 'react';
import { ChevronLeft } from 'lucide-react';
import { Link } from 'react-router-dom';

import { cn } from '@/lib/utils';

export const CabecalhoDoEstudio: React.FC<{
  /** Rótulo curto de contexto, em caixa alta. Navegação, não decoração. */
  kicker?: string;
  titulo: string;
  /** Uma frase que diz para que a tela serve. */
  proposito: string;
  /** No máximo UM botão primário por região. */
  acao?: React.ReactNode;
  voltar?: { para: string; rotulo: string };
  /** Fatos curtos de frescor e contagem, abaixo do propósito. */
  situacao?: React.ReactNode;
  className?: string;
}> = ({ kicker, titulo, proposito, acao, voltar, situacao, className }) => (
  <header className={cn('border-b border-border bg-card', className)}>
    <div className="mx-auto w-full max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8">
      {voltar && (
        <Link
          to={voltar.para}
          className={cn(
            'mb-3 inline-flex min-h-[1.75rem] items-center gap-1 rounded-sm text-[13px] text-muted-foreground',
            'transition-colors duration-150 ease-out hover:text-foreground',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
          )}
        >
          <ChevronLeft className="h-4 w-4" aria-hidden />
          {voltar.rotulo}
        </Link>
      )}
      <div className="flex flex-wrap items-start justify-between gap-x-8 gap-y-4">
        <div className="min-w-0 max-w-[70ch]">
          {kicker && <p className="kicker">{kicker}</p>}
          <h1 className="mt-1 text-balance font-display text-[1.75rem] font-semibold leading-tight tracking-tight text-foreground lg:text-[2rem]">
            {titulo}
          </h1>
          <p className="mt-2 text-pretty text-sm leading-relaxed text-muted-foreground">
            {proposito}
          </p>
        </div>
        {acao && <div className="flex shrink-0 flex-wrap items-center gap-2">{acao}</div>}
      </div>
      {situacao && <div className="mt-4">{situacao}</div>}
    </div>
  </header>
);

export const Corpo: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className,
}) => (
  <div className={cn('mx-auto w-full max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8', className)}>
    {children}
  </div>
);

export const Secao: React.FC<{
  titulo: string;
  /** Frase curta que explica o que a seção afirma. */
  descricao?: string;
  acao?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  /** `id` do título, para `aria-labelledby` de quem precisar. */
  id?: string;
}> = ({ titulo, descricao, acao, children, className, id }) => {
  const idTitulo = id ?? `secao-${titulo.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
  return (
    <section
      aria-labelledby={idTitulo}
      className={cn('rounded-lg border border-border bg-card', className)}
    >
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2 border-b border-border px-4 py-3 sm:px-5">
        <div className="min-w-0 max-w-[70ch]">
          <h2
            id={idTitulo}
            className="font-display text-base font-semibold tracking-tight text-foreground"
          >
            {titulo}
          </h2>
          {descricao && (
            <p className="mt-0.5 text-pretty text-[13px] leading-relaxed text-muted-foreground">
              {descricao}
            </p>
          )}
        </div>
        {acao && <div className="shrink-0">{acao}</div>}
      </div>
      <div className="px-4 py-4 sm:px-5">{children}</div>
    </section>
  );
};

/** Par rótulo/valor de uma ficha técnica. Alinhado, denso e sem cartão. */
export const Ficha: React.FC<{ itens: { rotulo: string; valor: React.ReactNode }[] }> = ({
  itens,
}) => (
  <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
    {itens.map((item) => (
      <div key={item.rotulo} className="min-w-0">
        <dt className="kicker">{item.rotulo}</dt>
        <dd className="mt-0.5 break-words text-sm text-foreground">{item.valor}</dd>
      </div>
    ))}
  </dl>
);
