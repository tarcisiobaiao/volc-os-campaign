/**
 * A RÉGUA DE LEILÃO — onde a forma carrega a decisão.
 *
 * ## O problema que ela resolve, medido
 *
 * Uma lista de checkboxes mostra 23 linhas de tamanho igual. O cluster real do
 * card 73 tem esta distribuição:
 *
 *   banco pan telefone   27.100 de volume  →  89,1% do grupo ACESSO
 *   os outros 4 termos    3.330 somados    →  10,9%
 *
 * Uma keyword é 81% de todo o tráfego das 23 aprovadas. E a intenção dela é
 * "quero o telefone do Banco Pan" — a landing page responde "como conseguir
 * cartão para negativado". É o defeito exato que o brief do FGTS evitou à mão:
 * *"o genérico ficou de fora de propósito: volume enorme com intenção difusa,
 * e a LP responde uma pergunta específica"*.
 *
 * Numa lista isso é invisível. Aqui é a primeira coisa que se vê, porque a
 * LARGURA é a participação no volume: um bloco só ocupando a faixa inteira É o
 * alarme. Não precisa de rótulo dizendo "atenção, concentração".
 *
 * ## O encoding, e por que ele é honesto
 *
 *   largura = participação no volume do conjunto selecionado
 *   altura  = CPC, na escala do CPC mais caro selecionado
 *   área    ≈ o que aquele termo custaria
 *
 * Não é decoração: `largura × altura` é volume × preço, que é a conta que o
 * operador está fazendo. E o CPC ponderado do conjunto é, literalmente, a área
 * total dividida pela largura total.
 *
 * ## ⚠️ O que ela NÃO afirma
 *
 * Os CPCs são MINERADOS. O `DATAFORSEO-MEDIDO` mediu que `keyword_info.cpc`
 * superestima o real em 7,4× e inverte a ordem dentro do cluster. A régua serve
 * para comparar termos ENTRE SI e ver concentração — as duas coisas sobrevivem
 * a um erro de escala. Ela não serve para prever gasto, e diz isso.
 */
import React, { useMemo } from 'react';

import { cn } from '@/lib/utils';
import type { GrupoCandidato, KeywordCandidata } from '@/types/trafego';

const ALTURA_MAX = 96;
const ALTURA_MIN = 4;

export interface Selecionada extends KeywordCandidata {
  grupo: string;
}

interface Barra extends Selecionada {
  larguraPct: number;
  alturaPx: number;
  /** Marca a concentração que a forma já mostra, para o leitor de tela também
   *  saber. Sem isto, a régua é informação só para quem enxerga. */
  domina: boolean;
}

/** O limiar de "domina". 40% é arbitrário e está declarado como arbitrário —
 *  não medi qual participação começa a fazer mal. O que ESTÁ medido é o caso:
 *  89,1% num termo cuja intenção não bate com a página. O limiar existe para
 *  o `aria-label` poder dizer o que a forma diz, não para reprovar nada. */
const LIMIAR_DOMINIO = 0.4;

function moeda(v: number, m: string | null): string {
  const n = v.toFixed(2).replace('.', ',');
  return m ? `${m} ${n}` : n;
}

function compacto(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace('.', ',')}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace('.', ',')}k`;
  return String(n);
}

export function medir(selecionadas: Selecionada[]) {
  // ⚠️ O DENOMINADOR HONESTO É O DOS PRESENTES.
  //
  // Desde que `Cpc.valor` e `volume` passaram a ser `number | null` (a ausência
  // deixou de virar `0` na projeção do servidor), estas contas precisam
  // distinguir "não medido" de "medido em zero". `k.cpc` existir NÃO garante
  // mais que `k.cpc.valor` é número: um CPC sem valor ainda carrega procedência
  // e moeda, e é exatamente esse o caso que o cluster medido produz.
  //
  // Somar ausência como zero puxaria a média para baixo em silêncio — que é a
  // forma mais barata de um lance parecer seguro e não ser.
  const comVolume = selecionadas.filter((k) => k.volume != null);
  const volume = comVolume.length
    ? comVolume.reduce((a, k) => a + (k.volume as number), 0) : 0;
  const comCpc = selecionadas.filter((k) => k.cpc?.valor != null);
  const cpcMax = comCpc.reduce((a, k) => Math.max(a, k.cpc!.valor as number), 0);
  // Ponderado pelo VOLUME, não pela contagem: é o CPC do tráfego que entra, e é
  // o número que se compara com o RPM. A média simples diria outra coisa e a
  // diferença entre as duas é justamente a concentração.
  //
  // Só pesa quem tem CPC **e** volume: uma keyword sem volume não tem peso, e
  // dar-lhe peso zero a faria desaparecer da média em vez de ficar de fora dela.
  const pesaveis = comCpc.filter((k) => k.volume != null);
  const custoTotal = pesaveis.reduce(
    (a, k) => a + (k.cpc!.valor as number) * (k.volume as number), 0);
  const volumeComCpc = pesaveis.reduce((a, k) => a + (k.volume as number), 0);
  const ponderado = volumeComCpc > 0 ? custoTotal / volumeComCpc : 0;
  const simples = comCpc.length
    ? comCpc.reduce((a, k) => a + (k.cpc!.valor as number), 0) / comCpc.length : 0;
  const moedas = new Set(comCpc.map((k) => k.cpc!.moeda).filter(Boolean));
  return {
    volume, cpcMax, ponderado, simples,
    n: selecionadas.length,
    /** Quantas ficaram fora da média de CPC — por não ter CPC medido. */
    semCpc: selecionadas.length - comCpc.length,
    /** Quantas ficaram fora do volume — por não ter volume medido. */
    semVolume: selecionadas.length - comVolume.length,
    moeda: moedas.size === 1 ? [...moedas][0]! : null,
    // Divergência entre ponderado e simples É o sinal de concentração,
    // expressa em número para quem quiser o número.
    concentracao: simples > 0 ? Math.abs(ponderado - simples) / simples : 0,
    medidoNaConta: comCpc.length > 0 && comCpc.every((k) => k.cpc!.medido_na_conta),
    procedencias: [...new Set(comCpc.map((k) => k.cpc!.procedencia).filter(Boolean))],
  };
}

export const ReguaDeLeilao: React.FC<{
  selecionadas: Selecionada[];
  /** O lance que o operador declarou. A linha dele atravessa a régua: tudo
   *  acima dela é termo que pede mais do que ele está disposto a pagar. */
  lance?: number;
  aoPassar?: (k: Selecionada | null) => void;
}> = ({ selecionadas, lance, aoPassar }) => {
  const m = useMemo(() => medir(selecionadas), [selecionadas]);

  const barras: Barra[] = useMemo(() => {
    if (!m.volume || !m.cpcMax) return [];
    // Só entra na régua quem tem volume MEDIDO e maior que zero. Quem não foi
    // medido não vira barra de largura zero — ele fica de fora, e a contagem
    // `semVolume` diz que ficou.
    return [...selecionadas]
      .filter((k) => k.volume != null && k.volume > 0)
      .sort((a, b) => (b.volume as number) - (a.volume as number))
      .map((k) => {
        const pct = (k.volume as number) / m.volume;
        // ⚠️ `?? 0` aqui é DESENHO, não medida: uma keyword com volume e sem CPC
        // aparece com a altura mínima. O número que o operador lê continua
        // vindo de `m`, que a exclui do denominador.
        const cpc = k.cpc?.valor ?? 0;
        return {
          ...k,
          larguraPct: pct * 100,
          alturaPx: Math.max(ALTURA_MIN, Math.round(ALTURA_MAX * (cpc / m.cpcMax))),
          domina: pct >= LIMIAR_DOMINIO,
        };
      });
  }, [selecionadas, m]);

  if (!barras.length) {
    return (
      <div className="border border-dashed border-border px-4 py-10 text-center">
        <p className="mx-auto max-w-[46ch] text-xs leading-relaxed text-muted-foreground">
          Marque keywords para ver a forma do leilão: a largura de cada bloco é a
          participação no volume, a altura é o CPC.
        </p>
      </div>
    );
  }

  const alturaDoLance = lance && m.cpcMax
    ? Math.round(ALTURA_MAX * Math.min(1, lance / m.cpcMax)) : null;
  const dominante = barras.find((b) => b.domina);

  return (
    <div>
      {/* A faixa. Alinhada pela BASE: a base é o zero e a altura é o preço. */}
      <div className="relative flex items-end border-b border-foreground/30"
           style={{ height: ALTURA_MAX }}
           role="img"
           aria-label={
             `Régua do leilão: ${m.n} keywords, volume ${m.volume}, ` +
             `CPC ponderado ${m.ponderado.toFixed(2)}` +
             (dominante
               ? `. Atenção: "${dominante.texto}" concentra ${dominante.larguraPct.toFixed(0)}% do volume.`
               : '')
           }>
        {barras.map((b, i) => (
          <div
            key={`${b.grupo}:${b.texto}`}
            onMouseEnter={() => aoPassar?.(b)}
            onMouseLeave={() => aoPassar?.(null)}
            className={cn(
              'group/b relative shrink-0 transition-[height] duration-200',
              // 1px de vão entre blocos: fills adjacentes não podem se colar,
              // senão dois termos viram um só na leitura.
              i > 0 && 'ml-px',
            )}
            style={{ width: `${b.larguraPct}%`, height: b.alturaPx }}
          >
            <div className={cn(
              'h-full w-full transition-colors',
              b.domina ? 'bg-foreground' : 'bg-foreground/45 group-hover/b:bg-foreground/70',
            )} />
            {/* O rótulo só cabe no bloco largo — e bloco largo é justamente o
                que precisa ser nomeado. Nos estreitos, quem nomeia é o hover. */}
            {b.larguraPct > 14 && (
              <span className="pointer-events-none absolute inset-x-1 top-1 truncate text-[10px] leading-tight text-background mix-blend-difference">
                {b.texto}
              </span>
            )}
          </div>
        ))}

        {/* A linha do lance. Tudo ACIMA dela pede mais do que o operador
            declarou estar disposto a pagar — e isso se vê, não se calcula. */}
        {alturaDoLance !== null && alturaDoLance > 0 && (
          <div className="pointer-events-none absolute inset-x-0 flex items-center"
               style={{ bottom: alturaDoLance }}>
            <div className="h-px flex-1"
                 style={{ backgroundImage: 'repeating-linear-gradient(90deg, hsl(var(--foreground)) 0 4px, transparent 4px 8px)' }} />
            <span className="kicker ml-2 shrink-0 bg-background pl-1 text-[9px]">
              seu lance {moeda(lance!, m.moeda)}
            </span>
          </div>
        )}
      </div>

      {/* O eixo, dito em palavras — a forma sozinha não diz qual eixo é qual. */}
      <div className="mt-1.5 flex items-baseline justify-between">
        <span className="kicker text-muted-foreground">← largura: volume</span>
        <span className="kicker text-muted-foreground">altura: CPC ↑</span>
      </div>

      {/* Os números do conjunto. */}
      <div className="mt-5 flex flex-wrap gap-x-10 gap-y-4 border-t border-border pt-4">
        <Medida rotulo="keywords" valor={String(m.n)} />
        <Medida rotulo="volume/mês" valor={compacto(m.volume)} />
        <Medida
          rotulo="CPC ponderado"
          valor={moeda(m.ponderado, m.moeda)}
          nota={m.moeda ? undefined : 'moeda não declarada'}
        />
        {m.concentracao > 0.15 && (
          <Medida
            rotulo="CPC simples"
            valor={moeda(m.simples, m.moeda)}
            nota={`${(m.concentracao * 100).toFixed(0)}% de diferença`}
          />
        )}
      </div>

      {/* ⚠️ A procedência. Nunca omitida: o CPC minerado superestima o real em
          7,4× e inverte a ordem dentro do cluster — nenhum fator conserta. A
          régua compara termos entre si e mostra concentração; as duas coisas
          sobrevivem ao erro de escala. Prever gasto não sobrevive. */}
      {!m.medidoNaConta && m.procedencias.length > 0 && (
        <p className="mt-4 max-w-[74ch] text-xs leading-relaxed text-muted-foreground">
          CPC <b>minerado</b> ({m.procedencias.join(', ')}), não medido na sua
          conta. Use para comparar termos entre si e ver onde o volume se
          concentra — não para estimar quanto vai gastar.
          {m.semCpc > 0 && ` ${m.semCpc} sem CPC nenhum.`}
        </p>
      )}

      {dominante && (
        <p className="mt-3 max-w-[74ch] text-xs leading-relaxed">
          <b>{dominante.texto}</b> é {dominante.larguraPct.toFixed(0)}% de todo o
          volume selecionado. Confira se a intenção dela bate com a página de
          destino: volume grande com intenção difusa compra clique que não
          converte, e é o erro mais caro de montar campanha.
        </p>
      )}
    </div>
  );
};

const Medida: React.FC<{ rotulo: string; valor: string; nota?: string }> =
  ({ rotulo, valor, nota }) => (
    <div>
      <div className="kicker">{rotulo}</div>
      <div className="tabular font-display text-xl font-bold">{valor}</div>
      {nota && <div className="text-[11px] leading-tight text-muted-foreground">{nota}</div>}
    </div>
  );

/** As keywords de um grupo, achatadas com o nome do grupo junto — a régua
 *  mistura grupos de propósito, porque o leilão não sabe de ad group. */
export function achatar(grupos: GrupoCandidato[], marcadas: Set<string>): Selecionada[] {
  const fora: Selecionada[] = [];
  for (const g of grupos) {
    for (const k of g.keywords) {
      if (marcadas.has(`${g.tipo}:${k.texto}`)) fora.push({ ...k, grupo: g.tipo });
    }
  }
  return fora;
}
