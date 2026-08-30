/**
 * O que o Google decidiu sobre o anúncio — e por que isto vale com a campanha
 * PAUSADA.
 *
 * ## O fato que este painel explora
 *
 * Medido em 19/08/2026 na conta 5478096539: seis anúncios em campanhas
 * `PAUSED`, todos com `review_status = REVIEWED`, quatro `APPROVED` e dois
 * `APPROVED_LIMITED`. **O Google revisa o anúncio independente do status da
 * campanha.**
 *
 * A consequência operacional é grande: subir pausado é o teste de política mais
 * barato que existe. Descobre-se se a vertical foi enquadrada, se a copy passou
 * e se falta habilitação — sem gastar um centavo, e sem depender da resposta do
 * formulário de desenquadramento.
 *
 * ## As três respostas que a tela não pode confundir
 *
 * `em revisão` não é `aprovado`. Um painel que pinta de verde enquanto o Google
 * ainda não decidiu faz o operador ativar a campanha achando que passou. Por
 * isso o estado de revisão vem antes da aprovação na hierarquia visual.
 *
 * E `isentavel` separa dois caminhos que custam coisas diferentes: pedir
 * isenção (formulário, dias) ou reescrever o anúncio (minutos). Sem essa
 * distinção o operador descobre qual é por tentativa e erro.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Check, Loader2, RefreshCw, ShieldAlert, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { pautadorApi } from '@/lib/pautadorApi';
import { cn } from '@/lib/utils';
import type { VereditoDePolitica as Veredito } from '@/types/trafego';

interface Props {
  customerId: string;
  campaignId: string;
}

/** O que cada aprovação significa em português, e o que fazer com ela. */
const LEITURA: Record<string, { rotulo: string; tom: 'bom' | 'atencao' | 'ruim'; oque: string }> = {
  APPROVED: {
    rotulo: 'aprovado', tom: 'bom',
    oque: 'Veicula sem restrição. Ativar é decisão sua.',
  },
  APPROVED_LIMITED: {
    rotulo: 'aprovado com limitação', tom: 'atencao',
    oque: 'Veicula, mas com alcance restrito — em geral é habilitação faltando.',
  },
  AREA_OF_INTEREST_ONLY: {
    rotulo: 'só fora do país-alvo', tom: 'ruim',
    oque: 'Não veicula no país segmentado. Habilitação por país é o suspeito.',
  },
  DISAPPROVED: {
    rotulo: 'reprovado', tom: 'ruim',
    oque: 'Não veicula. Ou pede isenção, ou reescreve — veja os tópicos abaixo.',
  },
};

export const VereditoDePolitica: React.FC<Props> = ({ customerId, campaignId }) => {
  const [v, setV] = useState<Veredito | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  const ler = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      setV(await pautadorApi.vereditoDePolitica(customerId, campaignId));
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falhei ao ler o veredito.');
    } finally {
      setCarregando(false);
    }
  }, [customerId, campaignId]);

  useEffect(() => { void ler(); }, [ler]);

  return (
    <section className="card-volc p-5 md:p-6" aria-label="veredito de política">
      <div className="mb-4 flex items-baseline gap-3">
        <h2 className="text-[15px] font-medium tracking-tight">o que o Google decidiu</h2>
        <span className="hairline flex-1" />
        <Button variant="ghost" size="sm" onClick={() => void ler()} disabled={carregando}>
          {carregando
            ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            : <RefreshCw className="h-3.5 w-3.5" aria-hidden />}
          <span className="ml-1.5 text-[11px]">reconsultar</span>
        </Button>
      </div>

      {/* O fato que justifica o painel, dito uma vez. */}
      <p className="mb-4 max-w-[74ch] text-[11px] leading-relaxed text-muted-foreground">
        O Google revisa o anúncio <b>mesmo com a campanha pausada</b>. É por isso
        que subir pausado responde sobre enquadramento sem gastar nada.
      </p>

      {erro && (
        <div className="rounded-md border border-destructive/40 bg-destructive/[0.05] p-3 text-[11px]">
          {erro}
        </div>
      )}

      {v?.sem_anuncios && (
        <div className="rounded-md border border-border p-3 text-[11px] text-muted-foreground">
          Esta campanha ainda não tem anúncio. Se acabou de subir, o Google leva
          alguns minutos para registrar.
        </div>
      )}

      {/* ⚠️ Em revisão NÃO é aprovado, e a tela diz isso antes de qualquer cor. */}
      {v?.em_revisao && !v.sem_anuncios && (
        <div className="flex items-start gap-2 rounded-md border border-border p-3 text-[11px] leading-relaxed">
          <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden />
          <span>
            <b>O Google ainda está revisando.</b> Costuma levar até um dia útil.
            Isto <b>não</b> é aprovação — reconsulte mais tarde.
          </span>
        </div>
      )}

      {v && !v.sem_anuncios && (
        <ul className="space-y-2">
          {v.anuncios.map((a) => {
            const l = LEITURA[a.aprovacao] ?? {
              rotulo: a.aprovacao.toLowerCase(), tom: 'atencao' as const, oque: '',
            };
            return (
              <li key={a.ad_id} className="rounded-md border border-border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Marca tom={l.tom} />
                  <span className="text-sm font-medium">{l.rotulo}</span>
                  <span className="kicker">{a.ad_group || 'ad group'}</span>
                  <span className="tabular ml-auto text-[11px] text-muted-foreground">
                    #{a.ad_id}
                  </span>
                </div>
                {l.oque && (
                  <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
                    {l.oque}
                  </p>
                )}
                {a.topicos.length > 0 && (
                  <ul className="mt-2 space-y-1 border-l-2 border-border pl-3">
                    {a.topicos.map((t, i) => (
                      <li key={i} className="text-[11px] leading-relaxed">
                        <span className="font-mono">{t.topico}</span>
                        <span className="text-muted-foreground"> · {t.tipo}</span>
                        {/* A distinção que decide o próximo passo do operador. */}
                        <span className={cn('ml-1.5', t.isentavel ? 'text-warning' : 'text-muted-foreground')}>
                          {t.isentavel ? '— dá para pedir isenção' : '— só reescrevendo'}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {v && !v.sem_anuncios && (
        <p className="mt-4 border-t border-border pt-3 text-[11px] text-muted-foreground">
          campanha <span className="tabular">{v.campanha.id}</span> ·{' '}
          <span className="font-mono">{v.campanha.status}</span>
          {v.campanha.status === 'PAUSED' && ' — não está gastando'}
        </p>
      )}
    </section>
  );
};

const Marca: React.FC<{ tom: 'bom' | 'atencao' | 'ruim' }> = ({ tom }) => (
  <span aria-hidden>
    {tom === 'bom' ? <Check className="h-4 w-4 text-success" />
     : tom === 'ruim' ? <X className="h-4 w-4 text-destructive" />
     : <ShieldAlert className="h-4 w-4 text-warning" />}
  </span>
);
