/**
 * A zona segura de Stories/Reels, como regra de PRÉVIA.
 *
 * ## De onde vêm os números
 *
 * EV-META-20 (`docs/specs/creative-supply-chain-v1/OFFICIAL-API-EVIDENCE.json`,
 * confiança COMPROVADO, consultada em 05/09/2026): ~14% no topo, 35% na base e
 * 6% nas laterais, com 1% de tolerância na proporção 9:16. A evidência diz que
 * a zona "entra como regra determinística de preview" — é isto.
 *
 * São os mesmos números que a Prensa usa para reservar a interface de Stories
 * numa variante 9:16 sem `safe_area` própria (`services/prensa/motor/variantes.py`,
 * `SAFE_STORIES_PCT`, W6b), arredondados para cima do mesmo jeito. Se um lado
 * mudar, os dois mudam juntos; o teste deste arquivo trava os valores.
 *
 * ## O que esta regra NÃO é
 *
 * Não é verificação da peça. Desenhar a zona sobre a prévia mostra ONDE a
 * interface do Instagram cobre a imagem; quem confere se há tinta ali é o
 * `verify` da Prensa, no servidor. A tela nunca diz "dentro da zona segura".
 */

export const ZONA_SEGURA_DE_STORIES_PCT = {
  topo: 14,
  base: 35,
  esquerda: 6,
  direita: 6,
} as const;

export const FONTE_DA_ZONA_SEGURA = 'EV-META-20';

/** Tolerância da Meta na proporção, em fração (1%). */
const TOLERANCIA = 0.01;

export type LadoDaZona = keyof typeof ZONA_SEGURA_DE_STORIES_PCT;

export interface ZonaSegura {
  /** Margens em px, arredondadas para cima (como a Prensa). */
  px: Record<LadoDaZona, number>;
  /** Margens em % da dimensão, para desenhar sobre a prévia em qualquer escala. */
  pct: Record<LadoDaZona, number>;
}

/**
 * A peça é vertical 9:16, dentro da tolerância da Meta?
 *
 * ⚠️ Recebe a dimensão PEDIDA ou a MEDIDA, nunca uma inventada. `null` não é
 * 9:16 nem deixa de ser: devolve `false`, e quem chama não desenha nada.
 */
export function eStory(largura: number | null, altura: number | null): boolean {
  if (!largura || !altura || largura <= 0 || altura <= 0) return false;
  const razao = largura / altura;
  const alvo = 9 / 16;
  return Math.abs(razao - alvo) / alvo <= TOLERANCIA;
}

/** A zona segura em px para uma dimensão 9:16; `null` fora de 9:16. */
export function zonaSeguraDeStories(
  largura: number | null,
  altura: number | null,
): ZonaSegura | null {
  if (!eStory(largura, altura)) return null;
  const w = largura as number;
  const h = altura as number;
  const p = ZONA_SEGURA_DE_STORIES_PCT;
  return {
    px: {
      topo: Math.ceil((h * p.topo) / 100),
      base: Math.ceil((h * p.base) / 100),
      esquerda: Math.ceil((w * p.esquerda) / 100),
      direita: Math.ceil((w * p.direita) / 100),
    },
    pct: { ...p },
  };
}

/** A frase que acompanha a moldura, sempre com a fonte e a ressalva. */
export function fraseDaZonaSegura(zona: ZonaSegura): string {
  const { px } = zona;
  return (
    `Interface do Instagram cobre ${px.topo} px no topo, ${px.base} px na base e `
    + `${px.esquerda} px em cada lateral (guia da Meta, ${FONTE_DA_ZONA_SEGURA}). `
    + 'A moldura mostra onde olhar; quem confere a tinta é a verificação da Prensa.'
  );
}

/**
 * Proporção legível de uma peça, para a mesa de proporções.
 *
 * Usa a dimensão PEDIDA: é a que o operador escolheu no briefing e a que o
 * canal exige. A medida aparece à parte, na ficha da peça.
 */
export function proporcaoLegivel(largura: number, altura: number): string {
  const conhecidas: [number, string][] = [
    [1, '1:1'],
    [4 / 5, '4:5'],
    [9 / 16, '9:16'],
    [1.91, '1,91:1'],
    [16 / 9, '16:9'],
  ];
  const razao = largura / altura;
  for (const [alvo, rotulo] of conhecidas) {
    if (Math.abs(razao - alvo) / alvo <= TOLERANCIA) return rotulo;
  }
  return `${largura}:${altura}`;
}
