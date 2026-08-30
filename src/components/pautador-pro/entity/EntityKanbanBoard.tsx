import React, { useMemo } from 'react';
import {
  DndContext, DragEndEvent, DragOverlay, DragStartEvent, PointerSensor,
  useSensor, useSensors, closestCorners, useDroppable,
} from '@dnd-kit/core';
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { ValidacaoMarca } from './ValidacaoFaixa';
import { CSS } from '@dnd-kit/utilities';
import { Card, CardContent } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { cn } from '@/lib/utils';
import {
  ContextMenu, ContextMenuContent, ContextMenuItem, ContextMenuTrigger,
} from '@/components/ui/context-menu';
import { Loader2, Sparkles, Landmark, Eye, EyeOff, ExternalLink, Plus, CheckCircle2, Copy, Inbox, PenLine } from 'lucide-react';
import { TierBadge } from '@/components/pautador-pro/TierBadge';
import { PAUTADOR_KANBAN_COLUMNS } from '@/types/pautador';
import type { OpportunityStatus, Tier, PautadorKanbanColumn } from '@/types/pautador';
import { entityKey, entitySubtitle } from '@/types/pautadorEntity';
import type { EntityCard as EntityCardT } from '@/types/pautadorEntity';
import { alvoDeOuro, ETAPAS_DA_MEDICAO,
         type EixoEmProgresso, type ValidacaoRelatorio } from '@/types/pautadorValidacao';

/* ── A AURORA DO ALVO DE OURO ───────────────────────────────────────────────
 *
 * `docs/design/DESIGN-SYSTEM.md` é explícito e este é o único lugar do produto onde ele
 * aparece inteiro: **"strictly flat UI — do not use standard drop shadows. The
 * vibrant gradient backgrounds should feel like they are glowing BEHIND the
 * solid dark foreground elements"**, e **"gradients MUST have a subtle film
 * grain overlaid"**.
 *
 * Então o ouro não ganha um brilho dourado genérico — que é a resposta de
 * catálogo e não é desta marca. Ganha a Aurora: os quatro neons do sistema
 * (`neon-orange #FF3D00`, `neon-purple #8A2BE2`, `deep-blue #0D47A1`,
 * `neon-blue #00D4FF`) num gradiente desfocado ATRÁS do card, com grão por
 * cima do gradiente e nada por cima do conteúdo. O card em si continua chapado.
 *
 * Duas camadas, e a separação é necessária: se o grão entrasse na mesma camada
 * do gradiente, o `blur` que faz o brilho o apagaria. `::before` é a luz
 * (desfocada), `::after` é a textura (nítida, em `overlay`).
 *
 * O hover intensifica em vez de mover. Curva `cubic-bezier(.16,1,.3,1)` —
 * ease-out expo, sem quique — e desligada em `prefers-reduced-motion`.
 *
 * Só na coluna "Em validação": é lá que se escolhe, e ouro brilhando em coluna
 * onde a decisão já foi tomada é decoração. */
const AURORA = `
.val-aurora { position: relative; }
.val-aurora::before,
.val-aurora::after {
  content: ''; position: absolute; inset: -7px; z-index: -1;
  border-radius: 18px; pointer-events: none;
}
.val-aurora::before {
  background: linear-gradient(118deg,#FF3D00 0%,#8A2BE2 34%,#0D47A1 68%,#00D4FF 100%);
  filter: blur(11px); opacity: .34;
  transition: opacity .5s cubic-bezier(.16,1,.3,1), filter .5s cubic-bezier(.16,1,.3,1);
}
.dark .val-aurora::before { opacity: .46; }
/* O grão tem tamanho FIXO e se repete. Sem \`width/height\` no SVG o navegador
   estica a textura até o tamanho do card, e aí um card alto ganha grão graúdo e
   um card baixo ganha grão fino — que é o oposto de textura de filme. Ladrilho
   de 90px com \`stitchTiles\` para a emenda não aparecer. */
.val-aurora::after {
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='90' height='90'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/></filter><rect width='90' height='90' filter='url(%23n)'/></svg>");
  background-size: 90px 90px;
  opacity: .16; mix-blend-mode: overlay;
  transition: opacity .5s cubic-bezier(.16,1,.3,1);
}
.val-aurora:hover::before { opacity: .72; filter: blur(15px); }
.dark .val-aurora:hover::before { opacity: .82; }
.val-aurora:hover::after { opacity: .24; }
/* A linha de 1px que o design pede — mesma aurora, sem desfoque, marcando o
   topo do card como as barras de mineração já marcam. Aqui ela é HAIRLINE:
   estado permanente não grita, estado em curso sim. */
.val-aurora-fio {
  height: 1px; width: 100%;
  background: linear-gradient(90deg,#FF3D00,#8A2BE2,#0D47A1,#00D4FF);
}
@media (prefers-reduced-motion: reduce) {
  .val-aurora::before, .val-aurora::after { transition: none; }
}
`;

function scoreColor(score?: number | null): string {
  const s = score || 0;
  if (s >= 100) return 'text-warning';
  if (s >= 70) return 'text-success';
  if (s >= 45) return 'text-info';
  return 'text-muted-foreground';
}

// volume de busca estimado (descoberta LLM) -> "45k", "1.2M"
function formatVolume(v?: number | null): string {
  if (v == null) return '—';
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1).replace('.0', '')}M`;
  if (v >= 1_000) return `${Math.round(v / 1_000)}k`;
  return String(v);
}

// vertical (linha editorial) + faixa de eCPM (monetização)
const VERTICAL_LABEL: Record<string, string> = {
  gov_beneficios: 'gov', financas: 'finanças', credito: 'crédito', seguros: 'seguros',
  carros_transito: 'carros', imoveis: 'imóveis', educacao: 'educação', saude: 'saúde',
  empregos_concursos: 'empregos', juridico: 'jurídico', tecnologia: 'tech', outros: 'outros',
};
const verticalLabel = (v?: string | null): string => (v ? VERTICAL_LABEL[v] || v : '');
function ecpmTone(b?: string | null): string {
  if (b === 'premium') return 'border-success/30 bg-success/10 text-success';
  if (b === 'medio' || b === 'médio') return 'border-warning/30 bg-warning/10 text-warning';
  if (b === 'baixo') return 'border-border bg-muted text-muted-foreground';
  return 'border-border bg-muted/50 text-muted-foreground';
}

const VALID_TIERS: Tier[] = ['S', 'A', 'B', 'EXPERIMENTAL'];

// Duplicar só faz sentido depois da mineração — é justamente o trabalho (e o
// token) que a cópia reaproveita. Card demo não persiste, então não duplica.
const DUPLICABLE_STATUSES: OpportunityStatus[] = ['mining', 'funnel', 'ready'];
const canDuplicate = (c: EntityCardT): boolean =>
  !c.ephemeral && !!c.id && DUPLICABLE_STATUSES.includes(c.status);

/**
 * O selo de MEDIÇÃO EM CURSO — e ele CONTA, não gira.
 *
 * A mineração acontece no n8n, assíncrona, e o front só sabe que disparou: por
 * isso ela gira. A medição é diferente — ela grava eixo a eixo no banco
 * enquanto roda, e o hook já faz poll desses eixos a cada 1,5s para alimentar o
 * drawer. O dado do progresso real já existia; só não chegava ao card.
 *
 * Então aqui não tem spinner: tem contagem. "3 de 9 eixos" diz quanto falta,
 * um spinner não diz nada — e a diferença importa numa operação que leva dois
 * minutos e custa dinheiro.
 *
 * A ETAPA vem de `ETAPAS_DA_MEDICAO`, a mesma lista que o drawer usa: histórico
 * do cluster, SERP e audiência, leitura da pessoa. O card mostra em qual delas
 * está, para o operador saber se travou no começo ou no fim.
 */
const MedindoSelo: React.FC<{ progresso?: EixoEmProgresso[] }> = ({ progresso }) => {
  const caidos = progresso?.length ?? 0;
  const total = ETAPAS_DA_MEDICAO.reduce((n, e) => n + e.eixos.length, 0);
  const nomes = new Set((progresso ?? []).map((e) => e.eixo));
  // a etapa CORRENTE é a primeira que ainda tem eixo faltando
  const etapa = ETAPAS_DA_MEDICAO.find((e) => e.eixos.some((x) => !nomes.has(x)))
    ?? ETAPAS_DA_MEDICAO[ETAPAS_DA_MEDICAO.length - 1];

  return (
    <span
      className="text-[8px] rounded px-1 py-0.5 border border-info/40 bg-info/10 text-info
                 leading-none shrink-0 inline-flex items-center gap-1 tabular"
      title={`Medindo agora: ${etapa.rotulo}.\n${caidos} de ${total} eixos já gravados. `
        + `O progresso sobrevive a fechar o card — cada eixo vai para o banco assim que é medido.`}
    >
      <Loader2 className="h-2.5 w-2.5 animate-spin shrink-0" aria-hidden />
      {caidos}/{total} · {etapa.rotulo}
    </span>
  );
};


const EntityCardView: React.FC<{
  card: EntityCardT; cardKey: string; busy?: boolean; mining?: boolean; building?: boolean; done?: boolean;
  /** Medindo AGORA. Vinha do hook até o drawer e parava ali — quem arrastava e
   *  fechava o card não tinha sinal nenhum de que a medição estava correndo. */
  medindo?: boolean;
  /** Os eixos que JÁ caíram. A medição grava um a um, então aqui existe
   *  progresso REAL — diferente da mineração, que só pode girar. */
  progresso?: EixoEmProgresso[];
  onClick: (c: EntityCardT) => void;
  onToggleComplete?: (c: EntityCardT, completed: boolean) => void;
  onEscreverFunil?: (c: EntityCardT) => void;
  onDuplicate?: (c: EntityCardT) => void;
}> = ({ card, cardKey, busy, mining, building, done, medindo, progresso, onClick, onToggleComplete, onEscreverFunil, onDuplicate }) => {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: cardKey,
    data: { card },
  });
  const style = { transform: CSS.Transform.toString(transform), transition };
  const tier = (card.gold_tier && VALID_TIERS.includes(card.gold_tier as Tier) ? card.gold_tier : 'B') as Tier;

  // "etapa concluída" DATA-DRIVEN (persistente, sobrevive a refresh):
  //  - parado em "Em funil" e não arquitetando  -> funil pronto
  //  - parado em "Em mineração" com keywords do n8n -> minerado
  // + o flash transitório `done` (mineração interna / momento exato da conclusão).
  const funnelReady = card.status === 'funnel' && !building;
  const minedReady = card.status === 'mining' && !mining && !!card.seed_queries?.some((q) => q.source === 'n8n');
  const showDone = !mining && !building && !card.funnel_completed && (funnelReady || minedReady || !!done);
  const doneLabel = funnelReady ? 'funil pronto' : minedReady ? 'minerado' : 'concluído';

  const duplicable = canDuplicate(card);
  // nome de exibição diferencia CÓPIAS da mesma entidade; sem ele, o card mostra
  // o canonical_name exatamente como sempre mostrou.
  const displayTitle = (card.display_title || '').trim();
  const title = displayTitle || card.entity.canonical_name;

  // O ouro só acende na coluna onde a escolha acontece. Em `mining` ou `funnel`
  // a decisão já foi tomada, e brilho sobre decisão tomada é enfeite.
  const ouroAceso = card.status === 'validating' && alvoDeOuro(card.validacao).e;

  const cardBody = (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}
         className={cn(ouroAceso && 'val-aurora')}>
      {ouroAceso && <style>{AURORA}</style>}
      <Card
        className={cn(
          'hover-lift border-border cursor-grab active:cursor-grabbing',
          isDragging && 'opacity-50 shadow-elevated',
          mining && 'ring-2 ring-warning/60',
          medindo && 'ring-2 ring-info/60',
          building && 'ring-2 ring-primary/50',
          showDone && 'ring-2 ring-success/60',
          card.funnel_completed && 'opacity-60 ring-1 ring-success/40',
          // sem `ring`: o anel é a linguagem dos estados EM CURSO (medindo,
          // construindo). O ouro é um estado permanente e fala pela aurora.
          ouroAceso && 'border-transparent',
        )}
        onClick={() => onClick(card)}
      >
        {ouroAceso && !mining && !building && !showDone && (
          <div className="val-aurora-fio rounded-t-xl" />
        )}
        {medindo && <div className="h-1 w-full rounded-t-xl bg-info animate-pulse" />}
        {mining && <div className="h-1 w-full rounded-t-xl bg-warning animate-pulse" />}
        {building && <div className="h-1 w-full rounded-t-xl bg-primary animate-pulse" />}
        {showDone && <div className="h-1 w-full rounded-t-xl bg-success" />}
        <CardContent className="p-3 space-y-2">
          <div className="flex items-start justify-between gap-1">
            <h4 className="font-display font-bold text-sm leading-snug flex-1 line-clamp-1" title={title}>
              {title}
            </h4>
            <TierBadge tier={tier} />
          </div>

          <p className="text-[10px] text-muted-foreground leading-tight line-clamp-2">
            {displayTitle
              ? `${card.entity.canonical_name} · ${entitySubtitle(card.entity)}`
              : entitySubtitle(card.entity)}
          </p>

          {(card.entity.vertical || card.ecpm_band || true) && (
            <div className="flex items-center gap-1 flex-wrap">
              {card.entity.vertical && (
                <span className="text-[9px] rounded px-1 py-0.5 border border-info/20 bg-info/10 text-info">
                  {verticalLabel(card.entity.vertical)}
                </span>
              )}
              {/* MEDIÇÃO SUBSTITUI PALPITE — nunca convivem.
                *
                * `ecpm_band` é estimativa do descobridor. Enquanto o card não
                * foi medido ela é o único sinal que existe, e some do card
                * seria cegar a coluna de descobertas — então ela FICA, com o
                * mesmo glifo de julgamento que o drawer usa (◇).
                *
                * Assim que há medição, ela SAI: um alvo de ouro medido ao lado
                * de um eCPM adivinhado, os dois em badge de cor, é exatamente a
                * confusão que a disciplina de proveniência existe para impedir. */}
              {!card.validacao && card.ecpm_band && (
                <span className={`text-[9px] rounded px-1 py-0.5 border ${ecpmTone(card.ecpm_band)}`}
                      title="Palpite do descobridor, não medição — sai do card assim que houver medida.">
                  ◇ eCPM {card.ecpm_band}
                </span>
              )}
              {/* ENQUANTO MEDE, o selo dá lugar ao progresso.
                  Mostrar "não medido" durante a medição é dizer uma coisa que
                  já deixou de ser verdade — e é o que a tela fazia. */}
              {medindo
                ? <MedindoSelo progresso={progresso} />
                : <ValidacaoMarca validacao={card.validacao} />}
            </div>
          )}

          <div className="flex items-center justify-between gap-1">
            <span className="text-[10px] text-muted-foreground truncate">{card.strategic_stage || '—'}</span>
            {card.estimated_volume != null ? (
              <span className="text-right leading-tight shrink-0" title={`Volume de busca estimado: ~${card.estimated_volume.toLocaleString('pt-BR')}/mês`}>
                <span className="font-display text-sm font-bold tabular text-info">≈ {formatVolume(card.estimated_volume)}</span>
                <span className="block text-[8px] text-muted-foreground -mt-0.5">buscas/mês</span>
              </span>
            ) : (
              <span className={cn('font-display text-sm font-bold tabular', scoreColor(card.score))} title="Nota de arbitragem">{card.score ?? '—'}</span>
            )}
          </div>

          {card.pains?.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {card.pains.slice(0, 3).map((p, i) => (
                <span key={i} className="text-[9px] bg-muted rounded px-1 py-0.5 truncate max-w-[120px]" title={p.pain_name}>
                  {p.pain_name}
                </span>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between gap-1 pt-0.5">
            <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground truncate">
              <Landmark className="h-3 w-3" />
              {card.entity.official_source || '—'}
            </span>
            <div className="flex items-center gap-1">
              {mining && (
                <span className="inline-flex items-center gap-0.5 text-[9px] font-medium text-warning" title="Minerando no n8n">
                  <Loader2 className="h-2.5 w-2.5 animate-spin" /> minerando…
                </span>
              )}
              {building && (
                <span className="inline-flex items-center gap-0.5 text-[9px] font-medium text-primary" title="Arquitetando o funil">
                  <Loader2 className="h-2.5 w-2.5 animate-spin" /> arquitetando…
                </span>
              )}
              {showDone && (
                <span className="inline-flex items-center gap-0.5 text-[9px] font-semibold text-success animate-scale-in" title="Etapa concluída">
                  <CheckCircle2 className="h-3 w-3" /> {doneLabel}
                </span>
              )}
              {card.ephemeral && (
                <span className="inline-flex items-center gap-0.5 rounded bg-primary/10 text-primary px-1 py-0.5 text-[9px]" title="Demo (não persistido)">
                  <Sparkles className="h-2.5 w-2.5" /> demo
                </span>
              )}
              {busy && !mining && !building && <Loader2 className="h-3 w-3 animate-spin text-primary" />}
            </div>
          </div>

          {/* Pronto: "dar baixa" quando o redator de fato criou o funil */}
          {card.status === 'ready' && onToggleComplete && (
            <div
              className="flex items-center gap-2 pt-1.5 mt-1 border-t border-border"
              onClick={(e) => e.stopPropagation()}
              onPointerDown={(e) => e.stopPropagation()}
            >
              <Checkbox
                id={`done-${cardKey}`}
                checked={!!card.funnel_completed}
                onCheckedChange={(v) => onToggleComplete(card, v === true)}
                className="h-3.5 w-3.5"
              />
              <label
                htmlFor={`done-${cardKey}`}
                className={cn(
                  'text-[10px] cursor-pointer select-none inline-flex items-center gap-1',
                  card.funnel_completed ? 'text-success font-medium' : 'text-muted-foreground',
                )}
              >
                {card.funnel_completed ? <><CheckCircle2 className="h-3 w-3" /> funil criado</> : 'funil criado?'}
              </label>
              {/* Escrever é a etapa mais cara da esteira e precisa de um dado que o
                  card não carrega — em QUAL site. Por isso botão + popup, e não
                  arraste: um arraste acidental aqui gasta dólar e escreve no
                  site errado, e isso não tem desfazer. */}
              {onEscreverFunil && (
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onEscreverFunil(card); }}
                  className="ml-auto inline-flex items-center gap-1 text-[9px] font-medium text-primary hover:underline"
                  title="Escolher o site e mandar o redator escrever"
                >
                  <PenLine className="h-2.5 w-2.5" /> escrever
                </button>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );

  // Sem ação disponível, nem monta o menu — clique direito segue o do navegador.
  if (!duplicable || !onDuplicate) return cardBody;

  return (
    <ContextMenu>
      {/* asChild: o trigger É o card arrastável (não cria wrapper que quebre o dnd).
          O PointerSensor do dnd-kit só ativa com botão esquerdo, então o clique
          direito abre o menu sem iniciar arraste. */}
      <ContextMenuTrigger asChild>{cardBody}</ContextMenuTrigger>
      <ContextMenuContent className="w-56">
        <ContextMenuItem onSelect={() => onDuplicate(card)} className="gap-2">
          <Copy className="h-3.5 w-3.5" />
          Duplicar para outro site
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
};

// Identidade da coluna no vocabulário VOLC (tokens semânticos, cinza frio
// consistente — sem paleta crua do Tailwind, sem warm/cool misturado).
const COLUMN_ACCENT: Record<string, { bar: string; dot: string; pill: string }> = {
  gray:   { bar: 'bg-muted-foreground/40', dot: 'bg-muted-foreground', pill: 'bg-muted text-muted-foreground' },
  blue:   { bar: 'bg-info',                dot: 'bg-info',             pill: 'bg-info/10 text-info' },
  yellow: { bar: 'bg-warning',             dot: 'bg-warning',          pill: 'bg-warning/10 text-warning' },
  purple: { bar: 'bg-primary',             dot: 'bg-primary',          pill: 'bg-primary/10 text-primary' },
  green:  { bar: 'bg-success',             dot: 'bg-success',          pill: 'bg-success/10 text-success' },
  red:    { bar: 'bg-destructive',         dot: 'bg-destructive',      pill: 'bg-destructive/10 text-destructive' },
};
const columnAccent = (color: string) => COLUMN_ACCENT[color] || COLUMN_ACCENT.gray;

/**
 * O rodapé da coluna "Em validação".
 *
 * O botão de LOTE é o caminho padrão, e o texto diz por quê: a base de
 * US$ 0,012 por chamada domina na cauda curta, então validar vinte cards um a
 * um paga a base vinte vezes nos dois nós lotáveis. Sem este número visível,
 * alguém arrasta card a card e paga várias vezes mais sem saber.
 */
export const ValidacaoRodape: React.FC<{
  cards: number;
  ultimoLote?: { custo_usd: number; cards: number; custo_individual_estimado_usd: number } | null;
  ocupado?: boolean;
  onValidar?: () => void;
}> = ({ cards, ultimoLote, ocupado, onValidar }) => (
  <div className="px-2 pb-2 pt-1 space-y-1 border-t border-border/60">
    <button
      type="button"
      disabled={!cards || ocupado || !onValidar}
      onClick={onValidar}
      className={cn(
        'w-full text-[10px] rounded border border-info/30 bg-info/10 text-info',
        'px-2 py-1 font-medium transition-colors hover:bg-info/20',
        'disabled:opacity-40 disabled:cursor-not-allowed',
      )}
    >
      {ocupado ? 'medindo…' : `Validar coluna (${cards})`}
    </button>
    {ultimoLote && (
      <p className="text-[8px] text-muted-foreground leading-tight">
        último lote: {ultimoLote.cards} card{ultimoLote.cards === 1 ? '' : 's'} medido{ultimoLote.cards === 1 ? '' : 's'}
      </p>
    )}
  </div>
);

const EntityColumn: React.FC<{
  onMedirColuna?: (cards: EntityCardT[]) => void;
  medindoLote?: boolean;
  ultimoLote?: { custo_usd: number; cards: number; custo_individual_estimado_usd?: number } | null;
  column: PautadorKanbanColumn; cards: EntityCardT[]; busyKeys: Set<string>; miningKeys: Set<string>; buildingKeys: Set<string>; doneKeys: Set<string>;
  medindoKeys?: Set<string>; progresso?: Record<string, EixoEmProgresso[]>;
  onCardClick: (c: EntityCardT) => void;
  onToggleComplete?: (c: EntityCardT, completed: boolean) => void;
  onEscreverFunil?: (c: EntityCardT) => void;
  showCompleted?: boolean; onToggleShowCompleted?: () => void; completedCount?: number;
  onAddManual?: () => void;
  onAddEnrich?: () => void;
  onDuplicate?: (c: EntityCardT) => void;
  index?: number;
}> = ({ column, cards, busyKeys, miningKeys, buildingKeys, doneKeys, onCardClick, onToggleComplete, onEscreverFunil, showCompleted, onToggleShowCompleted, completedCount, onAddManual, onAddEnrich, onDuplicate, index = 0 , onMedirColuna, medindoLote, ultimoLote, medindoKeys, progresso }) => {
  const { setNodeRef, isOver } = useDroppable({ id: column.id });
  const ids = cards.map(entityKey);
  const isReady = column.id === 'ready';
  const isDiscovered = column.id === 'discovered';
  const showToggle = isReady && (completedCount ?? 0) > 0 && !!onToggleShowCompleted;
  const accent = columnAccent(column.color);
  return (
    <div
      ref={setNodeRef}
      style={{ ['--i' as any]: index }}
      className={cn(
        'reveal flex flex-col rounded-xl border border-border bg-muted/20 min-w-[250px] max-w-[290px] w-full overflow-hidden transition-shadow duration-200',
        isOver && 'ring-2 ring-primary/30 shadow-elevated',
      )}
    >
      <span className={cn('h-0.5 w-full', accent.bar)} />
      <div className="border-b border-border">
        <div className="p-3 flex items-center gap-2">
          <span className={cn('h-2 w-2 rounded-full', accent.dot)} />
          <h3 className="kicker flex-1 truncate">{column.title}</h3>
          {isDiscovered && onAddEnrich && (
            <button
              onClick={onAddEnrich}
              title="Adicionar entidade manualmente (o agente preenche o card)"
              className="text-primary hover:text-primary/80 rounded p-0.5 hover:bg-primary/10 transition-colors"
            >
              <Plus className="h-4 w-4" />
            </button>
          )}
          {isReady && onAddManual && (
            <button
              onClick={onAddManual}
              title="Adicionar entidade manualmente (sem ClickUp)"
              className="text-success hover:text-success/80 rounded p-0.5 hover:bg-success/10 transition-colors"
            >
              <Plus className="h-4 w-4" />
            </button>
          )}
          <span className={cn('text-xs tabular rounded-full px-2 py-0.5 font-medium', accent.pill)}>{cards.length}</span>
        </div>
        {showToggle && (
          <button
            onClick={onToggleShowCompleted}
            className="w-full px-3 pb-2 -mt-1 flex items-center gap-1 text-[10px] text-muted-foreground hover:text-success transition-colors"
          >
            {showCompleted ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
            {showCompleted ? `ocultar ${completedCount} concluído(s)` : `ver ${completedCount} concluído(s)`}
          </button>
        )}
      </div>
      <div className="p-2 flex-1 overflow-y-auto max-h-[calc(100vh-360px)] space-y-2">
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          {cards.map((card) => {
            const key = entityKey(card);
            return <EntityCardView key={key} cardKey={key} card={card} busy={busyKeys.has(key)} mining={miningKeys.has(key)} building={buildingKeys.has(key)} done={doneKeys.has(key)} medindo={medindoKeys?.has(key)} progresso={progresso?.[key]} onClick={onCardClick} onToggleComplete={onToggleComplete} onEscreverFunil={onEscreverFunil} onDuplicate={onDuplicate} />;
          })}
        </SortableContext>
        {cards.length === 0 && (
          <div className="flex flex-col items-center gap-1.5 py-10 text-center">
            <span className="rounded-md bg-muted p-1.5 text-muted-foreground">
              <Inbox className="h-4 w-4" />
            </span>
            <span className="kicker">Vazio</span>
          </div>
        )}
      </div>
      {column.id === 'validating' && onMedirColuna && (
        <ValidacaoRodape cards={cards.length} ocupado={medindoLote}
                         ultimoLote={ultimoLote ? {
                           custo_usd: ultimoLote.custo_usd, cards: ultimoLote.cards,
                           custo_individual_estimado_usd: ultimoLote.custo_individual_estimado_usd ?? 0,
                         } : null}
                         onValidar={() => onMedirColuna(cards)} />
      )}
      </div>
  );
};

interface EntityKanbanBoardProps {
  cards: EntityCardT[];
  busyKeys: Set<string>;
  miningKeys: Set<string>;
  buildingKeys: Set<string>;
  doneKeys: Set<string>;
  onCardClick: (c: EntityCardT) => void;
  onStatusChange: (c: EntityCardT, status: OpportunityStatus) => void;
  onToggleComplete?: (c: EntityCardT, completed: boolean) => void;
  onEscreverFunil?: (c: EntityCardT) => void;
  onAddManual?: () => void;
  onAddEnrich?: () => void;
  /** Botão direito no card (só em cards persistidos que já passaram pela mineração). */
  onDuplicate?: (c: EntityCardT) => void;

  // ── OS CINCO QUE A PÁGINA PASSAVA E O BOARD ENGOLIA ─────────────────────
  //
  // Não estavam declarados aqui e não eram repassados à coluna. Props em
  // excesso em JSX só são checadas contra o tipo quando o objeto é literal, e
  // com um componente de 15 props o TypeScript deixou passar — a página
  // entregava, o board descartava, e ninguém via.
  //
  // O sintoma que ficou seis meses na tela sem ninguém ligar os pontos: a
  // condição `column.id === 'validating' && onMedirColuna` nunca era verdadeira,
  // então o rodapé "Validar coluna" — o caminho BARATO da medição, que paga a
  // base da API uma vez em vez de N — nunca apareceu.
  onMedirColuna?: (cards: EntityCardT[]) => void;
  medindoLote?: boolean;
  ultimoLote?: ValidacaoRelatorio | null;
  /** Cards medindo AGORA (chaves), e os eixos que já caíram de cada um. */
  medindo?: Set<string>;
  progresso?: Record<string, EixoEmProgresso[]>;
}

export const EntityKanbanBoard: React.FC<EntityKanbanBoardProps> = ({ cards, busyKeys, miningKeys, buildingKeys, doneKeys, onCardClick, onStatusChange, onToggleComplete, onEscreverFunil, onAddManual, onAddEnrich, onDuplicate, onMedirColuna, medindoLote, ultimoLote, medindo, progresso }) => {
  const [active, setActive] = React.useState<EntityCardT | null>(null);
  const [showCompleted, setShowCompleted] = React.useState(false);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

  // baixa dada (funil_completed) some por padrão; o toggle na coluna Pronto reexibe
  const completedCount = useMemo(() => cards.filter((c) => c.status === 'ready' && c.funnel_completed).length, [cards]);
  const byColumn = useMemo(() => {
    const visible = showCompleted ? cards : cards.filter((c) => !c.funnel_completed);
    const map: Record<string, EntityCardT[]> = {};
    for (const col of PAUTADOR_KANBAN_COLUMNS) map[col.id] = visible.filter((c) => col.statuses.includes(c.status));
    return map;
  }, [cards, showCompleted]);

  const handleDragStart = (e: DragStartEvent) => setActive((e.active.data.current?.card as EntityCardT) || null);
  const handleDragEnd = (e: DragEndEvent) => {
    setActive(null);
    const { active: a, over } = e;
    if (!over) return;
    const card = a.data.current?.card as EntityCardT | undefined;
    if (!card) return;
    const overId = typeof over.id === 'string' ? over.id : String(over.id);
    let target = PAUTADOR_KANBAN_COLUMNS.find((c) => c.id === overId);
    if (!target) {
      const overCard = over.data.current?.card as EntityCardT | undefined;
      if (overCard) target = PAUTADOR_KANBAN_COLUMNS.find((c) => c.statuses.includes(overCard.status));
    }
    if (target) {
      const newStatus = target.statuses[0];
      if (newStatus !== card.status) onStatusChange(card, newStatus);
    }
  };

  return (
    <DndContext sensors={sensors} collisionDetection={closestCorners} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
      <div className="flex gap-4 overflow-x-auto pb-4">
        {PAUTADOR_KANBAN_COLUMNS.map((column, i) => (
          <EntityColumn
            key={column.id}
            column={column}
            index={i}
            cards={byColumn[column.id] || []}
            busyKeys={busyKeys}
            miningKeys={miningKeys}
            buildingKeys={buildingKeys}
            doneKeys={doneKeys}
            onCardClick={onCardClick}
            onToggleComplete={onToggleComplete}
            onEscreverFunil={onEscreverFunil}
            showCompleted={showCompleted}
            onToggleShowCompleted={() => setShowCompleted((v) => !v)}
            completedCount={completedCount}
            onAddManual={onAddManual}
            onAddEnrich={onAddEnrich}
            onDuplicate={onDuplicate}
            onMedirColuna={onMedirColuna}
            medindoLote={medindoLote}
            ultimoLote={ultimoLote}
            medindoKeys={medindo}
            progresso={progresso}
          />
        ))}
      </div>
      <DragOverlay>
        {active ? <div className="w-[270px]"><EntityCardView cardKey={entityKey(active)} card={active} onClick={() => {}} /></div> : null}
      </DragOverlay>
    </DndContext>
  );
};
