/**
 * Nenhuma superfície Meta calcula retorno pela fórmula legada.
 *
 * ---------------------------------------------------------------------------
 * POR QUE ISTO É UMA VARREDURA DE FONTE E NÃO UM TESTE DE RENDERIZAÇÃO
 * ---------------------------------------------------------------------------
 *
 * Um teste de tela só prova o caminho que ele renderiza. `calculateROAS` pode
 * voltar amanhã num cartão que nenhum teste abre, num ramo condicional, ou numa
 * tela Meta que ainda não existe — e a regressão passa despercebida porque o
 * NÚMERO é quase sempre o mesmo. A diferença aparece só nos dois casos que a
 * função legada inventa:
 *
 *   · gasto ausente  → ela devolve `0`   (a tela lê "retorno zero")
 *   · receita sem gasto → devolve `100`  (a tela lê "100% de retorno")
 *
 * Nos dois, o honesto é `null`. Numa tela cuja regra é "ausência nunca vira
 * zero", esta era a última função capaz de inventar número.
 *
 * A varredura é sobre o ARQUIVO, então ela cobre também o código que nenhum
 * teste executa. Comentários são descartados de propósito: as decisões do
 * milestone estão escritas nos cabeçalhos, e elas CITAM o nome da função
 * legada para explicar por que ela saiu.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { calculateROAS, retornoExcedentePct, roasRatio } from '@/utils/roasCalculations';

const raiz = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../..');

/** Toda superfície Meta que renderiza número de retorno. */
const SUPERFICIES_META = [
  'src/pages/MetaCampaignInsightPage.tsx',
  'src/pages/settings/MetaCampaignsSettingsDemo.tsx',
  'src/pages/trafego/MetaObjetoPage.tsx',
  'src/components/trafego/meta/MetaCampaignReadView.tsx',
];

/**
 * Remove comentários de bloco e de linha.
 *
 * Ingênuo de propósito: não entende string com `//` dentro. Nenhuma das
 * superfícies tem uma, e um analisador de verdade aqui seria mais código para
 * revisar do que o que ele protege.
 */
function semComentarios(fonte: string): string {
  return fonte.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}

describe('nenhuma tela Meta usa a fórmula legada de ROAS', () => {
  it.each(SUPERFICIES_META)('%s não chama calculateROAS', (caminho) => {
    const codigo = semComentarios(readFileSync(resolve(raiz, caminho), 'utf-8'));
    expect(codigo).not.toContain('calculateROAS');
    expect(codigo).not.toContain('calculateTraditionalROAS');
  });

  it('as superfícies Meta que mostram retorno o nomeiam com a UNIDADE', () => {
    // `ROAS` sozinho é ambíguo entre razão (2) e excedente (100). O rótulo da
    // tela precisa dizer qual dos dois está ali.
    for (const caminho of [
      'src/pages/settings/MetaCampaignsSettingsDemo.tsx',
      'src/components/trafego/meta/MetaCampaignReadView.tsx',
    ]) {
      const codigo = semComentarios(readFileSync(resolve(raiz, caminho), 'utf-8'));
      expect(codigo).toContain('Retorno excedente (%)');
    }
  });

  it('a rota canônica delega o número e o rótulo à view auditada, tanto em demo como no real', () => {
    // O wrapper deixou de renderizar KPIs. Exigir nele o texto do rótulo
    // duplicaria apresentação; o contrato é encaminhar ambos os ramos à view.
    const codigo = semComentarios(readFileSync(resolve(raiz, 'src/pages/MetaCampaignInsightPage.tsx'), 'utf-8'));
    expect(codigo).toContain("import { MetaCampaignReadView } from '@/components/trafego/meta/MetaCampaignReadView'");
    expect(codigo.match(/<MetaCampaignReadView\b/g)).toHaveLength(2);
  });

  it('o que a fórmula legada inventa é exatamente o que as novas recusam', () => {
    // Esta é a razão de tudo acima, escrita como número.
    expect(calculateROAS(0, 0)).toBe(0);
    expect(retornoExcedentePct(0, 0)).toBeNull();

    expect(calculateROAS(500, 0)).toBe(100);
    expect(retornoExcedentePct(500, 0)).toBeNull();
    expect(roasRatio(500, 0)).toBeNull();
  });
});
