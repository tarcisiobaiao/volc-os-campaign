import React from 'react';
import {
  Aperture, Check, CircleDashed, Eye, Globe2, Image as ImageIcon,
  MapPin, ShieldAlert, ShieldCheck, Users2,
} from 'lucide-react';

import type { Cockpit } from '@/types/trafego';
import type { LeituraDoDestinoPago } from '@/lib/landing-policy/prontidao';
import { cn } from '@/lib/utils';
import { LinhaDeFato } from '../BlocoDeEvidencia';

const LinhaDeRequisito: React.FC<{
  titulo: string;
  detalhe: string;
  estado?: 'presente' | 'nao_lido' | 'obrigatorio';
}> = ({ titulo, detalhe, estado = 'nao_lido' }) => {
  const Icon = estado === 'presente' ? Check : estado === 'obrigatorio' ? Aperture : CircleDashed;
  return (
    <li className="flex min-h-16 items-start gap-3 border-b border-border/80 py-3 last:border-0">
      <span className={cn(
        'mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full border',
        estado === 'presente'
          ? 'border-success/30 bg-success/10 text-success'
          : 'border-border bg-muted/50 text-muted-foreground',
      )}>
        <Icon className="h-4 w-4" aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold text-foreground">{titulo}</span>
        <span className="mt-0.5 block text-[13px] leading-relaxed text-muted-foreground">{detalhe}</span>
      </span>
      <span className="mt-1 whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        {estado === 'presente' ? 'presente' : estado === 'obrigatorio' ? 'requerido' : 'não lido'}
      </span>
    </li>
  );
};

export const ParadaDisplayDestino: React.FC<{
  cockpit: Cockpit;
  destino: LeituraDoDestinoPago;
}> = ({ cockpit, destino }) => {
  const url = cockpit.origem?.url_final ?? null;
  return (
    <div className="space-y-6">
      <section className="destination-hero">
        <div className="destination-hero-icon" aria-hidden><Globe2 className="h-5 w-5" /></div>
        <div className="min-w-0 flex-1">
          <p className="kicker text-muted-foreground">destino comprado</p>
          <p className="mt-1 break-all font-display text-lg font-semibold text-foreground sm:text-xl">
            {url ?? 'O funil ainda não declarou um endereço'}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            A campanha Display não pode trocar este endereço silenciosamente.
          </p>
        </div>
        <span className={cn(
          'destination-status',
          destino.apto_para_campanha ? 'destination-status-ok' : 'destination-status-blocked',
        )}>
          {destino.apto_para_campanha ? <ShieldCheck className="h-4 w-4" /> : <CircleDashed className="h-4 w-4" />}
          {destino.apto_para_campanha ? 'destino apto' : 'aguarda prova'}
        </span>
      </section>

      <div className="grid gap-4 border-t border-border pt-5 sm:grid-cols-2">
        <LinhaDeFato rotulo="Conta" valor={cockpit.conta?.customer_id ?? null} fonte="projeto" />
        <LinhaDeFato rotulo="Objetivo" valor={null} fonte="ainda não declarado" />
      </div>
    </div>
  );
};

export const ParadaDisplayGeografia: React.FC<{ cockpit: Cockpit }> = ({ cockpit }) => (
  <section className="space-y-6">
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-info/10 text-info">
        <MapPin className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <h3 className="font-display text-lg font-semibold">Onde a impressão pode acontecer</h3>
        <p className="mt-1 max-w-[62ch] text-sm leading-relaxed text-muted-foreground">
          País e idioma vêm da oportunidade. Expansões de rede e localização só aparecem quando o servidor as declarar.
        </p>
      </div>
    </div>
    <dl className="grid gap-4 border-y border-border py-5 sm:grid-cols-2">
      <LinhaDeFato rotulo="País" valor={cockpit.origem?.pais ?? null} fonte="oportunidade" />
      <LinhaDeFato rotulo="Idioma" valor={cockpit.origem?.idioma ?? null} fonte="oportunidade" />
    </dl>
  </section>
);

export const ParadaDisplayAudiencia: React.FC = () => (
  <section className="space-y-6">
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
        <Users2 className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <p className="kicker text-muted-foreground">controle de alcance</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Audiência não é um chute por interesse</h3>
        <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted-foreground">
          Esta oportunidade ainda não trouxe um recibo de audiência. O VOLC preserva o estado como não lido, sem inventar público ou transformar ausência em segmentação ampla.
        </p>
      </div>
    </div>
    <div className="flex items-center gap-3 border-y border-border py-4 text-sm">
      <CircleDashed className="h-4 w-4 text-warning" aria-hidden />
      <span className="font-medium">Audiência e contexto ainda não medidos</span>
    </div>
  </section>
);

export const ParadaDisplayCriativo: React.FC = () => (
  <section>
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-verified/10 text-verified">
        <ImageIcon className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <p className="kicker text-muted-foreground">responsive display ad</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Cobertura criativa</h3>
        <p className="mt-2 text-sm text-muted-foreground">O Estúdio precisa entregar recursos aprovados; esta bancada não substitui arquivos ausentes por placeholders.</p>
      </div>
    </div>
    <ul className="mt-5 border-y border-border" aria-label="requisitos do criativo Display">
      <LinhaDeRequisito titulo="Imagem horizontal" detalhe="Marketing image na proporção aceita pelo contrato." estado="obrigatorio" />
      <LinhaDeRequisito titulo="Imagem quadrada" detalhe="Variação para inventários responsivos." estado="obrigatorio" />
      <LinhaDeRequisito titulo="Logo e identidade" detalhe="Somente assets aprovados no Estúdio." />
      <LinhaDeRequisito titulo="Mensagem" detalhe="Headlines, long headline, descriptions e nome da empresa." estado="obrigatorio" />
    </ul>
  </section>
);

export const ParadaDisplayInventario: React.FC = () => (
  <section className="space-y-5">
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-warning/10 text-warning">
        <ShieldAlert className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <p className="kicker text-muted-foreground">brand safety</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Proteções antes de ganhar alcance</h3>
        <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">
          Posicionamentos, exclusões e inventário sensível só ficam verdes com evidência da conta. O construtor não converte “não lido” em configuração segura.
        </p>
      </div>
    </div>
    <div className="flex items-center gap-3 border-y border-border py-4 text-sm">
      <Eye className="h-4 w-4 text-muted-foreground" aria-hidden />
      <span>Configuração da conta ainda não lida nesta oportunidade.</span>
    </div>
  </section>
);

export const ParadaDisplayEconomia: React.FC<{ cockpit: Cockpit; orcamento: number | null }> = ({ cockpit, orcamento }) => (
  <section className="space-y-5">
    <div>
      <p className="kicker text-muted-foreground">economia da impressão</p>
      <h3 className="mt-1 font-display text-xl font-semibold">Compra e medição</h3>
      <p className="mt-2 text-sm text-muted-foreground">A interface não reutiliza CPC manual do Search para um canal que compra de outra forma.</p>
    </div>
    <dl className="grid gap-4 border-y border-border py-5 sm:grid-cols-3">
      <LinhaDeFato rotulo="Conta vinculada" valor={cockpit.conta?.vinculada ? 'sim' : null} fonte="projeto" />
      <LinhaDeFato rotulo="Orçamento" valor={orcamento == null ? null : `R$ ${orcamento.toFixed(2).replace('.', ',')}/dia`} fonte="rascunho" />
      <LinhaDeFato rotulo="Conversão" valor={cockpit.conta?.meta_conversao?.primaria?.nome ?? null} fonte="conta" />
    </dl>
  </section>
);

export const ParadaDisplayRevisao: React.FC<{ url: string | null; faltas: string[] }> = ({ url, faltas }) => (
  <section className="space-y-6">
    <div className="flex items-start justify-between gap-4 border-b border-border pb-5">
      <div>
        <p className="kicker text-muted-foreground">revisão Display</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Pedido visual em preparação</h3>
        <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">
          A criação pausada só aparece quando assets, destino e portão do servidor convergirem. Esta tela ainda não envia nada ao Google.
        </p>
      </div>
      <span className="shrink-0 rounded-full border border-warning/30 bg-warning/10 px-3 py-1 text-xs font-semibold text-warning">preparação</span>
    </div>
    <dl className="grid gap-4 sm:grid-cols-2">
      <LinhaDeFato rotulo="Destino" valor={url} fonte="funil" />
      <LinhaDeFato rotulo="Criação real" valor={null} fonte="depende do portão do servidor" />
    </dl>
    {faltas.length > 0 && <p className="text-sm text-muted-foreground">Próximo: {faltas[0]}</p>}
  </section>
);
