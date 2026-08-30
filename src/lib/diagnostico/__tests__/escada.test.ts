/**
 * A LEI DA ESCADA: ausência de prova nunca vira boa notícia.
 *
 * O defeito que a rodada anterior fechou no inventário (`reconciliacao: null`
 * virando `?? 0`) tem um irmão exato aqui: um degrau que não pôde ser lido,
 * tratado como "sem impedimento", faz a tela dizer "está tudo bem" apoiada numa
 * consulta que falhou. Este arquivo existe para que esse irmão não nasça.
 */
import { describe, expect, it } from 'vitest';

import type { DegrauDeEntrega, EixoDeEntrega, EstadoDoDegrau } from '@/types/diagnostico';
import { degrausConfiaveis, emOrdemCausal, escadaParcial, vereditoDaEscada } from '../escada';

function degrau(eixo: EixoDeEntrega, estado: EstadoDoDegrau): DegrauDeEntrega {
  return {
    eixo,
    estado,
    palavra: estado,
    frase: 'frase de prova',
    motivo_da_conta: [],
    evidencias: [],
    impedimento: estado === 'nao_apurado' ? 'a consulta falhou' : null,
    propostas: [],
  };
}

describe('veredito da escada', () => {
  it('o degrau que bloqueia mais baixo é o veredito', () => {
    const v = vereditoDaEscada([
      degrau('conta', 'ok'),
      degrau('campanha', 'bloqueia'),
      degrau('leilao', 'bloqueia'),
    ]);
    expect(v).toEqual({ tipo: 'bloqueada', eixo: 'campanha' });
  });

  it('a ordem de chegada não muda o veredito: quem manda é a ordem causal', () => {
    const v = vereditoDaEscada([
      degrau('leilao', 'bloqueia'),
      degrau('conta', 'bloqueia'),
      degrau('anuncio', 'ok'),
    ]);
    expect(v).toEqual({ tipo: 'bloqueada', eixo: 'conta' });
  });

  it('⚠️ um degrau NÃO APURADO interrompe a leitura — não vira "sem impedimento"', () => {
    const v = vereditoDaEscada([
      degrau('conta', 'ok'),
      degrau('campanha', 'nao_apurado'),
      degrau('orcamento', 'ok'),
      degrau('anuncio', 'ok'),
      degrau('leilao', 'ok'),
    ]);
    expect(v).toEqual({ tipo: 'nao_apurado', eixo: 'campanha' });
  });

  it('bloqueio ABAIXO de um não apurado continua sendo o veredito', () => {
    const v = vereditoDaEscada([
      degrau('conta', 'bloqueia'),
      degrau('campanha', 'nao_apurado'),
    ]);
    expect(v).toEqual({ tipo: 'bloqueada', eixo: 'conta' });
  });

  it('sem bloqueio e sem falha, o `limita` mais baixo decide', () => {
    const v = vereditoDaEscada([
      degrau('conta', 'ok'),
      degrau('orcamento', 'limita'),
      degrau('leilao', 'limita'),
    ]);
    expect(v).toEqual({ tipo: 'limitada', eixo: 'orcamento' });
  });

  it('tudo apurado e nada impedindo é o único caminho para "sem impedimento"', () => {
    const v = vereditoDaEscada([degrau('conta', 'ok'), degrau('leilao', 'ok')]);
    expect(v).toEqual({ tipo: 'sem_impedimento' });
  });

  it('⚠️ escada VAZIA é `nao_apurado`, nunca "sem impedimento"', () => {
    // Nenhuma medida nenhuma é o caso em que a tela sabe menos, e é justamente
    // onde uma implementação distraída devolveria a resposta mais tranquila.
    expect(vereditoDaEscada([])).toEqual({ tipo: 'nao_apurado', eixo: 'conta' });
  });
});

describe('leitura suspensa', () => {
  it('o degrau do corte entra em suspensos junto com os de cima', () => {
    const degraus = [
      degrau('conta', 'ok'),
      degrau('campanha', 'nao_apurado'),
      degrau('orcamento', 'ok'),
    ];
    const { confiaveis, suspensos } = degrausConfiaveis(degraus, vereditoDaEscada(degraus));
    expect(confiaveis.map((d) => d.eixo)).toEqual(['conta']);
    expect(suspensos.map((d) => d.eixo)).toEqual(['campanha', 'orcamento']);
  });

  it('sem impedimento não suspende nada', () => {
    const degraus = [degrau('conta', 'ok'), degrau('leilao', 'ok')];
    const { suspensos } = degrausConfiaveis(degraus, vereditoDaEscada(degraus));
    expect(suspensos).toEqual([]);
  });
});

describe('utilitários', () => {
  it('ordena pela causa, e eixo desconhecido vai para o fim e não para o topo', () => {
    const ordem = emOrdemCausal([
      degrau('leilao', 'ok'),
      degrau('inventado' as EixoDeEntrega, 'ok'),
      degrau('conta', 'ok'),
    ]).map((d) => d.eixo);
    expect(ordem[0]).toBe('conta');
    expect(ordem[ordem.length - 1]).toBe('inventado');
  });

  it('`parcial` é verdadeiro quando algum degrau não foi apurado', () => {
    expect(escadaParcial([degrau('conta', 'ok')])).toBe(false);
    expect(escadaParcial([degrau('conta', 'nao_apurado')])).toBe(true);
  });
});
