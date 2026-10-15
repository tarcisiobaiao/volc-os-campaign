/**
 * A faixa econômica do Hub: o que a carteira gastou, na leitura que existe.
 *
 * Módulo puro (sem React, sem HTTP). Recebe o inventário SEM recorte e decide,
 * para cada número da faixa, o valor e a verdade dele (PRODUCT §4). A tela só
 * desenha.
 *
 * O que esta projeção se recusa a fazer:
 *  - somar moedas diferentes. Se a carteira tem BRL e USD, a soma fica na
 *    moeda dominante e a verdade cai para `parcial`, dizendo o que ficou fora;
 *  - somar o que não foi medido como se fosse zero. Campanha com entrega
 *    `null` fica fora da soma e rebaixa a verdade para `parcial`;
 *  - inventar receita ou ROAS. O inventário não traz receita por campanha;
 *    os dois chegam `indisponivel` com o motivo, até existir fonte datada;
 *  - dar moeda a quem não declarou. Campanha medida sem moeda fica fora; se
 *    nenhuma declarou, o custo é `indisponivel`, nunca reais por omissão;
 *  - calar as removidas. Campanha REMOVED não é operacional, mas pode ter
 *    gastado na janela: com gasto medido, a soma cai para `parcial` e diz.
 *
 * ⚠️ A fonte é o ESPELHO do inventário (`trafego_campanha_espelho`, gravado pela
 * varredura com GAQL `LAST_30_DAYS`), não o fato diário canônico
 * (`google_ads_campanha_dia`, v12_04). O espelho não grava a janela; a tela
 * declara a da varredura padrão. Apontar para o fato canônico pede rota nova.
 */
import type { Verdade } from '@/components/sistema/VerdadeDoDado';
import type { CampanhaNoInventario, Inventario } from '@/types/trafego';

export interface NumeroDaFaixa {
  valor: number | null;
  verdade: Verdade;
  /** Frase curta do que limita este número. `undefined` quando nada limita. */
  detalhe?: string;
}

export interface FaixaEconomicaDoHub {
  /** Moeda da soma. `null` quando nenhuma campanha medida declarou moeda. */
  moeda: string | null;
  custo: NumeroDaFaixa;
  cliques: NumeroDaFaixa;
  impressoes: NumeroDaFaixa;
  /** Custo ÷ cliques, só quando os dois foram medidos e há clique. */
  cpc: NumeroDaFaixa;
  /** Campanhas com impressão medida > 0 NA JANELA (pausadas hoje incluídas). */
  entregando: NumeroDaFaixa;
  receita: NumeroDaFaixa;
  roas: NumeroDaFaixa;
  /** A leitura MAIS ANTIGA entre as somadas: o frescor de uma soma é o pior. */
  lidoEm: string | null;
  /** Quantas campanhas entraram na soma, e de quantas operacionais. */
  somadas: number;
  operacionais: number;
}

const SEM_RECEITA =
  'a receita por campanha ainda não chega a esta tela; ela não é estimada a partir do custo';

function operacional(c: CampanhaNoInventario): boolean {
  return c.estado_externo !== 'REMOVED';
}

function medida(c: CampanhaNoInventario): boolean {
  const e = c.entrega;
  return e.leitura != null && e.custo_micros != null && e.cliques != null && e.impressoes != null;
}

/** A moeda com mais custo medido. Empate: ordem alfabética, para ser estável. */
function moedaDominante(campanhas: CampanhaNoInventario[]): string | null {
  const porMoeda = new Map<string, number>();
  for (const c of campanhas) {
    const m = c.entrega.moeda;
    if (!m) continue;
    porMoeda.set(m, (porMoeda.get(m) ?? 0) + (c.entrega.custo_micros ?? 0));
  }
  let melhor: string | null = null;
  let maior = -1;
  for (const [m, total] of [...porMoeda.entries()].sort(([a], [b]) => a.localeCompare(b))) {
    if (total > maior) {
      melhor = m;
      maior = total;
    }
  }
  return melhor;
}

/** Janela declarada da varredura padrão do espelho (GAQL `LAST_30_DAYS`). */
export const JANELA_DO_ESPELHO = 'últimos 30 dias';

export function projetarFaixaDoHub(inventario: Inventario | null): FaixaEconomicaDoHub | null {
  if (!inventario) return null;

  const doInventario = inventario.contas.flatMap((conta) => conta.campanhas);
  const todas = doInventario.filter(operacional);
  const medidas = todas.filter(medida);
  const moeda = moedaDominante(medidas);
  const somadas = moeda == null ? [] : medidas.filter((c) => c.entrega.moeda === moeda);
  const removidasComGasto = doInventario.filter(
    (c) => !operacional(c) && (c.entrega.custo_micros ?? 0) > 0,
  ).length;

  const limites: string[] = [];
  if (inventario.parcial || inventario.faltou.length > 0) {
    limites.push('ao menos uma conta não pôde ser lida nesta resposta');
  }
  if (inventario.proximo_cursor != null) {
    limites.push('nem todas as campanhas foram carregadas');
  }
  const naoMedidas = todas.length - medidas.length;
  if (naoMedidas > 0) {
    limites.push(`${naoMedidas} ${naoMedidas === 1 ? 'campanha sem entrega medida' : 'campanhas sem entrega medida'}`);
  }
  const semMoeda = medidas.filter((c) => !c.entrega.moeda).length;
  if (semMoeda > 0) {
    limites.push(`${semMoeda} sem moeda declarada, fora da soma`);
  }
  const outraMoeda = medidas.length - somadas.length - semMoeda;
  if (outraMoeda > 0) {
    limites.push(`${outraMoeda} em outra moeda, fora da soma`);
  }
  if (removidasComGasto > 0) {
    limites.push(
      `${removidasComGasto} ${removidasComGasto === 1 ? 'removida com gasto' : 'removidas com gasto'} na janela, fora da soma`,
    );
  }

  const vazio = somadas.length === 0;
  // Medida sem moeda nenhuma: há número, mas ninguém disse em quê. Não é "não sei
  // se gastou" (desconhecido); é "não dá para dizer em dinheiro" (indisponível).
  const verdadeDaSoma: Verdade = vazio
    ? medidas.length > 0 ? 'indisponivel' : 'desconhecido'
    : limites.length > 0 ? 'parcial' : 'real';
  const detalhe = limites.length > 0 ? limites.join(' · ') : undefined;

  const somar = (f: (c: CampanhaNoInventario) => number): number | null =>
    vazio ? null : somadas.reduce((total, c) => total + f(c), 0);

  const custoMicros = somar((c) => c.entrega.custo_micros ?? 0);
  const custo = custoMicros == null ? null : custoMicros / 1_000_000;
  const cliques = somar((c) => c.entrega.cliques ?? 0);
  const impressoes = somar((c) => c.entrega.impressoes ?? 0);
  const entregando = vazio ? null : somadas.filter((c) => (c.entrega.impressoes ?? 0) > 0).length;

  const comZero = (valor: number | null): NumeroDaFaixa => ({
    valor,
    // Zero medido é afirmação, e o selo diz que foi medido (PRODUCT §4).
    verdade: valor === 0 && verdadeDaSoma === 'real' ? 'zero' : verdadeDaSoma,
    detalhe,
  });

  const cpc: NumeroDaFaixa =
    custo != null && cliques != null && cliques > 0
      ? { valor: custo / cliques, verdade: verdadeDaSoma, detalhe }
      : {
          valor: null,
          verdade: 'desconhecido',
          detalhe: cliques === 0 ? 'nenhum clique medido; custo por clique não se aplica' : detalhe,
        };

  const leituras = somadas
    .map((c) => c.entrega.leitura?.lido_em)
    .filter((l): l is string => typeof l === 'string')
    .sort();

  return {
    moeda,
    custo: comZero(custo),
    cliques: comZero(cliques),
    impressoes: comZero(impressoes),
    cpc,
    entregando: comZero(entregando),
    receita: { valor: null, verdade: 'indisponivel', detalhe: SEM_RECEITA },
    roas: { valor: null, verdade: 'indisponivel', detalhe: 'sem receita datada, o ROAS não é calculado' },
    lidoEm: leituras[0] ?? null,
    somadas: somadas.length,
    operacionais: todas.length,
  };
}
