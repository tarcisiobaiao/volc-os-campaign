/**
 * A MATRIZ — uma linha por página, uma coluna por etapa, uma célula por passo.
 *
 * ## Duas perguntas, uma forma
 *
 * A grade responde "onde o motor está" e "para onde foi o dinheiro" ao mesmo
 * tempo, porque a ALTURA de cada célula é proporcional ao custo dela. Medido no
 * run de referência: `write` e `research` levam 79,5% do total e formam um
 * paredão à esquerda; `build`, `publish` e `screenshot` custam zero e viram um
 * fio. Uma grade de quadrados idênticos esconderia exatamente isso — e é essa
 * informação que decide se vale a pena cancelar aos 20 minutos.
 *
 * ## Cor está descartada POR MEDIÇÃO
 *
 * Contraste WCAG dos tokens semânticos sobre `--card` no tema claro: `--success`
 * 3,03:1, `--warning` 2,38:1, `--info` 2,76:1 — três dos cinco reprovam o piso
 * de 4,5:1, e o `--warning` reprova até o piso de 3:1 para elemento não-textual.
 * Pior: a razão de luminância entre `warning` e `success` no claro é 1,32, que é
 * o par exato que um protanope confunde. E os números INVERTEM entre os temas.
 *
 * Daí a ordem: **geometria primeiro, glifo redundante, cor em último** e só onde
 * ela some sem prejuízo (`--destructive`, que passa nos dois temas).
 */
import React from 'react';

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import type { CelulaDaMatriz, MatrizDoRun, PaginaDaMatriz } from '@/types/redator';
import type { CelulaCorrente } from '@/hooks/redator/useMatrizDoRun';

// ⚠️ ESTA ESCALA É O ARGUMENTO DA TELA, não uma preferência.
//
// A primeira versão usava 34×26 com 22px de altura máxima — o número que a spec
// derivou de caber em 375px de mobile. Renderizado, o resultado foi medido: a
// grade ocupava 506px de uma viewport de 1440 e a diferença entre a célula de
// US$ 0,4556 e a de US$ 0,0046 virava 24px contra 2px em blocos que o olho lê
// como "duas barrinhas". O paredão de pesquisa+redação — os 79,5% do dinheiro,
// que é a única razão de a altura codificar custo — simplesmente não aparecia.
//
// A razão entre as células é a mesma; o que muda é a amplitude em que ela é
// legível. O mobile continua atendido pela rolagem horizontal (§5.9).
const CELULA_W = 56;
const CELULA_H = 72;
const BLOCO_W = 48;      // 4px de vão: fills adjacentes nunca se colam
const ALTURA_MAX = 64;
const ROTULO_W = 180;

const CSS = `
/* Hachura de 45°: "houve retrabalho aqui". Mesma primitiva do painel de
   validação, para o vocabulário do produto não ter dois jeitos de dizer isso. */
.mtz-hachura {
  background-image: repeating-linear-gradient(45deg,
    hsl(var(--card)) 0 1px, transparent 1px 4px);
}
/* O cursor da célula corrente. O motor não emite "em andamento" — isto é
   inferência da tela, e por isso ela se move: forma parada seria indistinguível
   de uma etapa que terminou. */
@keyframes mtz-varrer {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(${BLOCO_W}px); }
}
.mtz-cursor {
  position: absolute; bottom: 0; left: 0; width: 6px; height: 100%;
  background: hsl(var(--primary));
  animation: mtz-varrer 1.4s cubic-bezier(.4,0,.6,1) infinite;
}
.mtz-cursor::after {
  content: ''; position: absolute; inset: 0;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='90' height='90'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/></filter><rect width='90' height='90' filter='url(%23n)'/></svg>");
  background-size: 90px 90px; opacity: .2; mix-blend-mode: overlay;
}
/* ⚠️ A guarda de movimento reduzido do index.css cobre só as classes
   utilitárias de lá. Todo @keyframes novo TEM de repetir a guarda. Aqui o
   cursor some e sobra o cronômetro — que é o dado; o resto era a embalagem. */
@media (prefers-reduced-motion: reduce) {
  .mtz-cursor { animation: none; opacity: .55; width: 100%; }
}
.mtz-col-rotulo {
  writing-mode: vertical-rl; transform: rotate(180deg);
  letter-spacing: .08em; text-transform: uppercase;
}
`;

/** A altura é o custo. Piso de 2px: uma etapa de custo zero EXISTE, e sumir com
 *  ela seria confundi-la com "não se aplica". */
export function alturaDaCelula(custo: number, maior: number): number {
  if (!maior || maior <= 0) return 2;
  return 2 + Math.round(ALTURA_MAX * Math.min(1, Math.max(0, custo / maior)));
}

type Estado =
  | 'nao_se_aplica' | 'pendente' | 'rodando' | 'ok'
  | 'retentado' | 'falhou' | 'pulado' | 'cancelada';

export function estadoDaCelula(
  etapa: string, pg: PaginaDaMatriz, celula: CelulaDaMatriz | undefined,
  corrente: CelulaCorrente | null, ordem: string[],
): Estado {
  if (!pg.aplicaveis.includes(etapa)) return 'nao_se_aplica';
  if (celula) {
    switch (celula.status) {
      case 'FAILED': return 'falhou';
      case 'SKIPPED': return 'pulado';
      // FALLBACK passou — num modelo diferente do configurado. Desenha como OK;
      // a distinção vive no popover, que é onde o modelo aparece.
      case 'RETRIED': return 'retentado';
      default: return (celula.tentativas ?? 1) > 1 ? 'retentado' : 'ok';
    }
  }
  // Sem chave. A página morreu antes de chegar aqui?
  if (pg.bloqueada) {
    const corte = pg.bloqueada_em ? ordem.indexOf(pg.bloqueada_em) : -1;
    if (corte >= 0 && ordem.indexOf(etapa) > corte) return 'cancelada';
    return 'cancelada';
  }
  if (corrente && corrente.chave === `${etapa}_p${pg.page_number}`) return 'rodando';
  return 'pendente';
}

const ROTULO_ACESSIVEL: Record<Estado, string> = {
  nao_se_aplica: 'não se aplica a esta página',
  pendente: 'pendente',
  rodando: 'em andamento',
  ok: 'concluído',
  retentado: 'concluído com retentativa',
  falhou: 'falhou',
  pulado: 'pulado',
  cancelada: 'cancelada: a página foi bloqueada antes',
};

function moeda(v: number): string {
  // Quatro casas, não duas: as células vão de US$ 0,0026 a US$ 0,4556 e duas
  // casas apagariam metade da matriz.
  return `US$ ${v.toFixed(4).replace('.', ',')}`;
}

function duracao(ms: number): string {
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}min ${String(s % 60).padStart(2, '0')}s`;
}

/** O motivo ESPECÍFICO de uma coluna não se aplicar. Um genérico
 *  ("não se aplica") deixaria o operador achando que é defeito. */
function porQueNaoSeAplica(etapa: string, pg: PaginaDaMatriz): string {
  if (etapa === 'judge' && pg.papel === 'LP')
    return 'A LP não passa pelo juiz: ela é JSON de slots, não prosa — o roteamento dela é determinístico.';
  if (etapa === 'screenshot')
    return pg.papel !== 'SOLUTION'
      ? 'Print do canal oficial só roda em página de SOLUÇÃO.'
      : 'A flag `official_screenshots` está desligada neste motor.';
  if (etapa === 'widget') {
    if (pg.papel !== 'SOLUTION') return 'Widget interativo só roda em página de SOLUÇÃO.';
    if (pg.engajamento === 'dado_unico')
      return 'O engajamento desta página é `dado_unico` — o motor não gera widget nesse arquétipo.';
    return 'A flag `widgets_enabled` está desligada neste motor.';
  }
  if (etapa === 'image_gen') return 'Esta página não pede imagem destacada.';
  if (etapa === 'publish') return 'Este run não publica.';
  return 'Esta etapa não se aplica a esta página.';
}

/** As 4 etapas existenciais: falhar nelas mata a página. `seo` FAILED, por
 *  exemplo, NÃO bloqueia — e a tela precisa dizer a diferença. */
const EXISTENCIAIS = new Set(['research', 'write', 'judge', 'content_gate']);

const Celula: React.FC<{
  etapa: string; pg: PaginaDaMatriz; m: MatrizDoRun; corrente: CelulaCorrente | null;
  ordem: string[]; paga: boolean;
}> = ({ etapa, pg, m, corrente, ordem, paga }) => {
  const chave = `${etapa}_p${pg.page_number}`;
  const celula = m.celulas[chave];
  const estado = estadoDaCelula(etapa, pg, celula, corrente, ordem);
  const altura = celula ? alturaDaCelula(celula.custo_usd, m.custo_maior_celula) : 2;
  const rotulo = `${etapa}, página ${pg.page_number}: ${ROTULO_ACESSIVEL[estado]}`
    + (estado === 'rodando' && corrente ? ` há ${corrente.segundos} segundos` : '');

  const corpo = (() => {
    switch (estado) {
      case 'nao_se_aplica':
        // Um ponto de 1px NA BASE, junto com as outras células: erguido ao meio
        // da célula ele viraria uma quarta linha flutuante na grade.
        return <span className="absolute bottom-0 left-1/2 h-px w-px -translate-x-1/2 bg-muted-foreground/40" />;
      case 'pendente':
        return (
          <span className="absolute bottom-0 left-1/2 h-px -translate-x-1/2"
                style={{ width: BLOCO_W, backgroundImage:
                  'repeating-linear-gradient(90deg, hsl(var(--muted-foreground)/.45) 0 2px, transparent 2px 4px)' }} />
        );
      case 'rodando':
        return (
          <>
            <span className="absolute bottom-0 left-1/2 h-px -translate-x-1/2 bg-foreground/50" style={{ width: BLOCO_W }} />
            <span className="absolute bottom-0 left-1/2 -translate-x-1/2 overflow-hidden"
                  style={{ width: BLOCO_W, height: 10 }}>
              <span className="mtz-cursor" />
            </span>
          </>
        );
      case 'ok':
      case 'retentado':
        return (
          <span className={cn('absolute bottom-0 left-1/2 -translate-x-1/2 bg-foreground/80',
                              estado === 'retentado' && 'mtz-hachura')}
                style={{ width: BLOCO_W, height: altura }} />
        );
      case 'pulado':
        return (
          <span className="absolute bottom-0 left-1/2 -translate-x-1/2 border border-muted-foreground/50"
                style={{ width: BLOCO_W, height: Math.max(altura, 8) }} />
        );
      case 'falhou':
        return (
          <span className="absolute bottom-0 left-1/2 -translate-x-1/2 border border-destructive"
                style={{ width: BLOCO_W, height: Math.max(altura, 10) }}>
            <svg className="h-full w-full" preserveAspectRatio="none" viewBox="0 0 10 10" aria-hidden>
              <line x1="0" y1="10" x2="10" y2="0" stroke="hsl(var(--destructive))" strokeWidth="1"
                    vectorEffect="non-scaling-stroke" />
            </svg>
          </span>
        );
      case 'cancelada':
        return (
          <span className="mtz-hachura absolute bottom-0 left-1/2 -translate-x-1/2 border border-muted-foreground/30 opacity-40"
                style={{ width: BLOCO_W, height: 8 }} />
        );
    }
  })();

  // O glifo é o canal REDUNDANTE à cor, e só onde a geometria sozinha deixa
  // dúvida. Um `◆` em cada célula OK poria 40 losangos numa grade de 55 — é o
  // "número em cada ponto" que a leitura de relance perde.
  const glifo = estado === 'falhou' ? '×'
    : estado === 'pulado' ? '⌀'
    : estado === 'nao_se_aplica' ? '·'
    : estado === 'retentado' ? `×${celula?.tentativas ?? 2}`
    : etapa === 'screenshot' && celula ? `◆${pg.prints}`
    // O cronômetro fica NA CÉLULA, não só no cabeçalho. Ele existe para que os
    // três minutos que a pesquisa da primeira página leva não sejam
    // indistinguíveis de uma tela travada — e obrigar o olho a sair da matriz
    // para conferir isso desfaz o propósito.
    : estado === 'rodando' && corrente
      ? `${Math.floor(corrente.segundos / 60)}:${String(corrente.segundos % 60).padStart(2, '0')}`
    : null;

  // A que altura o bloco desta célula termina — é aí que o glifo se apoia.
  const alturaDoGlifo =
    estado === 'falhou' ? Math.max(altura, 10)
    : estado === 'pulado' ? Math.max(altura, 8)
    : estado === 'cancelada' ? 8
    : estado === 'nao_se_aplica' ? 0
    : estado === 'rodando' ? 12       // logo acima do cursor
    : altura;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={rotulo}
          className={cn(
            'relative shrink-0 outline-none transition-opacity',
            'focus-visible:ring-1 focus-visible:ring-ring',
            estado === 'nao_se_aplica' ? 'cursor-default' : 'cursor-pointer hover:opacity-70',
          )}
          style={{ width: CELULA_W, height: CELULA_H }}
        >
          {corpo}
          {/* O glifo fica ancorado LOGO ACIMA do bloco que ele descreve. Preso
              no topo da célula, ele flutuaria a até 70px do próprio bloco e
              viraria ruído solto na grade em vez de anotação. */}
          {glifo && (
            <span className={cn(
              'tabular absolute left-1/2 -translate-x-1/2 text-[9px] leading-none',
              estado === 'falhou' ? 'text-destructive'
                : estado === 'rodando' ? 'text-foreground' : 'text-muted-foreground',
            )} style={{ bottom: alturaDoGlifo + 3 }}>{glifo}</span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 rounded-lg p-4 text-sm">
        <div className="kicker mb-1">
          {chave} · página {pg.page_number} · {pg.papel}
        </div>
        <div className="mb-3 truncate font-display text-sm font-bold" title={pg.slug}>{pg.slug}</div>

        <dl className="space-y-1.5">
          <div className="flex gap-3">
            <dt className="w-20 shrink-0 text-xs text-muted-foreground">estado</dt>
            <dd className="text-xs">
              {ROTULO_ACESSIVEL[estado].toUpperCase()}
              {celula?.status === 'FALLBACK' && ' — num modelo de reserva'}
            </dd>
          </div>

          {estado === 'nao_se_aplica' && (
            <p className="pt-1 text-xs leading-relaxed text-muted-foreground">
              {porQueNaoSeAplica(etapa, pg)}
            </p>
          )}

          {/* Coluna de custo zero por construção: as linhas de dinheiro, modelo e
              latência simplesmente NÃO aparecem. Escrever "US$ 0,00" sugeriria
              medição onde nunca houve. */}
          {celula && paga && (
            <>
              <div className="flex gap-3">
                <dt className="w-20 shrink-0 text-xs text-muted-foreground">custo</dt>
                <dd className="tabular text-xs">
                  {moeda(celula.custo_usd)}
                  {(celula.tentativas ?? 1) > 1 && (
                    <span className="text-muted-foreground">
                      {' '}({moeda(celula.custo_usd / (celula.tentativas || 1))} por tentativa)
                    </span>
                  )}
                </dd>
              </div>
              {celula.modelo && (
                <div className="flex gap-3">
                  <dt className="w-20 shrink-0 text-xs text-muted-foreground">modelo</dt>
                  <dd className="text-xs">{celula.modelo}</dd>
                </div>
              )}
              {celula.latencia_ms > 0 && (
                <div className="flex gap-3">
                  <dt className="w-20 shrink-0 text-xs text-muted-foreground">latência</dt>
                  <dd className="tabular text-xs">{duracao(celula.latencia_ms)}</dd>
                </div>
              )}
            </>
          )}

          {etapa === 'screenshot' && celula && (
            <div className="flex gap-3">
              <dt className="w-20 shrink-0 text-xs text-muted-foreground">prints</dt>
              <dd className="tabular text-xs">
                {pg.prints}
                {pg.prints === 0 && (
                  <span className="text-muted-foreground"> — a etapa passou sem capturar nada</span>
                )}
              </dd>
            </div>
          )}
        </dl>

        {!!celula?.issues.length && (
          <div className="mt-3 space-y-2 border-t border-border pt-3">
            {celula.issues.map((i, k) => (
              <div key={k}>
                <div className="kicker text-destructive">{i.code}</div>
                <p className="text-xs leading-relaxed text-muted-foreground">{i.message}</p>
              </div>
            ))}
          </div>
        )}

        <p className="mt-3 border-t border-border pt-3 text-xs leading-relaxed text-muted-foreground">
          {EXISTENCIAIS.has(etapa)
            ? 'Esta etapa é EXISTENCIAL: se ela falhar, a página não é construída nem publicada.'
            : 'Esta etapa NÃO bloqueia: a página publica mesmo se ela falhar.'}
        </p>
      </PopoverContent>
    </Popover>
  );
};

export const Matriz: React.FC<{
  m: MatrizDoRun; corrente: CelulaCorrente | null;
}> = ({ m, corrente }) => {
  const ordem = m.colunas.map((c) => c.chave);
  const pagas = new Map(m.colunas.map((c) => [c.chave, c.paga]));

  return (
    <div className="reveal">
      <style>{CSS}</style>

      {/* Com 11 colunas o container ganha rolagem horizontal em vez de virar
          lista: a FORMA da grade é o dado, e uma lista a destruiria. */}
      <div className="overflow-x-auto">
        <div className="min-w-max">
          {/* Cabeçalho: rótulos verticais. Nomes inteiros em 34px só cabem
              girados — e abreviar apagaria a diferença entre "prompt img" e
              "imagem", que são etapas distintas e de custos distintos. */}
          <div className="flex items-end gap-0" style={{ paddingLeft: ROTULO_W }}>
            {m.colunas.map((c) => (
              <div key={c.chave} className="shrink-0" style={{ width: CELULA_W }}>
                <div className="mtz-col-rotulo mx-auto h-[72px] text-[9px] font-semibold text-muted-foreground">
                  {c.rotulo}
                </div>
              </div>
            ))}
          </div>

          <div className="hairline mt-2" />

          {m.paginas.map((pg) => (
            <div key={pg.page_number}
                 className="flex items-end border-b border-border/40 last:border-b-0">
              <div className="shrink-0 py-3 pr-4" style={{ width: ROTULO_W }}>
                <div className="kicker leading-tight">
                  p{pg.page_number} · {pg.papel}
                </div>
                <div className="truncate text-[11px] text-muted-foreground" title={pg.slug}>
                  {pg.slug}
                </div>
              </div>
              <div className="flex items-end pb-2 pt-3">
                {ordem.map((etapa) => (
                  <Celula key={etapa} etapa={etapa} pg={pg} m={m} corrente={corrente}
                          ordem={ordem} paga={pagas.get(etapa) ?? true} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <p className="mt-4 max-w-[68ch] text-xs leading-relaxed text-muted-foreground">
        A altura de cada bloco é o custo daquela etapa, na escala da mais cara do
        run ({moeda(m.custo_maior_celula)}). As colunas locais — print, build,
        portão e publicar — não custam nada e por isso são um fio.
      </p>
    </div>
  );
};
