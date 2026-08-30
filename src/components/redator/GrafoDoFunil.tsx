/**
 * O FUNIL COMO ELE É — um grafo, não uma lista.
 *
 * ## Por que a grade de cards estava errada
 *
 * Cinco cards em duas fileiras dizem "cinco páginas". O que o motor produziu é
 * outra coisa, e ela está no campo `routes`: a LP aponta para TRÊS páginas ao
 * mesmo tempo (uma no hero, uma no meio do texto, uma no rodapé), a página 3
 * sai para o Banco Central, e a página 5 sai para OUTRO funil do mesmo domínio.
 *
 * Isso não é enfeite: é a mecânica da arbitragem. Cada salto interno é mais um
 * pageview na mesma sessão comprada, e a sessão só paga o clique se render mais
 * do que custou. Um funil onde todo mundo cai direto na saída oficial perde
 * dinheiro, e uma grade de cards esconde exatamente esse defeito.
 *
 * ## A posição do link é o peso da aresta
 *
 * `hero`, `inline` e `footer` não são metadados: um link no hero é lido por
 * quase todo mundo, um no rodapé por quase ninguém. A espessura e a opacidade
 * da linha carregam isso, então a forma do grafo mostra para onde o tráfego
 * REALMENTE vai — não só para onde ele poderia ir.
 *
 * ## As arestas são medidas, não desenhadas por palpite
 *
 * As posições saem de `getBoundingClientRect` num `ResizeObserver`. Coordenadas
 * calculadas a partir de índice de coluna quebrariam no primeiro título que
 * ocupasse duas linhas, e o operador veria setas apontando para o vazio.
 */
import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, ImageOff, Lock, PenLine } from 'lucide-react';

import { pautadorApi } from '@/lib/pautadorApi';
import { cn } from '@/lib/utils';
import { estaNoAr, linkDeEdicao } from '@/lib/wordpress';
import type { PaginaEscrita, RotaDaPagina } from '@/types/redatorPaginas';
import { ImagemDoArtefato } from './ImagemDoArtefato';

// Peso visual por posição do link. Medido pelo bom senso do ofício, não pelo
// analytics: hero é acima da dobra, footer é depois do texto inteiro.
const PESO: Record<string, { largura: number; opacidade: number; rotulo: string }> = {
  hero:   { largura: 2,   opacidade: 0.85, rotulo: 'hero' },
  inline: { largura: 1.5, opacidade: 0.55, rotulo: 'no texto' },
  footer: { largura: 1,   opacidade: 0.3,  rotulo: 'rodapé' },
};
const PESO_PADRAO = { largura: 1, opacidade: 0.4, rotulo: '' };

const TOM_DO_PAPEL: Record<string, string> = {
  LP: 'border-primary/50 text-primary',
  PRESELL: 'border-info/40 text-info',
  SOLUTION: 'border-border text-muted-foreground',
};

interface Aresta {
  de: string; para: string; kind: string; placement: string; anchor: string;
}

interface Traco extends Aresta { d: string; }

/** As saídas do funil viram nós próprios. Sem isso, as duas arestas mais
 *  importantes do grafo — a que cumpre a promessa da página e a que recicla o
 *  leitor para outro funil — apontariam para fora da tela. */
interface NoDeSaida { id: string; kind: 'external_official' | 'cross_funnel'; alvo: string }

function hostDe(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; }
}

/** O estado de publicação, dito por extenso — inclusive o negativo.
 *
 * ⚠️ ISTO EXISTE PORQUE O SILÊNCIO ERA AMBÍGUO.
 *
 * Até 19/08/2026 o cartão só falava de WordPress quando havia post: página não
 * publicada não mostrava NADA. Um teste chamava isso de "não inventa estado
 * nenhum", e a intenção era boa — não afirmar que está no ar quem não está.
 *
 * Mas ausência de informação não é neutralidade. Diante de um funil recuperado,
 * o operador olhava cinco cartões e não sabia distinguir "publicada" de "pronta
 * e parada" de "barrada" — as três se pareciam. Dizer "não publicada" não é
 * inventar estado; é relatar o que existe.
 */
const ESTADO_DA_PAGINA = (p: PaginaEscrita) => {
  if (p.bloqueada) {
    return { rotulo: 'barrada', tom: 'bg-destructive', texto: 'text-destructive' as const };
  }
  if (!p.publicada) {
    return { rotulo: 'não publicada', tom: 'bg-muted-foreground/40',
             texto: 'text-muted-foreground' as const };
  }
  return estaNoAr(p.publicada)
    ? { rotulo: 'no ar', tom: 'bg-success', texto: 'text-foreground' as const }
    : { rotulo: 'rascunho no WP', tom: 'bg-muted-foreground/40',
        texto: 'text-muted-foreground' as const };
};

const NoDaPagina: React.FC<{
  p: PaginaEscrita; runId: number; registrar: (el: HTMLElement | null) => void;
}> = ({ p, runId, registrar }) => {
  const noAr = estaNoAr(p.publicada);
  const edicao = linkDeEdicao(p.publicada);
  const estado = ESTADO_DA_PAGINA(p);
  return (
  // ⚠️ O `registrar` mede a CAIXA para desenhar as arestas, então ele fica no
  // wrapper — que tem exatamente a mesma geometria do `Link` de antes. Movê-lo
  // para dentro faria as setas apontarem para o vazio.
  //
  // E o wrapper existe por outro motivo: o cartão inteiro é um `Link` interno, e
  // âncora dentro de âncora é HTML inválido — o navegador desfaz o aninhamento e
  // o clique passa a cair no lugar errado. Os links para o WordPress vivem no
  // rodapé, ao LADO do `Link`, nunca dentro dele.
  <div ref={registrar as never}
       className={cn(
         'group relative flex w-[248px] flex-col overflow-hidden rounded-xl border bg-card shadow-card',
         'transition-[border-color,box-shadow] duration-200',
         'hover:border-foreground/40',
         p.bloqueada ? 'border-destructive/40'
           : noAr ? 'border-success/50' : 'border-border',
       )}>
  <span className={cn(
    'pointer-events-none absolute inset-x-0 top-0 z-10 h-0.5',
    p.bloqueada ? 'bg-destructive' : noAr ? 'bg-success' : 'bg-muted-foreground/40',
  )} />
  <Link
    to={`/redator/funil/${runId}/p/${p.page_number}`}
    className={cn(
      'flex flex-col focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
    )}
  >
    <div className="relative aspect-[16/7] w-full overflow-hidden bg-muted">
      {p.imagem ? (
        <ImagemDoArtefato runId={runId} arquivo={p.imagem}
             classNameEstado="h-full w-full"
             className={cn('h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.04]',
                           p.bloqueada && 'opacity-45 grayscale')} />
      ) : (
        <div className="flex h-full items-center justify-center text-muted-foreground">
          <ImageOff className="h-4 w-4" aria-hidden />
        </div>
      )}
      <span className="tabular absolute left-0 top-0 bg-background/85 px-1.5 py-0.5 text-[10px] font-bold">
        {String(p.page_number).padStart(2, '0')}
      </span>
    </div>

    <div className="space-y-1.5 p-3">
      <span className={cn('kicker inline-block border px-1.5 py-0.5',
                          TOM_DO_PAPEL[p.papel] ?? TOM_DO_PAPEL.SOLUTION)}>
        {p.papel}
      </span>
      <h4 className="font-display text-[13px] font-bold leading-snug line-clamp-2" title={p.h1}>
        {p.h1 || p.slug}
      </h4>
      <div className="tabular flex items-center justify-between gap-2 pt-0.5 text-[11px] text-muted-foreground">
        <span>{p.texto.palavras ? `${p.texto.palavras} pal.` : '—'}</span>
        <span>US$ {p.custo_usd.toFixed(2).replace('.', ',')}</span>
      </div>
      {p.bloqueada && (
        <div className="flex items-center gap-1 text-[11px] text-destructive">
          <Lock className="h-3 w-3 shrink-0" aria-hidden />
          <span className="truncate">{p.issues[0]?.code ?? 'barrada'}</span>
        </div>
      )}
    </div>
  </Link>

  {/* O RODAPÉ DE ESTADO — sempre presente, em toda página.
      Fica FORA do `<Link>` de propósito: âncora dentro de âncora é HTML
      inválido, o navegador desfaz o aninhamento em silêncio e o clique passa a
      cair no lugar errado. Isso não aparece no `tsc` nem no build; só clicando.

      Estado por PALAVRA, não só por cor: `--success` mede 3,03:1 sobre
      `--card` no tema claro, abaixo do piso de 4,5:1. Quem não distingue a cor
      lê o texto. */}
  <div className="mt-auto flex items-center gap-2 border-t border-border px-3 py-2 text-[11px]">
    <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', estado.tom)} aria-hidden />
    <span className={cn('truncate', estado.texto)}>{estado.rotulo}</span>
    <span className="ml-auto flex shrink-0 items-center gap-2.5">
      {/* ⚠️ A URL PÚBLICA só aparece para quem está NO AR.
          Rascunho devolve um endereço provisório (`?post_type=r&p=2198`) que
          troca no momento da publicação; oferecê-lo como link do cartão
          convidaria a divulgar um endereço que vai mudar — e é por igualdade
          de string exata que a receita é atribuída à campanha. */}
      {noAr && p.publicada && (
        <a href={p.publicada.url_wp} target="_blank" rel="noreferrer"
           title={p.publicada.url_wp}
           aria-label={`abrir a página publicada ${p.h1 || p.slug} em nova aba`}
           className="inline-flex items-center gap-1 text-muted-foreground underline
                      underline-offset-2 transition-[color] duration-150 hover:text-foreground
                      focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring">
          <ExternalLink className="h-3 w-3" aria-hidden /> ver
        </a>
      )}
      {/* O link de EDIÇÃO vale também para rascunho — ele leva ao painel do
          WordPress, não ao endereço público. É justamente no rascunho que ele
          mais serve: é lá que se confere se o run deu certo, e sem ele o
          operador procura o post por título no admin — mas o título no WP é a
          copy calma, não o h1 que ele leu aqui. */}
      {edicao && (
        <a href={edicao} target="_blank" rel="noreferrer"
           title={`editar o post #${p.publicada?.post_id} no WordPress`}
           aria-label={`editar ${p.h1 || p.slug} no WordPress`}
           className="inline-flex items-center gap-1 text-muted-foreground underline
                      underline-offset-2 transition-[color] duration-150 hover:text-foreground
                      focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring">
          <PenLine className="h-3 w-3" aria-hidden /> editar
        </a>
      )}
    </span>
  </div>
  </div>
  );
};

const NoDeSaidaVis: React.FC<{
  no: NoDeSaida; registrar: (el: HTMLElement | null) => void;
}> = ({ no, registrar }) => (
  <a ref={registrar as never} href={no.alvo} target="_blank" rel="noreferrer"
     className="flex w-[248px] items-center gap-2 rounded-xl border border-dashed border-border bg-card px-3 py-2.5 text-left shadow-card transition-[border-color] duration-150 hover:border-foreground/40">
    <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
    <div className="min-w-0">
      <div className="kicker">
        {no.kind === 'external_official' ? 'canal oficial' : 'outro funil'}
      </div>
      <div className="tabular truncate text-[11px] text-muted-foreground" title={no.alvo}>
        {hostDe(no.alvo)}
      </div>
    </div>
  </a>
);

const Faixa: React.FC<{ rotulo: string; nota?: string; children: React.ReactNode }> =
  ({ rotulo, nota, children }) => (
    <div className="relative">
      <div className="mb-3 flex items-baseline gap-3">
        <span className="kicker">{rotulo}</span>
        {nota && <span className="text-[11px] text-muted-foreground">{nota}</span>}
        <span className="hairline flex-1" />
      </div>
      {/* Centrado, e não encostado à esquerda: é isso que dá ao conjunto a
          silhueta de funil — uma entrada, várias saídas — e faz o leque de
          arestas abrir simétrico em vez de todo para um lado. */}
      <div className="flex flex-wrap items-start justify-center gap-x-10 gap-y-6">{children}</div>
    </div>
  );

export const GrafoDoFunil: React.FC<{ paginas: PaginaEscrita[]; runId: number }> = ({
  paginas, runId,
}) => {
  const caixa = useRef<HTMLDivElement>(null);
  const nos = useRef<Map<string, HTMLElement>>(new Map());
  const [tracos, setTracos] = useState<Traco[]>([]);
  const [tamanho, setTamanho] = useState({ w: 0, h: 0 });

  const registrar = useCallback((id: string) => (el: HTMLElement | null) => {
    if (el) nos.current.set(id, el);
    else nos.current.delete(id);
  }, []);

  const porSlug = new Map(paginas.map((p) => [p.slug, p]));
  const camadas = {
    LP: paginas.filter((p) => p.papel === 'LP'),
    PRESELL: paginas.filter((p) => p.papel === 'PRESELL'),
    SOLUTION: paginas.filter((p) => p.papel === 'SOLUTION'),
  };

  // Arestas e nós de saída, extraídos das rotas reais.
  const arestas: Aresta[] = [];
  const saidas = new Map<string, NoDeSaida>();
  for (const p of paginas) {
    for (const r of (p.rotas || []) as RotaDaPagina[]) {
      const alvo = String(r.target || '');
      if (!alvo) continue;
      if (r.kind === 'funnel') {
        if (porSlug.has(alvo)) {
          arestas.push({ de: p.slug, para: alvo, kind: r.kind,
                         placement: r.placement || '', anchor: r.anchor || '' });
        }
        continue;
      }
      // Saída: um nó por DESTINO, não por aresta — duas páginas que apontam
      // para o Banco Central apontam para o mesmo lugar, e desenhar dois nós
      // sugeriria dois destinos diferentes.
      const id = `saida:${alvo}`;
      if (!saidas.has(id)) {
        saidas.set(id, { id, kind: r.kind as NoDeSaida['kind'], alvo });
      }
      arestas.push({ de: p.slug, para: id, kind: r.kind,
                     placement: r.placement || '', anchor: r.anchor || '' });
    }
  }

  const medir = useCallback(() => {
    const raiz = caixa.current;
    if (!raiz) return;
    const base = raiz.getBoundingClientRect();
    setTamanho({ w: base.width, h: base.height });

    // ⚠️ AS ARESTAS PRECISAM SAIR DE PONTOS DIFERENTES.
    //
    // A LP tem três saídas (hero, no texto, rodapé). Todas partindo do centro
    // da borda inferior, elas se sobrepõem nos primeiros 40px e leem como UMA
    // linha grossa que se abre — exatamente a informação que o grafo existe
    // para negar. O mesmo vale na chegada: três pontas de seta no mesmo pixel
    // viram um borrão.
    //
    // Cada aresta recebe uma fatia da largura do card, na ordem do pipeline
    // (hero à esquerda, rodapé à direita), então a posição do link também se lê
    // na horizontal.
    const saindo = new Map<string, number>();
    const chegando = new Map<string, number>();
    for (const a of arestas) {
      saindo.set(a.de, (saindo.get(a.de) ?? 0) + 1);
      chegando.set(a.para, (chegando.get(a.para) ?? 0) + 1);
    }
    const usadoSaindo = new Map<string, number>();
    const usadoChegando = new Map<string, number>();

    /** i-ésimo de n pontos distribuídos na largura útil (60%) de uma borda. */
    const fatia = (i: number, n: number, largura: number) =>
      n <= 1 ? largura / 2 : largura * (0.2 + 0.6 * (i / (n - 1)));

    const novos: Traco[] = [];
    for (const a of arestas) {
      const de = nos.current.get(a.de);
      const para = nos.current.get(a.para);
      if (!de || !para) continue;
      const A = de.getBoundingClientRect();
      const B = para.getBoundingClientRect();

      const iS = usadoSaindo.get(a.de) ?? 0;
      const iC = usadoChegando.get(a.para) ?? 0;
      usadoSaindo.set(a.de, iS + 1);
      usadoChegando.set(a.para, iC + 1);

      const x1 = A.left - base.left + fatia(iS, saindo.get(a.de) ?? 1, A.width);
      const y1 = A.bottom - base.top;
      const x2 = B.left - base.left + fatia(iC, chegando.get(a.para) ?? 1, B.width);
      const y2 = B.top - base.top;

      // Curva de Bézier com alças verticais: uma reta diagonal entre colunas
      // distantes cruzaria os cards do meio e viraria rabisco.
      const alca = Math.max(24, Math.abs(y2 - y1) * 0.45);
      novos.push({ ...a, d: `M ${x1} ${y1} C ${x1} ${y1 + alca}, ${x2} ${y2 - alca}, ${x2} ${y2}` });
    }
    setTracos(novos);
    // `arestas` é recriado a cada render; a dependência real é o conteúdo dela.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(arestas)]);

  useLayoutEffect(() => { medir(); }, [medir]);

  useEffect(() => {
    const raiz = caixa.current;
    if (!raiz || typeof ResizeObserver === 'undefined') return;
    const obs = new ResizeObserver(() => medir());
    obs.observe(raiz);
    nos.current.forEach((el) => obs.observe(el));
    // As imagens chegam depois e mudam a altura dos cards; sem isto as arestas
    // ficam nas posições de antes do carregamento.
    const imgs = Array.from(raiz.querySelectorAll('img'));
    imgs.forEach((i) => i.addEventListener('load', medir));
    window.addEventListener('resize', medir);
    return () => {
      obs.disconnect();
      imgs.forEach((i) => i.removeEventListener('load', medir));
      window.removeEventListener('resize', medir);
    };
  }, [medir]);

  const oficiais = [...saidas.values()].filter((s) => s.kind === 'external_official');
  const cruzados = [...saidas.values()].filter((s) => s.kind === 'cross_funnel');

  return (
    <div>
      <div ref={caixa} className="relative">
        {/* As arestas ficam ATRÁS dos nós e não capturam clique: elas informam,
            os cards é que são alvo. */}
        <svg className="pointer-events-none absolute inset-0 z-0 overflow-visible"
             width={tamanho.w} height={tamanho.h} aria-hidden>
          <defs>
            <marker id="gf-seta" viewBox="0 0 8 8" refX="7" refY="4"
                    markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 8 4 L 0 8 z" fill="currentColor" />
            </marker>
          </defs>
          {tracos.map((t, i) => {
            const peso = PESO[t.placement] ?? PESO_PADRAO;
            const externo = t.kind !== 'funnel';
            return (
              <path key={i} d={t.d} fill="none"
                    className="text-muted-foreground"
                    stroke="currentColor"
                    strokeWidth={peso.largura}
                    strokeOpacity={peso.opacidade}
                    strokeDasharray={externo ? '3 4' : undefined}
                    markerEnd="url(#gf-seta)" />
            );
          })}
        </svg>

        <div className="relative z-10 space-y-14">
          <Faixa rotulo="entrada" nota="é aqui que o clique comprado chega">
            {camadas.LP.map((p) => (
              <NoDaPagina key={p.slug} p={p} runId={runId} registrar={registrar(p.slug)} />
            ))}
          </Faixa>

          {!!camadas.PRESELL.length && (
            <Faixa rotulo="pré-venda" nota="qualifica e distribui">
              {camadas.PRESELL.map((p) => (
                <NoDaPagina key={p.slug} p={p} runId={runId} registrar={registrar(p.slug)} />
              ))}
            </Faixa>
          )}

          <Faixa rotulo="soluções" nota="onde a receita entra">
            {camadas.SOLUTION.map((p) => (
              <NoDaPagina key={p.slug} p={p} runId={runId} registrar={registrar(p.slug)} />
            ))}
          </Faixa>

          {(oficiais.length > 0 || cruzados.length > 0) && (
            <Faixa rotulo="saídas" nota="o leitor deixa o funil por aqui">
              {[...oficiais, ...cruzados].map((s) => (
                <NoDeSaidaVis key={s.id} no={s} registrar={registrar(s.id)} />
              ))}
            </Faixa>
          )}
        </div>
      </div>

      {/* A legenda não é enfeite: sem ela, três espessuras de linha são ruído.
          Com ela, a forma do grafo vira leitura de para onde o tráfego vai. */}
      <div className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-border pt-4">
        {Object.entries(PESO).map(([k, v]) => (
          <span key={k} className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <svg width="26" height="8" aria-hidden className="text-muted-foreground">
              <line x1="0" y1="4" x2="26" y2="4" stroke="currentColor"
                    strokeWidth={v.largura} strokeOpacity={v.opacidade} />
            </svg>
            link no {v.rotulo}
          </span>
        ))}
        <span className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <svg width="26" height="8" aria-hidden className="text-muted-foreground">
            <line x1="0" y1="4" x2="26" y2="4" stroke="currentColor"
                  strokeWidth="1" strokeDasharray="3 4" strokeOpacity="0.6" />
          </svg>
          saída do funil
        </span>
      </div>
    </div>
  );
};
