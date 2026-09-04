import React from 'react';
import {
  CircleDashed, Film, Globe2, Image as ImageIcon, LayoutTemplate,
  MessageSquareText, ScanSearch, ShieldCheck, Users2,
} from 'lucide-react';

import type { Cockpit } from '@/types/trafego';
import type {
  AssetDemandGen, CanalSelecionavelDemandGen, EstrategiaDeCanaisDemandGen,
} from '@/types/trafego';
import type { LeituraDoDestinoPago } from '@/lib/landing-policy/prontidao';
import { cn } from '@/lib/utils';
import { LinhaDeFato } from '../BlocoDeEvidencia';
import { Input } from '@/components/ui/input';
import {
  AcaoDeProva, CampoDeTexto, EditorDeLista, EscolhaExplicita, IrParaEstudio, SeletorDeAsset,
} from './ControlesMulticanal';

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

const CANAIS: Array<{ id: CanalSelecionavelDemandGen; nome: string }> = [
  { id: 'youtube_in_stream', nome: 'YouTube In-stream' },
  { id: 'youtube_in_feed', nome: 'YouTube In-feed' },
  { id: 'youtube_shorts', nome: 'YouTube Shorts' },
  { id: 'discover', nome: 'Discover' },
  { id: 'gmail', nome: 'Gmail' },
  { id: 'display', nome: 'Display' },
  { id: 'maps', nome: 'Maps' },
];

export const ParadaDemandSuperficies: React.FC<{
  estrategia: EstrategiaDeCanaisDemandGen | null;
  onEstrategia: (valor: EstrategiaDeCanaisDemandGen) => void;
  selecionados: CanalSelecionavelDemandGen[];
  onSelecionados: (valor: CanalSelecionavelDemandGen[]) => void;
}> = ({ estrategia, onEstrategia, selecionados, onSelecionados }) => (
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
    <div className="mt-5 grid gap-2 sm:grid-cols-3" role="group" aria-label="estratégia de superfícies">
      {([
        ['ALL_CHANNELS', 'Todos os canais'],
        ['ALL_OWNED_AND_OPERATED_CHANNELS', 'Superfícies próprias'],
        ['SELECTED_CHANNELS', 'Escolher canais'],
      ] as const).map(([valor, nome]) => (
        <button
          key={valor}
          type="button"
          aria-pressed={estrategia === valor}
          onClick={() => onEstrategia(valor)}
          className={cn(
            'min-h-12 rounded-lg border px-4 py-3 text-left text-sm font-semibold transition-colors',
            estrategia === valor ? 'border-primary/45 bg-primary/[0.07]' : 'border-border bg-background text-muted-foreground hover:border-primary/25',
          )}
        >{nome}</button>
      ))}
    </div>
    {estrategia === 'SELECTED_CHANNELS' && (
      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {CANAIS.map(({ id, nome }) => {
          const ativo = selecionados.includes(id);
          return (
            <button
              key={id}
              type="button"
              aria-pressed={ativo}
              onClick={() => onSelecionados(ativo ? selecionados.filter((item) => item !== id) : [...selecionados, id])}
              className={cn(
                'flex min-h-11 items-center gap-3 rounded-lg border px-3 text-sm transition-colors',
                ativo ? 'border-primary/40 bg-primary/[0.06] font-semibold' : 'border-border bg-background text-muted-foreground',
              )}
            >
              <span className={cn('h-2.5 w-2.5 rounded-full', ativo ? 'bg-primary' : 'bg-muted-foreground/30')} />
              {nome}
            </button>
          );
        })}
      </div>
    )}
  </section>
);

export const ParadaDemandAudiencia: React.FC<{
  upgradedTargeting: boolean | null;
  onUpgradedTargeting: (valor: boolean) => void;
  audiencias: string;
  onAudiencias: (valor: string) => void;
  audienciasConfirmadas: boolean;
  onAudienciasConfirmadas: (valor: boolean) => void;
}> = ({
  upgradedTargeting, onUpgradedTargeting, audiencias, onAudiencias,
  audienciasConfirmadas, onAudienciasConfirmadas,
}) => (
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
    <EscolhaExplicita
      rotulo="Onde geo e idioma serão aplicados?"
      valor={upgradedTargeting}
      onChange={onUpgradedTargeting}
      positivo="No grupo (upgraded targeting ligado)"
      negativo="Na campanha (upgraded targeting desligado)"
      ajuda="É uma decisão imutável na criação; o VOLC nunca aceita o default remoto silenciosamente."
    />
    <EditorDeLista
      id="demand-audiences"
      rotulo="Audiências positivas"
      valor={audiencias}
      onChange={onAudiencias}
      placeholder="customers/123/audiences/456"
      ajuda="resource names de Audience existentes na mesma conta; vazio confirmado é aceito"
      linhas={4}
    />
    <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-border bg-background px-4 text-sm">
      <input type="checkbox" checked={audienciasConfirmadas} onChange={(e) => onAudienciasConfirmadas(e.target.checked)} className="h-4 w-4 accent-primary" />
      <span><strong>Confirmo esta lista</strong> — vazia significa Demand Gen sem Audience anexada.</span>
    </label>
    <div className="grid gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-2">
      {[
        ['Intenção textual', 'visível, mas fechada: materialize em Audience aprovada'],
        ['Exclusão de audiência', 'visível, mas fechada até o contrato v25 ser comprovado'],
      ].map(([item, detalhe]) => (
        <div key={item} className="bg-muted/25 p-4">
          <p className="text-sm font-semibold">{item}</p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{detalhe}</p>
        </div>
      ))}
    </div>
  </section>
);

export const ParadaDemandKit: React.FC<{
  assets: AssetDemandGen[];
  onAssets: (assets: AssetDemandGen[]) => void;
}> = ({ assets, onAssets }) => (
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
    <div className="mt-6 grid gap-4 sm:grid-cols-2">
      <SeletorDeAsset id="demand-marketing" rotulo="Paisagem" tipo="imagem_marketing" detalhe="1.91:1 · compõe o mínimo de marketing" assets={assets} onChange={onAssets} maximo={20} />
      <SeletorDeAsset id="demand-square" rotulo="Quadrado" tipo="imagem_marketing_quadrada" detalhe="1:1 · compõe o mínimo de marketing" assets={assets} onChange={onAssets} maximo={20} />
      <SeletorDeAsset id="demand-portrait" rotulo="Retrato" tipo="imagem_marketing_retrato" detalhe="4:5 · inventário vertical" assets={assets} onChange={onAssets} maximo={20} />
      <SeletorDeAsset id="demand-tall" rotulo="Retrato alto" tipo="imagem_marketing_retrato_alto" detalhe="9:16 · Shorts" assets={assets} onChange={onAssets} maximo={20} />
      <SeletorDeAsset id="demand-logo" rotulo="Logo quadrado" tipo="logo_quadrado" detalhe="1:1 · ao menos um obrigatório" assets={assets} onChange={onAssets} maximo={5} />
    </div>
    <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4 text-sm text-muted-foreground">
      <span className="flex items-center gap-3"><Film className="h-4 w-4" aria-hidden /> Vídeo responsivo pertence a outra modalidade e não entra nesta onda.</span>
      <IrParaEstudio canal="DEMAND_GEN" />
    </div>
  </section>
);

export const ParadaDemandMensagem: React.FC<{
  nomeEmpresa: string;
  onNomeEmpresa: (valor: string) => void;
  titulos: string;
  onTitulos: (valor: string) => void;
  descricoes: string;
  onDescricoes: (valor: string) => void;
}> = ({ nomeEmpresa, onNomeEmpresa, titulos, onTitulos, descricoes, onDescricoes }) => (
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
    <div className="grid gap-5 border-t border-border pt-5 lg:grid-cols-2">
      <div className="lg:col-span-2">
        <CampoDeTexto id="demand-business-name" rotulo="Nome da empresa" valor={nomeEmpresa} onChange={onNomeEmpresa} limite={25} placeholder="Ex.: Portal Mundo Mais" />
      </div>
      <EditorDeLista id="demand-headlines" rotulo="Títulos" valor={titulos} onChange={onTitulos} minimo={1} maximo={5} limitePorItem={30} placeholder={'Título 1\nTítulo 2'} />
      <EditorDeLista id="demand-descriptions" rotulo="Descrições" valor={descricoes} onChange={onDescricoes} minimo={1} maximo={5} limitePorItem={90} placeholder={'Descrição 1\nDescrição 2'} />
    </div>
  </section>
);

export const ParadaDemandEconomia: React.FC<{
  cockpit: Cockpit;
  orcamento: number | null;
  orcamentoBruto: string;
  onOrcamento: (valor: string) => void;
}> = ({ cockpit, orcamento, orcamentoBruto, onOrcamento }) => (
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
    <label className="block max-w-sm space-y-2 text-sm font-semibold">
      <span>Orçamento diário</span>
      <Input inputMode="decimal" value={orcamentoBruto} onChange={(e) => onOrcamento(e.target.value)} placeholder="10,00" className="h-11 bg-background" />
      <span className="block text-xs font-normal text-muted-foreground">Estratégia fixa nesta onda: maximizar conversões, sem CPA-alvo.</span>
    </label>
  </section>
);

export const ParadaDemandRevisao: React.FC<{
  url: string | null;
  faltas: string[];
  estadoDaProva: 'ociosa' | 'provando' | 'aprovada' | 'recusada';
  mensagemDaProva: string | null;
  onProvar: () => void;
}> = ({ url, faltas, estadoDaProva, mensagemDaProva, onProvar }) => (
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
      <LinhaDeFato rotulo="Ato disponível" valor="validate_only" fonte="Google Ads; nada é criado" />
    </dl>
    {faltas.length > 0 && <p className="text-sm text-muted-foreground">Próximo: {faltas[0]}</p>}
    <AcaoDeProva estado={estadoDaProva} mensagem={mensagemDaProva} desabilitada={faltas.length > 0} motivo={faltas[0] ?? null} onProvar={onProvar} />
  </section>
);
