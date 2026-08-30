/**
 * O que este funil já lançou — e é isto que substitui o botão de lançar.
 *
 * ## O defeito que este cartão conserta
 *
 * Medido em 19/08/2026: depois de publicar, o cockpit continuava idêntico —
 * mesmo trilho, mesmo botão "lançar campanha", nenhuma menção à campanha que
 * acabara de nascer. O operador não tinha como saber que já tinha lançado.
 *
 * A causa não era de tela: o `/subir` gravava o recibo em ARQUIVO e mais nada.
 * A campanha existia no Google Ads e era invisível para o nosso sistema. Sem
 * `funnel_run_id` no banco, nem a tela nem o motor de gestão sabiam da ligação.
 *
 * O risco disso não é estético. A doutrina desta casa é **um termo, uma
 * campanha** (P7): uma tela que oferece "lançar" a quem já lançou convida ao
 * lançamento duplicado, e duas campanhas para o mesmo termo competem entre si
 * no leilão — você passa a dar lance contra você mesmo.
 *
 * ## Por que ele não esconde o botão, e sim o desloca
 *
 * Relançar é legítimo: foi o que o operador fez ao remover a primeira campanha
 * e refazer com a taxonomia certa. O caminho continua aberto — só deixa de ser
 * a ação óbvia da tela.
 */
import React from 'react';
import { CheckCircle2, ExternalLink, PauseCircle } from 'lucide-react';

import { cn } from '@/lib/utils';
import type { CampanhaLancada } from '@/types/trafego';

interface Props {
  campanhas: CampanhaLancada[];
  /** Abre o veredito de política da campanha escolhida, na mesma tela. */
  onVerVeredito?: (customerId: string, campaignId: string) => void;
}

const ESTADO: Record<string, { rotulo: string; tom: 'pausada' | 'ativa' }> = {
  PAUSED: { rotulo: 'pausada — não está gastando', tom: 'pausada' },
  ENABLED: { rotulo: 'ATIVA — está gastando agora', tom: 'ativa' },
};

export const JaNoAr: React.FC<Props> = ({ campanhas, onVerVeredito }) => {
  if (campanhas.length === 0) return null;

  return (
    <section className="card-volc p-5 md:p-6" aria-label="campanhas já lançadas">
      <div className="mb-4 flex items-baseline gap-3">
        <h2 className="text-[15px] font-medium tracking-tight">
          {campanhas.length === 1 ? 'esta pauta já virou campanha' : 'esta pauta já virou campanhas'}
        </h2>
        <span className="hairline flex-1" />
        <span className="kicker">{campanhas.length}</span>
      </div>

      <ul className="space-y-2">
        {campanhas.map((c) => {
          const e = ESTADO[c.google_ads_status] ?? {
            rotulo: c.google_ads_status.toLowerCase(), tom: 'pausada' as const,
          };
          return (
            <li key={c.campaign_id} className="rounded-md border border-border p-3">
              <div className="flex flex-wrap items-center gap-2">
                {e.tom === 'ativa'
                  ? <CheckCircle2 className="h-4 w-4 shrink-0 text-warning" aria-hidden />
                  : <PauseCircle className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />}
                <span className={cn('text-sm', e.tom === 'ativa' && 'font-medium')}>
                  {e.rotulo}
                </span>
                <span className="tabular ml-auto text-[11px] text-muted-foreground">
                  {c.campaign_id}
                </span>
              </div>
              <p className="mt-1.5 break-all text-[11px] leading-relaxed text-muted-foreground">
                {c.campaign_name}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px]">
                {c.budget_amount != null && (
                  <span className="text-muted-foreground">
                    orçamento <span className="tabular text-foreground">
                      {c.budget_amount.toFixed(2).replace('.', ',')}
                    </span>/dia
                  </span>
                )}
                {onVerVeredito && (
                  <button type="button"
                          onClick={() => onVerVeredito(c.customer_id, c.campaign_id)}
                          className="underline underline-offset-4">
                    ver o veredito do Google
                  </button>
                )}
                <a href={`https://ads.google.com/aw/campaigns?campaignId=${c.campaign_id}`}
                   target="_blank" rel="noreferrer"
                   className="inline-flex items-center gap-1 underline underline-offset-4">
                  abrir no Google Ads <ExternalLink className="h-3 w-3" aria-hidden />
                </a>
              </div>
            </li>
          );
        })}
      </ul>

      {/* ⚠️ Relançar é legítimo — foi o que o operador fez ao remover a primeira
          campanha e refazer com a taxonomia certa. Mas a doutrina é um termo,
          uma campanha: duas para o mesmo termo competem no leilão, e você passa
          a dar lance contra você mesmo. Por isso o aviso, não o bloqueio. */}
      <p className="mt-4 border-t border-border pt-3 text-[11px] leading-relaxed text-muted-foreground">
        Lançar de novo cria uma <b>segunda</b> campanha para o mesmo termo — e duas
        campanhas no mesmo leilão competem entre si. Se a intenção é refazer,
        remova a anterior antes.
      </p>
    </section>
  );
};
