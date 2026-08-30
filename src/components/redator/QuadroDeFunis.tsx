/**
 * O QUADRO — onde cada funil está no ciclo.
 *
 * ## Por que quatro colunas e não uma lista
 *
 * A lista de execuções responde "o que já rodou". A pergunta que o operador
 * realmente tem ao abrir o Redator é outra, e tem três partes:
 *
 *   o que está pronto para eu mandar escrever?
 *   o que está sendo escrito agora?
 *   o que virou rascunho e está esperando eu revisar?
 *
 * A primeira coluna é a que muda o produto. Ela não vem da tabela de runs: são
 * os cards do Pautador que chegaram a `ready` COM arquitetura e ainda não
 * tiveram um run bem-sucedido. Sem ela, disparar um funil exige voltar ao
 * Pautador e achar o card — e quem abriu o Redator para trabalhar não tem por
 * onde começar.
 *
 * ## Interrompidos volta para a fila, e isso é de propósito
 *
 * Um run `failed` NÃO tira o card da coluna "prontos": falhou é justamente o
 * caso em que se quer tentar de novo. Mas o funil interrompido continua
 * visível na quarta coluna, porque ele gastou dinheiro e pode ter publicado
 * páginas — redisparar sem olhar isso duplica trabalho no site.
 */
import React from 'react';
import { Link } from 'react-router-dom';
import { FileCheck, Inbox, Loader2, PenLine, Play, Trash2, TriangleAlert } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import type { CardPronto, FunilNoQuadro, QuadroDoRedator } from '@/types/redatorQuadro';

function moeda2(v: number | null | undefined): string {
  return `US$ ${(v ?? 0).toFixed(2).replace('.', ',')}`;
}

function quando(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

const COLUNA = {
  prontos: {
    bar: 'bg-primary', dot: 'bg-primary', pill: 'bg-primary/10 text-primary',
    Icon: PenLine,
  },
  escrevendo: {
    bar: 'bg-info', dot: 'bg-info', pill: 'bg-info/10 text-info',
    Icon: Loader2,
  },
  escritos: {
    bar: 'bg-success', dot: 'bg-success', pill: 'bg-success/10 text-success',
    Icon: FileCheck,
  },
  interrompidos: {
    bar: 'bg-destructive', dot: 'bg-destructive', pill: 'bg-destructive/10 text-destructive',
    Icon: TriangleAlert,
  },
} as const;

const Coluna: React.FC<{
  titulo: string; nota: string; n: number;
  tom: keyof typeof COLUNA; children: React.ReactNode;
}> = ({ titulo, nota, n, tom, children }) => {
  const accent = COLUNA[tom];
  const Icon = accent.Icon;
  return (
    <section className="flex min-h-[12rem] min-w-0 flex-col overflow-hidden rounded-xl border border-border bg-muted">
      <span className={cn('h-0.5 w-full', accent.bar)} />
      <div className="flex items-center gap-2 border-b border-border p-3">
        <span className={cn('flex h-5 w-5 items-center justify-center rounded-md', accent.pill)}>
          <Icon className={cn('h-3.5 w-3.5', tom === 'escrevendo' && n > 0 && 'animate-spin')} aria-hidden />
        </span>
        <h2 className="kicker flex-1 truncate">{titulo}</h2>
        <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium tabular', accent.pill)}>
          {n}
        </span>
      </div>
      <p className="px-3 pt-2 text-[11px] leading-tight text-muted-foreground">{nota}</p>
      <div className="flex-1 space-y-2 p-2">{children}</div>
    </section>
  );
};

const Vazio: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="flex flex-col items-center gap-1.5 rounded-lg border border-dashed border-border px-3 py-10 text-center">
    <span className="rounded-md bg-card p-1.5 text-muted-foreground">
      <Inbox className="h-4 w-4" aria-hidden />
    </span>
    <p className="text-[11px] leading-relaxed text-muted-foreground">{children}</p>
  </div>
);

const CardParaEscrever: React.FC<{ c: CardPronto; onDisparar: () => void }> = ({ c, onDisparar }) => (
  <Card className="relative overflow-hidden hover-lift">
    <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-primary" />
    <CardContent className="space-y-2.5 p-3">
      <h4 className="line-clamp-2 font-display text-sm font-bold leading-snug" title={c.titulo}>
        {c.titulo}
      </h4>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="kicker rounded-md border border-border bg-muted/50 px-1.5 py-0.5 text-foreground">
          {c.paginas} páginas
        </span>
        {c.score != null && (
          <span className="kicker rounded-md border border-border bg-muted/50 px-1.5 py-0.5 text-foreground">
            nota {c.score}
          </span>
        )}
        {c.ecpm_band && (
          <span className="kicker rounded-md border border-border bg-muted/50 px-1.5 py-0.5 text-foreground">
            {c.ecpm_band}
          </span>
        )}
      </div>
      {/* O custo estimado vem antes do botão de propósito: escrever um funil
          custa ~US$ 2 e leva ~45 min, e um disparo acidental não tem desfazer
          barato. */}
      <p className="text-[11px] leading-tight text-muted-foreground">
        ~US$ 2 e ~45 min para escrever as {c.paginas} páginas.
      </p>
      <Button type="button" size="sm" className="w-full" onClick={onDisparar}>
        <Play className="h-3.5 w-3.5" aria-hidden /> escrever este funil
      </Button>
    </CardContent>
  </Card>
);

const CardDeFunil: React.FC<{
  f: FunilNoQuadro; vivo?: boolean; onExcluir?: (f: FunilNoQuadro) => void;
}> = ({ f, vivo, onExcluir }) => {
  const progresso = f.paginas_planejadas
    ? Math.min(1, (f.paginas_publicadas || f.paginas_geradas || 0) / f.paginas_planejadas)
    : 0;
  const barra = f.status === 'done' ? 'bg-success'
    : f.status === 'running' || f.status === 'queued' || vivo ? 'bg-primary'
    : 'bg-destructive';
  const preenchimento = vivo ? 'bg-primary'
    : f.status === 'done' ? 'bg-success'
    : 'bg-muted-foreground';

  return (
    <div className="group/card relative">
      {/* Excluir só aparece no hover e só onde faz sentido: um funil que
          publicou não pode sumir (a linha é o único registro de quais rascunhos
          vieram dele), e o backend recusa de qualquer forma. Mostrar um botão
          que vai dar 409 seria pior que não mostrar. */}
      {onExcluir && f.paginas_publicadas === 0 && (
        <button type="button"
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); onExcluir(f); }}
                aria-label={`excluir a execução ${f.id} de ${f.titulo}`}
                className="absolute right-1.5 top-2 z-10 flex h-6 w-6 items-center justify-center rounded-md border border-border bg-card text-muted-foreground opacity-0 transition-[opacity,color,border-color] duration-150 hover:border-destructive hover:text-destructive focus-visible:opacity-100 group-hover/card:opacity-100">
          <Trash2 className="h-3 w-3" aria-hidden />
        </button>
      )}
      <Link to={`/redator/funil/${f.id}`} className="block">
        <Card className="relative overflow-hidden hover-lift">
          <span className={cn('pointer-events-none absolute inset-x-0 top-0 h-0.5', barra)} />
          <CardContent className="space-y-2 p-3">
            <h4 className="line-clamp-2 font-display text-sm font-bold leading-snug" title={f.titulo}>
              {f.titulo}
            </h4>
            <p className="truncate text-[11px] text-muted-foreground tabular" title={f.dominio}>
              {f.dominio || `projeto ${f.project_id}`}
            </p>

            {/* Uma barra só, e ela mede PÁGINAS, não etapas: é a unidade que o
                operador reconhece. "3 de 5 páginas" diz mais que "29 de 43
                etapas", que é vocabulário do motor.
                Sem transição de width: o contrato de motion anima transform e
                opacity, não geometria. */}
            {!!f.paginas_planejadas && (
              <div className="space-y-1 pt-0.5">
                <div className="h-1 w-full overflow-hidden rounded-full bg-secondary">
                  <div className={cn('h-full', preenchimento)}
                       style={{ width: `${progresso * 100}%` }} />
                </div>
                <div className="flex items-baseline justify-between text-[11px] text-muted-foreground tabular">
                  <span>
                    {f.paginas_publicadas || f.paginas_geradas || 0}/{f.paginas_planejadas} páginas
                  </span>
                  <span>{moeda2(f.custo_usd)}</span>
                </div>
              </div>
            )}

            <div className="flex items-center gap-1.5 border-t border-border pt-2 text-[11px] text-muted-foreground tabular">
              {vivo && <Loader2 className="h-3 w-3 animate-spin" aria-hidden />}
              <span>{vivo ? `${f.etapas} etapas registradas` : quando(f.criado_em)}</span>
            </div>

            {/* Um funil interrompido que JÁ publicou é a armadilha cara: quem
                redispara sem ver isso duplica as páginas no site. */}
            {f.status !== 'done' && !vivo && f.paginas_publicadas > 0 && (
              <p className="text-[11px] leading-tight text-destructive">
                interrompido, mas {f.paginas_publicadas} página
                {f.paginas_publicadas > 1 ? 's já subiram' : ' já subiu'} — confira
                antes de reescrever
              </p>
            )}
          </CardContent>
        </Card>
      </Link>
    </div>
  );
};

export const QuadroDeFunis: React.FC<{
  quadro: QuadroDoRedator;
  onDisparar: (c: CardPronto) => void;
  onExcluir: (f: FunilNoQuadro) => void;
}> = ({ quadro, onDisparar, onExcluir }) => (
  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
    <Coluna tom="prontos" titulo="prontos para escrever" n={quadro.prontos.length}
            nota="Cards que o Pautador aprovou e arquitetou. Cada um vira um funil de 5 a 7 páginas.">
      {quadro.prontos.length
        ? quadro.prontos.map((c) => (
            <CardParaEscrever key={c.opportunity_id} c={c} onDisparar={() => onDisparar(c)} />))
        : <Vazio>
            Nenhum card aprovado esperando. Valide um card no{' '}
            <Link to="/pautador-pro" className="underline underline-offset-2">Pautador Pro</Link>{' '}
            para ele aparecer aqui.
          </Vazio>}
    </Coluna>

    <Coluna tom="escrevendo" titulo="escrevendo" n={quadro.escrevendo.length}
            nota="Um por vez: dois runs simultâneos disputariam o mesmo teto de gasto.">
      {quadro.escrevendo.length
        ? quadro.escrevendo.map((f) => <CardDeFunil key={f.id} f={f} vivo />)
        : <Vazio>O motor está parado.</Vazio>}
    </Coluna>

    <Coluna tom="escritos" titulo="escritos · rascunho" n={quadro.escritos.length}
            nota="No WordPress como rascunho, invisíveis para o público. Esperando revisão.">
      {quadro.escritos.length
        ? quadro.escritos.map((f) => <CardDeFunil key={f.id} f={f} />)
        : <Vazio>Nenhum funil concluído ainda.</Vazio>}
    </Coluna>

    <Coluna tom="interrompidos" titulo="interrompidos" n={quadro.interrompidos.length}
            nota="Falharam ou foram cancelados. O que já foi pago continua no funil — abra antes de reescrever.">
      {quadro.interrompidos.length
        ? quadro.interrompidos.map((f) => (
            <CardDeFunil key={f.id} f={f} onExcluir={onExcluir} />))
        : <Vazio>Nenhum.</Vazio>}
    </Coluna>
  </div>
);
