/**
 * Vazio, vazio depois do filtro, carregando e erro são quatro fatos.
 *
 * Cada um leva a uma ação diferente: produzir algo, afrouxar o filtro, esperar,
 * ou tentar ler de novo. Achatar dois deles produz a ação errada.
 */
import { describe, expect, it } from 'vitest';

import { classificarLeitura } from '@/components/criativos/comum/leitura';
import {
  FILTROS_VAZIOS,
  contagemLegivel,
  filtrosAtivos,
  removerFiltro,
  temFiltro,
} from '@/components/criativos/biblioteca/filtros';
import {
  NAO_MEDIDO,
  bytesLegiveis,
  custoLegivel,
  dimensoes,
} from '@/components/criativos/comum/formato';

const base = { carregando: false, erro: null, visiveis: 0, universo: 0, temFiltro: false };

describe('classificação da leitura', () => {
  it('fonte vazia sem filtro é vazio', () => {
    expect(classificarLeitura(base)).toBe('vazio');
  });

  it('recorte vazio com filtro ativo NÃO é vazio', () => {
    expect(classificarLeitura({ ...base, universo: 48, temFiltro: true })).toBe(
      'vazio_apos_filtro',
    );
  });

  it('erro nunca é confundido com vazio, mesmo com zero visível', () => {
    expect(classificarLeitura({ ...base, erro: new Error('caiu') })).toBe('erro');
    expect(classificarLeitura({ ...base, erro: new Error('caiu'), universo: 48 })).toBe('erro');
  });

  it('erro tem precedência sobre carregando: uma leitura que falhou não sabe o total', () => {
    expect(classificarLeitura({ ...base, carregando: true, erro: new Error('caiu') })).toBe('erro');
  });

  it('carregando não é vazio', () => {
    expect(classificarLeitura({ ...base, carregando: true })).toBe('carregando');
  });

  it('universo maior que zero sem filtro declarado não afirma que a fonte está vazia', () => {
    expect(classificarLeitura({ ...base, universo: 12 })).toBe('vazio_apos_filtro');
  });

  it('universo desconhecido com filtro ativo continua sendo recorte vazio', () => {
    expect(classificarLeitura({ ...base, universo: null, temFiltro: true })).toBe(
      'vazio_apos_filtro',
    );
  });
});

describe('filtros removíveis e contagem', () => {
  it('sem filtro, a contagem fala do universo inteiro', () => {
    expect(temFiltro(FILTROS_VAZIOS)).toBe(false);
    expect(contagemLegivel(48, 48, false)).toBe('48 ativos na biblioteca');
  });

  it('com filtro, a contagem diz o recorte E o universo', () => {
    expect(contagemLegivel(12, 48, true)).toBe('12 de 48 ativos');
  });

  it('todo filtro ativo vira uma ficha removível', () => {
    const f = { ...FILTROS_VAZIOS, busca: 'agosto', kind: 'imagem' as const, destino: 'meta_feed' };
    const ativos = filtrosAtivos(f);
    expect(ativos.map((a) => a.chave)).toEqual(['busca', 'kind', 'destino']);
    expect(ativos[2].valor).toBe('Meta feed');
    expect(temFiltro(removerFiltro(removerFiltro(removerFiltro(f, 'busca'), 'kind'), 'destino'))).toBe(
      false,
    );
  });

  it('o brand pack aparece pelo nome, nunca pelo identificador cru', () => {
    const f = { ...FILTROS_VAZIOS, brandPack: 'uuid-longo-e-ilegivel' };
    const [ficha] = filtrosAtivos(f, () => 'Positivo v3');
    expect(ficha.valor).toBe('Positivo v3');
  });
});

describe('ausência não vira zero na formatação', () => {
  it('medida ausente é declarada, não arredondada', () => {
    expect(dimensoes(null, null)).toBe(NAO_MEDIDO);
    expect(dimensoes(1080, null)).toBe(NAO_MEDIDO);
    expect(bytesLegiveis(null)).toBe(NAO_MEDIDO);
    expect(custoLegivel(null)).toBe('custo não apurado');
  });

  it('zero medido continua sendo zero medido', () => {
    expect(bytesLegiveis(0)).toBe('0 B');
    expect(custoLegivel(0)).toBe('US$ 0.0000');
  });
});
