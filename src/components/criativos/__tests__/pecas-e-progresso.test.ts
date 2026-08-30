/**
 * Um lote parcial preserva o que ficou pronto, e ausência de percentual não
 * vira barra.
 */
import { describe, expect, it } from 'vitest';

import {
  frasePecas,
  ofertaDeCancelamento,
  ofertaDeRetry,
  resumirPecas,
} from '@/components/criativos/job/pecas';
import { faseLegivel, lerProgresso, percentualUtil } from '@/components/criativos/job/progresso';
import type { CreativeJob, EventoDoJob, FalhaCriativa, Rendition } from '@/types/criativos';

const peca = (over: Partial<Rendition>): Rendition => ({
  id: over.id ?? 'r1',
  slot: over.slot ?? '1x1',
  rotulo: over.rotulo ?? 'Quadrado',
  estado: over.estado ?? 'pronta',
  larguraPedida: 1080,
  alturaPedida: 1080,
  nativoLargura: null,
  nativoAltura: null,
  largura: null,
  altura: null,
  bytesTotais: null,
  mime: null,
  contentHash: null,
  enquadramento: null,
  masterId: null,
  previewUrl: null,
  erro: null,
  custoUsd: null,
  concluidaEm: null,
  ...over,
});

const falha = (permanente: boolean): FalhaCriativa => ({
  codigo: 'motor.recusou',
  mensagem: 'O motor recusou este pedido.',
  permanente,
  em: '2026-08-27T12:00:00Z',
});

const job = (over: Partial<CreativeJob>): CreativeJob => ({
  id: 'j1',
  briefingId: 'b1',
  projetoId: 'p1',
  projetoTitulo: 'Campanha de agosto',
  tipo: 'imagem',
  modo: 'full_llm',
  motor: 'motor',
  motorVersao: '1',
  estado: 'partial',
  tentativa: 1,
  procedenciaExecucao: 'volc_os',
  origemExterna: null,
  custoEstimadoUsd: null,
  custoRealUsd: null,
  iniciadoEm: null,
  terminadoEm: null,
  canceladoPedidoEm: null,
  canceladoEm: null,
  criadoEm: '2026-08-27T12:00:00Z',
  falha: null,
  renditions: [],
  cursorEventos: 0,
  ...over,
});

describe('lote parcial', () => {
  const renditions = [
    peca({ id: 'a', slot: '1x1', estado: 'pronta', previewUrl: 'https://exemplo/a' }),
    peca({ id: 'b', slot: '4x5', estado: 'pronta', previewUrl: 'https://exemplo/b' }),
    peca({ id: 'c', slot: '9x16', estado: 'falhou', erro: falha(false) }),
  ];

  it('separa prontas e falhadas sem descartar nenhuma', () => {
    const r = resumirPecas(renditions);
    expect(r.prontas.map((p) => p.slot)).toEqual(['1x1', '4x5']);
    expect(r.falhadas.map((p) => p.slot)).toEqual(['9x16']);
    expect(r.total).toBe(3);
  });

  it('a frase não chama o lote de sucesso nem de falha', () => {
    const frase = frasePecas(resumirPecas(renditions));
    expect(frase).toContain('2 de 3');
    expect(frase).toContain('1 com falha');
    expect(frase).not.toMatch(/^Falhou/);
  });

  it('as peças prontas mantêm o arquivo mesmo com uma irmã falhada', () => {
    const r = resumirPecas(renditions);
    expect(r.prontas.every((p) => p.previewUrl !== null)).toBe(true);
  });

  it('retry é oferecido, e a explicação diz que não regera as prontas', () => {
    const oferta = ofertaDeRetry(job({ renditions }));
    expect(oferta.disponivel).toBe(true);
    expect(oferta.motivo).toContain('não são geradas de novo');
  });

  it('retry some quando toda falha pendente é permanente', () => {
    const permanentes = [
      peca({ id: 'a', estado: 'pronta' }),
      peca({ id: 'c', slot: '9x16', estado: 'falhou', erro: falha(true) }),
    ];
    const oferta = ofertaDeRetry(job({ renditions: permanentes }));
    expect(oferta.disponivel).toBe(false);
    expect(oferta.motivo).toContain('permanentes');
  });

  it('build observado não oferece retry nem cancelamento', () => {
    const observado = job({ procedenciaExecucao: 'observado', estado: 'succeeded' });
    expect(ofertaDeRetry(observado).disponivel).toBe(false);
    expect(ofertaDeCancelamento(observado).disponivel).toBe(false);
  });

  it('cancelar só existe enquanto há o que interromper', () => {
    expect(ofertaDeCancelamento(job({ estado: 'running' })).disponivel).toBe(true);
    expect(ofertaDeCancelamento(job({ estado: 'queued' })).disponivel).toBe(true);
    expect(ofertaDeCancelamento(job({ estado: 'succeeded' })).disponivel).toBe(false);
  });
});

describe('progresso sem percentual inventado', () => {
  const ev = (over: Partial<EventoDoJob>): EventoDoJob => ({
    seq: 1,
    fase: 'gerando',
    mensagem: null,
    percentual: null,
    slot: null,
    em: '2026-08-27T12:00:00Z',
    ...over,
  });

  it('percentual nulo continua nulo, nunca zero', () => {
    const p = lerProgresso([ev({})]);
    expect(p.percentual).toBeNull();
    expect(p.frase).toBe('Gerando as peças.');
  });

  it('não reaproveita o percentual de um evento anterior', () => {
    const p = lerProgresso([ev({ seq: 1, percentual: 40 }), ev({ seq: 2, percentual: null })]);
    expect(p.percentual).toBeNull();
  });

  it('recusa percentual fora de 0 a 100 e NaN', () => {
    expect(percentualUtil(-1)).toBeNull();
    expect(percentualUtil(101)).toBeNull();
    expect(percentualUtil(Number.NaN)).toBeNull();
    expect(percentualUtil(0)).toBe(0);
    expect(percentualUtil(100)).toBe(100);
  });

  it('sem evento nenhum a frase não finge etapa', () => {
    const p = lerProgresso([]);
    expect(p.fase).toBeNull();
    expect(p.percentual).toBeNull();
    expect(p.frase).toContain('Ainda não houve nenhum evento');
  });

  it('fase desconhecida vira frase, não vocabulário de máquina', () => {
    expect(faseLegivel('gerando_voz')).toBe('Gerando a voz.');
    const nova = faseLegivel('polindo_alpha');
    expect(nova).toContain('polindo alpha');
    expect(nova).not.toBe('polindo_alpha');
  });
});
