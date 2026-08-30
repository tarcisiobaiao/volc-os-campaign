/**
 * Meta ainda não tem integração. A tela diz isso; não desenha desempenho.
 */
import React from 'react';
import { Link } from 'react-router-dom';

import { rotuloDoNivelMeta } from './perfilDeCanal';
import type { NivelMeta } from './contrato';

export const MetaNaoConfigurada: React.FC<{ nivel: NivelMeta }> = ({ nivel }) => (
  <section
    aria-label="Meta Ads ainda não configurado"
    className="rounded-md border border-dashed border-border px-4 py-8"
  >
    <p className="kicker">Meta Ads</p>
    <h2 className="mt-2 font-display text-lg font-semibold">
      Integração ainda não configurada
    </h2>
    <p className="mt-2 max-w-[68ch] text-[13px] leading-relaxed text-muted-foreground">
      O nível <span className="font-medium text-foreground">{rotuloDoNivelMeta(nivel)}</span> da
      árvore Meta (campanha → conjunto → anúncio → criativo) já tem lugar nesta tela. Ainda
      não há leitura da conta, então não há campanha, conjunto, anúncio nem criativo para
      mostrar — e não há número de desempenho.
    </p>
    <p className="mt-3 max-w-[68ch] text-[13px] leading-relaxed text-muted-foreground">
      Google Ads continua sendo o padrão desta casa. Volte para a rede Google para conferir
      o que já está no ar.
    </p>
    <Link
      to="/trafego?rede=google"
      className="mt-4 inline-flex min-h-11 items-center text-sm font-medium text-primary underline-offset-2 hover:underline"
    >
      voltar para Google Ads
    </Link>
  </section>
);

export default MetaNaoConfigurada;
