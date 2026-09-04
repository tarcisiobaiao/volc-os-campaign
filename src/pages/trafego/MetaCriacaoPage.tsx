import React from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CircleDollarSign,
  Crosshair,
  FileCheck2,
  Image,
  Info,
  Layers3,
  LockKeyhole,
  Megaphone,
  Settings2,
  Users,
} from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';

import { Layout } from '@/components/layout/Layout';
import { MetaConfiguracaoLocal } from '@/components/trafego/meta/MetaConfiguracaoLocal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';

const ETAPAS = [
  { id: 'base', nome: 'Base', resumo: 'conta e projeto', icone: Layers3 },
  { id: 'campanha', nome: 'Campanha', resumo: 'objetivo e identidade', icone: Megaphone },
  { id: 'orcamento', nome: 'Orçamento', resumo: 'verba, lance e agenda', icone: CircleDollarSign },
  { id: 'conjunto', nome: 'Conjunto', resumo: 'otimização e entrega', icone: Crosshair },
  { id: 'publico', nome: 'Público', resumo: 'quem pode receber', icone: Users },
  { id: 'criativo', nome: 'Anúncio', resumo: 'identidade e mensagem', icone: Image },
  { id: 'mensuracao', nome: 'Mensuração', resumo: 'pixel e evento', icone: Settings2 },
  { id: 'revisao', nome: 'Revisão', resumo: 'pedido pausado', icone: FileCheck2 },
] as const;

type Etapa = typeof ETAPAS[number]['id'];

const campo = 'h-10 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2';

const Grupo: React.FC<{ titulo: string; ajuda?: string; children: React.ReactNode }> = ({ titulo, ajuda, children }) => (
  <section className="border-b border-border py-5 first:pt-0 last:border-0 last:pb-0">
    <h2 className="font-display text-lg font-semibold text-foreground">{titulo}</h2>
    {ajuda && <p className="mt-1 max-w-[70ch] text-sm leading-relaxed text-muted-foreground">{ajuda}</p>}
    <div className="mt-4 grid gap-4 md:grid-cols-2">{children}</div>
  </section>
);

const Campo: React.FC<{ id: string; rotulo: string; ajuda?: string; children: React.ReactNode; largo?: boolean }> = ({ id, rotulo, ajuda, children, largo }) => (
  <div className={cn('space-y-2', largo && 'md:col-span-2')}>
    <Label htmlFor={id}>{rotulo}</Label>
    {children}
    {ajuda && <p className="text-xs leading-relaxed text-muted-foreground">{ajuda}</p>}
  </div>
);

const Resumo: React.FC<{ rotulo: string; valor: string; pendente?: boolean }> = ({ rotulo, valor, pendente }) => (
  <div className="flex items-start justify-between gap-5 border-b border-border py-3 last:border-0">
    <dt className="text-sm text-muted-foreground">{rotulo}</dt>
    <dd className={cn('max-w-[65%] text-right text-sm font-medium', pendente ? 'text-warning' : 'text-foreground')}>{valor}</dd>
  </div>
);

const Conteudo: React.FC<{ etapa: Etapa }> = ({ etapa }) => {
  switch (etapa) {
    case 'base':
      return (
        <Grupo titulo="Onde esta campanha vai viver?" ajuda="A conta é autoridade externa; o projeto mantém a linhagem com funil, domínio e ativos.">
          <Campo id="meta-conta" rotulo="Conta de anúncios">
            <select id="meta-conta" className={campo} defaultValue="demo"><option value="demo">Conta Meta demonstrativa · ••••2048</option></select>
          </Campo>
          <Campo id="meta-projeto" rotulo="Projeto VOLC">
            <select id="meta-projeto" className={campo} defaultValue="foco"><option value="foco">Foco Genial</option><option value="credito">Crédito Up</option></select>
          </Campo>
          <Campo id="meta-pagina" rotulo="Página do Facebook">
            <select id="meta-pagina" className={campo} defaultValue="foco"><option value="foco">Foco Genial · demonstração</option></select>
          </Campo>
          <Campo id="meta-instagram" rotulo="Identidade do Instagram" ajuda="Opcional quando o posicionamento não exige identidade Instagram.">
            <select id="meta-instagram" className={campo} defaultValue="auto"><option value="auto">Usar identidade vinculada à Página</option></select>
          </Campo>
        </Grupo>
      );
    case 'campanha':
      return (
        <Grupo titulo="O que a campanha precisa alcançar?" ajuda="O objetivo é estrutural na Meta: ele determina eventos, otimização e campos permitidos nos próximos níveis.">
          <Campo id="meta-nome" rotulo="Nome da campanha" largo><Input id="meta-nome" defaultValue="FG · Encceja 2026 · Tráfego · 202609" /></Campo>
          <Campo id="meta-objetivo" rotulo="Objetivo">
            <select id="meta-objetivo" className={campo} defaultValue="traffic"><option value="traffic">Tráfego</option><option value="engagement">Engajamento</option><option value="sales">Vendas</option><option value="leads">Cadastros</option></select>
          </Campo>
          <Campo id="meta-buying" rotulo="Tipo de compra"><select id="meta-buying" className={campo} defaultValue="auction"><option value="auction">Leilão</option></select></Campo>
          <Campo id="meta-special" rotulo="Categoria especial de anúncio" ajuda="Deve ser declarada, mesmo quando não se aplica.">
            <select id="meta-special" className={campo} defaultValue="none"><option value="none">Nenhuma</option><option value="credit">Crédito</option><option value="employment">Emprego</option><option value="housing">Moradia</option><option value="issues">Temas sociais, eleições ou política</option></select>
          </Campo>
          <Campo id="meta-status" rotulo="Estado ao nascer"><Input id="meta-status" value="PAUSADA" readOnly aria-readonly /></Campo>
        </Grupo>
      );
    case 'orcamento':
      return (
        <Grupo titulo="Quanto pode ser investido?" ajuda="A escolha entre orçamento na campanha e no conjunto é explícita; o motor nunca migra verba silenciosamente.">
          <Campo id="meta-budget-level" rotulo="Onde controlar o orçamento"><select id="meta-budget-level" className={campo} defaultValue="campaign"><option value="campaign">Campanha · Advantage campaign budget</option><option value="adset">Cada conjunto</option></select></Campo>
          <Campo id="meta-budget-type" rotulo="Período"><select id="meta-budget-type" className={campo} defaultValue="daily"><option value="daily">Diário</option><option value="lifetime">Vitalício</option></select></Campo>
          <Campo id="meta-budget" rotulo="Orçamento diário"><Input id="meta-budget" inputMode="decimal" defaultValue="120,00" /></Campo>
          <Campo id="meta-bid" rotulo="Estratégia de lance"><select id="meta-bid" className={campo} defaultValue="lowest"><option value="lowest">Maior volume · menor custo</option><option value="cost-cap">Meta de custo</option><option value="bid-cap">Limite de lance</option></select></Campo>
          <Campo id="meta-start" rotulo="Início"><Input id="meta-start" type="datetime-local" /></Campo>
          <Campo id="meta-end" rotulo="Término" ajuda="Sem data deixa a campanha contínua."><Input id="meta-end" type="datetime-local" /></Campo>
        </Grupo>
      );
    case 'conjunto':
      return (
        <Grupo titulo="Como a Meta deve entregar?" ajuda="Este é o nível que liga evento de otimização, cobrança, público e posicionamentos.">
          <Campo id="meta-adset-name" rotulo="Nome do conjunto" largo><Input id="meta-adset-name" defaultValue="Brasil · Amplo · 18–54 · Landing page view" /></Campo>
          <Campo id="meta-performance" rotulo="Meta de desempenho"><select id="meta-performance" className={campo} defaultValue="landing"><option value="landing">Maximizar visualizações da página de destino</option><option value="link">Maximizar cliques no link</option><option value="impressions">Maximizar impressões</option></select></Campo>
          <Campo id="meta-billing" rotulo="Evento de cobrança"><select id="meta-billing" className={campo} defaultValue="impressions"><option value="impressions">Impressões</option><option value="link">Clique no link · quando elegível</option></select></Campo>
          <Campo id="meta-conversion" rotulo="Local de conversão"><select id="meta-conversion" className={campo} defaultValue="website"><option value="website">Site</option><option value="instant">Experiência instantânea</option></select></Campo>
          <Campo id="meta-promoted" rotulo="Objeto promovido" ajuda="Derivado do pixel/dataset e evento quando o objetivo exigir."><Input id="meta-promoted" value="Site · evento de destino" readOnly /></Campo>
        </Grupo>
      );
    case 'publico':
      return (
        <Grupo titulo="Quem pode receber o anúncio?" ajuda="Público amplo é uma decisão visível. Inclusões e exclusões permanecem auditáveis no blueprint.">
          <Campo id="meta-location" rotulo="Localização"><Input id="meta-location" defaultValue="Brasil" /></Campo>
          <Campo id="meta-age" rotulo="Faixa etária"><select id="meta-age" className={campo} defaultValue="18-54"><option value="18-54">18 a 54 anos</option><option value="18-65">18 a 65+ anos</option></select></Campo>
          <Campo id="meta-language" rotulo="Idiomas"><Input id="meta-language" defaultValue="Português (Brasil)" /></Campo>
          <Campo id="meta-advantage" rotulo="Expansão Advantage+"><select id="meta-advantage" className={campo} defaultValue="on"><option value="on">Ligada · manter exclusões</option><option value="off">Desligada</option></select></Campo>
          <Campo id="meta-includes" rotulo="Públicos incluídos" largo><Input id="meta-includes" placeholder="Pesquisar público salvo, personalizado ou semelhante" /></Campo>
          <Campo id="meta-excludes" rotulo="Públicos excluídos" largo><Input id="meta-excludes" defaultValue="Visitantes convertidos · 180 dias" /></Campo>
          <Campo id="meta-placements" rotulo="Posicionamentos" largo><select id="meta-placements" className={campo} defaultValue="advantage"><option value="advantage">Advantage+ · automáticos</option><option value="manual">Manuais · revisar inventário</option></select></Campo>
        </Grupo>
      );
    case 'criativo':
      return (
        <Grupo titulo="O que a pessoa vai ver?" ajuda="Identidade, texto, destino e peças ficam juntos; o anúncio referencia um criativo, não duplica a mídia sem recibo.">
          <Campo id="meta-ad-name" rotulo="Nome do anúncio" largo><Input id="meta-ad-name" defaultValue="Certificado Encceja · Imagem A · v1" /></Campo>
          <Campo id="meta-primary" rotulo="Texto principal" largo><Textarea id="meta-primary" rows={4} defaultValue="Entenda como consultar o certificado do Encceja e quais documentos podem ser necessários." /></Campo>
          <Campo id="meta-headline" rotulo="Título"><Input id="meta-headline" defaultValue="Certificado Encceja 2026" /></Campo>
          <Campo id="meta-cta" rotulo="Chamada para ação"><select id="meta-cta" className={campo} defaultValue="learn"><option value="learn">Saiba mais</option><option value="none">Sem botão</option></select></Campo>
          <Campo id="meta-url" rotulo="URL de destino" largo><Input id="meta-url" type="url" defaultValue="https://focogenial.com/encceja-2026-certificado-ensino-medio/" /></Campo>
          <Campo id="meta-media" rotulo="Peça do Estúdio" largo><button id="meta-media" type="button" className="flex min-h-20 w-full items-center justify-between rounded-md border border-dashed border-border bg-muted/20 px-4 text-left text-sm hover:bg-muted/40"><span><strong className="block text-foreground">Encceja · estudante no notebook</strong><span className="mt-1 block text-xs text-muted-foreground">Imagem 1:1 · aprovada localmente · demonstração</span></span><ArrowRight className="h-4 w-4 text-muted-foreground" aria-hidden /></button></Campo>
        </Grupo>
      );
    case 'mensuracao':
      return (
        <Grupo titulo="Como a entrega será medida?" ajuda="A ausência de pixel, evento ou UTMs bloqueia a pretensão de mensuração; não vira zero nem sucesso implícito.">
          <Campo id="meta-dataset" rotulo="Pixel ou dataset"><select id="meta-dataset" className={campo} defaultValue="demo"><option value="demo">Dataset Foco Genial · ••••0184</option></select></Campo>
          <Campo id="meta-event" rotulo="Evento"><select id="meta-event" className={campo} defaultValue="view"><option value="view">ViewContent</option><option value="landing">LandingPageView · otimização de tráfego</option></select></Campo>
          <Campo id="meta-domain" rotulo="Domínio"><Input id="meta-domain" value="focogenial.com" readOnly /></Campo>
          <Campo id="meta-attribution" rotulo="Janela de atribuição"><select id="meta-attribution" className={campo} defaultValue="7d"><option value="7d">7 dias após clique · 1 dia após visualização</option><option value="1d">1 dia após clique</option></select></Campo>
          <Campo id="meta-utm" rotulo="Parâmetros de URL" largo><Input id="meta-utm" defaultValue="utm_source=meta&utm_medium=paid_social&utm_campaign={{campaign.name}}&utm_content={{ad.name}}" /></Campo>
        </Grupo>
      );
    case 'revisao':
      return (
        <>
          <Grupo titulo="Pedido que seria criado pausado" ajuda="Esta revisão mostra consequências e lacunas antes de qualquer escrita externa.">
            <dl className="md:col-span-2">
              <Resumo rotulo="Conta" valor="Conta Meta demonstrativa · ••••2048" />
              <Resumo rotulo="Campanha" valor="FG · Encceja 2026 · Tráfego · 202609" />
              <Resumo rotulo="Objetivo" valor="Tráfego · visualização da página de destino" />
              <Resumo rotulo="Orçamento" valor="R$ 120,00/dia · campanha" />
              <Resumo rotulo="Estrutura" valor="1 campanha · 1 conjunto · 1 anúncio · 1 criativo" />
              <Resumo rotulo="Estado ao nascer" valor="PAUSADA" />
              <Resumo rotulo="Validação externa" valor="não executada" pendente />
            </dl>
          </Grupo>
          <div className="mt-5 flex items-start gap-2 rounded-md border border-warning/25 bg-warning/5 p-3 text-sm">
            <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
            <p><strong>Criação real bloqueada.</strong> Esta bancada demonstra o contrato. Falta ligar o blueprint ao executor, validar na conta e emitir recibo idempotente.</p>
          </div>
        </>
      );
  }
};

const MetaCriacaoPage: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const pedida = params.get('etapa') as Etapa | null;
  const etapa = ETAPAS.some((item) => item.id === pedida) ? pedida! : 'base';
  const indice = ETAPAS.findIndex((item) => item.id === etapa);
  const navegar = (proxima: Etapa) => {
    const novos = new URLSearchParams(params);
    novos.set('modo', 'demo');
    novos.set('etapa', proxima);
    setParams(novos);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <Layout>
      <main className="p-4 md:p-8">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <Link to="/trafego?rede=meta&aba=preparar" className="inline-flex min-h-9 items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" aria-hidden /> Tráfego · Meta Ads</Link>
            <div className="mt-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground"><span className="inline-flex h-5 w-5 items-center justify-center rounded-md bg-primary/10 text-primary"><Megaphone className="h-3.5 w-3.5" aria-hidden /></span>criação guiada · demonstração</div>
            <h1 className="mt-2 font-display text-[2rem] font-bold leading-[1.05] tracking-tight md:text-[2.4rem]">Nova campanha Meta</h1>
            <div className="aurora-rule mt-3 w-16" aria-hidden />
            <p className="mt-3 max-w-[70ch] text-sm text-muted-foreground">Uma decisão por vez, preservando a hierarquia campanha → conjunto → anúncio → criativo.</p>
          </div>
          <MetaConfiguracaoLocal />
        </header>

        <div className="mb-5 flex items-start gap-2 rounded-md border border-verified/25 bg-verified/5 px-3 py-2.5 text-xs"><Info className="mt-0.5 h-4 w-4 shrink-0 text-verified" aria-hidden /><p><strong>Modo demonstrativo.</strong> Os campos representam o contrato v26; nada será enviado ou salvo fora desta página.</p></div>

        <div className="grid gap-5 lg:grid-cols-[250px_minmax(0,1fr)]">
          <nav aria-label="Etapas da criação Meta" className="h-fit rounded-md border border-border bg-card p-2 shadow-card">
            {ETAPAS.map((item, posicao) => {
              const Icone = item.icone;
              const atual = item.id === etapa;
              const passou = posicao < indice;
              return (
                <button key={item.id} type="button" onClick={() => navegar(item.id)} aria-current={atual ? 'step' : undefined} className={cn('flex min-h-12 w-full items-center gap-3 rounded-md px-3 text-left transition-[background-color,color] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', atual ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground')}>
                  <span className={cn('flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs', atual ? 'border-primary-foreground/40' : passou ? 'border-success/30 bg-success/10 text-success' : 'border-border')}>
                    {passou ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Icone className="h-3.5 w-3.5" aria-hidden />}
                  </span>
                  <span className="min-w-0"><strong className="block truncate text-sm font-medium">{item.nome}</strong><span className={cn('block truncate text-[11px]', atual ? 'text-primary-foreground/75' : 'text-muted-foreground')}>{item.resumo}</span></span>
                </button>
              );
            })}
          </nav>

          <form className="rounded-md border border-border bg-card p-5 shadow-card md:p-6" onSubmit={(evento) => evento.preventDefault()}>
            <Conteudo etapa={etapa} />
            <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5">
              <Button type="button" variant="outline" disabled={indice === 0} onClick={() => navegar(ETAPAS[indice - 1].id)}><ArrowLeft className="mr-2 h-4 w-4" aria-hidden /> Voltar</Button>
              {indice < ETAPAS.length - 1 ? (
                <Button type="button" onClick={() => navegar(ETAPAS[indice + 1].id)}>Continuar <ArrowRight className="ml-2 h-4 w-4" aria-hidden /></Button>
              ) : (
                <Button type="button" disabled title="Executor Meta ainda não ligado">Criar campanha pausada</Button>
              )}
            </div>
          </form>
        </div>
      </main>
    </Layout>
  );
};

export default MetaCriacaoPage;
