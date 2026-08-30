/**
 * A regra dos critérios — os MESMOS casos que a prova em Python usa.
 *
 * Duas implementações da mesma regra só se justificam se elas concordarem, e a
 * única forma de saber que concordam é medir as duas contra os mesmos casos.
 * Se um destes testes divergir de `volc_ads/campanha/testes_criterio.py`, a
 * tela está afirmando uma coisa e o payload fazendo outra — que é exatamente o
 * defeito que a tela existe para não cometer.
 */
import { describe, expect, it } from 'vitest';

import {
  bloqueia,
  chave,
  conflitos,
  deduplicar,
  explicarAlcance,
  explicarEscopo,
  identidade,
  medido,
  novoCriterio,
  resumir,
} from '../criterios';
import type { CriterioDeKeyword, MatchType } from '@/types/trafego';

const pos = (texto: string, match_type: MatchType = 'PHRASE',
             troca: Partial<CriterioDeKeyword> = {}): CriterioDeKeyword => ({
  texto, match_type, negativa: false, nivel: 'AD_GROUP', grupo: null,
  origem: 'PAUTADOR', motivo: null, evidencia: null, observado_em: null,
  aprovado_por: null, ...troca,
});

const neg = (texto: string, match_type: MatchType = 'PHRASE',
             troca: Partial<CriterioDeKeyword> = {}): CriterioDeKeyword =>
  novoCriterio(texto, { match_type, ...troca });

describe('chave', () => {
  it('colapsa caixa e espaço duplo, mas PRESERVA acento', () => {
    expect(chave('  Curso   Inglês ')).toBe('curso inglês');
    expect(chave('CURSO inglês')).toBe(chave('curso  Inglês'));
  });
});

describe('bloqueia — a semântica da API, não a das positivas', () => {
  const consulta = 'curso de ingles gratis';

  it('EXACT só bloqueia a consulta idêntica', () => {
    expect(bloqueia(neg('curso gratis', 'EXACT'), consulta)).toBe(false);
    expect(bloqueia(neg('curso de ingles gratis', 'EXACT'), consulta)).toBe(true);
  });

  it('PHRASE exige os tokens na ordem e contíguos', () => {
    expect(bloqueia(neg('de ingles', 'PHRASE'), consulta)).toBe(true);
    expect(bloqueia(neg('curso gratis', 'PHRASE'), consulta)).toBe(false);
  });

  it('BROAD pega todos os tokens em qualquer ordem — é o mais largo', () => {
    expect(bloqueia(neg('curso gratis', 'BROAD'), consulta)).toBe(true);
    expect(bloqueia(neg('gratis curso', 'BROAD'), consulta)).toBe(true);
    expect(bloqueia(neg('curso alemao', 'BROAD'), consulta)).toBe(false);
  });

  it('uma POSITIVA nunca bloqueia', () => {
    expect(bloqueia(pos('curso gratis', 'BROAD'), consulta)).toBe(false);
  });
});

describe('identidade e deduplicação', () => {
  it('o match type faz parte da identidade', () => {
    expect(identidade(neg('curso', 'EXACT'))).not.toBe(identidade(neg('curso', 'PHRASE')));
  });

  it('mesmo texto com match types diferentes são DOIS critérios', () => {
    const { unicos, descartados } = deduplicar([neg('curso', 'EXACT'), neg('curso', 'PHRASE')]);
    expect(unicos).toHaveLength(2);
    expect(descartados).toHaveLength(0);
  });

  it('acento e espaço duplo colapsam, e o primeiro declarado vence', () => {
    const a = neg('simulador grátis', 'PHRASE', { motivo: 'primeiro' });
    const b = neg('SIMULADOR  GRÁTIS', 'PHRASE', { motivo: 'segundo' });
    const { unicos, descartados } = deduplicar([a, b]);
    expect(unicos).toHaveLength(1);
    expect(unicos[0].motivo).toBe('primeiro');
    expect(descartados[0].dono.motivo).toBe('primeiro');
  });
});

describe('conflitos', () => {
  it('detecta a negativa que ANULA uma positiva', () => {
    const c = conflitos([pos('saque anual fgts'), neg('saque', 'PHRASE', { nivel: 'CAMPAIGN' })]);
    expect(c).toHaveLength(1);
    expect(c[0].positiva.texto).toBe('saque anual fgts');
  });

  it('respeita o escopo: negativa de um grupo não alcança outro', () => {
    const p = pos('saque anual', 'PHRASE', { grupo: 'ACESSO' });
    expect(conflitos([p, neg('saque', 'PHRASE', { grupo: 'ACESSO' })])).toHaveLength(1);
    expect(conflitos([p, neg('saque', 'PHRASE', { grupo: 'VALOR' })])).toHaveLength(0);
  });

  it('negativa de campanha alcança toda positiva', () => {
    const p = pos('saque anual', 'PHRASE', { grupo: 'VALOR' });
    expect(conflitos([p, neg('saque', 'PHRASE', { nivel: 'CAMPAIGN', grupo: null })]))
      .toHaveLength(1);
  });
});

describe('a regra da ausência', () => {
  it('critério novo nasce sem motivo e sem evidência inventados', () => {
    const c = novoCriterio('simulador');
    expect(c.motivo).toBeNull();
    expect(c.evidencia).toBeNull();
    expect(c.observado_em).toBeNull();
    expect(c.aprovado_por).toBeNull();
    expect(medido(c)).toBe(false);
  });

  it('só evidência MEDIDO conta como medida', () => {
    expect(medido(neg('x', 'PHRASE', {
      evidencia: { tipo: 'HIPOTESE', fonte: 'modelo' },
    }))).toBe(false);
    expect(medido(neg('x', 'PHRASE', {
      evidencia: {
        tipo: 'MEDIDO', fonte: 'search_term_view',
        janela_inicio: '2026-08-01', janela_fim: '2026-08-27',
        metricas: { impressoes: 312 },
      },
    }))).toBe(true);
  });
});

describe('as explicações que a tela mostra', () => {
  it('dizem o alcance em português, sem o nome do enum', () => {
    expect(explicarAlcance(neg('gratis', 'EXACT'))).toContain('idêntica');
    expect(explicarAlcance(neg('curso gratis', 'BROAD'))).toContain('qualquer ordem');
    expect(explicarAlcance(neg('curso gratis', 'BROAD'))).not.toContain('BROAD');
  });

  it('dizem onde a exclusão vale', () => {
    expect(explicarEscopo(neg('x', 'PHRASE', { nivel: 'CAMPAIGN', grupo: null })))
      .toBe('na campanha inteira');
    // Com um conjunto só (P7), "em todos os grupos" seria tecnicamente
    // verdadeiro e enganoso: sugere uma escolha que a campanha não tem.
    expect(explicarEscopo(neg('x', 'PHRASE', { grupo: null }))).toBe('no grupo de anúncios');
    expect(explicarEscopo(neg('x', 'PHRASE', { grupo: 'ACESSO' }))).toBe('só no grupo ACESSO');
  });
});

describe('resumir', () => {
  it('conta cada nível separadamente e marca as hipóteses', () => {
    const r = resumir([
      pos('saque anual fgts'),
      pos('valor do saque'),
      neg('emprestimo', 'PHRASE', { nivel: 'CAMPAIGN', grupo: null }),
      neg('simulador', 'PHRASE'),
    ]);
    expect(r.ativam).toBe(2);
    expect(r.excluidasNaCampanha).toBe(1);
    expect(r.excluidasNoGrupo).toBe(1);
    expect(r.hipoteses).toBe(2);
    expect(r.conflitos).toHaveLength(0);
  });
});
