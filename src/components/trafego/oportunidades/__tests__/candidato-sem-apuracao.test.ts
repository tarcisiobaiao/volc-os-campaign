/**
 * #9 · o ramo VERDE de `estadoDoCandidato` nascia de um `?? 0`.
 *
 *     const jaNoAr = p.campanhas_lancadas ?? 0;
 *
 * O contrato diz o contrário, em `types/trafego.ts`: "`null` quando a prova não
 * pôde ser feita. Nulo não é zero: zero afirmaria 'não há campanha', que é
 * exatamente o que não foi apurado."
 *
 * Com `null` (ou com a chave ausente, que o tipo permite), `jaNoAr` virava 0, o
 * `if (jaNoAr > 0)` não disparava e a função caía no chip verde `pronto` /
 * `CircleCheck`. Hoje o quadro substitui esse chip por `fraseDeReconciliacao`,
 * então é código morto — com a armadilha carregada para o próximo consumidor.
 */
import { describe, expect, it } from 'vitest';

import { estadoDoCandidato } from '../linguagem';
import type { CandidatoNoQuadro } from '@/types/trafego';

const base = {
  opportunity_id: 63, run_id: 7, titulo: 'Cartão para Negativado',
  tem_cluster: true, keywords_para_anuncio: 23, volume_total: 37400,
  servicos_declarados: ['n8n:dataforseo'],
} as unknown as CandidatoNoQuadro;

describe('#9 · lançamento não apurado nunca é o chip verde', () => {
  it('`campanhas_lancadas: null` não vira "pronto"', () => {
    const e = estadoDoCandidato({ ...base, campanhas_lancadas: null });
    expect(e.jaNoAr).toBeNull();
    expect(e.chip.tom).not.toBe('bom');
    expect(e.chip.palavra).not.toBe('pronto');
    expect(e.chip.palavra).toMatch(/não apurad/i);
  });

  it('chave ausente é o mesmo caso — o tipo a declara opcional', () => {
    const e = estadoDoCandidato({ ...base });
    expect(e.jaNoAr).toBeNull();
    expect(e.chip.tom).not.toBe('bom');
  });

  it('zero MEDIDO continua sendo "pronto" — zero é uma medição', () => {
    const e = estadoDoCandidato({ ...base, campanhas_lancadas: 0 });
    expect(e.jaNoAr).toBe(0);
    expect(e.chip.palavra).toBe('pronto');
    expect(e.chip.tom).toBe('bom');
  });

  it('campanha no ar continua contando', () => {
    const e = estadoDoCandidato({ ...base, campanhas_lancadas: 2 });
    expect(e.chip.palavra).toBe('2 campanhas no ar');
  });

  it('sem cluster continua vencendo qualquer outra leitura', () => {
    const e = estadoDoCandidato({
      ...base, tem_cluster: false, keywords_para_anuncio: 0, campanhas_lancadas: null,
    });
    expect(e.pronto).toBe(false);
    expect(e.chip.palavra).toBe('sem keywords mineradas');
  });
});
