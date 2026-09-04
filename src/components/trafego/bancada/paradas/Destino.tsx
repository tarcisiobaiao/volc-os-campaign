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
        {/* ⚠️ O caso que este aviso existe para nomear: de um RASCUNHO o
            WordPress devolve `?post_type=r&p=2146`, e não o permalink. Anunciar
            essa URL manda tráfego para um endereço que vai mudar — e a falha
            some de vista, porque a campanha continua existindo e "no ar". */}
        {o?.status_wp === 'draft' && (
          <p className="mt-3 max-w-[70ch] text-sm leading-6 text-warning text-pretty">
            A página está em rascunho. O endereço acima é provisório: quando ela for
            publicada, o permalink muda e a campanha fica apontando para o endereço antigo.
          </p>
        )}
      </BlocoDeEvidencia>

      {/* O recibo do portão, inteiro: as cinco perguntas, o frescor, a
          procedência da evidência e o que o portão NÃO sabe. */}
      <PainelDoDestinoPago leitura={destino} titulo="recibo do portão de destino pago" />
    </div>
  );
};
