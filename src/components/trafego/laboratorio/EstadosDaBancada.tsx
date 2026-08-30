import React from 'react';
import {
  Ban,
  CircleDot,
  CircleHelp,
  CircleOff,
  Inbox,
  WifiOff,
} from 'lucide-react';

import { Skeleton } from '@/components/ui/skeleton';
import { Chip } from '@/components/trafego/inventario/Selos';
import type { EstadoDaMedida } from './projection';

export const CarregandoBancada: React.FC = () => (
  <div role="status" aria-live="polite" className="mt-6">
    <span className="sr-only">Carregando o replay sintético</span>
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_280px]">
      <div className="space-y-5">
        <Skeleton className="h-24 w-full motion-reduce:animate-none" />
        <Skeleton className="h-36 w-full motion-reduce:animate-none" />
        <Skeleton className="h-64 w-full motion-reduce:animate-none" />
      </div>
      <Skeleton className="h-72 w-full motion-reduce:animate-none" />
    </div>
  </div>
);

export const EstadoTerminalBancada: React.FC<{
  titulo: string;
  texto: string;
  codigo?: string;
  tipo: 'vazio' | 'falha' | 'versao';
}> = ({ titulo, texto, codigo, tipo }) => {
  const Icone = tipo === 'vazio' ? Inbox : tipo === 'versao' ? CircleHelp : WifiOff;
  return (
    <section className="mt-6 border-y border-border py-12 text-center" role={tipo === 'falha' ? 'alert' : 'status'}>
      <Icone className="mx-auto h-7 w-7 text-muted-foreground" aria-hidden />
      <h2 className="mt-3 text-balance font-display text-xl font-semibold">{titulo}</h2>
      <p className="mx-auto mt-2 max-w-[62ch] text-pretty text-[14px] leading-relaxed text-muted-foreground">{texto}</p>
      {codigo && <code className="mt-4 inline-block rounded-sm border border-border bg-muted px-2 py-1 text-[11px]">{codigo}</code>}
    </section>
  );
};

const MEDIDA: Record<EstadoDaMedida, { palavra: string; descricao: string; tom: 'neutro' | 'verificado' | 'atencao' | 'ruim'; glifo: typeof Ban }> = {
  valor: { palavra: 'valor', descricao: 'o contrato enviou este valor medido', tom: 'verificado', glifo: CircleDot },
  ausente: { palavra: 'ausente', descricao: 'o contrato enviou ausência, não zero', tom: 'atencao', glifo: CircleOff },
  zero_medido: { palavra: 'zero medido', descricao: 'zero foi observado de fato, e não é ausência', tom: 'neutro', glifo: Ban },
  nao_aplicavel: { palavra: 'não aplicável', descricao: 'o contrato marcou este campo como não aplicável', tom: 'neutro', glifo: Ban },
  falha: { palavra: 'falha de leitura', descricao: 'a leitura deste campo falhou', tom: 'ruim', glifo: WifiOff },
  lista_vazia: { palavra: 'lista vazia', descricao: 'a lista foi observada e veio sem itens', tom: 'verificado', glifo: Inbox },
  campo_ausente: { palavra: 'campo ausente', descricao: 'este campo não veio na fotografia', tom: 'atencao', glifo: CircleHelp },
};

export const SeloDaMedida: React.FC<{ estado: EstadoDaMedida }> = ({ estado }) => {
  const visual = MEDIDA[estado];
  return <Chip glifo={visual.glifo} palavra={visual.palavra} descricao={visual.descricao} tom={visual.tom} />;
};
