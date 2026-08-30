/**
 * A CAIXA HERDA A CAUSALIDADE DA ESCADA.
 *
 * Duas regras, e as duas são sobre não gastar dinheiro por engano:
 *
 *  1. degrau não apurado não gera proposta nenhuma — recomendar mudança a
 *     partir de uma leitura que falhou é a forma mais curta de errar caro;
 *  2. a proposta é sobre o degrau que o veredito alcança. Com a campanha
 *     pausada, propor "subir a verba" seria gastar mais numa campanha que nem
 *     está no leilão.
 */
import { describe, expect, it } from 'vitest';

import { derivarDiagnostico } from '../derivar';
import { evidenciaDeProva, ID_FGTS, ID_MAQUININHA } from '../fixtureDeEvidencia';
import { SEM_ENDERECO_SEGURO, comValorProposto, proporMudancas } from '../propor';

const AGORA = new Date('2026-08-26T18:10:11.000Z');

const diagnosticoDe = (id: string, opcoes = {}) =>
  derivarDiagnostico(evidenciaDeProva(opcoes), id, { agora: AGORA });

describe('nenhuma proposta a partir de leitura que falhou', () => {
  it('com a cobrança não lida, a caixa sai VAZIA — e com leitura, para dizer que foi apurada', () => {
    const caixa = proporMudancas(diagnosticoDe(ID_FGTS, { derrubar: ['faturamento'] }));
    expect(caixa.propostas).toEqual([]);
    // ⚠️ `leitura` continua preenchida: a apuração aconteceu e o resultado foi
    // "não dá para propor". Zerá-la aqui confundiria com "a caixa não carregou".
    expect(caixa.leitura).not.toBeNull();
  });
});

describe('a proposta segue o veredito', () => {
  it('campanha pausada gera "ligar", e não "subir a verba"', () => {
    const caixa = proporMudancas(diagnosticoDe(ID_MAQUININHA));
    expect(caixa.propostas.map((p) => p.id)).toEqual(['ligar-campanha']);
    const p = caixa.propostas[0];
    expect(p.alvo).toBe('status');
    expect(p.diff.linhas[0]).toEqual({
      rotulo: 'estado da campanha',
      antes: 'PAUSED',
      depois: 'ENABLED',
      delta: null,
    });
  });

  it('campanha limitada pela verba gera a proposta de verba, com a amostra declarada insuficiente', () => {
    const caixa = proporMudancas(diagnosticoDe(ID_FGTS));
    const verba = caixa.propostas.find((p) => p.id === 'subir-verba')!;
    expect(verba.alvo).toBe('orcamento');
    expect(verba.confianca).toBe('alta');
    // A parcela perdida é agregada: ela não diz em quantos dias a verba estourou.
    expect(verba.amostra.insuficiente).toBe(true);
    expect(verba.diff.linhas[0].antes).toContain('20,00');
  });
});

describe('toda proposta nasce bloqueada, com a dependência real', () => {
  it('nenhuma proposta chega aplicável — e o motivo é um só, num lugar só', () => {
    const caixa = proporMudancas(diagnosticoDe(ID_FGTS));
    expect(caixa.propostas.length).toBeGreaterThan(0);
    for (const p of caixa.propostas) {
      expect(p.bloqueio).toEqual(SEM_ENDERECO_SEGURO);
      expect(p.aprovacao.estado).toBe('nao_submetida');
      expect(p.aprovacao.por).toBeNull();
    }
  });
});

describe('o "depois" só existe quando alguém o digita', () => {
  it('a proposta de verba chega SEM valor proposto — a tela não inventa o número', () => {
    const caixa = proporMudancas(diagnosticoDe(ID_FGTS));
    const verba = caixa.propostas.find((p) => p.id === 'subir-verba')!;
    expect(verba.diff.linhas[0].depois).toBeNull();
    expect(verba.diff.gasto_diario).toBeNull();
  });

  it('com valor digitado, o diff ganha o depois formatado na moeda da conta', () => {
    const caixa = proporMudancas(diagnosticoDe(ID_FGTS));
    const verba = caixa.propostas.find((p) => p.id === 'subir-verba')!;
    const com = comValorProposto(verba, 35_000_000, 'BRL');
    expect(com.diff.linhas[0].depois).toContain('35,00');
  });

  it('valor nulo continua nulo — não degrada para zero', () => {
    const caixa = proporMudancas(diagnosticoDe(ID_FGTS));
    const verba = caixa.propostas.find((p) => p.id === 'subir-verba')!;
    expect(comValorProposto(verba, null, 'BRL').diff.linhas[0].depois).toBeNull();
  });
});
