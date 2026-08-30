/**
 * A reconexão do fluxo não pode duplicar evento nem abrir buraco.
 *
 * Estes dois defeitos aparecem juntos e por causa da mesma escolha: usar
 * timestamp como cursor. Dois eventos no mesmo milissegundo empatam, e o
 * cliente ou repete um ou pula um. `seq` é ordem total, e o acumulador só
 * aceita `seq` maior que o cursor.
 */
import { describe, expect, it } from 'vitest';

import {
  fluxoInicial,
  receberEvento,
  receberLote,
  ultimos,
} from '@/components/criativos/stream/fluxo';
import { lerQuadro, repartirQuadros } from '@/components/criativos/stream/sse';
import type { EventoDoJob } from '@/types/criativos';

const evento = (seq: number, fase = 'gerando'): EventoDoJob => ({
  seq,
  fase,
  mensagem: null,
  percentual: null,
  slot: null,
  em: '2026-08-27T12:00:00Z',
});

describe('acumulador de eventos', () => {
  it('aceita eventos em ordem e move o cursor', () => {
    const f = receberLote(fluxoInicial(0), [evento(1), evento(2), evento(3)]);
    expect(f.eventos.map((e) => e.seq)).toEqual([1, 2, 3]);
    expect(f.cursor).toBe(3);
    expect(f.repetidos).toBe(0);
  });

  it('não duplica quando a retomada reenvia a janela inteira', () => {
    const primeira = receberLote(fluxoInicial(0), [evento(1), evento(2), evento(3)]);
    // O servidor reabre em `desde=3` e reenvia 3 (limite inclusivo) mais os novos.
    const depois = receberLote(primeira, [evento(3), evento(4), evento(5)]);
    expect(depois.eventos.map((e) => e.seq)).toEqual([1, 2, 3, 4, 5]);
    expect(depois.cursor).toBe(5);
    expect(depois.repetidos).toBe(1);
  });

  it('reconexão que só traz repetição não acrescenta nada', () => {
    const antes = receberLote(fluxoInicial(0), [evento(1), evento(2)]);
    const depois = receberLote(antes, [evento(1), evento(2)]);
    expect(depois.eventos).toHaveLength(2);
    expect(depois.cursor).toBe(2);
    expect(depois.repetidos).toBe(2);
  });

  it('começa do cursor que a carga por HTTP já conhecia', () => {
    // O job veio com `cursorEventos: 7`. Reprocessar 1 a 7 encheria a tela de
    // histórico como se fosse novidade.
    const f = receberLote(fluxoInicial(7), [evento(5), evento(6), evento(7), evento(8)]);
    expect(f.eventos.map((e) => e.seq)).toEqual([8]);
    expect(f.cursor).toBe(8);
  });

  it('recusa seq que não é número finito em vez de mover o cursor para NaN', () => {
    const f = receberEvento(fluxoInicial(2), { ...evento(1), seq: Number.NaN });
    expect(f.cursor).toBe(2);
    expect(f.eventos).toHaveLength(0);
  });

  it('ultimos devolve do mais recente para o mais antigo', () => {
    const f = receberLote(fluxoInicial(0), [evento(1), evento(2), evento(3)]);
    expect(ultimos(f, 2).map((e) => e.seq)).toEqual([3, 2]);
  });
});

describe('protocolo SSE lido por fetch', () => {
  it('não perde quadro cortado no meio pelo chunk da rede', () => {
    const primeiro = repartirQuadros('event: evento\ndata: {"seq":1}\n\nevent: evento\ndata: {"se');
    expect(primeiro.quadros).toHaveLength(1);
    expect(primeiro.resto).toBe('event: evento\ndata: {"se');

    const segundo = repartirQuadros(`${primeiro.resto}q":2}\n\n`);
    expect(segundo.quadros).toHaveLength(1);
    expect(lerQuadro(segundo.quadros[0])).toEqual({ evento: 'evento', dados: '{"seq":2}' });
  });

  it('lê os três nomes de evento do contrato', () => {
    expect(lerQuadro('event: evento\ndata: {"seq":1}')?.evento).toBe('evento');
    expect(lerQuadro('event: job\ndata: {"id":"a"}')?.evento).toBe('job');
    expect(lerQuadro('event: fim\ndata: {"estado":"succeeded"}')?.evento).toBe('fim');
  });

  it('ignora comentário de keep-alive e quadro sem data', () => {
    expect(lerQuadro(': ping')).toBeNull();
    expect(lerQuadro('event: evento')).toBeNull();
  });
});
