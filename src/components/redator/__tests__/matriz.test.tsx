// @vitest-environment jsdom
/**
 * A matriz, medida contra o payload REAL do run #6.
 *
 * `run6.json` é a resposta literal de `GET /redator/runs/6/matriz`: 5 páginas,
 * 40 células, US$ 2,4215, 3 rascunhos publicados e 2 páginas bloqueadas por
 * motivos DIFERENTES — a 4 morreu na pesquisa, a 3 no portão de conteúdo. É a
 * única fixture que exercita os sete estados de célula ao mesmo tempo.
 *
 * O que estes testes protegem não é a aparência, é a HONESTIDADE da grade:
 * altura proporcional ao custo, nenhuma ausência sem explicação, e nenhum
 * "US$ 0,00" onde nunca houve medição.
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { Matriz, alturaDaCelula, estadoDaCelula } from '../MatrizDoRun';
import type { MatrizDoRun as Payload, PaginaDaMatriz } from '@/types/redator';
import bruto from './run6.json';

const m = bruto as unknown as Payload;
const ordem = m.colunas.map((c) => c.chave);
const porN = Object.fromEntries(m.paginas.map((p) => [p.page_number, p])) as Record<number, PaginaDaMatriz>;

// Sem `globals: true` no vitest.config, a limpeza entre testes não é
// automática — e dois `render` sem ela deixam duas grades no mesmo document,
// fazendo todo `getByLabelText` estourar por "multiple elements".
afterEach(cleanup);

describe('a altura é o custo', () => {
  it('escala proporcionalmente à célula mais cara', () => {
    // Trava a PROPORÇÃO, não os pixels: a escala absoluta já mudou uma vez (de
    // 22px para 64px, quando o render provou que o paredão de custo não aparecia
    // no tamanho original) e vai poder mudar de novo. O que não pode mudar é a
    // metade custar metade.
    const teto = m.custo_maior_celula;
    const cheia = alturaDaCelula(teto, teto);
    const meia = alturaDaCelula(teto / 2, teto);
    expect(cheia).toBeGreaterThan(40);            // amplitude legível de relance
    expect((meia - 2) / (cheia - 2)).toBeCloseTo(0.5, 1);
    // e é monotônica: mais caro nunca desenha mais baixo
    const custos = Object.values(m.celulas).map((c) => c.custo_usd).sort((a, b) => a - b);
    const alturas = custos.map((c) => alturaDaCelula(c, teto));
    expect(alturas).toEqual([...alturas].sort((a, b) => a - b));
  });

  it('custo zero fica com 2px — existe, mas não pesa', () => {
    // Sumir com a célula a confundiria com "não se aplica", que é outra coisa.
    expect(alturaDaCelula(0, m.custo_maior_celula)).toBe(2);
  });

  it('não divide por zero num run que ainda não gastou nada', () => {
    expect(alturaDaCelula(0, 0)).toBe(2);
    expect(Number.isFinite(alturaDaCelula(0.5, 0))).toBe(true);
  });

  it('a grade real reproduz o paredão de redação e pesquisa', () => {
    const soma = (fam: string) => Object.entries(m.celulas)
      .filter(([k]) => k.startsWith(`${fam}_p`))
      .reduce((a, [, c]) => a + c.custo_usd, 0);
    // É esta desproporção que a forma da grade ensina: quando a redação da
    // última página fecha, a maior parte do dinheiro já saiu.
    const pesados = soma('research') + soma('write');
    expect(pesados / m.custo_total).toBeGreaterThan(0.7);
    // E as colunas locais são um fio, não um bloco.
    for (const fam of ['build', 'publish', 'screenshot', 'content_gate']) {
      expect(soma(fam)).toBe(0);
    }
  });
});

describe('os estados das células', () => {
  const est = (etapa: string, n: number) =>
    estadoDaCelula(etapa, porN[n], m.celulas[`${etapa}_p${n}`], null, ordem);

  it('reconhece o que rodou', () => {
    expect(est('research', 2)).toBe('ok');         // OK de primeira
    expect(est('write', 2)).toBe('retentado');     // RETRIED, 2 tentativas
    expect(est('write', 5)).toBe('retentado');     // RETRIED, 3 tentativas
    expect(est('research', 4)).toBe('falhou');
    expect(est('content_gate', 3)).toBe('falhou');
  });

  it('a retentativa da PESQUISA se disfarça de OK — e a grade não cai nessa', () => {
    // A pesquisa tem laço de retentativa PRÓPRIO (`research_max_attempts: 4`) e
    // não passa pelo caminho que marca RETRIED no runner. Medido no run #6:
    //
    //   research_p2  OK  1 tentativa   US$ 0,1464
    //   research_p3  OK  4 tentativas  US$ 0,4215   ← 2,9× mais caro, mesmo status
    //
    // Ler só o `status` faria a célula mais cara em retrabalho do run parecer
    // idêntica à mais eficiente. O estado vem de `tentativas`, não do rótulo.
    expect(m.celulas['research_p3'].status).toBe('OK');
    expect(m.celulas['research_p3'].tentativas).toBe(4);
    expect(est('research', 3)).toBe('retentado');
    expect(est('research', 1)).toBe('retentado');  // OK com 2 tentativas
    expect(m.celulas['research_p3'].custo_usd)
      .toBeGreaterThan(m.celulas['research_p2'].custo_usd * 2);
  });

  it('a LP não tem juiz, print nem widget — e isso não é falha', () => {
    expect(est('judge', 1)).toBe('nao_se_aplica');
    expect(est('screenshot', 1)).toBe('nao_se_aplica');
    expect(est('widget', 1)).toBe('nao_se_aplica');
  });

  it('a PRESELL tem juiz mas não widget', () => {
    expect(est('judge', 2)).toBe('ok');
    expect(est('widget', 2)).toBe('nao_se_aplica');
  });

  it('a cauda de uma página bloqueada é CANCELADA, nunca pendente', () => {
    // A página 3 morreu no portão; o `publish` dela nunca vai existir.
    expect(porN[3].bloqueada_em).toBe('content_gate');
    expect(est('publish', 3)).toBe('cancelada');
    // A 4 morreu na pesquisa e deixou a linha quase inteira órfã.
    expect(porN[4].bloqueada_em).toBe('research');
    expect(est('seo', 4)).toBe('cancelada');
    expect(est('build', 4)).toBe('cancelada');
  });

  it('nenhuma célula do run real fica sem explicação', () => {
    const orfas: string[] = [];
    for (const pg of m.paginas) {
      for (const etapa of ordem) {
        const e = estadoDaCelula(etapa, pg, m.celulas[`${etapa}_p${pg.page_number}`], null, ordem);
        // Sem run vivo, "pendente" só é legítimo em página não bloqueada — e o
        // run #6 terminou, então não deveria sobrar nenhuma.
        if (e === 'pendente') orfas.push(`${etapa}_p${pg.page_number}`);
      }
    }
    expect(orfas).toEqual([]);
  });

  it('a célula corrente é a única que desenha "rodando"', () => {
    const corrente = { chave: 'seo_p1', page_number: 1, etapa: 'seo', segundos: 12 };
    // (num run vivo hipotético em que seo_p1 ainda não chegou)
    const semSeo = { ...m.celulas } as Payload['celulas'];
    delete semSeo['seo_p1'];
    expect(estadoDaCelula('seo', porN[1], undefined, corrente, ordem)).toBe('rodando');
    expect(estadoDaCelula('build', porN[1], undefined, corrente, ordem)).toBe('pendente');
  });
});

describe('a grade renderizada', () => {
  it('desenha 11 colunas × 5 páginas e rotula cada célula para leitor de tela', () => {
    render(<Matriz m={m} corrente={null} />);
    expect(m.colunas).toHaveLength(11);
    // Toda célula tem `aria-label` com etapa, página e estado — a leitura sem
    // cor e sem forma, que é a garantia de que a grade não depende de visão.
    for (const pg of m.paginas) {
      for (const etapa of ordem) {
        expect(screen.getByLabelText(new RegExp(`^${etapa}, página ${pg.page_number}:`)))
          .toBeTruthy();
      }
    }
  });

  it('nomeia o estado por extenso, não por cor', () => {
    render(<Matriz m={m} corrente={null} />);
    expect(screen.getByLabelText('research, página 4: falhou')).toBeTruthy();
    expect(screen.getByLabelText('judge, página 1: não se aplica a esta página')).toBeTruthy();
    expect(screen.getByLabelText('publish, página 3: cancelada: a página foi bloqueada antes')).toBeTruthy();
    expect(screen.getByLabelText('write, página 5: concluído com retentativa')).toBeTruthy();
  });

  it('a escala aparece escrita, para o operador saber contra o que comparar', () => {
    const { container } = render(<Matriz m={m} corrente={null} />);
    expect(container.textContent).toContain('US$ 0,4556');
  });
});
