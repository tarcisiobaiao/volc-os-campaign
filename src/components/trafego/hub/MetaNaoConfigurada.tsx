/** Fundação local presente, integração externa ainda fechada. */
import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, CheckCircle2, CircleAlert } from 'lucide-react';

import { rotuloDoNivelMeta } from './perfilDeCanal';
import type { NivelMeta } from './contrato';
import { MetaInventarioDemo } from '@/components/trafego/meta/MetaInventarioDemo';
import { MetaReadPreview } from '@/components/trafego/meta/MetaReadPreview';

export const MetaNaoConfigurada: React.FC<{
  nivel: NivelMeta;
  secao?: 'campanhas' | 'preparar' | 'atencao';
}> = ({ nivel, secao = 'campanhas' }) => secao === 'campanhas' ? (
  <>
    <section className="mb-6 flex flex-wrap items-center justify-between gap-5 border-b border-border pb-6">
      <div><h2 className="font-display text-2xl font-semibold">Sua próxima campanha começa aqui</h2>
        <p className="mt-2 max-w-xl text-sm text-muted-foreground">Defina o destino, escolha o resultado e prepare os criativos. O acompanhamento por conjunto já entra no plano.</p></div>
      <Link to="/trafego/meta/nova" className="inline-flex min-h-12 items-center gap-2 rounded-md bg-primary px-5 text-sm font-semibold text-primary-foreground focus-visible:ring-2 focus-visible:ring-ring">
        Criar campanha guiada <ArrowRight className="h-4 w-4" aria-hidden /></Link>
    </section>
    <details className="mb-5 rounded-lg border border-border bg-card p-4">
      <summary className="cursor-pointer text-sm font-medium">Conexão e sincronização da conta</summary>
      <div className="mt-4"><MetaReadPreview /></div>
    </details>
    <details className="text-sm"><summary className="cursor-pointer py-3 font-medium">Explorar campanhas de demonstração</summary>
      <MetaInventarioDemo nivel={nivel} />
    </details>
  </>
) : secao === 'preparar' ? (
  <section className="rounded-md border border-border bg-card p-5 shadow-card">
    <p className="kicker">Estúdio de criação Meta</p>
    <h2 className="mt-2 font-display text-xl font-semibold">Prepare sua campanha, uma decisão por vez</h2>
    <p className="mt-2 max-w-[68ch] text-sm leading-relaxed text-muted-foreground">
      Comece pelo destino. Depois escolha o resultado, o público, o orçamento e os criativos.
      Você confere o plano antes de qualquer envio. Criar depende de aprovação e liberação do servidor.
    </p>
    <Link
      to="/trafego/meta/nova"
      className="mt-5 inline-flex min-h-10 items-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground transition-[background-color,transform] duration-150 hover:bg-primary/90 active:scale-[0.96] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    >
      Criar campanha guiada <ArrowRight className="h-4 w-4" aria-hidden />
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
