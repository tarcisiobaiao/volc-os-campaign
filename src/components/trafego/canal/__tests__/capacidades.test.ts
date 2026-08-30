/**
 * CAPACIDADE VEM DO MANIFESTO — e as três respostas são três fatos.
 *
 * `manifesto: null` ("o Hub não opera este canal") e manifesto com
 * `capacidades: []` ("opera, e não pode nada") parecem a mesma tela vazia e
 * levam a lugares opostos: a primeira ao painel do Google, a segunda a quem
 * cuida do Hub.
 */
import { describe, expect, it } from 'vitest';

import type { ManifestoDeCanal } from '@/types/trafego';
import { capacidadesDoCanal, palavraDaCapacidade, temFormulario } from '../capacidades';

const manifesto = (over: Partial<ManifestoDeCanal> = {}): ManifestoDeCanal => ({
  plataforma: 'GOOGLE_ADS',
  canal: 'SEARCH',
  rotulo: 'Search',
  hierarquia: ['campanha', 'grupo'],
  paineis: [],
  campos_do_pedido: ['objetivo', 'verba'],
  capacidades: ['ler', 'propor'],
  provas_obrigatorias: ['validate_only'],
  indisponibilidades: [],
  sabe_criar: true,
  ...over,
});

describe('as três respostas', () => {
  it('⚠️ `null` é "o Hub não opera este canal" — afirmação, não falta de dado', () => {
    const c = capacidadesDoCanal(null);
    expect(c.tipo).toBe('nao_operado');
    if (c.tipo === 'nao_operado') {
      expect(c.frase).toContain('o Hub não o opera');
    }
  });

  it('manifesto com capacidades vazias é OUTRO fato, e tem rótulo próprio', () => {
    const c = capacidadesDoCanal(manifesto({ capacidades: [] }));
    expect(c.tipo).toBe('sem_capacidade');
    if (c.tipo === 'sem_capacidade') {
      expect(c.rotulo).toBe('Search');
      expect(c.frase).toContain('diferente de não operar');
    }
  });

  it('manifesto com capacidades traduz cada uma para a língua de quem opera', () => {
    const c = capacidadesDoCanal(manifesto());
    expect(c.tipo).toBe('operado');
    if (c.tipo === 'operado') {
      expect(c.capacidades).toEqual([
        'ler a conta e mostrar o que existe',
        'propor mudança para uma pessoa aprovar',
      ]);
      expect(c.recusa).toBeNull();
    }
  });
});

describe('a recusa ensina', () => {
  it('`sabe_criar: false` usa a indisponibilidade declarada pelo backend', () => {
    const c = capacidadesDoCanal(
      manifesto({ sabe_criar: false, indisponibilidades: ['Display ainda não tem construtor.'] }),
    );
    if (c.tipo === 'operado') {
      expect(c.recusa).toBe('Display ainda não tem construtor.');
    }
  });

  it('sem indisponibilidade declarada, a frase de reserva ainda é uma frase', () => {
    const c = capacidadesDoCanal(manifesto({ sabe_criar: false, indisponibilidades: [] }));
    if (c.tipo === 'operado') {
      expect(c.recusa).toContain('não tem construtor');
    }
  });
});

describe('vocabulário e formulário', () => {
  it('capacidade desconhecida é dita, não apagada', () => {
    expect(palavraDaCapacidade('graduar')).toBe('graduar (capacidade não reconhecida)');
  });

  it('sem campos declarados não há formulário para desenhar', () => {
    expect(temFormulario(manifesto({ campos_do_pedido: [] }))).toBe(false);
    expect(temFormulario(null)).toBe(false);
    expect(temFormulario(manifesto())).toBe(true);
  });
});
