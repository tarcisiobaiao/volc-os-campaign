/**
 * O que a tela NÃO pode fazer com o contrato dos canais.
 *
 * Cada teste aqui nomeia um colapso que custaria uma decisão errada:
 * ignorância desenhada como recusa, ausência desenhada como zero, e
 * autorização recalculada no navegador.
 */
import { describe, expect, it } from 'vitest';

import {
  A_QUEM_PEDIR,
  ORDEM_DOS_PORTOES,
  ROTULO_DO_PORTAO,
  incoerenciasDoContrato,
  numeroOuTraco,
  portao,
  portoesAbertos,
  tomDoBloqueio,
  tomDoEstado,
  type ContratoDeCanal,
  type PortaoDeCanal,
} from '@/lib/trafego/canais';

function p(
  nome: PortaoDeCanal['nome'],
  estado: PortaoDeCanal['estado'],
  bloqueadores: PortaoDeCanal['bloqueadores'] = [],
): PortaoDeCanal {
  return { nome, estado, aberto: estado === 'PERMITIDO', bloqueadores };
}

function contrato(portoes: PortaoDeCanal[]): ContratoDeCanal {
  return {
    plataforma: 'GOOGLE_ADS',
    canal: 'SEARCH',
    rotulo: 'Search',
    manifesto: {
      plataforma: 'GOOGLE_ADS',
      canal: 'SEARCH',
      rotulo: 'Search',
      hierarquia: [],
      paineis: [],
      campos_do_pedido: [],
      capacidades: [],
      provas_obrigatorias: [],
      indisponibilidades: [],
      sabe_criar: true,
      sabe_provar: true,
    },
    portoes,
    assets: {
      estado: 'PERMITIDO',
      recursos: ['texto'],
      quantidade: 1,
      fonte: 'x',
      causa: null,
    },
    mensuracao: {
      lida: false,
      conversion_goal_status: 'INDETERMINADO',
      conversion_signal_status: 'INDETERMINADO',
      signal_sources: [],
      measurement_readiness: 'INDETERMINADO',
      data_manager_status: 'INDETERMINADO',
      observability_status: 'INDETERMINADO',
      smart_bidding_eligible: false,
      fonte: 'ninguém leu',
      notas: {},
    },
    observabilidade: {
      estado: 'INDETERMINADO',
      coletor: null,
      causa: 'ninguém contou',
      campanhas_no_espelho: null,
      contagem_truncada: false,
    },
    operacional: {},
  };
}

describe('os quatro estados não colapsam em dois', () => {
  it('INDETERMINADO tem tom PRÓPRIO e nunca herda o de BLOQUEADO', () => {
    // Pintar "não sei" de vermelho afirma uma recusa que ninguém fez, e ensina
    // o operador a tratar todo vermelho como ruído.
    expect(tomDoEstado('INDETERMINADO')).not.toBe(tomDoEstado('BLOQUEADO'));
    expect(tomDoEstado('INDETERMINADO')).toBe('ignorado');
  });

  it('NAO_APLICAVEL não vira BLOQUEADO', () => {
    expect(tomDoEstado('NAO_APLICAVEL')).not.toBe(tomDoEstado('BLOQUEADO'));
  });

  it('só PERMITIDO produz o tom de aberto', () => {
    expect(tomDoEstado('PERMITIDO')).toBe('aberto');
    for (const e of ['BLOQUEADO', 'INDETERMINADO', 'NAO_APLICAVEL'] as const) {
      expect(tomDoEstado(e)).not.toBe('aberto');
    }
  });
});

describe('o tom de um bloqueio não é o tom do portão', () => {
  it('decisão registrada não é erro', () => {
    // "Não habilitado nesta versão" não é falha, não é ausência e não é zero.
    expect(tomDoBloqueio('produto')).toBe('decidido');
    expect(tomDoBloqueio('politica')).toBe('decidido');
  });

  it('permissão, ausência e falta de prova são três coisas', () => {
    const tons = new Set([
      tomDoBloqueio('operador'),
      tomDoBloqueio('construtor'),
      tomDoBloqueio('mensuracao'),
    ]);
    expect(tons.size).toBe(3);
  });

  it('toda origem sabe dizer a quem pedir', () => {
    for (const origem of [
      'construtor', 'manifesto', 'servidor', 'operador',
      'politica', 'mensuracao', 'observabilidade', 'produto',
    ] as const) {
      expect(A_QUEM_PEDIR[origem]).toBeTruthy();
      expect(tomDoBloqueio(origem)).toBeTruthy();
    }
  });
});

describe('ausência não vira zero', () => {
  it('null vira traço, e nunca 0', () => {
    expect(numeroOuTraco(null)).toBe('—');
    expect(numeroOuTraco(undefined)).toBe('—');
    expect(numeroOuTraco(null)).not.toBe('0');
  });

  it('zero medido continua sendo zero', () => {
    // "contei e não há nenhuma" é um fato, e apagá-lo seria tão errado quanto
    // inventá-lo.
    expect(numeroOuTraco(0)).toBe('0');
  });

  it('uma contagem truncada é declarada como piso', () => {
    expect(numeroOuTraco(500, '+')).toBe('500+');
  });
});

describe('a tela audita o contrato, e não o recalcula', () => {
  it('liberado com motivo de recusa é denunciado', () => {
    const c = contrato([
      { nome: 'planejavel', estado: 'PERMITIDO', aberto: true,
        bloqueadores: [{ codigo: 'x', causa: 'y', origem: 'produto',
                         observado_em: null, revalidacao: null }] },
    ]);
    expect(incoerenciasDoContrato(c)[0]).toContain('ao mesmo tempo');
  });

  it('fechado sem causa é denunciado', () => {
    const c = contrato([p('validavel', 'BLOQUEADO')]);
    expect(incoerenciasDoContrato(c)[0]).toContain('sem dizer por quê');
  });

  it('veredito que discorda do estado é denunciado', () => {
    const c = contrato([
      { nome: 'ativavel', estado: 'BLOQUEADO', aberto: true,
        bloqueadores: [{ codigo: 'x', causa: 'y', origem: 'produto',
                         observado_em: null, revalidacao: null }] },
    ]);
    expect(incoerenciasDoContrato(c).some((i) => i.includes('discordam'))).toBe(true);
  });

  it('um contrato coerente não produz achado', () => {
    const c = contrato([
      p('planejavel', 'PERMITIDO'),
      p('validavel', 'BLOQUEADO', [{ codigo: 'x', causa: 'porque sim',
        origem: 'servidor', observado_em: null, revalidacao: null }]),
    ]);
    expect(incoerenciasDoContrato(c)).toEqual([]);
  });
});

describe('nenhum campo é derivado no navegador', () => {
  it('portoesAbertos conta `aberto`, e não o estado', () => {
    // Reimplementar a regra aqui criaria uma segunda definição de "aberto", e
    // ela divergiria no dia em que o servidor mudasse a dele.
    const c = contrato([
      { nome: 'planejavel', estado: 'PERMITIDO', aberto: false, bloqueadores: [] },
    ]);
    expect(portoesAbertos(c)).toBe(0);
  });
});

describe('os quatro portões', () => {
  it('a ordem é a do trabalho', () => {
    expect(ORDEM_DOS_PORTOES).toEqual([
      'planejavel', 'validavel', 'criavel_pausada', 'ativavel',
    ]);
  });

  it('"criável pausada" carrega a restrição no nome', () => {
    // Chamar o portão de "criável" faria o operador ler permissão de gasto
    // onde há permissão de existência.
    expect(ROTULO_DO_PORTAO.criavel_pausada).toContain('pausada');
  });

  it('portão que o servidor não mandou devolve null, e não um inventado', () => {
    expect(portao(contrato([]), 'ativavel')).toBeNull();
  });
});
