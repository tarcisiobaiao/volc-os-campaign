import React from 'react';
import { cn } from '@/lib/utils';
import {
  DECISAO_HUMANA, FORMATO_HUMANO,
  type TeseDeOportunidade, type TesesResposta,
} from '@/types/pautadorOportunidade';

/**
 * Comparar oportunidades — e dizer por que uma está acima da outra.
 *
 * ## Por que tabela, e não cartões
 *
 * Inventário comparável é tabela. Uma grade de cartões iguais obriga o olho a
 * saltar entre blocos para comparar dois números que deviam estar na mesma
 * coluna, e é o padrão que o contrato de design deste produto proíbe. Aqui a
 * pergunta é literalmente "esta acima daquela?", então as colunas alinham.
 *
 * ## O que a tabela recusa a fazer
 *
 * **Não ordena o incomparável.** Card com cobertura abaixo do mínimo não entra
 * no ranking — e também NÃO SOME. Ele aparece embaixo, numa seção própria, com
 * o motivo escrito. Sumir seria a ordenação silenciosa; ordenar seria pior.
 *
 * **Não inventa uma nota.** Não há coluna "score". Há a decisão (palavra),
 * o índice que o motor de eixos já calculou (citado, não recalculado) e a
 * cobertura que diz quanto daquele índice é opinião sobre o vazio.
 *
 * **Não usa cor sozinha.** A decisão é glifo + palavra. A cor reforça.
 *
 * A ordenação é a do servidor (`app.validacao.oportunidade.comparar`), não uma
 * segunda régua no cliente. Reordenar aqui criaria duas verdades.
 */

const TOM_TEXTO: Record<string, string> = {
  success: 'text-success', warning: 'text-warning', destructive: 'text-destructive',
  info: 'text-info', muted: 'text-muted-foreground',
};

const Decisao: React.FC<{ t: TeseDeOportunidade }> = ({ t }) => {
  const d = DECISAO_HUMANA[t.decisao] ?? DECISAO_HUMANA.sem_validacao;
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span aria-hidden className={cn('text-[11px] leading-none', TOM_TEXTO[d.tom])}>{d.glifo}</span>
      <span className="text-[12px] font-medium text-foreground">{d.palavra}</span>
    </span>
  );
};

const Linha: React.FC<{
  t: TeseDeOportunidade;
  posicao?: number;
  selecionada?: boolean;
  onSelecionar?: (t: TeseDeOportunidade) => void;
}> = ({ t, posicao, selecionada, onSelecionar }) => {
  const formato = t.formato_de_funil ? FORMATO_HUMANO[t.formato_de_funil] : null;
  const interativa = !!onSelecionar;
  return (
    <tr
      className={cn('border-t border-border',
        selecionada && 'bg-primary/[.06]',
        interativa && 'cursor-pointer hover:bg-muted/40 [transition:background-color_160ms_cubic-bezier(.22,1,.36,1)]')}
      {...(interativa
        ? {
            tabIndex: 0,
            role: 'button',
            'aria-pressed': !!selecionada,
            onClick: () => onSelecionar?.(t),
            onKeyDown: (e: React.KeyboardEvent) => {
              if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelecionar?.(t); }
            },
          }
        : {})}
    >
      <td className="py-1.5 pl-2 pr-1 align-top text-[11px] tabular-nums text-muted-foreground">
        {posicao ?? '—'}
      </td>
      <td className="py-1.5 pr-2 align-top">
        <span className="text-[12px] font-medium text-foreground break-words">{t.tema}</span>
      </td>
      <td className="py-1.5 pr-2 align-top"><Decisao t={t} /></td>
      <td className="py-1.5 pr-2 align-top text-[11px] text-muted-foreground">
        {formato ? formato.nome : <span className="text-muted-foreground/60">—</span>}
      </td>
      <td className="py-1.5 pr-2 align-top text-right text-[11px] tabular-nums text-foreground/80">
        {t.indice_citado != null ? t.indice_citado.toFixed(3) : '—'}
      </td>
      <td className="py-1.5 pr-2 align-top text-right text-[11px] tabular-nums text-foreground/80">
        {t.cobertura != null ? `${Math.round(t.cobertura * 100)}%` : '—'}
      </td>
      <td className="py-1.5 pr-2 align-top text-right text-[11px] tabular-nums">
        <span className="text-foreground/70">{t.fatos.length}</span>
        <span className="text-muted-foreground/50"> / </span>
        <span className={cn(t.desconhecidos.length ? 'text-warning' : 'text-muted-foreground/70')}>
          {t.desconhecidos.length}
        </span>
      </td>
    </tr>
  );
};

const Cabecalho: React.FC = () => (
  <thead>
    <tr className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
      <th scope="col" className="py-1 pl-2 pr-1 text-left font-semibold w-8">#</th>
      <th scope="col" className="py-1 pr-2 text-left font-semibold">Tema</th>
      <th scope="col" className="py-1 pr-2 text-left font-semibold">Decisão</th>
      <th scope="col" className="py-1 pr-2 text-left font-semibold">Formato</th>
      <th scope="col" className="py-1 pr-2 text-right font-semibold">Índice</th>
      <th scope="col" className="py-1 pr-2 text-right font-semibold">Cobertura</th>
      <th scope="col" className="py-1 pr-2 text-right font-semibold" title="fatos / desconhecidos">
        Fato/Desc
      </th>
    </tr>
  </thead>
);

export const ComparadorDeOportunidades: React.FC<{
  dados?: TesesResposta | null;
  carregando?: boolean;
  erro?: string | null;
  selecionadaId?: number | null;
  onSelecionar?: (t: TeseDeOportunidade) => void;
  className?: string;
}> = ({ dados, carregando, erro, selecionadaId, onSelecionar, className }) => {
  if (carregando) {
    return (
      <div className={cn('rounded-lg border border-border bg-card p-3', className)}>
        <p className="text-[11px] text-muted-foreground">Lendo as teses já gravadas…</p>
        <div aria-hidden className="mt-2 space-y-1.5">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-6 rounded bg-muted/50" />
          ))}
        </div>
      </div>
    );
  }

  if (erro) {
    return (
      <div className={cn('rounded-lg border border-destructive/30 bg-destructive/[.07] p-3', className)}>
        <p className="text-[11px] text-foreground">
          Não foi possível ler as teses. O que está na tela pode estar desatualizado.
        </p>
        <p className="text-[10px] text-muted-foreground mt-0.5">{erro}</p>
      </div>
    );
  }

  const ranking = dados?.ranking ?? [];
  const fora = dados?.fora_do_ranking ?? [];

  if (!ranking.length && !fora.length) {
    return (
      <div className={cn('rounded-lg border border-border bg-card p-4 text-center', className)}>
        <p className="text-[12px] text-foreground">Nenhum card medido nesta coluna.</p>
        <p className="text-[11px] text-muted-foreground mt-1 max-w-[46ch] mx-auto leading-snug">
          A comparação lê o que a validação já gravou. Arraste cards para
          Em validação — ou meça a coluna inteira, que é mais barato.
        </p>
      </div>
    );
  }

  return (
    <section className={cn('rounded-lg border border-border bg-card', className)}
      aria-label="Comparação de oportunidades">
      <header className="flex items-baseline justify-between gap-2 px-3 pt-3 pb-2">
        <div>
          <h3 className="font-display text-[15px] font-bold tracking-tight text-foreground">
            Onde apostar
          </h3>
          <p className="text-[11px] text-muted-foreground mt-0.5 max-w-[64ch] leading-snug">
            Ordenado pela decisão, depois pelo índice que o motor de eixos já
            calculou. Cobertura diz quanto desse índice é opinião sobre o vazio.
          </p>
        </div>
        <span className="text-[10px] tabular-nums text-muted-foreground shrink-0">
          {ranking.length} comparáveis
        </span>
      </header>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse">
          <caption className="sr-only">
            Oportunidades comparáveis, ordenadas por decisão e índice
          </caption>
          <Cabecalho />
          <tbody>
            {ranking.map((t, i) => (
              <Linha key={t.opportunity_id ?? t.tema} t={t} posicao={i + 1}
                selecionada={selecionadaId != null && t.opportunity_id === selecionadaId}
                onSelecionar={onSelecionar} />
            ))}
          </tbody>
        </table>
      </div>

      {fora.length > 0 && (
        <div className="border-t border-border">
          <div className="px-3 py-2">
            <h4 className="text-[10px] font-semibold uppercase tracking-[0.08em] text-foreground">
              Fora do ranking
              <span className="ml-1.5 tabular-nums font-normal text-muted-foreground">{fora.length}</span>
            </h4>
            <p className="text-[10px] text-muted-foreground mt-0.5 max-w-[64ch] leading-snug">
              Não entram na ordenação porque não há base para comparar. Ficam
              aqui, com o motivo — some da lista seria pior que aparecer último.
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse">
              <caption className="sr-only">Oportunidades sem base para comparação</caption>
              <tbody>
                {fora.map((t) => (
                  <tr key={t.opportunity_id ?? t.tema} className="border-t border-border">
                    <td className="py-1.5 pl-2 pr-1 w-8 text-[11px] text-muted-foreground/60" aria-hidden>—</td>
                    <td className="py-1.5 pr-2 align-top">
                      <span className="text-[12px] text-foreground/80 break-words">{t.tema}</span>
                    </td>
                    <td className="py-1.5 pr-2 align-top"><Decisao t={t} /></td>
                    <td className="py-1.5 pr-2 align-top text-[11px] text-muted-foreground" colSpan={4}>
                      {t.motivo_incomparavel ?? 'sem base para comparar'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
};
