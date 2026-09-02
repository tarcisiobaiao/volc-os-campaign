/**
 * #6 · o `default` do `switch` do veredito da escada devolvia VERDE.
 *
 * `VereditoDaEscada` é união fechada em COMPILAÇÃO. Em runtime o `tipo` vem do
 * diagnóstico do servidor, e um valor novo caía em
 * `case 'sem_impedimento': default:` — virando "Nenhum impedimento medido",
 * tom `bom`, no título da tela inteira.
 *
 * A função irmã, trinta linhas acima no mesmo arquivo, faz o oposto e escreve o
 * porquê: "Nunca `bom`. Estado que a tela não conhece degradando para 'sem
 * impedimento' é a forma mais silenciosa de esta superfície mentir."
 */
import { describe, expect, it } from 'vitest';

import { fraseDoVeredito } from '../vocabulario';
import type { VereditoDaEscada } from '@/types/diagnostico';

describe('#6 · veredito que esta versão não conhece nunca é verde', () => {
  it('tipo novo do servidor não vira "Nenhum impedimento medido"', () => {
    const novo = { tipo: 'suspensa_por_politica', eixo: 'anuncio' } as unknown as VereditoDaEscada;
    const f = fraseDoVeredito(novo);
    expect(f.tom).not.toBe('bom');
    expect(f.titulo).not.toBe('Nenhum impedimento medido');
    expect(f.titulo).toMatch(/não reconhecid/i);
    // A palavra crua tem de aparecer: o fato é real, o que falta é a frase.
    expect(f.descricao).toContain('suspensa_por_politica');
  });

  it('`sem_impedimento` de verdade continua sendo verde', () => {
    const f = fraseDoVeredito({ tipo: 'sem_impedimento' });
    expect(f.tom).toBe('bom');
    expect(f.titulo).toBe('Nenhum impedimento medido');
  });

  it('os outros três continuam como estavam', () => {
    expect(fraseDoVeredito({ tipo: 'bloqueada', eixo: 'anuncio' }).tom).toBe('ruim');
    expect(fraseDoVeredito({ tipo: 'limitada', eixo: 'anuncio' }).tom).toBe('atencao');
    expect(fraseDoVeredito({ tipo: 'nao_apurado', eixo: 'anuncio' }).tom).toBe('atencao');
  });
});
