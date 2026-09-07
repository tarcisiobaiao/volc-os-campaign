/**
 * As primitivas de formulário da bancada Meta.
 *
 * ## Por que elas saíram de `MetaCriacaoPage.tsx`
 *
 * `Campo`, `Escolha`, a classe `campo` e o vocabulário `radiogroup` já eram o
 * desenho da bancada — mas viviam dentro do arquivo da página, e por isso cada
 * painel novo teria de recriá-los. Recriar é como um produto ganha um segundo
 * vocabulário de controle sem ninguém decidir isso: `design.md` chama de
 * "invent a third visual language" e proíbe por nome.
 *
 * ## ⚠️ MÓDULO, e a fronteira de módulo é o ponto
 *
 * Um componente declarado DENTRO do corpo de outro componente é uma função nova
 * a cada render: o React desmonta e remonta a subárvore, e um `<input>` dentro
 * dela PERDE O FOCO no primeiro caractere digitado. É exatamente o defeito
 * `A31` no campo de orçamento. Enquanto estas peças estiverem aqui, no topo do
 * módulo, a identidade delas é estável por construção.
 */
import React from 'react';

import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

/** Espelha a primitiva `Input` (h-10, rounded-md, anel `ring`) para que um
 *  `<select>` nativo não seja um segundo vocabulário de controle. */
export const campo = 'h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground ring-offset-background transition-volc duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50';

export const Campo: React.FC<{
  id: string; rotulo: string; ajuda?: React.ReactNode; children: React.ReactNode; largo?: boolean;
}> = ({ id, rotulo, ajuda, children, largo }) => (
  <div className={cn('space-y-2', largo && 'md:col-span-2')}>
    <Label htmlFor={id}>{rotulo}</Label>
    {children}
    {ajuda && <p className="max-w-[70ch] text-sm leading-relaxed text-pretty text-muted-foreground">{ajuda}</p>}
  </div>
);

export const Escolha: React.FC<{
  marcado: boolean; onChange: (v: boolean) => void; titulo: string;
  children: React.ReactNode; desabilitado?: boolean;
}> = ({ marcado, onChange, titulo, children, desabilitado }) => (
  <label className={cn(
    'flex min-h-11 items-start gap-3 rounded-lg border border-border bg-muted/20 p-3 md:col-span-2',
    desabilitado ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
  )}>
    <input
      type="checkbox" checked={marcado} disabled={desabilitado}
      onChange={(e) => onChange(e.target.checked)}
      className="mt-0.5 h-4 w-4 shrink-0"
    />
    <span>
      <strong className="block text-sm text-foreground">{titulo}</strong>
      <span className="mt-1 block max-w-[72ch] text-sm leading-relaxed text-pretty text-muted-foreground">
        {children}
      </span>
    </span>
  </label>
);

export interface OpcaoDeEscolha<T extends string> {
  id: T;
  nome: string;
  detalhe: React.ReactNode;
  /** Quando `true`, a opção continua VISÍVEL e não clicável. Esconder uma
   *  escolha indisponível ensina o operador a achar que ela não existe. */
  desabilitada?: boolean;
}

/**
 * O grupo segmentado da bancada: um poço `bg-muted`, uma pílula `bg-card`.
 *
 * ⚠️ É o mesmo vocabulário do seletor de modo de criativo — `role="radiogroup"`
 * com `role="radio"` e `aria-checked` — e não um `Tabs` novo. `design.md` fecha
 * o assunto: "Never recreate a third tab style".
 */
export function GrupoDeEscolha<T extends string>({
  rotuloAcessivel, valor, opcoes, onEscolher, colunas = 'sm:grid-cols-2', id,
}: {
  rotuloAcessivel: string;
  valor: T;
  opcoes: readonly OpcaoDeEscolha<T>[];
  onEscolher: (proximo: T) => void;
  colunas?: string;
  id?: string;
}) {
  return (
    <div
      id={id}
      className={cn('grid gap-2 rounded-lg border border-border bg-muted p-1', colunas)}
      role="radiogroup"
      aria-label={rotuloAcessivel}
    >
      {opcoes.map((opcao) => (
        <button
          key={opcao.id}
          type="button"
          role="radio"
          aria-checked={valor === opcao.id}
          disabled={opcao.desabilitada}
          onClick={() => onEscolher(opcao.id)}
          className={cn(
            'min-h-14 rounded-md px-3 py-2 text-left transition-volc duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            opcao.desabilitada && 'cursor-not-allowed opacity-60',
            valor === opcao.id
              ? 'bg-card text-foreground shadow-card'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          <strong className="block text-sm">{opcao.nome}</strong>
          <span className="block text-sm">{opcao.detalhe}</span>
        </button>
      ))}
    </div>
  );
}

/**
 * Um nome curto de arquivo/peça, truncado e sem overflow (`A30`).
 *
 * ⚠️ Caminho de storage NÃO é título. Um `gs://…/2026/09/…/arquivo.png` como
 * cabeçalho estoura a coluna, empurra o controle para fora da tela e não diz
 * nada que o operador precise. O nome inteiro continua acessível pelo `title`.
 */
export const NomeCurto: React.FC<{ nome: string | null | undefined; ausencia?: string; className?: string }> = ({
  nome, ausencia = 'sem nome', className,
}) => {
  const bruto = String(nome ?? '').trim();
  // O último segmento é o que identifica; o caminho é ruído de armazenamento.
  const curto = bruto.split(/[\\/]/).filter(Boolean).at(-1) || '';
  return (
    <span
      className={cn('block max-w-full truncate', className)}
      title={bruto || undefined}
    >
      {curto || ausencia}
    </span>
  );
};
