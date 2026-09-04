/**
 * Parada 1 — Destino. Para onde este anúncio manda o clique.
 *
 * É a única parada que se resolve inteira sem gastar nada, e por isso vem
 * primeiro: descobrir aqui que a página está em rascunho custa zero; descobrir
 * depois de `validate_only` custa a chamada mais lenta do fluxo, e descobrir
 * depois de criar custa uma campanha apontando para uma URL que vai mudar.
 *
 * ⚠️ Falha de leitura APARECE. O painel nunca é escondido quando o recibo não
 * chegou: `sem_recibo` é "ninguém avaliou", que é um estado a mostrar, não uma
 * ausência a silenciar. A versão anterior tratava `status_wp: null` — que
 * significa "o servidor nunca leu o WordPress" — como "LP no ar", com a etapa
 * marcada como pronta.
 */
import React from 'react';
import { ChevronDown, Globe2, LockKeyhole, ShieldCheck } from 'lucide-react';

import { BlocoDeEvidencia, LinhaDeFato } from '../BlocoDeEvidencia';
import { PainelDoDestinoPago } from '@/components/landing-policy/PainelDoDestinoPago';
import type { LeituraDoDestinoPago } from '@/lib/landing-policy/prontidao';
import type { Cockpit } from '@/types/trafego';

/** O estado do WordPress em palavra, com a ausência dita. */
function estadoDaPagina(statusWp: string | null | undefined, postType: string | null | undefined) {
  if (statusWp == null) return null;
  const base = statusWp === 'publish' ? 'publicada'
    : statusWp === 'draft' ? 'em rascunho'
      : statusWp;
  return postType ? `${base} · ${postType}` : base;
}

export const ParadaDestino: React.FC<{
  cockpit: Cockpit;
  destino: LeituraDoDestinoPago;
}> = ({ cockpit, destino }) => {
  const o = cockpit.origem;
  const tom = destino.apto_para_campanha ? 'bom'
    : destino.bloqueadores.length > 0 ? 'ruim'
      : 'atencao';

  return (
    <div className="space-y-4">
      <section className="destination-hero">
        <div className="destination-hero-icon" aria-hidden>
          <Globe2 className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="kicker text-muted-foreground">Destino final</p>
          <p className="mt-1 break-all font-display text-lg font-semibold text-foreground sm:text-xl">
            {o?.url_final ?? 'O funil ainda não declarou um endereço'}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {o?.dominio ?? 'domínio não identificado'}
          </p>
        </div>
        <span className={tom === 'bom' ? 'destination-status destination-status-ok' : 'destination-status destination-status-blocked'}>
          {tom === 'bom' ? <ShieldCheck className="h-4 w-4" aria-hidden /> : <LockKeyhole className="h-4 w-4" aria-hidden />}
          {tom === 'bom' ? 'Destino apto' : o?.status_wp === 'draft' ? 'Rascunho' : 'Exige atenção'}
        </span>
      </section>

      {o?.status_wp === 'draft' && (
        <div className="destination-alert">
          <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <div>
            <p className="font-medium text-foreground">Publique a página antes de comprar o clique</p>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              Este endereço é provisório: ao publicar, o permalink muda e a campanha fica apontando
              para o endereço antigo. Use o endereço definitivo antes de criar.
            </p>
          </div>
        </div>
      )}

      <details className="bancada-evidence-drawer">
        <summary>
          <span>Conferir procedência do endereço</span>
          <ChevronDown className="h-4 w-4" aria-hidden />
        </summary>
        <BlocoDeEvidencia titulo="O endereço" tom={tom}>
          <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <LinhaDeFato
            rotulo="URL final"
            valor={o?.url_final
              ? <span className="break-all">{o.url_final}</span>
              : null}
            fonte="o funil"
            ausencia="o funil não declarou destino"
          />
          <LinhaDeFato rotulo="domínio" valor={o?.dominio || null} fonte="o projeto" />
          <LinhaDeFato
            rotulo="estado da página"
            valor={estadoDaPagina(o?.status_wp, o?.post_type)}
            fonte="o WordPress"
            ausencia="ninguém leu o WordPress"
          />
          <LinhaDeFato
            rotulo="procedência da URL"
            valor={o?.url_procedencia || null}
            fonte="o funil"
          />
          </dl>
        </BlocoDeEvidencia>
      </details>

      <details className="bancada-evidence-drawer">
        <summary>
          <span>Ver diagnóstico completo da política do destino</span>
          <ChevronDown className="h-4 w-4" aria-hidden />
        </summary>
        <div className="pt-4">
          <PainelDoDestinoPago leitura={destino} titulo="recibo do portão de destino pago" />
        </div>
      </details>
    </div>
  );
};
