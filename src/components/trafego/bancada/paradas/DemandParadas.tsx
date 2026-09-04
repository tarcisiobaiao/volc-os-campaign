import React from 'react';
import {
  CircleDashed, Film, Globe2, Image as ImageIcon, LayoutTemplate,
  MessageSquareText, ScanSearch, ShieldCheck, Users2,
} from 'lucide-react';

import type { Cockpit } from '@/types/trafego';
import type { LeituraDoDestinoPago } from '@/lib/landing-policy/prontidao';
import { cn } from '@/lib/utils';
import { LinhaDeFato } from '../BlocoDeEvidencia';

const Superficie: React.FC<{ nome: string; detalhe: string }> = ({ nome, detalhe }) => (
  <li className="flex min-h-20 items-center gap-3 border-b border-border/80 py-3 last:border-0">
    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-border bg-muted/50 text-muted-foreground">
      <CircleDashed className="h-4 w-4" aria-hidden />
    </span>
    <span>
      <span className="block text-sm font-semibold">{nome}</span>
      <span className="mt-0.5 block text-[13px] text-muted-foreground">{detalhe}</span>
    </span>
    <span className="ml-auto text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">não selecionado</span>
  </li>
);

export const ParadaDemandResultado: React.FC<{
  cockpit: Cockpit;
  destino: LeituraDoDestinoPago;
}> = ({ cockpit, destino }) => (
  <div className="space-y-6">
    <section className="destination-hero">
      <div className="destination-hero-icon" aria-hidden><Globe2 className="h-5 w-5" /></div>
      <div className="min-w-0 flex-1">
        <p className="kicker text-muted-foreground">resultado e destino</p>
        <p className="mt-1 break-all font-display text-lg font-semibold text-foreground sm:text-xl">
          {cockpit.origem?.url_final ?? 'Endereço não declarado'}
        </p>
        <p className="mt-1 text-sm text-muted-foreground">A descoberta começa numa LP identificada — não numa URL escolhida depois.</p>
      </div>
      <span className={cn(
        'destination-status',
        destino.apto_para_campanha ? 'destination-status-ok' : 'destination-status-blocked',
      )}>
        {destino.apto_para_campanha ? <ShieldCheck className="h-4 w-4" /> : <CircleDashed className="h-4 w-4" />}
        {destino.apto_para_campanha ? 'destino apto' : 'aguarda prova'}
      </span>
    </section>
    <dl className="grid gap-4 border-t border-border pt-5 sm:grid-cols-2">
      <LinhaDeFato rotulo="Conta" valor={cockpit.conta?.customer_id ?? null} fonte="projeto" />
      <LinhaDeFato rotulo="Meta observada" valor={cockpit.conta?.meta_conversao?.primaria?.nome ?? null} fonte="conta" />
    </dl>
  </div>
);

export const ParadaDemandSuperficies: React.FC = () => (
  <section>
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-info/10 text-info">
        <LayoutTemplate className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <p className="kicker text-muted-foreground">inventário nativo</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Escolha de superfícies é uma decisão explícita</h3>
        <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted-foreground">
          O contrato do canal admite combinações diferentes. Nenhuma delas foi escolhida por esta oportunidade; por isso a tela não assume “todas”.
        </p>
      </div>
    </div>
    <ul className="mt-5 border-y border-border" aria-label="superfícies Demand Gen">
      <Superficie nome="YouTube" detalhe="In-stream, In-feed e Shorts dependem da seleção do pedido." />
      <Superficie nome="Discover e Gmail" detalhe="Superfícies próprias do Google, separadas de Display de terceiros." />
      <Superficie nome="Display e Maps" detalhe="Só entram quando o ramo de canais selecionados os declarar." />
    </ul>
  </section>
);

export const ParadaDemandAudiencia: React.FC = () => (
  <section className="space-y-5">
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
        <Users2 className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <p className="kicker text-muted-foreground">sinais ≠ certeza</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Audiência, intenção e exclusões viajam separadas</h3>
        <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted-foreground">
          Ainda não há resource names aprovados para esta oportunidade. Nada é convertido em lookalike, intenção ou público amplo por conveniência.
        </p>
      </div>
    </div>
    <div className="grid gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-3">
      {['Audiência positiva', 'Intenção', 'Exclusões'].map((item) => (
        <div key={item} className="bg-card p-4">
          <p className="text-sm font-semibold">{item}</p>
          <p className="mt-1 text-xs text-muted-foreground">não informado</p>
        </div>
      ))}
    </div>
  </section>
);

export const ParadaDemandKit: React.FC = () => (
  <section>
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-verified/10 text-verified">
        <ImageIcon className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <p className="kicker text-muted-foreground">kit de mídia</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Uma família visual, vários enquadramentos</h3>
        <p className="mt-2 text-sm text-muted-foreground">A cobertura só será medida quando o Estúdio entregar assets com recibo e geometria válidos.</p>
      </div>
    </div>
    <div className="mt-6 grid gap-3 sm:grid-cols-3">
      {[
        ['Paisagem', '1.91:1', 'aspect-[1.91/1]'],
        ['Quadrado', '1:1', 'aspect-square'],
        ['Retrato', '4:5 / 9:16', 'aspect-[4/5]'],
      ].map(([nome, proporcao, aspect]) => (
        <div key={nome} className="min-w-0">
          <div className={cn('grid place-items-center rounded-lg border border-dashed border-border bg-muted/30', aspect)}>
            <ImageIcon className="h-5 w-5 text-muted-foreground/60" aria-hidden />
          </div>
          <div className="mt-2 flex items-center justify-between gap-2 text-xs">
            <span className="font-semibold">{nome}</span><span className="text-muted-foreground">{proporcao}</span>
          </div>
        </div>
      ))}
    </div>
    <div className="mt-5 flex items-center gap-3 border-t border-border pt-4 text-sm text-muted-foreground">
      <Film className="h-4 w-4" aria-hidden /> Vídeo e logos continuam não lidos nesta oportunidade.
    </div>
  </section>
);

export const ParadaDemandMensagem: React.FC = () => (
  <section className="space-y-5">
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-info/10 text-info">
        <MessageSquareText className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <p className="kicker text-muted-foreground">mensagem nativa</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Copy criada para descoberta, não transplantada do Search</h3>
        <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">
          Business name, headlines, descriptions e CTA ainda aguardam o contrato do Estúdio. A UI não reaproveita automaticamente uma RSA.
        </p>
      </div>
    </div>
  </section>
);

export const ParadaDemandEconomia: React.FC<{ cockpit: Cockpit; orcamento: number | null }> = ({ cockpit, orcamento }) => (
  <section className="space-y-5">
    <div>
      <p className="kicker text-muted-foreground">prova antes da criação</p>
      <h3 className="mt-1 font-display text-xl font-semibold">Economia e medição</h3>
      <p className="mt-2 text-sm text-muted-foreground">Demand Gen pode ser preparado para conferência; a criação real permanece fechada nesta onda.</p>
    </div>
    <dl className="grid gap-4 border-y border-border py-5 sm:grid-cols-3">
      <LinhaDeFato rotulo="Conta vinculada" valor={cockpit.conta?.vinculada ? 'sim' : null} fonte="projeto" />
      <LinhaDeFato rotulo="Orçamento" valor={orcamento == null ? null : `R$ ${orcamento.toFixed(2).replace('.', ',')}/dia`} fonte="rascunho" />
      <LinhaDeFato rotulo="Mutação real" valor="fechada" fonte="contrato do canal" />
    </dl>
  </section>
);

export const ParadaDemandRevisao: React.FC<{ url: string | null; faltas: string[] }> = ({ url, faltas }) => (
  <section className="space-y-6">
    <div className="flex items-start gap-4 border-b border-border pb-5">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary"><ScanSearch className="h-5 w-5" /></span>
      <div>
        <p className="kicker text-muted-foreground">revisão Demand Gen</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Preparar para validar, sem criar</h3>
        <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">O próximo produto é um pedido provável e um kit de mídia completo. A CTA de criação permanece ausente enquanto o mutate estiver fechado.</p>
      </div>
    </div>
    <dl className="grid gap-4 sm:grid-cols-2">
      <LinhaDeFato rotulo="Destino" valor={url} fonte="funil" />
      <LinhaDeFato rotulo="Ato disponível" valor="preparar" fonte="interface local" />
    </dl>
    {faltas.length > 0 && <p className="text-sm text-muted-foreground">Próximo: {faltas[0]}</p>}
  </section>
);
