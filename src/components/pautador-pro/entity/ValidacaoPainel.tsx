import React from 'react';
import { cn } from '@/lib/utils';
import {
  alvoDeOuro, CORTE_QUADRANTE, ESCOPO_PAUTADOR, ETAPAS_DA_MEDICAO, FAMILIA,
  MOTIVO_AUSENCIA, PERFIL_HUMANO, PESO, QUEM_MEDE, ROTULO_EIXO, ROTULO_FAMILIA,
  FORMATO_PAGINA, VALOR_DO_NIVEL, VEREDITO_PORTAO,
  type EixoEmProgresso, type FormatosDaEntidade, type PerguntaLida,
  type Proveniencia, type ValidacaoResumo,
} from '@/types/pautadorValidacao';

/**
 * A tela onde se decide gastar quinze dias produzindo páginas.
 *
 * Três profundidades, e a ordem visual é a ordem da decisão:
 *
 *     3 segundos    o selo do portão, ou o quadrante — construo?
 *     30 segundos   a resposta que a pessoa encontra — por quê?
 *     3 minutos     as nove barras — auditar eixo a eixo
 *
 * ## Os invariantes, e por que cada um existe
 *
 * **O trilho é o PESO, o preenchimento é o VALOR.** `PRIORES` vai de 0,35 a
 * 0,90: `ignorancia` pesa 2,6x `producao`. Dez linhas de mesma altura mentem
 * sobre o que importa. E o preenchimento nunca é reescalado pelo peso — um
 * eixo no topo da própria escala aparece CHEIO por menor que seja o trilho
 * (`texto_busca` vale 1,00 e pesa 0,35: trilho curto, cheio). Confundir os
 * dois é o erro que a barra existe para evitar.
 *
 * **Cor é proveniência, nunca valor.** Um hue só, para o que foi medido.
 * Julgamento é cinza. `vacuo: disputado` não é vermelho — é uma posição, e
 * quem colore valor está pontuando. A tela não pontua.
 *
 * Consequência aceita de propósito: um card com poucos eixos medidos fica
 * **visualmente lavado**. Isso é a confiança codificada sem indicador
 * separado — quatro barras azuis e cinco cinzas parecem menos firmes que oito
 * azuis, e são. Nada aqui compensa isso com saturação.
 *
 * **Ausente é buraco, nunca zero.** Hachura sobre o trilho inteiro, sem
 * preenchimento. Barra curta sugeriria "baixo", que é uma afirmação.
 *
 * **O portão rompe o layout.** Não é linha destacada: é selo sobre o cartão,
 * e o resto cai de opacidade porque deixou de importar.
 */

// ── proveniência: um hue, um cinza, uma textura ────────────────────────────
// Emphasis (1 hue + cinza), não paleta categórica. Validado: ΔE 16,7 (protan)
// e 17,5 (normal) entre os dois, contra piso 15. A margem é fina, então a
// distinção é SEMPRE dupla — cor e glifo —, nunca cor sozinha.
const TINTA: Record<Proveniencia, { fill: string; glifo: string; nome: string }> = {
  medido: { fill: 'var(--val-medido)', glifo: '◆', nome: 'medido pela API' },
  julgado: { fill: 'var(--val-julgado)', glifo: '◇', nome: 'julgado por LLM' },
  ausente: { fill: 'transparent', glifo: '·', nome: 'ausente' },
};

const ESTILO = `
/* OKLCH, e nenhum neutro puro: tudo puxa para o azul da marca (#0D47A1).
   Cinza sem tinta ao lado de uma cor de marca lê como sujeira. */
.val {
  --val-medido:   oklch(.55 .152 253);
  --val-julgado:  oklch(.55 .012 253);
  --val-trilho:   oklch(.55 .012 253 / .16);
  --val-ouro:     oklch(.63 .118 78);
  --val-piso:     oklch(.55 .012 253 / .07);
}
.dark .val {
  --val-medido:   oklch(.74 .132 214);
  --val-julgado:  oklch(.68 .014 253);
  --val-trilho:   oklch(.68 .014 253 / .2);
  --val-ouro:     oklch(.79 .112 82);
  --val-piso:     oklch(.68 .014 253 / .08);
}
.val-hachura {
  background-image: repeating-linear-gradient(45deg,
    var(--val-julgado) 0 1px, transparent 1px 5px);
  opacity:.4;
}

/* Um momento só, e ele conta o que acontece: as famílias somam, o card cai.
   Saída exponencial, sem bounce: overshoot em tela de decisão vira brinquedo. */
.val-barra-x { animation: val-x .5s cubic-bezier(.16,1,.3,1) both; }
.val-barra-y { animation: val-y .5s cubic-bezier(.16,1,.3,1) both; }
.val-guia    { animation: val-surge .28s linear .44s both; }
.val-ponto   { animation: val-pousa .34s cubic-bezier(.16,1,.3,1) .5s both; }
@keyframes val-x { from { transform:scaleX(0); transform-origin:left } to { transform:none } }
@keyframes val-y { from { transform:scaleY(0) } to { transform:none } }
@keyframes val-surge { from { opacity:0 } to { opacity:1 } }
@keyframes val-pousa { from { opacity:0; transform:scale(.2) } to { opacity:1; transform:none } }
@media (prefers-reduced-motion: reduce) {
  .val-barra-x, .val-barra-y, .val-guia, .val-ponto { animation:none }
}
`;

// ── o quadrante ────────────────────────────────────────────────────────────
//
// As duas coordenadas do ponto são `familia("demanda_humana")` e
// `familia("economia")`. Aqui elas VIRAM os eixos: uma barra pela base, outra
// pela lateral, e o ponto no encontro. Ninguém colocou o ponto no quadrante —
// os dois números o produziram.
//
// HIERARQUIA POR SUPRESSÃO. Três dos quatro quadrantes são lugares onde este
// card NÃO está, e a tela não precisa explicar os quatro toda vez: ela precisa
// dizer onde ESTE caiu. Os não ocupados recuam a quase nada.
//
// Alvo de varredura, não pôster: 268px de altura, para a citação e as barras
// caberem no mesmo campo de visão — que é o que faz a leitura de 30s funcionar.

const QUADRANTES = [
  { x: 0, y: 0, nome: 'audiência pobre' },
  { x: 1, y: 0, nome: 'alvo' },
  { x: 0, y: 1, nome: 'descartar' },
  { x: 1, y: 1, nome: 'mercado rico' },
] as const;

const Quadrante: React.FC<{
  h: number; ec: number; perfil?: string | null; ouro?: boolean;
  familiaAtiva?: string | null;
}> = ({ h, ec, ouro, familiaAtiva }) => {
  const W = 340, H = 268;
  const L = 30, B = 30, T = 18, R = 18;
  const px = L + ec * (W - L - R);
  const py = H - B - h * (H - B - T);
  const cx = L + CORTE_QUADRANTE * (W - L - R);
  const cy = H - B - CORTE_QUADRANTE * (H - B - T);
  const acento = ouro ? 'var(--val-ouro)' : 'var(--val-medido)';
  const ocupado = { x: ec >= CORTE_QUADRANTE, y: h < CORTE_QUADRANTE };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img"
         aria-label={`demanda humana ${h.toFixed(2)} por economia ${ec.toFixed(2)}`}>
      {/* SUPRESSÃO: o campo é um piso quase invisível. Só o quadrante ocupado
          ganha superfície — os outros três são lugares onde este card não está,
          e a tela não precisa explicá-los toda vez. */}
      <rect x={L} y={T} width={W - L - R} height={H - B - T} rx="2" fill="var(--val-piso)" />
      <rect x={ocupado.x ? cx : L} y={ocupado.y ? cy : T}
            width={ocupado.x ? W - R - cx : cx - L}
            height={ocupado.y ? H - B - cy : cy - T}
            rx="2" fill={acento} opacity=".07" />
      <line x1={cx} y1={T} x2={cx} y2={H - B} stroke="var(--val-trilho)" strokeWidth="1" />
      <line x1={L} y1={cy} x2={W - R} y2={cy} stroke="var(--val-trilho)" strokeWidth="1" />

      {QUADRANTES.map((q) => {
        const aqui = (ec >= CORTE_QUADRANTE) === !!q.x && (h >= CORTE_QUADRANTE) === !q.y;
        const tx = q.x ? (cx + W - R) / 2 : (L + cx) / 2;
        const ty = q.y ? (cy + H - B) / 2 : (T + cy) / 2;
        return (
          <text key={q.nome} x={tx} y={ty} textAnchor="middle"
                className={cn('tracking-[.16em] uppercase',
                  aqui ? 'text-[9px] font-semibold' : 'text-[7.5px] fill-muted-foreground/25')}
                fill={aqui ? acento : undefined}>
            {q.nome}
          </text>
        );
      })}

      <g style={{ stroke: acento }} className="val-guia">
        <line x1={px} y1={H - B} x2={px} y2={py} strokeWidth="1" strokeDasharray="1 3" opacity=".4" />
        <line x1={L} y1={py} x2={px} y2={py} strokeWidth="1" strokeDasharray="1 3" opacity=".4" />
      </g>

      {/* ECONOMIA: a barra É o eixo. O número mora na ponta dela. */}
      <g opacity={familiaAtiva && familiaAtiva !== 'economia' ? 0.3 : 1}
         className="transition-opacity duration-200">
        <rect x={L} y={H - B + 7} width={W - L - R} height="4" rx="2" fill="var(--val-trilho)" />
        <rect x={L} y={H - B + 7} height="4" rx="2" fill={acento}
              className="val-barra-x" style={{ width: (W - L - R) * ec }} />
        <text x={L} y={H - 6} className="fill-muted-foreground/60 text-[7px] uppercase tracking-[.18em]">economia</text>
        <text x={px} y={H - 6} textAnchor={ec > .86 ? 'end' : 'middle'} fill={acento}
              className="text-[10px] font-semibold tabular">{ec.toFixed(2)}</text>
      </g>

      {/* DEMANDA HUMANA */}
      <g opacity={familiaAtiva && familiaAtiva !== 'demanda_humana' ? 0.3 : 1}
         className="transition-opacity duration-200">
        <rect x={L - 11} y={T} width="4" height={H - B - T} rx="2" fill="var(--val-trilho)" />
        <rect x={L - 11} y={H - B} width="4" rx="2" fill={acento}
              className="val-barra-y" style={{ height: (H - B - T) * h, transformOrigin: `0px ${H - B}px` }} />
        <text x={L - 15} y={py + 3.5} textAnchor="end" fill={acento}
              className="text-[10px] font-semibold tabular">{h.toFixed(2)}</text>
        <text x={L - 15} y={T} textAnchor="end" transform={`rotate(-90 ${L - 15} ${T})`}
              className="fill-muted-foreground/60 text-[7px] uppercase tracking-[.18em]">demanda</text>
      </g>

      <g className="val-ponto">
        <title>{`demanda humana ${h.toFixed(2)} por economia ${ec.toFixed(2)}`}</title>
        <circle cx={px} cy={py} r="13" fill={acento} opacity=".1" />
        {ouro && <circle cx={px} cy={py} r="8" fill="none" stroke={acento} strokeWidth="1" opacity=".45" />}
        <circle cx={px} cy={py} r="4" fill={acento} stroke="var(--background)" strokeWidth="2" />
      </g>
    </svg>
  );
};

// ── medindo: os eixos caindo um a um, lidos do banco ──────────────────────
//
// Não é barra que anda sozinha. A gravação do orquestrador é incremental, e o
// hook sonda `GET /axes` a cada 1,5s enquanto o POST não volta. O que aparece
// aqui já está gravado — é a arquitetura ficando visível.

const EmMedicao: React.FC<{ progresso?: EixoEmProgresso[] }> = ({ progresso }) => {
  const caidos = new Set((progresso ?? []).map((e) => e.eixo));
  return (
    <div className="space-y-3 py-1">
      <p className="text-[10px] text-muted-foreground">
        Medindo — {caidos.size} de {ESCOPO_PAUTADOR.length} eixos gravados.
      </p>
      <div className="space-y-2">
        {ETAPAS_DA_MEDICAO.map((etapa) => {
          const prontos = etapa.eixos.filter((e) => caidos.has(e)).length;
          const completa = prontos === etapa.eixos.length;
          return (
            <div key={etapa.rotulo} className="space-y-1">
              <div className="flex items-baseline gap-2">
                <span className={cn('text-[9px] w-3', completa ? 'text-[color:var(--val-medido)]' : 'text-muted-foreground/40')}>
                  {completa ? '◆' : '·'}
                </span>
                <span className={cn('text-[10px]', completa ? 'text-foreground' : 'text-muted-foreground')}>
                  {etapa.rotulo}
                </span>
              </div>
              <div className="flex gap-1 pl-5">
                {etapa.eixos.map((e) => (
                  <div key={e} title={ROTULO_EIXO[e]}
                       className={cn('h-[3px] flex-1 rounded-full transition-colors duration-200',
                         caidos.has(e) ? 'bg-[color:var(--val-medido)]' : 'bg-muted')} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ── o esgotamento: a MEDIÇÃO na frente, o rótulo atrás ─────────────────────
//
// Aqui ficava o selo — ⛔ NÃO CONSTRUA — em 14px bold, e o número em lugar
// nenhum. Inverteu, e a medição mandou.
//
// Rodada real, 4 entidades, 3 passadas cada:
//
//     Registrato   shares 0,75 · 1,00 · 1,00   rótulos: limítrofe, portão, portão
//     FGTS         shares 0,50 · 0,25 · 0,50   limítrofe, sem portão, limítrofe
//     Cesantías    shares 0,25 · 0,50 · 0,50   sem portão, limítrofe, limítrofe
//
// A medição é estável — as três leituras ficam dentro de UMA pergunta de
// diferença em todos os casos. O rótulo é que pula, e a razão é aritmética: com
// 4 perguntas do PAA o share anda de 0,25 em 0,25, e os limiares (0,5 e 1,0)
// caem dentro dessa banda. Metade dos movimentos de uma única pergunta troca o
// veredito sem que nada tenha sido medido de outro jeito.
//
// Então o que a tela mostra é `3 de 4 se esgotam` com as três leituras
// marcadas, e o rótulo vira chip pequeno. Um número com dispersão à vista é
// honesto; um selo em caixa alta sobre uma fronteira que a aritmética não
// sustenta é encenação.

const Esgotamento: React.FC<{
  portao: ValidacaoResumo['portao'];
  veredito: string;
  selo: { simbolo: string; titulo: string; corpo: string; rodape: string };
}> = ({ portao, veredito, selo }) => {
  const shares = portao?.shares_por_passada ?? [];
  const n = portao?.n_perguntas ?? 0;
  const share = portao?.share_dado_unico ?? 0;
  const esgotam = Math.round(share * n);
  const min = shares.length ? Math.min(...shares) : share;
  const max = shares.length ? Math.max(...shares) : share;
  const pct = (v: number) => `${v * 100}%`;

  return (
    <>
      <div className="flex items-baseline justify-between gap-3">
        <p className="font-display text-sm leading-none">
          <strong className="tabular text-base">{esgotam}</strong>
          <span className="text-muted-foreground"> de </span>
          <strong className="tabular text-base">{n}</strong>
          <span className="text-muted-foreground"> perguntas se esgotam</span>
        </p>
        <span className="text-[9px] uppercase tracking-[.12em] text-muted-foreground shrink-0">
          {selo.simbolo} {veredito === 'portao' ? 'portão' : 'limítrofe'}
        </span>
      </div>

      {/* A faixa vai de 0 a 1 e mostra ONDE cada leitura caiu. A banda entre a
          menor e a maior é a incerteza real; os traços em 0,5 e 1,0 são os
          limiares, e vê-los dentro da banda é o argumento inteiro. */}
      {shares.length > 1 && (
        <div className="space-y-1">
          {/* O padding lateral de 5px é do RAIO DA BOLINHA, não decoração: uma
              leitura em 1,00 fica em `left:100%` com `-translate-x-1/2`, e sem a
              folga metade dela vazaria do container e alargaria a rolagem do
              drawer inteiro. A pista vive dentro da folga; os pontos usam a
              largura toda. */}
          <div className="relative h-[14px] px-[5px]">
            <div className="absolute inset-0">
              <div className="absolute inset-x-[5px] top-1/2 h-px -translate-y-1/2 bg-border" />
              {[0.5, 1].map((t) => (
                <div key={t} className="absolute top-[2px] bottom-[2px] w-px bg-border"
                     style={{ left: `calc(5px + ${t} * (100% - 10px))` }} />
              ))}
              <div className="absolute top-1/2 h-[3px] -translate-y-1/2 rounded-full
                              bg-[color:var(--val-julgado)]/30"
                   style={{ left: `calc(5px + ${min} * (100% - 10px))`,
                            width: `calc(${max - min} * (100% - 10px))` }} />
              {shares.map((s, i) => (
                <span key={i}
                      className="absolute top-1/2 h-[7px] w-[7px] -translate-x-1/2 -translate-y-1/2
                                 rounded-full bg-[color:var(--val-julgado)]
                                 ring-1 ring-background"
                      style={{ left: `calc(5px + ${s} * (100% - 10px))` }}
                      title={`leitura ${i + 1}: ${(s * 100).toFixed(0)}%`} />
              ))}
            </div>
          </div>
          <p className="text-[9px] text-muted-foreground tabular">
            {shares.map((s) => `${(s * 100).toFixed(0)}%`).join(' · ')}
            <span className="ml-1.5 tracking-wide">
              {min === max
                ? `— as ${shares.length} leituras concordaram`
                : `— ${shares.length} leituras, variação de ${Math.round((max - min) * n)} pergunta(s)`}
            </span>
          </p>
        </div>
      )}

      <p className="text-[11px] leading-snug">{selo.corpo}</p>
      <p className="text-[9px] text-muted-foreground">{selo.rodape}</p>
    </>
  );
};

// ── a leitura da entidade ──────────────────────────────────────────────────
//
// Uma entidade não tem UMA pergunta. Medido em 6 de 6: `DIRPF` tem uma de data,
// uma condicional e duas de diagnóstico; `Registrato`, que parecia lookup puro,
// tem metade das perguntas ramificando.
//
// É a informação mais rica do card e nenhuma ferramenta de keyword a produz:
// as perguntas vêm do Google, as respostas do modelo, e a forma de cada uma sai
// de contagem. Por isso ela sobe para perto do topo, e por isso as respostas
// ficam abertas em vez de escondidas atrás de um clique.

// A escala tinha cinco níveis e agora tem dois, porque foi isso que ela mediu:
// em dois lotes o nível dominante trocou de `diagnostico` (62,5%) para
// `condicional` (76,2%) só mudando a amostra, e `comparativo` e `sequencial`
// sumiram do segundo. Sempre havia um nível para carimbar quase tudo.
//
// QUANTO uma resposta sustenta continua na tela — pelas CONTAGENS, logo abaixo.
// Elas são o que o modelo de fato observou; os cinco nomes eram interpretação
// por cima delas, e a interpretação não sobreviveu à segunda amostra.
/**
 * ## De diagnóstico para PLANTA DE OBRA
 *
 * Antes esta lista dizia a FORMA de cada resposta — `esgota em segundos` /
 * `há o que ler`. Diagnóstico correto e resposta errada para quem vai executar:
 * ela contava o que a resposta É e deixava a pessoa traduzir sozinha para o que
 * fazer.
 *
 * Agora lidera o FORMATO, e isso não troca uma medição por outra — troca a
 * LINGUAGEM da mesma medição. O invariante garante:
 *
 *     formato === 'artigo'  ⟺  engajamento === 'sustenta'
 *
 * As duas leem `ramos >= 2 OU sobra decisão`. Então a lista continua mostrando
 * exatamente o que mostrava, na linguagem da ação em vez da do sintoma. Nenhuma
 * informação a mais foi afirmada; a mesma foi dita de um jeito executável.
 *
 * O funil tem cinco páginas e cada uma responde a sua pergunta — então esta
 * lista É a lista de páginas a construir, e o cabeçalho é a contagem que decide
 * se cabe no mês.
 *
 * A CONTAGEM CRUA fica, embaixo, como evidência: é ela que sobreviveu ao colapso
 * da escala, e o formato é derivação dela. Quem duvidar do envelope confere os
 * números que o produziram, na mesma linha.
 */
const Perguntas: React.FC<{
  ficha?: ValidacaoResumo['ficha'];
  formatos?: FormatosDaEntidade | null;
}> = ({ ficha, formatos }) => {
  const perguntas = ficha?.perguntas ?? [];
  if (!perguntas.length) return null;

  const envelope = (q: PerguntaLida) =>
    FORMATO_PAGINA[q.formato ?? ''] ??
    // Card medido antes do roteador existir: deriva do invariante em vez de
    // mostrar vazio. É a mesma condição, e por isso é honesto derivar.
    FORMATO_PAGINA[q.engajamento === 'dado_unico' ? 'nao_produzir' : 'artigo'];

  const paginas = perguntas.filter((q) => envelope(q).curto !== 'fora').length;
  const ferramentas = perguntas.filter((q) => envelope(q).curto === 'ferramenta').length;

  return (
    <section className="space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-[9px] uppercase tracking-[.14em] text-muted-foreground">
          o que perguntam, e o que a resposta exige
        </p>
        {/* A CONTAGEM DE PÁGINAS SAIU DAQUI, e é o ponto todo.
            "4 perguntas → 4 páginas" é prescrição de ESTRUTURA, e estrutura é
            trabalho do arquiteto de funil na etapa 4 — que tem protocolo
            próprio de 5 páginas TOFU→BOFU. Esta camada lê a PERGUNTA; quem
            desenha o funil é ele. */}
        <p className="text-[9px] text-muted-foreground tabular">
          {perguntas.length} perguntas · <strong className="text-foreground">{paginas}</strong>
          {' '}sustenta{paginas === 1 ? '' : 'm'} leitura
          {ferramentas > 0 && `, ${ferramentas} pede ferramenta`}
        </p>
      </div>

      {/* A PLANTA em uma linha: um bloco por pergunta, na ordem. Bloco cheio é
          artigo, hachurado é ferramenta, vazado é fora. Lê-se de relance quanto
          do PAA vira página. */}
      <div className="flex gap-[3px]">
        {perguntas.map((q, i) => {
          const e = envelope(q);
          return (
            <div key={i}
                 className={cn('h-[3px] flex-1 rounded-full',
                   e.curto === 'fora' ? 'bg-muted-foreground/25'
                     : e.curto === 'ferramenta' ? 'bg-[color:var(--val-medido)]'
                     : 'bg-[color:var(--val-medido)]/45')}
                 title={`${e.titulo} — ${q.pergunta}`} />
          );
        })}
      </div>

      <ul className="space-y-3">
        {perguntas.map((q, i) => {
          const e = envelope(q);
          const fora = e.curto === 'fora';
          const ferramenta = e.curto === 'ferramenta';
          return (
            <li key={i} className="space-y-1">
              {/* O rótulo técnico com a régua de 1px à direita: o Design System
                  pede linha fina e label em caixa alta com tracking largo, e
                  aqui a linha faz trabalho estrutural (separa entradas) em vez
                  de decorar. */}
              <div className="flex items-center gap-2" title={e.corpo}>
                <span className={cn('text-[8.5px] uppercase tracking-[.14em] shrink-0',
                  fora ? 'text-muted-foreground/60'
                    : ferramenta ? 'text-[color:var(--val-medido)] font-semibold'
                    : 'text-muted-foreground')}>
                  {e.glifo} {e.titulo}
                </span>
                <span className={cn('h-px flex-1',
                  ferramenta ? 'bg-[color:var(--val-medido)]/35' : 'bg-border')} />
              </div>

              <p className={cn('text-[11px] leading-snug font-medium',
                fora && 'text-muted-foreground')}>{q.pergunta}</p>
              <p className={cn('font-serif italic text-[11.5px] leading-snug',
                fora ? 'text-muted-foreground/70' : 'text-foreground/85')}>
                {q.resposta_literal}
              </p>

              {/* A ESPECIFICAÇÃO, quando é ferramenta — e ela sai de graça:
                  `campos_do_widget` é recorte literal da resposta que o modelo
                  escreveu, e já nomeia as entradas. É o que o redator recebe. */}
              {ferramenta && q.campos_do_widget && (
                <p className="text-[9.5px] leading-snug rounded-sm border border-[color:var(--val-medido)]/25
                              bg-[color:var(--val-medido)]/[.06] px-1.5 py-1">
                  <span className="uppercase tracking-[.12em] text-[8px] text-muted-foreground">
                    campos
                  </span>{' '}
                  <span className="text-foreground/90">{q.campos_do_widget}</span>
                </p>
              )}

              <p className="text-[8.5px] text-muted-foreground/70 tracking-wide">
                {q.ramos} ramo{q.ramos > 1 ? 's' : ''} ·{' '}
                {q.condicoes} condição{q.condicoes === 1 ? '' : 'ões'}
                {q.decide_depois && ' · sobra decisão'}
                {fora && q.oficial_fecha_sozinho && ' · o canal oficial resolve sozinho'}
                {fora && !q.oficial_fecha_sozinho && ' · a resposta é igual para todo mundo'}
              </p>
            </li>
          );
        })}
      </ul>
    </section>
  );
};

// ── as barras: trilho = peso, preenchimento = valor ────────────────────────

const PESO_MAX = Math.max(...Object.values(PESO));

const Barra: React.FC<{
  eixo: string; nivel?: string | null; prov: Proveniencia; motivo?: string | null;
  onHover?: (e: string | null) => void; ativo?: boolean;
}> = ({ eixo, nivel, prov, motivo, onHover, ativo }) => {
  const trilho = (PESO[eixo] / PESO_MAX) * 100;
  // NÃO reescalado pelo peso: o topo da escala enche o trilho, curto ou longo.
  const valor = nivel ? (VALOR_DO_NIVEL[eixo]?.[nivel] ?? 0) : 0;
  const tinta = TINTA[prov];
  const legivel = MOTIVO_AUSENCIA[motivo ?? ''] ?? motivo;

  return (
    <div className={cn('flex items-center gap-2 rounded-sm -mx-1 px-1 transition-colors',
                       ativo && 'bg-muted/50')}
         onMouseEnter={() => onHover?.(eixo)} onMouseLeave={() => onHover?.(null)}
         title={`${ROTULO_EIXO[eixo]} · peso ${PESO[eixo]} · ${QUEM_MEDE[eixo]}`}>
      <span className="w-[92px] shrink-0 text-[9px] text-muted-foreground truncate text-right whitespace-nowrap">
        {ROTULO_EIXO[eixo]}
      </span>
      {/* Largura fixa e não `flex-1`: com trilho curto por peso, uma pista
          elástica abriria um vão morto entre o fim da barra e o seu rótulo. */}
      <div className="w-[104px] shrink-0 h-[9px] relative">
        <div className="h-full rounded-[2px] overflow-hidden"
             style={{ width: `${trilho}%`, background: 'var(--val-trilho)' }}>
          {prov === 'ausente'
            ? <div className="val-hachura h-full w-full" />
            : <div className="h-full rounded-r-[2px] transition-[width] duration-200"
                   style={{ width: `${valor * 100}%`, background: tinta.fill }} />}
        </div>
      </div>
      <span className={cn('w-3 shrink-0 text-[9px] leading-none text-center',
        prov === 'medido' ? 'text-[color:var(--val-medido)]' : 'text-muted-foreground/70')}
        title={tinta.nome}>{tinta.glifo}</span>
      <span className={cn('flex-1 min-w-0 text-[9px] truncate',
        nivel ? 'text-foreground' : 'text-muted-foreground/60 italic')}
        title={nivel ? undefined : legivel ?? undefined}>
        {nivel ?? legivel ?? '—'}
      </span>
    </div>
  );
};

// ── o painel ───────────────────────────────────────────────────────────────

const ESTILO_OURO = `
.val-ouro-txt { color: var(--val-ouro-tinta); }
/* Um FIO de borda e o ícone. Ouro é o estado mais raro da tela — quando ele
   cobre tudo, para de ser especial e vira tema. A raridade comunica, não a
   área. O brilho é um INSTANTE na montagem, nunca um degradê permanente:
   movimento contínuo em tela de decisão cansa em dois dias. */
.val-evento { box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--val-ouro-tinta) 30%, transparent); }
.val-evento::before {
  content:''; position:absolute; inset:0; border-radius:inherit; pointer-events:none;
  background: linear-gradient(105deg, transparent 38%,
    color-mix(in srgb, var(--val-ouro-tinta) 20%, transparent) 50%, transparent 62%);
  animation: val-brilho .9s ease-out .15s both;
}
@keyframes val-brilho { from { transform:translateX(-120%);} to { transform:translateX(120%); opacity:0; } }
@media (prefers-reduced-motion: reduce) { .val-evento::before { animation:none; display:none; } }
`;

export const ValidacaoPainel: React.FC<{
  validacao?: ValidacaoResumo | null;
  custoEstimadoUsd?: number;
  medindo?: boolean;
  progresso?: EixoEmProgresso[];
  onMedir?: () => void;
}> = ({ validacao, custoEstimadoUsd = 0.0092, medindo, progresso, onMedir }) => {
  // Passar o mouse num eixo acende a família que ele alimenta. É a aritmética
  // respondendo ao toque: dá para ver `ignorancia` empurrando a demanda humana.
  const [eixoAtivo, setEixoAtivo] = React.useState<string | null>(null);
  const familiaAtiva = eixoAtivo ? FAMILIA[eixoAtivo] : null;
  // A validação NUNCA roda ao abrir. Card sem medição mostra o convite com o
  // preço no botão — medir custa dinheiro e quem manda é quem paga.
  if (medindo) {
    return (
      <div className="val">
        <style>{ESTILO + ESTILO_OURO}</style>
        <EmMedicao progresso={progresso} />
      </div>
    );
  }

  if (!validacao) {
    return (
      <div className="val space-y-3 py-6 text-center">
        <style>{ESTILO}</style>
        <p className="text-[11px] text-muted-foreground max-w-[260px] mx-auto leading-snug">
          Este card ainda não foi medido. A validação troca os palpites do
          descobridor por medição de dado público.
        </p>
        <button type="button" disabled={medindo || !onMedir} onClick={onMedir}
          className={cn('text-[10px] rounded border border-info/30 bg-info/10 text-info',
            'px-3 py-1.5 font-medium hover:bg-info/20 transition-colors',
            'disabled:opacity-40 disabled:cursor-not-allowed')}>
          {medindo ? 'medindo…' : `Medir agora — US$ ${custoEstimadoUsd.toFixed(4)}`}
        </button>
        <p className="text-[9px] text-muted-foreground/70">
          Mais barato pela coluna inteira: o lote paga a base uma vez, não uma por card.
        </p>
      </div>
    );
  }

  const eixos = validacao.eixos ?? {};
  const veredito = validacao.portao?.veredito ?? 'sem_portao';
  const rompe = veredito === 'portao' || veredito === 'limitrofe';
  const selo = VEREDITO_PORTAO[veredito];
  const perfil = PERFIL_HUMANO[validacao.perfil ?? 'indefinido'] ?? PERFIL_HUMANO.indefinido;
  const h = validacao.demanda_humana, ec = validacao.economia;
  const medidos = Object.values(eixos).filter((e) => e.proveniencia === 'medido').length;
  const ouro = alvoDeOuro(validacao);

  return (
    // `break-words` é o par necessário do `overflow-x-hidden` do drawer. Sem
    // ele, um termo longo (uma URL numa resposta, o nome de uma norma) seria
    // CLIPADO em silêncio em vez de rolar — trocaria um defeito visível por um
    // invisível, que é pior. Com ele o texto quebra e nada some.
    <div className="val space-y-5 break-words">
      <style>{ESTILO + ESTILO_OURO}</style>

      {/* ── 3 SEGUNDOS ──────────────────────────────────────────────── */}
      {rompe ? (
        <div className={cn('rounded-lg border-2 p-3 space-y-2',
          veredito === 'portao'
            ? 'border-destructive/45 bg-destructive/[.07]'
            : 'border-warning/45 bg-warning/[.07]')}>
          <Esgotamento portao={validacao.portao} veredito={veredito} selo={selo} />
        </div>
      ) : (
        <div className={cn('space-y-1.5', ouro.e && 'val-evento relative overflow-hidden rounded-lg p-2.5')}>
          {/* O OURO É UM EVENTO. Ele acontece uma vez a cada muitos cards, e
              quando acontece é a coisa mais importante que a tela pode dizer.
              Não vira mais um ícone na fileira: o quadrante inteiro muda de
              acento, a célula ALVO acende, e o título troca — `alvo` continua
              sendo o nome do quadrante, e o ouro é um estado ACIMA dele. */}
          {/* Escala com contraste real: 19px contra 11px é razão 1,7. Um
              veredito em 12px bold ao lado de um corpo em 11px é escala plana,
              e escala plana lê como formulário, não como resposta. */}
          {ouro.e ? (
            <div className="flex items-center gap-2">
              <span className="text-lg leading-none">🎯</span>
              <h3 className="font-display font-bold text-[19px] leading-none tracking-[-.01em] val-ouro-txt">
                Alvo de ouro
              </h3>
            </div>
          ) : (
            <h3 className="font-display font-bold text-[19px] leading-none tracking-[-.01em]">
              {perfil.titulo}
            </h3>
          )}
          <p className="text-[11px] leading-snug text-muted-foreground max-w-[42ch]">
            {ouro.e ? 'Lê, paga, e a medição fechou inteira.' : perfil.corpo}
          </p>
          {h != null && ec != null
            ? <Quadrante h={h} ec={ec} perfil={validacao.perfil} ouro={ouro.e}
                         familiaAtiva={familiaAtiva} />
            : null}
          <p className={cn('text-[9px] leading-snug tracking-wide',
              ouro.e ? 'val-ouro-txt' : 'text-muted-foreground/70')}>
            {ouro.motivo}
          </p>
        </div>
      )}

      {/* ── 30 SEGUNDOS ─────────────────────────────────────────────── */}
      <Perguntas ficha={validacao.ficha} formatos={validacao.portao?.formatos} />

      {/* ── 3 MINUTOS ───────────────────────────────────────────────── */}
      <div className={cn('space-y-3.5 transition-opacity duration-200', rompe && 'opacity-[.3]')}>
        {(['demanda_humana', 'economia', 'posicao'] as const).map((fam) => (
          <div key={fam} className="space-y-[2px]">
            <p className="text-[8px] uppercase tracking-widest text-muted-foreground/70 pl-[98px]">
              {ROTULO_FAMILIA[fam]}
            </p>
            {(ESCOPO_PAUTADOR as readonly string[])
              .filter((e) => FAMILIA[e] === fam)
              .sort((a, b) => PESO[b] - PESO[a])
              .map((e) => (
                <Barra key={e} eixo={e} nivel={eixos[e]?.nivel} motivo={eixos[e]?.motivo_ausencia}
                       prov={eixos[e]?.proveniencia ?? 'ausente'}
                       onHover={setEixoAtivo} ativo={eixoAtivo === e} />
              ))}
          </div>
        ))}
      </div>

      {/* ── rodapé: texto, e nada aqui ordena ───────────────────────── */}
      <div className="text-[9px] text-muted-foreground/80 space-y-0.5 border-t border-border pt-2">
        {validacao.cabeca_demanda && (
          <p className="truncate" title={`editorial: ${validacao.cabeca_editorial}`}>
            demanda “{validacao.cabeca_demanda}” · editorial “{validacao.cabeca_editorial}”
          </p>
        )}
        <p title="Média geométrica ponderada dos eixos declarados. NÃO ordena o board — metade dos eixos vem de julgamento.">
          índice {validacao.indice ?? '—'} · cobertura{' '}
          {validacao.cobertura != null ? `${Math.round(validacao.cobertura * 100)}%` : '—'} ·{' '}
          {medidos} de {Object.keys(eixos).length} medidos
          {validacao.apto === false && ` · fora da fila (${validacao.motivo})`}
        </p>

        {/* QUANTO CONFIAR NESTE CARD. Não é enfeite de rodapé: a confiabilidade
            do instrumento foi medida (AC1 de Gwet, input fixo: ignorância 0,81 ·
            tensão 0,76 · opacidade e engajamento 0,64) e estes dois números são
            como ela se comporta AQUI. Se despencarem ao longo do tempo, o modelo
            mudou embaixo e ninguém teria como saber sem eles na tela. */}
        {(validacao.portao?.concordancia_por_pergunta != null ||
          validacao.portao?.citacoes_conferidas != null) && (
          <p title="Concordância entre as leituras, e quantas citações do modelo estão mesmo na resposta que ele escreveu.">
            {validacao.portao?.concordancia_por_pergunta != null && (
              <>{Math.round(validacao.portao.concordancia_por_pergunta * 100)}% das
                perguntas iguais nas leituras</>
            )}
            {validacao.portao?.citacoes_conferidas != null && (
              <> · {Math.round(validacao.portao.citacoes_conferidas * 100)}% das{' '}
                {validacao.portao.n_citacoes} citações conferem</>
            )}
            {!!validacao.portao?.stake_sem_prova && (
              <> · {validacao.portao.stake_sem_prova} com stake sem prova</>
            )}
          </p>
        )}
        {validacao.portao?.sinal_paa_ausente && (
          <p className="text-warning/80">{validacao.portao.nota_paa_ausente}</p>
        )}
        {validacao.validado_em && (
          <p>medido em {new Date(validacao.validado_em).toLocaleString('pt-BR')}</p>
        )}
      </div>
    </div>
  );
};
