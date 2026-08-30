/**
 * ⚠️ Os títulos são `h3`, e não `h2`.
 *
 * Esta superfície vive DENTRO de uma seção da página canônica que já abre com
 * `h2` ("O que dá para fazer aqui"). Dois `h2` irmãos, um dentro do outro,
 * fazem o leitor de tela anunciar dois assuntos de mesmo peso onde há um só —
 * e a árvore do documento deixa de dizer o que pertence a quê.
 *
 * A visão por canal — o que o Hub pode fazer aqui, derivado do manifesto.
 *
 * Três estados, três fatos diferentes: canal não operado, canal operado sem
 * capacidade, e canal operado com capacidades. A tela nunca oferece um botão
 * que o manifesto não autorize, e nunca esconde a recusa atrás de cinza mudo:
 * `indisponibilidades[0]` é a frase que ensina por que não dá.
 */
import React from 'react';
import { Ban, CircleSlash, Layers } from 'lucide-react';

import { cn } from '@/lib/utils';
import type { ManifestoDeCanal } from '@/types/trafego';

import { capacidadesDoCanal } from './capacidades';

export interface VisaoDoCanalProps {
  manifesto: ManifestoDeCanal | null;
  /** O rótulo do canal quando não há manifesto para nomeá-lo. */
  rotuloDeReserva?: string;
  className?: string;
}

export const VisaoDoCanal: React.FC<VisaoDoCanalProps> = ({
  manifesto,
  rotuloDeReserva = 'este canal',
  className,
}) => {
  const c = capacidadesDoCanal(manifesto);
  const sabeProvar = manifesto != null && (manifesto.sabe_provar ?? manifesto.sabe_criar);

  if (c.tipo === 'nao_operado') {
    return (
      <section className={cn('max-w-[70ch]', className)} aria-label="capacidades do canal">
        <p className="kicker">canal</p>
        <h3 className="mt-1 flex items-center gap-2 font-display text-base font-semibold">
          <Ban className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          {rotuloDeReserva} não é operado pelo Hub
        </h3>
        <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">{c.frase}</p>
      </section>
    );
  }

  if (c.tipo === 'sem_capacidade') {
    return (
      <section className={cn('max-w-[70ch]', className)} aria-label="capacidades do canal">
        <p className="kicker">canal</p>
        <h3 className="mt-1 flex items-center gap-2 font-display text-base font-semibold">
          <CircleSlash className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          {c.rotulo} — nenhuma capacidade declarada
        </h3>
        <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">{c.frase}</p>
      </section>
    );
  }

  return (
    <section className={cn('max-w-[70ch]', className)} aria-label="capacidades do canal">
      <p className="kicker">canal</p>
      <h3 className="mt-1 flex items-center gap-2 font-display text-base font-semibold">
        <Layers className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        {c.rotulo}
      </h3>
      <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">
        O que esta tela oferece vem do manifesto do backend, não de uma lista de
        canais aqui dentro.
      </p>

      <ul className="mt-3 space-y-1 text-[13px]" role="list">
        {c.capacidades.map((cap) => (
          <li key={cap} className="flex gap-2">
            <span aria-hidden className="text-muted-foreground">
              ·
            </span>
            <span>{cap}</span>
          </li>
        ))}
      </ul>

      {c.provas_obrigatorias.length > 0 && (
        <p className="mt-3 text-[12px] leading-relaxed text-muted-foreground">
          provas exigidas nesta porta: {c.provas_obrigatorias.join(', ')}
        </p>
      )}

      <p
        className={cn(
          'mt-3 max-w-[68ch] text-[12px] leading-relaxed',
          c.sabe_criar ? 'text-muted-foreground' : 'text-foreground',
        )}
      >
        {c.sabe_criar
          ? 'o Hub sabe criar campanha neste canal.'
          : sabeProvar
            ? `o Hub sabe montar e provar; criação real indisponível: ${c.recusa}.`
            : `criação indisponível: ${c.recusa}.`}
      </p>

      {/* ⚠️ O que o canal NÃO monta, mesmo sabendo criar.
          Display declara cinco limitações e `sabe_criar: true` — e enquanto
          recusa e limite dividiam o mesmo campo, as cinco eram descartadas.
          Saber criar não é saber criar tudo, e o operador precisa ler o que
          falta ANTES de montar o pedido, não depois. */}
      {c.limites.length > 0 && (
        <div className="mt-3">
          <p className="font-display text-[12px] font-semibold">
            O que este canal ainda não monta
          </p>
          <ul className="mt-1.5 space-y-1.5 text-[12px] leading-relaxed text-muted-foreground" role="list">
            {c.limites.map((frase) => (
              <li key={frase} className="flex gap-1.5">
                <span aria-hidden>·</span>
                <span>{frase}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
};

export default VisaoDoCanal;
