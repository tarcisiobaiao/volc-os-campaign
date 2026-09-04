/** Fundação local presente, integração externa ainda fechada. */
import React from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, KeyRound } from 'lucide-react';

import { rotuloDoNivelMeta } from './perfilDeCanal';
import type { NivelMeta } from './contrato';

export const MetaNaoConfigurada: React.FC<{ nivel: NivelMeta }> = ({ nivel }) => (
  <section
    aria-label="Fundação Meta instalada; conexão real pendente"
    className="rounded-md border border-dashed border-border px-4 py-8"
  >
    <p className="kicker">Meta Ads</p>
    <h2 className="mt-2 font-display text-lg font-semibold">
      Fundação instalada · conexão real pendente
    </h2>
    <p className="mt-2 max-w-[68ch] text-[13px] leading-relaxed text-muted-foreground">
      O nível <span className="font-medium text-foreground">{rotuloDoNivelMeta(nivel)}</span> da
      árvore Meta (campanha → conjunto → anúncio → criativo) já está modelado. Ainda não há
      system user/token resolvido pelo Cofre nem leitura de uma conta real; por isso esta tela
      não inventa campanhas ou desempenho.
    </p>
    <div className="mt-5 grid max-w-3xl gap-3 sm:grid-cols-2">
      <div className="rounded-md border border-border bg-card p-4">
        <CheckCircle2 className="h-4 w-4 text-success" aria-hidden />
        <p className="mt-2 text-sm font-medium">Pronto localmente</p>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          Contrato v26, hierarquia, identidade, paginação segura e read model preparados.
        </p>
      </div>
      <div className="rounded-md border border-border bg-card p-4">
        <KeyRound className="h-4 w-4 text-warning-foreground" aria-hidden />
        <p className="mt-2 text-sm font-medium">Próximo ato</p>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          Referenciar a integração Meta no Cofre e provar uma leitura real somente leitura.
        </p>
      </div>
    </div>
    <div className="mt-4 flex flex-wrap gap-4">
      <Link
        to="/settings/cofre-ativos"
        className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline-offset-2 hover:underline"
      >
        abrir Cofre de Ativos
      </Link>
      <Link
        to="/trafego?rede=google"
        className="inline-flex min-h-11 items-center text-sm font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
      >
        voltar para Google Ads
      </Link>
    </div>
  </section>
);

export default MetaNaoConfigurada;
