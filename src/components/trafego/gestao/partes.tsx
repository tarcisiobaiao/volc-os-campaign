/**
 * Peças da gestão: campo com erro, seletor nativo, aviso de recusa e a tabela
 * antes → depois. Sem regra de negócio — ela mora em `lib/trafego/gestao`.
 *
 * Seletor nativo, e não o Radix: é acessível sem portal, funciona por teclado
 * e no leitor de tela do celular, e é o que a fila precisa — escolher, não
 * decorar.
 */
import React from 'react';
import { AlertTriangle, CircleHelp } from 'lucide-react';

import { cn } from '@/lib/utils';
import { AUSENTE } from '@/components/trafego/inventario/formato';
import type { ErroLegivel } from '@/lib/trafego/gestao/erros';
import type { LinhaDeDiff } from '@/lib/trafego/gestao/diff';

export const Campo: React.FC<{
  id: string;
  rotulo: string;
  ajuda?: string;
  erro?: string | null;
  children: React.ReactNode;
  className?: string;
}> = ({ id, rotulo, ajuda, erro, children, className }) => (
  <div className={cn('min-w-0', className)}>
    <label htmlFor={id} className="block text-[12px] font-medium">
      {rotulo}
    </label>
    {ajuda && <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{ajuda}</p>}
    <div className="mt-1">{children}</div>
    {erro && (
      <p id={`${id}-erro`} className="mt-1 text-[11px] text-destructive" role="alert">
        {erro}
      </p>
    )}
  </div>
);

export const classeDeEntrada =
  'block w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-[13px] ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring min-h-9';

export function Seletor<T extends string>({
  id,
  valor,
  opcoes,
  aoMudar,
  invalido,
}: {
  id: string;
  valor: T | '';
  opcoes: ReadonlyArray<{ valor: T; rotulo: string }>;
  aoMudar: (v: T) => void;
  invalido?: boolean;
}) {
  return (
    <select
      id={id}
      value={valor}
      aria-invalid={invalido || undefined}
      onChange={(e) => aoMudar(e.target.value as T)}
      className={classeDeEntrada}
    >
      {valor === '' && <option value="">escolha</option>}
      {opcoes.map((o) => (
        <option key={o.valor} value={o.valor}>
          {o.rotulo}
        </option>
      ))}
    </select>
  );
}

export const AvisoDeErro: React.FC<{
  erro: ErroLegivel;
  className?: string;
  children?: React.ReactNode;
}> = ({ erro, className, children }) => (
  <div
    className={cn(
      'rounded-md border px-3 py-2.5 text-[12px] leading-relaxed',
      erro.incerto ? 'border-warning/60 bg-warning/5' : 'border-destructive/50 bg-destructive/5',
      className,
    )}
    role="alert"
  >
    <p className="flex items-start gap-1.5 font-medium">
      {erro.incerto ? (
        <CircleHelp className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden />
      ) : (
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" aria-hidden />
      )}
      {erro.titulo}
    </p>
    {erro.proximoPasso && <p className="mt-1 text-muted-foreground">{erro.proximoPasso}</p>}
    {(erro.codigo || erro.tecnica) && (
      <p className="mt-1 break-words text-[11px] text-muted-foreground">
        {erro.codigo && <code className="tabular">{erro.codigo}</code>}
        {erro.codigo && erro.tecnica && ' · '}
        {erro.tecnica}
      </p>
    )}
    {children}
  </div>
);

export const AntesDepois: React.FC<{ linhas: LinhaDeDiff[]; legenda: string }> = ({ linhas, legenda }) => (
  <table className="mt-2 w-full text-[12px]">
    <caption className="sr-only">{legenda}</caption>
    <thead>
      <tr className="text-left text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
        <th scope="col" className="pb-1 font-normal">
          campo
        </th>
        <th scope="col" className="pb-1 pl-2 font-normal">
          antes
        </th>
        <th scope="col" className="pb-1 pl-2 font-normal">
          depois
        </th>
      </tr>
    </thead>
    <tbody>
      {linhas.map((l, i) => (
        <tr key={`${l.rotulo}-${i}`} className="border-t border-border/60 align-top">
          <th scope="row" className="py-1 pr-2 text-left font-normal text-muted-foreground">
            {l.rotulo}
          </th>
          <td className="tabular break-words py-1 pl-2 text-muted-foreground">{l.antes ?? AUSENTE}</td>
          <td className="tabular break-words py-1 pl-2 font-medium">{l.depois ?? AUSENTE}</td>
        </tr>
      ))}
    </tbody>
  </table>
);
