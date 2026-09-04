import React from 'react';
import {
  Aperture, Check, CircleDashed, Eye, Globe2, Image as ImageIcon,
  MapPin, ShieldAlert, ShieldCheck, Users2,
} from 'lucide-react';

import type { Cockpit } from '@/types/trafego';
import type { LeituraDoDestinoPago } from '@/lib/landing-policy/prontidao';
import { cn } from '@/lib/utils';
import { LinhaDeFato } from '../BlocoDeEvidencia';
import { Input } from '@/components/ui/input';
import type { AssetDemandGen } from '@/types/trafego';
import {
  AcaoDeProva, CampoDeTexto, EditorDeLista, IrParaEstudio, SeletorDeAsset,
} from './ControlesMulticanal';

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
        <h3 className="mt-1 font-display text-xl font-semibold">Inventário aberto, sem segmentação inventada</h3>
        <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted-foreground">
          O builder atual não opera user lists, tópicos, custom audiences, intenção ou demografia. A campanha nasce em inventário aberto, escolhido pelo lance; adicionar um campo aqui faria a interface prometer algo que o payload descarta.
        </p>
      </div>
    </div>
    <div className="flex items-center gap-3 border-y border-border py-4 text-sm">
      <CircleDashed className="h-4 w-4 text-warning" aria-hidden />
      <span className="font-medium">Segmentação positiva indisponível nesta fatia do engine</span>
    </div>
  </section>
);

export const ParadaDisplayCriativo: React.FC<{
  nomeEmpresa: string;
  onNomeEmpresa: (valor: string) => void;
  titulos: string;
  onTitulos: (valor: string) => void;
  tituloLongo: string;
  onTituloLongo: (valor: string) => void;
  descricoes: string;
  onDescricoes: (valor: string) => void;
  videos: string;
  onVideos: (valor: string) => void;
  assets: AssetDemandGen[];
  onAssets: (assets: AssetDemandGen[]) => void;
}> = ({
  nomeEmpresa, onNomeEmpresa, titulos, onTitulos, tituloLongo, onTituloLongo,
  descricoes, onDescricoes, videos, onVideos, assets, onAssets,
}) => (
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
    <div className="mt-5 grid gap-4 sm:grid-cols-2">
      <SeletorDeAsset id="display-marketing" rotulo="Imagem horizontal" tipo="imagem_marketing" detalhe="1.91:1 · mínimo 600×314 · obrigatória" assets={assets} onChange={onAssets} maximo={15} />
      <SeletorDeAsset id="display-square" rotulo="Imagem quadrada" tipo="imagem_marketing_quadrada" detalhe="1:1 · mínimo 300×300 · obrigatória" assets={assets} onChange={onAssets} maximo={15} />
      <SeletorDeAsset id="display-logo-landscape" rotulo="Logo horizontal" tipo="logo_paisagem" detalhe="4:1 · opcional · até 5 logos no total" assets={assets} onChange={onAssets} maximo={5} />
      <SeletorDeAsset id="display-logo-square" rotulo="Logo quadrado" tipo="logo_quadrado" detalhe="1:1 · opcional · até 5 logos no total" assets={assets} onChange={onAssets} maximo={5} />
    </div>
    <div className="mt-4 flex justify-end"><IrParaEstudio canal="DISPLAY" /></div>
    <div className="mt-6 grid gap-5 border-t border-border pt-6 lg:grid-cols-2">
      <CampoDeTexto id="display-business-name" rotulo="Nome da empresa" valor={nomeEmpresa} onChange={onNomeEmpresa} limite={25} placeholder="Ex.: Portal Mundo Mais" />
      <CampoDeTexto id="display-long-headline" rotulo="Título longo" valor={tituloLongo} onChange={onTituloLongo} limite={90} placeholder="Uma promessa editorial clara" />
      <EditorDeLista id="display-headlines" rotulo="Títulos" valor={titulos} onChange={onTitulos} minimo={1} maximo={5} limitePorItem={30} placeholder={'Título 1\nTítulo 2'} />
      <EditorDeLista id="display-descriptions" rotulo="Descrições" valor={descricoes} onChange={onDescricoes} minimo={1} maximo={5} limitePorItem={90} placeholder={'Descrição 1\nDescrição 2'} />
      <div className="lg:col-span-2">
        <EditorDeLista id="display-videos" rotulo="Vídeos do YouTube (opcional)" valor={videos} onChange={onVideos} maximo={5} placeholder="customers/123/assets/456" ajuda="resource name de asset já existente na mesma conta" linhas={3} />
      </div>
    </div>
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
          A fatia atual ainda não monta exclusões de placement nem filtros de inventário. O plano declara essa ausência; a interface não exibe seletores sem efeito.
        </p>
      </div>
    </div>
    <div className="flex items-center gap-3 border-y border-border py-4 text-sm">
      <Eye className="h-4 w-4 text-muted-foreground" aria-hidden />
      <span>Brand safety customizada ainda não é operada pelo builder Display.</span>
    </div>
  </section>
);

export const ParadaDisplayEconomia: React.FC<{
  cockpit: Cockpit;
  orcamento: number | null;
  orcamentoBruto: string;
  onOrcamento: (valor: string) => void;
  tcpa: string;
  onTcpa: (valor: string) => void;
}> = ({ cockpit, orcamento, orcamentoBruto, onOrcamento, tcpa, onTcpa }) => (
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
    <div className="grid gap-5 sm:grid-cols-2">
      <label className="space-y-2 text-sm font-semibold">
        <span>Orçamento diário</span>
        <Input inputMode="decimal" value={orcamentoBruto} onChange={(e) => onOrcamento(e.target.value)} placeholder="10,00" className="h-11 bg-background" />
        <span className="block text-xs font-normal text-muted-foreground">Moeda da conta · a campanha nasce pausada.</span>
      </label>
      <label className="space-y-2 text-sm font-semibold">
        <span>CPA-alvo (opcional)</span>
        <Input inputMode="decimal" value={tcpa} onChange={(e) => onTcpa(e.target.value)} placeholder="Deixe vazio para MaxConv puro" className="h-11 bg-background" />
        <span className="block text-xs font-normal text-muted-foreground">Estratégia fixa: maximizar conversões. O motor não aceita CPC manual em Display.</span>
      </label>
    </div>
  </section>
);

export const ParadaDisplayRevisao: React.FC<{
  url: string | null;
  faltas: string[];
  estadoDaProva: 'ociosa' | 'provando' | 'aprovada' | 'recusada';
  mensagemDaProva: string | null;
  onProvar: () => void;
}> = ({ url, faltas, estadoDaProva, mensagemDaProva, onProvar }) => (
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
    <AcaoDeProva estado={estadoDaProva} mensagem={mensagemDaProva} desabilitada={faltas.length > 0} motivo={faltas[0] ?? null} onProvar={onProvar} somenteLocal />
  </section>
);
