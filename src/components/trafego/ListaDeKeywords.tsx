/**
 * A lista de keywords — que precisa contar a MESMA história que a régua.
 *
 * ## O defeito que ela conserta
 *
 * A primeira versão eram 23 linhas de altura idêntica. A régua, logo abaixo,
 * mostrava que uma delas era 73% do volume. As duas peças da mesma tela
 * discordavam: quem lesse a lista concluiria que os 23 termos pesam parecido, e
 * quem lesse a régua concluiria o contrário.
 *
 * Agora cada linha carrega uma barra de volume atrás do texto, na mesma escala
 * do maior termo do grupo. Percorrer a lista e olhar a régua passam a produzir
 * a mesma conclusão — que é o mínimo que duas visões do mesmo dado devem fazer.
 *
 * ## Por que a barra é do GRUPO e não do conjunto todo
 *
 * Escalar pelo conjunto faria os grupos pequenos virarem uma linha de pixels:
 * VALOR tem 1.980 de volume contra 30.430 de ACESSO, e nele nada seria
 * comparável com nada. A régua já mostra a proporção ENTRE grupos; a lista
 * mostra a proporção DENTRO de cada um. São perguntas diferentes.
 */
import React from 'react';
import { Check } from 'lucide-react';

import { cn } from '@/lib/utils';
import type { GrupoCandidato, KeywordCandidata } from '@/types/trafego';

/** As tags que a mineração atribuiu. Cada uma é o motivo pelo qual aquele termo
 *  sobreviveu à triagem — não é decoração, é a justificativa. */
const TRADUCAO_DE_TAG: Record<string, string> = {
  VOLUME_TITAN: 'volume titânico',
  HIDDEN_GEM: 'joia escondida',
  USER_QUESTION: 'pergunta de usuário',
  SEASONAL: 'sazonal',
  SEASONAL_SPIKE: 'pico sazonal',
  FUTURE: 'tendência futura',
  FUTURE_TREND: 'tendência futura',
  TREND_RISING: 'em alta',
  EXPLOSIVE_TREND: 'em alta',
  EXPLOSIVE_MICRO: 'nicho em alta',
};

/** ⚠️ TAG QUE ESTÁ EM QUASE TUDO NÃO DISCRIMINA NADA.
 *
 * Medido no cluster do card 73: `EXPLOSIVE_TREND` e `EXPLOSIVE_MICRO` aparecem
 * em 20 das 23 keywords aprovadas — 87%. Renderizá-las produz a mesma linha de
 * texto cinza sob quase toda keyword, e o olho aprende a ignorar a faixa
 * inteira. Junto com elas some `VOLUME_TITAN`, que é a única que importava.
 *
 * O limiar é sobre o GRUPO, não sobre o cluster: uma tag pode ser banal em
 * ELEGIBILIDADE (13 termos) e ser o traço distintivo em VALOR (5). Filtrar pelo
 * conjunto todo apagaria justamente essa diferença.
 */
const LIMIAR_DE_RUIDO = 0.6;

function tagsQueDiscriminam(grupo: GrupoCandidato): Set<string> {
  const n = grupo.keywords.length || 1;
  const conta = new Map<string, number>();
  for (const k of grupo.keywords) {
    for (const t of new Set(k.tags)) conta.set(t, (conta.get(t) ?? 0) + 1);
  }
  return new Set([...conta].filter(([, c]) => c / n < LIMIAR_DE_RUIDO).map(([t]) => t));
}

export const ListaDeKeywords: React.FC<{
  grupo: GrupoCandidato;
  marcadas: Set<string>;
  onAlternar: (texto: string) => void;
}> = ({ grupo, marcadas, onAlternar }) => {
  // ⚠️ AUSÊNCIA NÃO É ZERO, NEM NA ORDENAÇÃO.
  //
  // `b.volume - a.volume` com `volume: number | null` devolve `NaN`, e um
  // comparador que devolve NaN produz ordem indefinida — a lista embaralharia
  // sem ninguém notar. Quem não tem volume medido vai para o FIM, junto, e não
  // se mistura com quem foi medido em zero: são fatos diferentes.
  const ordenadas = React.useMemo(
    () => [...grupo.keywords].sort((a, b) => {
      if (a.volume == null && b.volume == null) return 0;
      if (a.volume == null) return 1;
      if (b.volume == null) return -1;
      return b.volume - a.volume;
    }),
    [grupo.keywords],
  );
  // O maior volume MEDIDO. `|| 1` evita divisão por zero; ele não inventa dado,
  // porque a barra de quem não tem volume simplesmente não é desenhada.
  const maior = React.useMemo(
    () => grupo.keywords.reduce((m, k) => (k.volume != null && k.volume > m ? k.volume : m), 0) || 1,
    [grupo.keywords],
  );
  const uteis = React.useMemo(() => tagsQueDiscriminam(grupo), [grupo]);

  return (
    <ul className="mt-3">
      {ordenadas.map((k) => (
        <Linha key={k.texto} k={k} maior={maior} tagsUteis={uteis}
               marcada={marcadas.has(k.texto)} onAlternar={() => onAlternar(k.texto)} />
      ))}
    </ul>
  );
};

const Linha: React.FC<{
  k: KeywordCandidata; maior: number; tagsUteis: Set<string>;
  marcada: boolean; onAlternar: () => void;
}> = ({ k, maior, tagsUteis, marcada, onAlternar }) => {
  // `null` = sem barra. Desenhar 0,5% para quem não foi medido daria a mesma
  // forma de quem foi medido perto de zero.
  const pct = k.volume == null ? null : Math.max(0.5, (k.volume / maior) * 100);
  const volumeLido = k.volume == null ? null : k.volume.toLocaleString('pt-BR');
  const cpcLido = k.cpc?.valor == null ? null : k.cpc.valor.toFixed(2).replace('.', ',');
  const tags = [...new Set(k.tags)]
    .filter((t) => tagsUteis.has(t))
    .map((t) => TRADUCAO_DE_TAG[t] ?? t.toLowerCase().replace(/_/g, ' '));

  return (
    <li>
      <button
        type="button"
        onClick={onAlternar}
        aria-pressed={marcada}
        aria-label={`${k.texto}, volume ${volumeLido ?? 'não medido'}`
          + `${cpcLido ? `, CPC ${cpcLido}` : ', CPC não medido'}`
          + `${marcada ? ', selecionada' : ', fora'}`}
        className={cn(
          'group relative flex w-full items-center gap-3 overflow-hidden px-3 py-2.5 text-left',
          'transition-[opacity,transform] duration-150',
          // Feedback de pressionado. Sem ele a linha responde só depois do
          // re-render, e num clique rápido parece que nada aconteceu.
          'active:translate-y-px',
          'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
          marcada ? 'opacity-100' : 'opacity-45 hover:opacity-70',
        )}
      >
        {/* A barra de volume, ATRÁS do conteúdo. É o que faz a lista concordar
            com a régua: escanear as linhas dá a mesma conclusão que olhar a
            forma. */}
        {pct != null && (
          <span aria-hidden
                className={cn('absolute inset-y-0 left-0 -z-10 transition-[width] duration-200',
                              marcada ? 'bg-muted' : 'bg-muted/50')}
                style={{ width: `${pct}%` }} />
        )}

        <span className={cn(
          'flex h-4 w-4 shrink-0 items-center justify-center border transition-colors',
          marcada ? 'border-foreground bg-foreground' : 'border-muted-foreground/50 group-hover:border-foreground/70',
        )}>
          {marcada && <Check className="h-2.5 w-2.5 text-background" aria-hidden />}
        </span>

        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] leading-snug" title={k.texto}>
            {k.texto}
          </span>
          {(tags.length > 0 || k.tambem_em_conteudo) && (
            <span className="mt-0.5 block truncate text-[11px] leading-tight text-muted-foreground">
              {tags.join(' · ')}
              {k.tambem_em_conteudo && (tags.length ? ' · ' : '') + 'também em conteúdo'}
            </span>
          )}
        </span>

        {/* ⚠️ Ausência é escrita, não zerada. "não medido" e "0" são afirmações
            diferentes, e a segunda é cara: diz que ninguém procura por isso. */}
        <span className="tabular shrink-0 text-right text-[13px] leading-none">
          {volumeLido ?? <span className="text-muted-foreground">não medido</span>}
          <span className="mt-1 block text-[11px] text-muted-foreground">
            {cpcLido ?? 'CPC não medido'}
          </span>
        </span>
      </button>
    </li>
  );
};
