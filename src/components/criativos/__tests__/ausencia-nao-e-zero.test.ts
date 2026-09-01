/**
 * Contraprovas da auditoria P17 (`docs/architecture/UI-ESTADOS-HONESTOS-P17.md`).
 *
 * Todas as asserções aqui protegem a MESMA regra, na camada de lógica pura:
 * ausência não vira zero, estimativa não vira apuração, pedido não vira
 * confirmação e MISMATCH não vira "estado desconhecido".
 *
 * ⚠️ Cada bloco cita o defeito que ele mata. Um teste que passaria com o
 * comportamento antigo é tautologia; o comentário existe para a próxima pessoa
 * conseguir refazer o mutante e conferir que o teste ainda o mata.
 */
import { describe, expect, it } from 'vitest';

import {
  NAO_MEDIDO,
  custoDoJobLegivel,
  custoLegivel,
  enquadramentoLegivel,
} from '@/components/criativos/comum/formato';
import { divergenciaDeDimensao, estadoDoCancelamento } from '@/components/criativos/job/pecas';
import { fraseDaContagem } from '@/components/criativos/biblioteca/filtros';
import { fraseDaFila } from '@/components/criativos/aprovacoes/regras';
import type { CreativeJob, Rendition } from '@/types/criativos';

// ─────────────────────────────────────────────────────────────────────────────
// D2 — custo estimado não pode ser lido como custo apurado
// ─────────────────────────────────────────────────────────────────────────────

describe('D2: o custo diz QUAL custo está na tela', () => {
  it('custo real apurado é declarado como apurado', () => {
    const frase = custoDoJobLegivel(0.042, 0.03);
    expect(frase).toContain('0.0420');
    expect(frase).toMatch(/apurado/i);
    expect(frase).not.toMatch(/estimativa/i);
  });

  it('sem custo real, a estimativa aparece ROTULADA como estimativa', () => {
    // Mutante: `custoLegivel(real ?? estimado)` — a versão anterior de
    // `JobPage` e `Linhas`. Ela devolvia só "US$ 0,0300", indistinguível de
    // gasto realizado. Esta asserção é a que ela reprova.
    const frase = custoDoJobLegivel(null, 0.03);
    expect(frase).toContain('0.0300');
    expect(frase).toMatch(/estimativa/i);
    expect(frase).toMatch(/não apurado/i);
  });

  it('os dois ausentes é "não apurado", nunca zero', () => {
    const frase = custoDoJobLegivel(null, null);
    expect(frase).toMatch(/não apurado/i);
    expect(frase).not.toContain('0.0000');
    expect(frase).not.toContain('US$');
  });

  it('zero apurado continua sendo zero medido, e não ausência', () => {
    // Zero é medida. Achatar zero em "não apurado" seria o erro simétrico.
    expect(custoLegivel(0)).toBe('US$ 0.0000');
    expect(custoDoJobLegivel(0, null)).toMatch(/apurado/i);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// D4 — MISMATCH de dimensão
// ─────────────────────────────────────────────────────────────────────────────

describe('D4: a peça fora da dimensão pedida diz que está fora', () => {
  it('`nao_normalizado` é um enquadramento CONHECIDO, não um slug cru', () => {
    // Mutante: tirar a entrada do mapa em `formato.ts`. Aí a palavra volta a ser
    // o slug `nao_normalizado` e a descrição vira "esta versão da tela não
    // conhece" — rebaixando um MISMATCH declarado a estado desconhecido.
    const r = enquadramentoLegivel('nao_normalizado');
    expect(r.palavra).not.toBe('nao_normalizado');
    expect(r.descricao).not.toMatch(/não conhece/i);
    expect(r.descricao).toMatch(/pedida|pedido/i);
  });

  it('enquadramento ausente continua sendo ausência declarada', () => {
    expect(enquadramentoLegivel(null).palavra).toMatch(/não registrado/i);
  });

  const peca = (over: Partial<Rendition>): Rendition => ({
    id: 'r1',
    slot: '1x1',
    rotulo: 'Quadrado',
    estado: 'pronta',
    larguraPedida: 1080,
    alturaPedida: 1080,
    nativoLargura: null,
    nativoAltura: null,
    largura: 1080,
    altura: 1080,
    bytesTotais: null,
    mime: null,
    contentHash: null,
    enquadramento: 'nativo',
    masterId: null,
    previewUrl: null,
    erro: null,
    custoUsd: null,
    concluidaEm: null,
    ...over,
  });

  it('medida igual à pedida não inventa divergência', () => {
    expect(divergenciaDeDimensao(peca({}))).toBeNull();
  });

  it('medida diferente da pedida é MISMATCH com os dois números', () => {
    const d = divergenciaDeDimensao(peca({ largura: 1024, altura: 1024 }));
    expect(d).not.toBeNull();
    expect(d!.frase).toContain('1080 x 1080');
    expect(d!.frase).toContain('1024 x 1024');
  });

  it('medida AUSENTE não é divergência — é ausência', () => {
    // ⚠️ O colapso que este caso impede: `largura: null` comparado com
    // `larguraPedida: 1080` é diferente, mas dizer "a peça saiu fora da
    // dimensão" quando ninguém mediu é inventar uma reprovação.
    expect(divergenciaDeDimensao(peca({ largura: null, altura: null }))).toBeNull();
    expect(divergenciaDeDimensao(peca({ largura: 1080, altura: null }))).toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// D6 — pedido de cancelamento não é cancelamento
// ─────────────────────────────────────────────────────────────────────────────

describe('D6: "pedi para parar" e "parou" são notícias diferentes', () => {
  const job = (over: Partial<CreativeJob>): CreativeJob => ({
    id: 'j1',
    briefingId: 'b1',
    projetoId: 'p1',
    projetoTitulo: 'Campanha',
    tipo: 'imagem',
    modo: 'full_llm',
    motor: 'motor',
    motorVersao: '1',
    estado: 'running',
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

  it('sem pedido de cancelamento, não há aviso nenhum', () => {
    expect(estadoDoCancelamento(job({}))).toBeNull();
  });

  it('pedido registrado e não confirmado avisa que pode haver peça em voo', () => {
    // Mutante: nenhum componente lia `canceladoPedidoEm` (era o estado do
    // código antes desta correção). O job aparecia como "Em execução" puro,
    // com o botão Interromper intacto, e quem olhava o custo não sabia que
    // uma peça já paga podia estar em voo.
    const e = estadoDoCancelamento(job({ canceladoPedidoEm: '2026-08-27T12:05:00Z' }));
    expect(e).not.toBeNull();
    expect(e!.confirmado).toBe(false);
    expect(e!.frase).toMatch(/pedido|pedi/i);
    expect(e!.frase).toMatch(/não confirmou|ainda pode|em voo/i);
  });

  it('confirmado pelo servidor deixa de ser promessa', () => {
    const e = estadoDoCancelamento(
      job({
        estado: 'cancelled',
        canceladoPedidoEm: '2026-08-27T12:05:00Z',
        canceladoEm: '2026-08-27T12:06:00Z',
      }),
    );
    expect(e).not.toBeNull();
    expect(e!.confirmado).toBe(true);
    expect(e!.frase).toMatch(/parou|interrompido|confirmou/i);
  });

  it('confirmação sem pedido registrado ainda é confirmação', () => {
    const e = estadoDoCancelamento(job({ estado: 'cancelled', canceladoEm: '2026-08-27T12:06:00Z' }));
    expect(e!.confirmado).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// D5 — contagem que ninguém leu não é zero
// ─────────────────────────────────────────────────────────────────────────────

describe('D5: a contagem da biblioteca não inventa zero', () => {
  it('carregando não afirma número', () => {
    const f = fraseDaContagem({ carregando: true, erro: false, total: null, universo: null, comFiltro: false });
    expect(f).not.toMatch(/\b0\b/);
    expect(f).toMatch(/não lida|ainda/i);
  });

  it('leitura que FALHOU não afirma "0 ativos neste recorte"', () => {
    // Mutante: `total = consulta.data?.total ?? 0` com `isLoading` já falso —
    // era exatamente isto que a `BibliotecaPage` mostrava logo acima do próprio
    // alerta de erro.
    const f = fraseDaContagem({ carregando: false, erro: true, total: null, universo: null, comFiltro: false });
    expect(f).not.toMatch(/\b0 ativos?\b/);
    expect(f).toMatch(/não chegou|falhou|não foi lida/i);
  });

  it('universo desconhecido declara o recorte e a ausência do total', () => {
    const f = fraseDaContagem({ carregando: false, erro: false, total: 3, universo: null, comFiltro: true });
    expect(f).toContain('3');
    expect(f).toMatch(/não informou|não informado/i);
  });

  it('zero medido continua podendo ser dito', () => {
    const f = fraseDaContagem({ carregando: false, erro: false, total: 0, universo: 48, comFiltro: true });
    expect(f).toContain('0 de 48');
  });
});

describe('D5b: a fila de aprovação não afirma zero quando a leitura falhou', () => {
  it('leitura falhada não vira "0 peças aguardam decisão"', () => {
    // Mutante: `${consulta.data?.total ?? 0} peças aguardam decisão` — a
    // descrição da seção afirmava zero enquanto o corpo mostrava o erro.
    const f = fraseDaFila({ carregando: false, erro: true, total: null });
    expect(f).not.toMatch(/\b0 peças?\b/);
    expect(f).toMatch(/não chegou|falhou|não foi lida/i);
  });

  it('carregando não afirma número', () => {
    expect(fraseDaFila({ carregando: true, erro: false, total: null })).not.toMatch(/\b0\b/);
  });

  it('fila vazia medida é dita como zero medido', () => {
    expect(fraseDaFila({ carregando: false, erro: false, total: 0 })).toMatch(/nenhuma peça|0 peças/i);
  });

  it('uma peça usa singular', () => {
    expect(fraseDaFila({ carregando: false, erro: false, total: 1 })).toContain('1 peça aguarda');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Guarda-chuva: nenhuma frase de ausência vira traço
// ─────────────────────────────────────────────────────────────────────────────

describe('a autoridade de ausência continua sendo frase, nunca traço', () => {
  it('não medido é a frase, e não "—"', () => {
    expect(NAO_MEDIDO).toBe('não medido');
    expect(NAO_MEDIDO).not.toContain('—');
  });
});
