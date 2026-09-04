/**
 * As proibições visuais de `design.md`, varridas nos arquivos da Bancada.
 *
 * ## Por que uma varredura, e não uma revisão
 *
 * `design.md` abre com "Agent contract (read this first)" e fecha com uma lista
 * de "Hard bans (match and refuse)". Uma lista de proibições que só existe em
 * prosa é cumprida enquanto alguém lembra dela — e a própria revisão visual de
 * 2026-08-29 mediu o custo disso: o contrato tinha sido "aplicado às salas novas
 * e nunca às herdadas", e a pílula de aba selecionada media **1,025:1** contra o
 * poço em treze arquivos porque uma redação obsoleta do próprio `design.md`
 * dizia `bg-background`.
 *
 * ⚠️ Esta varredura NÃO substitui olho humano. Ela pega o que é textual —
 * classe proibida, token cru, tamanho abaixo do piso — e não pega hierarquia,
 * ritmo nem densidade. O escopo é declarado de propósito: um gate que promete
 * mais do que mede é pior que nenhum.
 *
 * Escopo: só os arquivos NOVOS desta entrega. Varrer o produto inteiro
 * misturaria a dívida herdada do webgo com o que esta lane escreveu, e a
 * primeira falha herdada faria alguém desligar o gate.
 */
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const RAIZ = new URL('../../../../..', import.meta.url).pathname;

const PASTAS = [
  'src/components/trafego/bancada',
  'src/components/trafego/recibos',
];

function arquivos(dir: string): string[] {
  const abs = join(RAIZ, dir);
  const saida: string[] = [];
  for (const nome of readdirSync(abs)) {
    const caminho = join(abs, nome);
    if (statSync(caminho).isDirectory()) {
      if (nome === '__tests__') continue;
      saida.push(...arquivos(join(dir, nome)));
      continue;
    }
    if (/\.tsx?$/.test(nome)) saida.push(join(dir, nome));
  }
  return saida;
}

/**
 * O código sem comentários.
 *
 * ⚠️ Indispensável: estes arquivos DOCUMENTAM as proibições em comentário
 * (`// PROIBIDO border-l-2 colorida`), e uma varredura ingênua acusaria
 * justamente a explicação de por que a coisa não está lá. Foi por isso que
 * `design.md` teve de escrever "in non-comment source" para o Estúdio.
 */
function codigo(rel: string): string {
  return readFileSync(join(RAIZ, rel), 'utf-8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');
}

const ALVOS = PASTAS.flatMap(arquivos);

describe('o contrato visual de design.md, varrido na Bancada', () => {
  it('varre um conjunto de arquivos que existe de verdade', () => {
    // Um gate que varre zero arquivo passa sempre. Se alguém renomear a pasta,
    // é aqui que aparece — e não numa suíte verde que não olhou nada.
    expect(ALVOS.length).toBeGreaterThanOrEqual(10);
  });

  it('nenhuma borda lateral colorida — o estado vai no hairline do topo', () => {
    // design.md §Hard bans: "Left/right color stripes >1px". O contrato manda
    // 2px no TOPO (§Surfaces, "Status on a card").
    for (const a of ALVOS) {
      expect(codigo(a), a).not.toMatch(/border-[lr]-(2|4|8)\b/);
    }
  });

  it('nenhum gradiente de texto fora dos marcos de identidade', () => {
    // design.md §Aurora: gradiente de texto só na segunda palavra do H1 em QG,
    // Pautador Pro e Redator. A Bancada não é sala de identidade.
    for (const a of ALVOS) {
      expect(codigo(a), a).not.toMatch(/bg-clip-text|text-aurora|gradient-aurora/);
    }
  });

  it('nenhum glassmorphism nem blur ornamental', () => {
    for (const a of ALVOS) {
      expect(codigo(a), a).not.toMatch(/backdrop-blur|\bglass\b/);
    }
  });

  it('nenhum `transition-all` — as propriedades são nomeadas', () => {
    // design.md §Motion: "Properties. Name them. Never `transition: all`."
    // Animar tudo inclui `width`/`height`, que a mesma seção proíbe.
    for (const a of ALVOS) {
      expect(codigo(a), a).not.toMatch(/transition-all|transition:\s*all/);
    }
  });

  it('nenhuma animação de propriedade de layout', () => {
    // design.md §Motion: "Animate `transform` and `opacity` (…). Never `width`,
    // `height`, `top`, `left`."
    for (const a of ALVOS) {
      expect(codigo(a), a).not.toMatch(/transition-\[[^\]]*\b(width|height|top|left)\b/);
    }
  });

  it('nenhuma paleta crua — o vocabulário semântico é fechado', () => {
    // design.md §Colors: "Semantic vocabulary is closed: primary, verified,
    // success, warning, destructive, info."
    const CRUA = new RegExp(
      '(bg|text|border|ring|from|via|to)-'
      + '(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald'
      + '|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-[0-9]{2,3}',
    );
    for (const a of ALVOS) {
      expect(codigo(a), a).not.toMatch(CRUA);
    }
  });

  it('nenhum texto abaixo do piso tipográfico em decisão', () => {
    // design.md §Typography: "essential actions and explanatory text never drop
    // below 14px"; metadado pode 11–12px.
    //
    // ⚠️ A varredura cobre px E rem. Um piso checado só por `text-[11px]`
    // passaria por cima de `text-[0.6875rem]`, que é o MESMO tamanho escrito de
    // outro jeito — e é assim que um gate literal vira teatro.
    for (const a of ALVOS) {
      const c = codigo(a);
      expect(c, a).not.toMatch(/text-\[(9|10)px\]/);
      expect(c, a).not.toMatch(/text-\[0\.(5625|625)rem\]/);
    }
  });

  it('nenhum cartão elevado dentro de cartão elevado', () => {
    // design.md §Surfaces: "Nested cards are always wrong." Dentro de uma
    // superfície `bg-card`, o agrupamento é hairline + poço `bg-muted/20`.
    for (const a of ALVOS) {
      const c = codigo(a);
      // Duas sombras de cartão no MESMO className é o sinal barato desse erro.
      for (const cls of c.match(/className=(?:"[^"]*"|\{[^}]*\})/g) ?? []) {
        const n = (cls.match(/shadow-card/g) ?? []).length;
        expect(n, `${a}: ${cls.slice(0, 120)}`).toBeLessThanOrEqual(1);
      }
    }
  });

  it('a pílula de aba nunca usa bg-background — esse token É o canvas', () => {
    // ⚠️ Medido na revisão adversarial de 2026-08-29: `bg-background` (#F3F5F7)
    // contra o poço `bg-muted` dá **1,025:1**. A pílula e a página viram o mesmo
    // cinza. `design.md` §Surfaces é explícito, e §Components carrega a redação
    // antiga — a §Surfaces é a que está certa.
    for (const a of ALVOS) {
      expect(codigo(a), a).not.toMatch(/data-\[state=active\]:bg-background/);
    }
  });
});
