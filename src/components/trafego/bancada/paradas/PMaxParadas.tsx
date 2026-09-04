import React from 'react';
import {
  Ban, CircleDashed, Film, FolderArchive, Globe2, Image as ImageIcon,
  Link2Off, Search, ShieldCheck, Sparkles, Target, Users2,
} from 'lucide-react';

import type { Cockpit } from '@/types/trafego';
import type { AssetDemandGen } from '@/types/trafego';
import type { LeituraDoDestinoPago } from '@/lib/landing-policy/prontidao';
import { cn } from '@/lib/utils';
import { LinhaDeFato } from '../BlocoDeEvidencia';
import { Input } from '@/components/ui/input';
import {
  AcaoDeProva, CampoDeTexto, EditorDeLista, EscolhaExplicita, IrParaEstudio, SeletorDeAsset,
} from './ControlesMulticanal';

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

export const ParadaPMaxAssetGroup: React.FC<{
  nomeAssetGroup: string;
  onNomeAssetGroup: (valor: string) => void;
  nomeEmpresa: string;
  onNomeEmpresa: (valor: string) => void;
  titulos: string;
  onTitulos: (valor: string) => void;
  titulosLongos: string;
  onTitulosLongos: (valor: string) => void;
  descricoes: string;
  onDescricoes: (valor: string) => void;
  videos: string;
  onVideos: (valor: string) => void;
  assets: AssetDemandGen[];
  onAssets: (assets: AssetDemandGen[]) => void;
}> = ({
  nomeAssetGroup, onNomeAssetGroup, nomeEmpresa, onNomeEmpresa, titulos,
  onTitulos, titulosLongos, onTitulosLongos, descricoes, onDescricoes,
  videos, onVideos, assets, onAssets,
}) => (
  <section>
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-verified/10 text-verified"><FolderArchive className="h-5 w-5" /></span>
      <div>
        <p className="kicker text-muted-foreground">asset group</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Uma história completa, não uma coleção de arquivos</h3>
        <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted-foreground">O grupo só fica elegível quando texto e mídia aprovados cobrem os formatos mínimos. Nada abaixo foi lido ainda.</p>
      </div>
    </div>
    <div className="mt-5">
      <CampoDeTexto id="pmax-asset-group-name" rotulo="Nome do asset group" valor={nomeAssetGroup} onChange={onNomeAssetGroup} limite={128} placeholder="Derivado do tema quando vazio" />
    </div>
    <div className="mt-5 grid gap-4 sm:grid-cols-2">
      <SeletorDeAsset id="pmax-marketing" rotulo="Imagem horizontal" tipo="imagem_marketing" detalhe="1.91:1 · 1 a 20" assets={assets} onChange={onAssets} maximo={20} />
      <SeletorDeAsset id="pmax-square" rotulo="Imagem quadrada" tipo="imagem_marketing_quadrada" detalhe="1:1 · 1 a 20" assets={assets} onChange={onAssets} maximo={20} />
      <SeletorDeAsset id="pmax-portrait" rotulo="Imagem vertical" tipo="imagem_marketing_retrato" detalhe="4:5 · opcional, até 20" assets={assets} onChange={onAssets} maximo={20} />
      <SeletorDeAsset id="pmax-logo" rotulo="Logo quadrado" tipo="logo_quadrado" detalhe="1:1 · 1 a 5" assets={assets} onChange={onAssets} maximo={5} />
      <SeletorDeAsset id="pmax-landscape-logo" rotulo="Logo horizontal" tipo="logo_paisagem" detalhe="4:1 · opcional, até 20" assets={assets} onChange={onAssets} maximo={20} />
    </div>
    <div className="mt-4 flex justify-end"><IrParaEstudio canal="PERFORMANCE_MAX" /></div>
    <div className="mt-6 grid gap-5 border-t border-border pt-6 lg:grid-cols-2">
      <div className="lg:col-span-2"><CampoDeTexto id="pmax-business-name" rotulo="Nome da empresa" valor={nomeEmpresa} onChange={onNomeEmpresa} limite={25} /></div>
      <EditorDeLista id="pmax-headlines" rotulo="Títulos curtos" valor={titulos} onChange={onTitulos} minimo={3} maximo={15} limitePorItem={30} />
      <EditorDeLista id="pmax-long-headlines" rotulo="Títulos longos" valor={titulosLongos} onChange={onTitulosLongos} minimo={1} maximo={5} limitePorItem={90} />
      <EditorDeLista id="pmax-descriptions" rotulo="Descrições" valor={descricoes} onChange={onDescricoes} minimo={2} maximo={5} limitePorItem={90} ajuda="ao menos uma descrição deve ter até 60 caracteres" />
      <EditorDeLista id="pmax-videos" rotulo="Vídeos do YouTube (opcional)" valor={videos} onChange={onVideos} maximo={15} placeholder="customers/123/assets/456" ajuda="resource names de vídeo já existentes na conta" />
    </div>
  </section>
);

export const ParadaPMaxSinais: React.FC<{
  audiencias: string;
  onAudiencias: (valor: string) => void;
  searchThemes: string;
  onSearchThemes: (valor: string) => void;
  sinaisConfirmados: boolean;
  onSinaisConfirmados: (valor: boolean) => void;
  negativas: string;
  onNegativas: (valor: string) => void;
  negativasConfirmadas: boolean;
  onNegativasConfirmadas: (valor: boolean) => void;
}> = ({
  audiencias, onAudiencias, searchThemes, onSearchThemes,
  sinaisConfirmados, onSinaisConfirmados, negativas, onNegativas,
  negativasConfirmadas, onNegativasConfirmadas,
}) => (
  <section className="space-y-6">
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-info/10 text-info"><Users2 className="h-5 w-5" /></span>
      <div>
        <p className="kicker text-muted-foreground">orientação do algoritmo</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Sinais ajudam a começar; não restringem como keywords</h3>
        <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted-foreground">Audience signals e Search Themes são pistas para o sistema. Eles não são termos de correspondência e não garantem em qual busca a campanha aparece.</p>
      </div>
    </div>
    <div className="grid gap-5 border-y border-border py-5 lg:grid-cols-2">
      <EditorDeLista id="pmax-audiences" rotulo="Audience signals" valor={audiencias} onChange={onAudiencias} placeholder="customers/123/audiences/456" ajuda="dicas imutáveis; não restringem a entrega" />
      <EditorDeLista id="pmax-search-themes" rotulo="Search Themes" valor={searchThemes} onChange={onSearchThemes} ajuda="temas, não keywords positivas" />
      <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-border bg-background px-4 text-sm lg:col-span-2">
        <input type="checkbox" checked={sinaisConfirmados} onChange={(e) => onSinaisConfirmados(e.target.checked)} className="h-4 w-4 accent-primary" />
        <span><strong>Confirmo estes sinais</strong> — listas vazias significam começar sem dicas.</span>
      </label>
      <div className="lg:col-span-2"><EditorDeLista id="pmax-negatives" rotulo="Keywords negativas de campanha" valor={negativas} onChange={onNegativas} maximo={10000} ajuda="único uso de keyword no PMax desta versão" /></div>
      <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-border bg-background px-4 text-sm lg:col-span-2">
        <input type="checkbox" checked={negativasConfirmadas} onChange={(e) => onNegativasConfirmadas(e.target.checked)} className="h-4 w-4 accent-primary" />
        <span><strong>Confirmo estas negativas</strong> — vazio é uma escolha explícita, não ausência.</span>
      </label>
    </div>
  </section>
);

export const ParadaPMaxMarca: React.FC<{
  brandGuidelines: boolean | null;
  onBrandGuidelines: (valor: boolean) => void;
}> = ({ brandGuidelines, onBrandGuidelines }) => (
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
        <div className="min-w-0 flex-1"><p className="text-sm font-semibold">Automação de assets de texto</p><p className="mt-0.5 text-xs text-muted-foreground">O brief ainda não expressa esta decisão; o builder não promete configurá-la.</p></div>
        <span className="text-xs font-semibold text-muted-foreground">não operada</span>
      </div>
    </div>
    <EscolhaExplicita
      rotulo="Brand guidelines"
      valor={brandGuidelines}
      onChange={onBrandGuidelines}
      positivo="Ligadas — nome e logo no nível da campanha"
      negativo="Desligadas — nome e logo no asset group"
      ajuda="Esta escolha é imutável na criação. A interface exige uma decisão em vez de herdar o default remoto."
    />
  </section>
);

export const ParadaPMaxEconomia: React.FC<{
  cockpit: Cockpit;
  orcamento: number | null;
  orcamentoBruto: string;
  onOrcamento: (valor: string) => void;
  estrategia: 'MAXIMIZE_CONVERSIONS' | 'MAXIMIZE_CONVERSION_VALUE';
  onEstrategia: (valor: 'MAXIMIZE_CONVERSIONS' | 'MAXIMIZE_CONVERSION_VALUE') => void;
  meta: string;
  onMeta: (valor: string) => void;
}> = ({ cockpit, orcamento, orcamentoBruto, onOrcamento, estrategia, onEstrategia, meta, onMeta }) => (
  <section className="space-y-5">
    <div>
      <p className="kicker text-muted-foreground">economia automatizada</p>
      <h3 className="mt-1 font-display text-xl font-semibold">Bidding depende de uma meta confiável</h3>
      <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">Esta bancada não reutiliza CPC manual do Search. Alvo e estratégia só podem nascer do contrato PMax.</p>
    </div>
    <dl className="grid gap-4 border-y border-border py-5 sm:grid-cols-3">
      <LinhaDeFato rotulo="Orçamento" valor={orcamento == null ? null : `R$ ${orcamento.toFixed(2).replace('.', ',')}/dia`} fonte="rascunho" />
      <LinhaDeFato rotulo="Estratégia" valor={estrategia} fonte="você, agora" />
      <LinhaDeFato rotulo="Meta efetiva" valor={cockpit.conta?.meta_conversao?.primaria?.nome ?? null} fonte="conta" />
    </dl>
    <div className="grid gap-5 sm:grid-cols-2">
      <label className="space-y-2 text-sm font-semibold">
        <span>Orçamento diário</span>
        <Input inputMode="decimal" value={orcamentoBruto} onChange={(e) => onOrcamento(e.target.value)} placeholder="10,00" className="h-11 bg-background" />
      </label>
      <label className="space-y-2 text-sm font-semibold">
        <span>Estratégia de lance</span>
        <select value={estrategia} onChange={(e) => onEstrategia(e.target.value as typeof estrategia)} className="flex h-11 w-full rounded-md border border-input bg-background px-3 text-sm">
          <option value="MAXIMIZE_CONVERSIONS">Maximizar conversões</option>
          <option value="MAXIMIZE_CONVERSION_VALUE">Maximizar valor de conversão</option>
        </select>
      </label>
      <label className="space-y-2 text-sm font-semibold sm:col-span-2">
        <span>{estrategia === 'MAXIMIZE_CONVERSION_VALUE' ? 'ROAS-alvo (opcional)' : 'CPA-alvo (opcional)'}</span>
        <Input inputMode="decimal" value={meta} onChange={(e) => onMeta(e.target.value)} placeholder="Deixe vazio para maximização sem meta numérica" className="h-11 max-w-sm bg-background" />
        <span className="block text-xs font-normal text-muted-foreground">O recibo de mensuração vem da conta e não pode ser digitado. Maximizar valor exige ações que carreguem valor.</span>
      </label>
    </div>
  </section>
);

export const ParadaPMaxRevisao: React.FC<{
  url: string | null;
  faltas: string[];
  estadoDoPlano: 'ociosa' | 'provando' | 'aprovada' | 'recusada';
  mensagemDoPlano: string | null;
  onPlanejar: () => void;
}> = ({ url, faltas, estadoDoPlano, mensagemDoPlano, onPlanejar }) => (
  <section className="space-y-6">
    <div className="flex items-start justify-between gap-4 border-b border-border pb-5">
      <div>
        <p className="kicker text-muted-foreground">revisão PMax</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Plano local, criação ainda fechada</h3>
        <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">O asset group pode ser projetado pelo contrato real, mas esta ação não lê a conta, não chama validate_only e não cria. Nenhum botão de mutate é exibido.</p>
      </div>
      <span className="shrink-0 rounded-full border border-info/30 bg-info/10 px-3 py-1 text-xs font-semibold text-info">planejamento</span>
    </div>
    <dl className="grid gap-4 sm:grid-cols-2">
      <LinhaDeFato rotulo="URL exclusiva" valor={url} fonte="funil" />
      <LinhaDeFato rotulo="Expansão de URL" valor="desligada" fonte="contrato PMax" />
    </dl>
    {faltas.length > 0 && <p className="text-sm text-muted-foreground">Próximo: {faltas[0]}</p>}
    <AcaoDeProva
      estado={estadoDoPlano}
      mensagem={mensagemDoPlano}
      desabilitada={faltas.length > 0}
      motivo={faltas[0] ?? null}
      onProvar={onPlanejar}
      somenteLocal
    />
  </section>
);
