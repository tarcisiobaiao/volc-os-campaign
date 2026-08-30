/**
 * As três peças em volta da matriz: a linha do funil, o cartão de custo e o que
 * já saiu.
 *
 * O que as une é uma regra só: **número real, nunca adjetivo**. "Quase pronto"
 * e "correndo bem" são o tipo de coisa que uma tela diz quando não sabe — e
 * aqui ela sabe.
 */
import React from 'react';

import { cn } from '@/lib/utils';
import type { MatrizDoRun } from '@/types/redator';

function moeda4(v: number): string {
  return `US$ ${v.toFixed(4).replace('.', ',')}`;
}

function relogio(s: number): string {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

// ── A linha do funil ────────────────────────────────────────────────────────
//
// PAUTA → FUNIL → CAMPANHA → RESULTADO. É o ciclo inteiro do negócio, e a razão
// de a página existir: sem o nó CAMPANHA ligado, o funil escrito é conteúdo que
// ninguém comprou tráfego para ler.

interface No { rotulo: string; valor: string; feito: boolean }

export const LinhaDoFunil: React.FC<{
  m: MatrizDoRun;
  /** ⚠️ OPCIONAL E QUASE SEMPRE DESNECESSÁRIO. O nome já vem em `m.titulo`,
   *  resolvido pelo servidor a partir de `pautador_entities.canonical_name`.
   *  Enquanto ele era só um prop, a `FunilPage` esquecia de passá-lo e o
   *  trilho escrevia `card #74` — o número da linha do banco como nome de um
   *  funil de seis páginas — mesmo com a manchete logo acima já corrigida. */
  tituloDaPauta?: string;
}> = ({ m, tituloDaPauta }) => {
  const publicadas = m.publicadas.length;
  const planejadas = m.run.paginas_planejadas ?? 0;
  const nos: No[] = [
    { rotulo: 'pauta', valor: tituloDaPauta || m.titulo || `card #${m.run.opportunity_id}`, feito: true },
    {
      rotulo: 'funil',
      valor: planejadas ? `${publicadas}/${planejadas} páginas` : '—',
      feito: publicadas > 0,
    },
    {
      // `não ligada` e não `—`: a diferença entre "ainda não sei" e "existe uma
      // ponta solta aqui" é a única coisa que faz alguém agir.
      rotulo: 'campanha',
      valor: m.lp_url ? 'LP pronta · não ligada' : 'não ligada',
      feito: false,
    },
    { rotulo: 'resultado', valor: '—', feito: false },
  ];
  const ultimoFeito = nos.reduce((acc, n, i) => (n.feito ? i : acc), -1);

  return (
    <div className="w-full">
      {/* ⚠️ A linha fica na FAIXA DOS NÓS, não no meio do bloco todo.
          Centralizada verticalmente no container inteiro, ela cortava os
          rótulos "PAUTA" e "FUNIL" ao meio — e uma régua de 1px passando por
          dentro do texto lê como defeito de renderização, não como conexão.
          Aqui ela mora na altura dos crosshairs, e o texto vem abaixo dela. */}
      <div className="relative h-3">
        <div className="absolute inset-x-0 top-1/2 flex -translate-y-1/2">
          <div className="h-px bg-primary"
               style={{ width: `${Math.max(0, (ultimoFeito / (nos.length - 1)) * 100)}%` }} />
          <div className="hairline flex-1" />
        </div>
        <div className="relative flex h-full items-center justify-between">
          {nos.map((n, i) => (
            <span key={n.rotulo}
                  className={cn('crosshair block h-1 w-1',
                    i <= ultimoFeito ? 'text-foreground' : 'text-muted-foreground/40')} />
          ))}
        </div>
      </div>
      <div className="mt-3 flex justify-between">
        {nos.map((n, i) => (
          <div key={n.rotulo}
               className={cn('flex flex-col gap-1', i === 0 ? 'items-start'
                 : i === nos.length - 1 ? 'items-end' : 'items-center')}>
            <span className="kicker">{n.rotulo}</span>
            <span className={cn('tabular max-w-[24ch] truncate text-xs',
              n.feito ? 'text-foreground' : 'text-muted-foreground')}
              title={n.valor}>{n.valor}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

// ── O cartão de custo ───────────────────────────────────────────────────────

export const CartaoDeCusto: React.FC<{
  m: MatrizDoRun; segundosSemCobranca: number; vivo: boolean;
}> = ({ m, segundosSemCobranca, vivo }) => {
  const teto = m.teto_usd;
  const fracao = teto && teto > 0 ? Math.min(1, m.custo_total / teto) : null;
  // 3 minutos é o limiar porque `research_p1` levou 3min07s num run real. Abaixo
  // disso, silêncio é normal; acima, a tela parece travada e precisa dizer que
  // não está.
  const parado = vivo && segundosSemCobranca > 180;

  return (
    <div className="border border-border bg-card p-6 shadow-card">
      <div className="kicker">custo contabilizado</div>
      <div className="mt-2 flex items-baseline gap-3">
        <span className="tabular font-display text-4xl font-bold tracking-tight">
          {moeda4(m.custo_total)}
        </span>
        {teto && (
          <span className="tabular text-sm text-muted-foreground">de {moeda4(teto)}</span>
        )}
        {parado && (
          <span className="tabular text-sm text-muted-foreground">
            — sem cobrança há {relogio(segundosSemCobranca)}
          </span>
        )}
      </div>

      {fracao !== null && (
        <div className="mt-4 h-1 w-full max-w-md bg-border">
          <div
            className="h-full bg-primary transition-[width] duration-200 motion-reduce:transition-none"
            style={{ width: `${fracao * 100}%` }}
          />
        </div>
      )}

      {/* Obrigatório quando o motor engoliu custo. A tela NÃO compensa o número
          por conta própria: trocar um total honestamente incompleto por um
          total inventado seria pior que o defeito. */}
      {m.subestimado && (
        <p className="mt-4 max-w-[62ch] text-xs leading-relaxed text-muted-foreground">
          Este total pode estar <b>abaixo</b> da fatura: alguma etapa falhou por
          exceção, e nesse caminho o provedor pode ter cobrado uma chamada que o
          motor nunca contabilizou.
        </p>
      )}
      {parado && (
        <p className="mt-3 max-w-[62ch] text-xs leading-relaxed text-muted-foreground">
          Silêncio não é travamento: a pesquisa da primeira página chega a levar
          três minutos, e o motor só reescreve o estado nos pontos de checkpoint.
        </p>
      )}
    </div>
  );
};

// ── O que já saiu ───────────────────────────────────────────────────────────

export const OQueJaSaiu: React.FC<{ m: MatrizDoRun }> = ({ m }) => {
  if (!m.publicadas.length) {
    return (
      <p className="text-sm text-muted-foreground">
        Nada publicado ainda.
      </p>
    );
  }
  return (
    <div className="divide-y divide-border/60 border-y border-border">
      {[...m.publicadas].sort((a, b) => a.page_number - b.page_number).map((p) => (
        <div key={p.post_id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-3">
          <span className="kicker w-24 shrink-0">p{p.page_number} · {p.role}</span>
          <a href={p.url_wp} target="_blank" rel="noreferrer"
             className="min-w-0 flex-1 truncate text-sm underline-offset-4 hover:underline"
             title={p.url_wp}>
            {p.url_wp}
          </a>
          <span className="tabular shrink-0 text-xs text-muted-foreground">
            post {p.post_id}
          </span>
          <span className="kicker shrink-0 border border-border px-2 py-0.5">
            {p.status_wp === 'draft' ? 'rascunho' : p.status_wp}
          </span>
        </div>
      ))}
      {/* ⚠️ De um rascunho o WordPress devolve `?post_type=r&p=2146`, não o
          permalink — o `/r/<slug>/` só nasce quando o post vai ao ar. Dizer isso
          evita que alguém copie essas URLs para a campanha agora. */}
      {m.publicadas.some((p) => p.status_wp === 'draft') && (
        <p className="max-w-[68ch] py-3 text-xs leading-relaxed text-muted-foreground">
          Estas são URLs de rascunho. O endereço definitivo — o que a campanha vai
          apontar — só nasce quando as páginas forem publicadas de verdade.
        </p>
      )}
    </div>
  );
};
