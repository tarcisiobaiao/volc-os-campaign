import React from 'react';
import {
  Ban, CircleDashed, Film, FolderArchive, Globe2, Image as ImageIcon,
  Link2Off, Search, ShieldCheck, Sparkles, Target, Users2,
} from 'lucide-react';

import type { Cockpit } from '@/types/trafego';
import type { LeituraDoDestinoPago } from '@/lib/landing-policy/prontidao';
import { cn } from '@/lib/utils';
import { LinhaDeFato } from '../BlocoDeEvidencia';

export const ParadaPMaxObjetivo: React.FC<{ cockpit: Cockpit }> = ({ cockpit }) => (
  <section className="space-y-6">
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
        <Target className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <p className="kicker text-muted-foreground">performance max</p>
        <h3 className="mt-1 font-display text-xl font-semibold">O objetivo vem antes da automação</h3>
        <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">
          PMax distribui a campanha por vários inventários. Sem uma meta de conversão observada, automatizar alcance não significa otimizar resultado.
        </p>
      </div>
    </div>
    <dl className="grid gap-4 border-y border-border py-5 sm:grid-cols-2">
      <LinhaDeFato rotulo="Conta" valor={cockpit.conta?.customer_id ?? null} fonte="projeto" />
      <LinhaDeFato rotulo="Meta efetiva" valor={cockpit.conta?.meta_conversao?.primaria?.nome ?? null} fonte="conta" />
    </dl>
  </section>
);

export const ParadaPMaxLp: React.FC<{
  cockpit: Cockpit;
  destino: LeituraDoDestinoPago;
}> = ({ cockpit, destino }) => (
  <div className="space-y-6">
    <section className="destination-hero">
      <div className="destination-hero-icon" aria-hidden><Globe2 className="h-5 w-5" /></div>
      <div className="min-w-0 flex-1">
        <p className="kicker text-muted-foreground">único destino permitido</p>
        <p className="mt-1 break-all font-display text-lg font-semibold text-foreground sm:text-xl">
          {cockpit.origem?.url_final ?? 'Aguardando uma LP aprovada'}
        </p>
        <p className="mt-1 text-sm text-muted-foreground">A URL nasce do funil e volta a ser conferida na revisão.</p>
      </div>
      <span className={cn(
        'destination-status',
        destino.apto_para_campanha ? 'destination-status-ok' : 'destination-status-blocked',
      )}>
        {destino.apto_para_campanha ? <ShieldCheck className="h-4 w-4" /> : <CircleDashed className="h-4 w-4" />}
        {destino.apto_para_campanha ? 'LP apta' : 'aguarda prova'}
      </span>
    </section>

    <div className="flex gap-4 border-y border-primary/20 bg-primary/[0.035] px-1 py-5">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-primary/10 text-primary"><Link2Off className="h-5 w-5" /></span>
      <div>
        <p className="text-sm font-semibold text-foreground">Trava de URL exclusiva</p>
        <p className="mt-1 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">
          O Google não pode escolher outra página do domínio. Final URL expansion permanece desligada e a revisão recusa deriva do destino aprovado.
        </p>
      </div>
    </div>
  </div>
);

export const ParadaPMaxAssetGroup: React.FC = () => (
  <section>
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-verified/10 text-verified"><FolderArchive className="h-5 w-5" /></span>
      <div>
        <p className="kicker text-muted-foreground">asset group</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Uma história completa, não uma coleção de arquivos</h3>
        <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted-foreground">O grupo só fica elegível quando texto e mídia aprovados cobrem os formatos mínimos. Nada abaixo foi lido ainda.</p>
      </div>
    </div>
    <div className="mt-6 grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
      {[
        [ImageIcon, 'Imagens', 'paisagem, quadrado e retrato'],
        [Sparkles, 'Textos', 'headlines, long headlines e descriptions'],
        [Film, 'Vídeos', 'asset próprio, sem geração silenciosa'],
        [ShieldCheck, 'Logos', 'marca aprovada e proporções válidas'],
      ].map(([Icon, titulo, detalhe]) => {
        const Glyph = Icon as typeof ImageIcon;
        return (
          <div key={String(titulo)} className="min-h-36 bg-card p-4">
            <Glyph className="h-5 w-5 text-muted-foreground" aria-hidden />
            <p className="mt-6 text-sm font-semibold">{String(titulo)}</p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{String(detalhe)}</p>
            <p className="mt-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">não lido</p>
          </div>
        );
      })}
    </div>
  </section>
);

export const ParadaPMaxSinais: React.FC = () => (
  <section className="space-y-6">
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-info/10 text-info"><Users2 className="h-5 w-5" /></span>
      <div>
        <p className="kicker text-muted-foreground">orientação do algoritmo</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Sinais ajudam a começar; não restringem como keywords</h3>
        <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted-foreground">Audience signals e Search Themes são pistas para o sistema. Eles não são termos de correspondência e não garantem em qual busca a campanha aparece.</p>
      </div>
    </div>
    <div className="grid gap-4 border-y border-border py-5 sm:grid-cols-2">
      <div className="flex gap-3"><Users2 className="mt-0.5 h-4 w-4 text-muted-foreground" /><div><p className="text-sm font-semibold">Audience signals</p><p className="mt-1 text-xs text-muted-foreground">não informados</p></div></div>
      <div className="flex gap-3"><Search className="mt-0.5 h-4 w-4 text-muted-foreground" /><div><p className="text-sm font-semibold">Search Themes</p><p className="mt-1 text-xs text-muted-foreground">não informados · não são keywords</p></div></div>
    </div>
  </section>
);

export const ParadaPMaxMarca: React.FC = () => (
  <section className="space-y-6">
    <div>
      <p className="kicker text-muted-foreground">controles de automação</p>
      <h3 className="mt-1 font-display text-xl font-semibold">O Google pode combinar assets, não trocar o destino</h3>
    </div>
    <div className="divide-y divide-border border-y border-border">
      <div className="flex items-center gap-4 py-4">
        <span className="grid h-9 w-9 place-items-center rounded-full bg-success/10 text-success"><Ban className="h-4 w-4" /></span>
        <div className="min-w-0 flex-1"><p className="text-sm font-semibold">Final URL expansion</p><p className="mt-0.5 text-xs text-muted-foreground">Nenhuma página alternativa do domínio.</p></div>
        <span className="rounded-full border border-success/30 bg-success/10 px-3 py-1 text-xs font-bold text-success">DESLIGADA</span>
      </div>
      <div className="flex items-center gap-4 py-4">
        <span className="grid h-9 w-9 place-items-center rounded-full border border-border text-muted-foreground"><Sparkles className="h-4 w-4" /></span>
        <div className="min-w-0 flex-1"><p className="text-sm font-semibold">Automação de assets de texto</p><p className="mt-0.5 text-xs text-muted-foreground">Decisão separada; nenhum estado foi lido nesta oportunidade.</p></div>
        <span className="text-xs font-semibold text-muted-foreground">não lida</span>
      </div>
    </div>
  </section>
);

export const ParadaPMaxEconomia: React.FC<{ cockpit: Cockpit; orcamento: number | null }> = ({ cockpit, orcamento }) => (
  <section className="space-y-5">
    <div>
      <p className="kicker text-muted-foreground">economia automatizada</p>
      <h3 className="mt-1 font-display text-xl font-semibold">Bidding depende de uma meta confiável</h3>
      <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">Esta bancada não reutiliza CPC manual do Search. Alvo e estratégia só podem nascer do contrato PMax.</p>
    </div>
    <dl className="grid gap-4 border-y border-border py-5 sm:grid-cols-3">
      <LinhaDeFato rotulo="Orçamento" valor={orcamento == null ? null : `R$ ${orcamento.toFixed(2).replace('.', ',')}/dia`} fonte="rascunho" />
      <LinhaDeFato rotulo="Estratégia" valor={null} fonte="não declarada para PMax" />
      <LinhaDeFato rotulo="Meta efetiva" valor={cockpit.conta?.meta_conversao?.primaria?.nome ?? null} fonte="conta" />
    </dl>
  </section>
);

export const ParadaPMaxRevisao: React.FC<{ url: string | null; faltas: string[] }> = ({ url, faltas }) => (
  <section className="space-y-6">
    <div className="flex items-start justify-between gap-4 border-b border-border pb-5">
      <div>
        <p className="kicker text-muted-foreground">revisão PMax</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Plano local, criação ainda fechada</h3>
        <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">O asset group pode ser desenhado, mas a ponte HTTP desta lane ainda não autoriza criar. Nenhum botão de mutate é exibido.</p>
      </div>
      <span className="shrink-0 rounded-full border border-info/30 bg-info/10 px-3 py-1 text-xs font-semibold text-info">planejamento</span>
    </div>
    <dl className="grid gap-4 sm:grid-cols-2">
      <LinhaDeFato rotulo="URL exclusiva" valor={url} fonte="funil" />
      <LinhaDeFato rotulo="Expansão de URL" valor="desligada" fonte="contrato PMax" />
    </dl>
    {faltas.length > 0 && <p className="text-sm text-muted-foreground">Próximo: {faltas[0]}</p>}
  </section>
);
