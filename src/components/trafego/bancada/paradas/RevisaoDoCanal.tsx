/**
 * O bloco comum das quatro Revisões: o resumo das escolhas do canal, os avisos
 * (previstos pelo contrato e, depois da prova, os do servidor) e os erros de
 * forma que o 422 devolveu — TODOS, com o caminho, inclusive os que nenhum
 * campo da tela soube mostrar.
 *
 * ⚠️ Nada aqui é editável. A Revisão confere; decidir depois de conferir é
 * como uma proposta editada após a assinatura vai ao ar com carimbo de aprovada.
 */
import React from 'react';
import { AlertTriangle, Info, ListChecks } from 'lucide-react';

import { cn } from '@/lib/utils';
import type { ErrosDoServidor } from '@/lib/trafego/configuracao/erros422';
import type { AvisoDaRevisao, LinhaDoResumo } from '@/lib/trafego/configuracao/revisao';

export const ResumoDoCanal: React.FC<{
  titulo: string;
  linhas: LinhaDoResumo[];
}> = ({ titulo, linhas }) => (
  <section aria-label={titulo} className="rounded-lg border border-border bg-background p-4">
    <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
      <ListChecks className="h-4 w-4 text-primary" aria-hidden /> {titulo}
    </p>
    <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
      {linhas.map((l) => (
        <div key={l.rotulo} className="min-w-0">
          <dt className="kicker text-muted-foreground">{l.rotulo}</dt>
          <dd className="mt-0.5 break-words text-sm text-foreground">{l.valor}</dd>
        </div>
      ))}
    </dl>
  </section>
);

export const AvisosDaRevisao: React.FC<{
  previstos: AvisoDaRevisao[];
  doServidor: AvisoDaRevisao[] | null;
}> = ({ previstos, doServidor }) => {
  // Depois da prova, quem fala é o servidor; antes, o contrato.
  const lista = doServidor ?? previstos;
  const titulo = doServidor
    ? 'Avisos devolvidos pelo servidor na prova'
    : 'Avisos que o servidor vai emitir para estas escolhas (pelo contrato)';
  return (
    <section aria-label="avisos" className="rounded-lg border border-border bg-background p-4">
      <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
        <Info className="h-4 w-4 text-info" aria-hidden /> {titulo}
      </p>
      {lista.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {doServidor ? 'A prova não devolveu aviso.' : 'Nenhum aviso previsto para estas escolhas.'}
        </p>
      ) : (
        <ul className="space-y-2">
          {lista.map((a, i) => (
            <li key={`${a.codigo}-${i}`} className="rounded-md border border-warning/30 bg-warning/[0.05] p-3">
              <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-foreground">
                <code className="rounded bg-muted px-1.5 py-0.5 text-[11px]">{a.codigo}</code>
                {a.titulo}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{a.detalhe}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};

/** Todos os erros de forma, com caminho. Os gerais (sem campo) também. */
export const ErrosDeForma: React.FC<{ erros: ErrosDoServidor; titulo?: string }> = ({
  erros, titulo = 'O servidor recusou a forma do pedido',
}) => {
  if (!erros.campos.length && !erros.gerais.length) return null;
  return (
    <section role="alert" aria-label="erros de forma"
             className="rounded-lg border border-destructive/40 bg-destructive/[0.05] p-4">
      <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-destructive">
        <AlertTriangle className="h-4 w-4" aria-hidden /> {titulo}
      </p>
      <ul className="space-y-1.5 text-sm">
        {erros.gerais.map((g, i) => <li key={`g-${i}`} className="text-foreground">{g}</li>)}
        {erros.campos.map((e, i) => (
          <li key={`c-${i}`} className={cn('text-foreground')}>
            <code className="mr-2 rounded bg-muted px-1.5 py-0.5 text-[11px]">{e.caminho}</code>
            {e.mensagem}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted-foreground">
        Cada erro também aparece no campo dele, na parada onde ele foi decidido.
      </p>
    </section>
  );
};
