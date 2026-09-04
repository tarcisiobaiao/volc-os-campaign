/** Fundação local presente, integração externa ainda fechada. */
import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, CheckCircle2, CircleAlert } from 'lucide-react';

import { rotuloDoNivelMeta } from './perfilDeCanal';
import type { NivelMeta } from './contrato';
import { MetaInventarioDemo } from '@/components/trafego/meta/MetaInventarioDemo';

export const MetaNaoConfigurada: React.FC<{
  nivel: NivelMeta;
  secao?: 'campanhas' | 'preparar' | 'atencao';
}> = ({ nivel, secao = 'campanhas' }) => secao === 'campanhas' ? (
  <MetaInventarioDemo nivel={nivel} />
) : secao === 'preparar' ? (
  <section className="rounded-md border border-border bg-card p-5 shadow-card">
    <p className="kicker">Estúdio de criação Meta</p>
    <h2 className="mt-2 font-display text-xl font-semibold">Do objetivo ao anúncio, sem esconder a hierarquia</h2>
    <p className="mt-2 max-w-[68ch] text-sm leading-relaxed text-muted-foreground">
      A bancada já pode ser explorada com um cenário demonstrativo. Ela percorre campanha,
      conjunto, público, criativo, mensuração e revisão; o envio real continua bloqueado.
    </p>
    <Link
      to="/trafego/meta/nova?modo=demo"
      className="mt-5 inline-flex min-h-10 items-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground transition-[background-color,transform] duration-150 hover:bg-primary/90 active:scale-[0.96] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    >
      Explorar criação Meta <ArrowRight className="h-4 w-4" aria-hidden />
    </Link>
  </section>
) : (
  <section
    aria-label="Atenção Meta"
    className="rounded-md border border-border bg-card p-5 shadow-card"
  >
    <p className="kicker">Meta Ads</p>
    <h2 className="mt-2 font-display text-xl font-semibold">Duas pendências para sair do modo demonstrativo</h2>
    <p className="mt-2 max-w-[68ch] text-[13px] leading-relaxed text-muted-foreground">
      A interface e o contrato de <span className="font-medium text-foreground">{rotuloDoNivelMeta(nivel)}</span> estão
      disponíveis. A engrenagem no cabeçalho valida o token local; depois, o read model precisa
      ser conectado à conta escolhida.
    </p>
    <div className="mt-5 grid max-w-3xl gap-3 sm:grid-cols-2">
      <div className="rounded-md border border-border bg-muted/20 p-4">
        <CheckCircle2 className="h-4 w-4 text-success" aria-hidden />
        <p className="mt-2 text-sm font-medium">Interface explorável</p>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          Campanhas, conjuntos, anúncios, criativos, detalhe e criação estão navegáveis.
        </p>
      </div>
      <div className="rounded-md border border-warning/25 bg-warning/5 p-4">
        <CircleAlert className="h-4 w-4 text-warning" aria-hidden />
        <p className="mt-2 text-sm font-medium">Leitura real pendente</p>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          Salvar e testar o token neste Mac; nenhuma ação de mídia será habilitada.
        </p>
      </div>
    </div>
    <div className="mt-4 flex flex-wrap gap-4">
      <Link
        to="/trafego/meta/nova?modo=demo"
        className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline-offset-2 hover:underline"
      >
        abrir bancada demonstrativa
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
