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
  ROTULO_DA_LEITURA,
  ROTULO_DA_MENSURACAO,
  textoDaFonteDoSinal,
  textoDaMetaEfetiva,
  textoDoFrescor,
  tomDoBloqueio,
  tomDoEstado,
  type ContratoDeCanal,
  type MetaEfetiva,
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
      // ⚠️ `null` é "ninguém leu os três recursos que decidem a meta
      // efetiva", e não "não há plano". O servidor sempre emite a chave.
      plano: null,
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

/**
 * A tradução do plano de mensuração para linguagem de operador.
 *
 * ⚠️ Cada função aqui é FORMATAÇÃO, e os testes cobram exatamente isso: nenhuma
 * delas escolhe meta, deriva prontidão ou inventa fallback. Cada ramo
 * corresponde a um estado que o SERVIDOR já distinguiu, e a frase só o diz em
 * português.
 */
describe('o plano de mensuração, em português', () => {
  function meta(over: Partial<MetaEfetiva> = {}): MetaEfetiva {
    return {
      nivel: 'CUSTOMER',
      nivel_estado: 'com_dados',
      nivel_decidido: true,
      custom_conversion_goal: null,
      usa_meta_customizada: false,
      campaign_id: null,
      metas_da_conta: [],
      metas_da_conta_estado: 'com_dados',
      metas_da_campanha: [],
      metas_da_campanha_estado: 'inelegivel',
      metas_que_mandam: [],
      metas_biddable: [
        {
          categoria: 'PURCHASE',
          origem: 'WEBSITE',
          biddable: true,
          campaign: null,
          semantica: 'PURCHASE/WEBSITE',
        },
      ],
      resolvida: true,
      causa: null,
      ...over,
    };
  }

  it('não confunde "não sei qual nível manda" com "não há meta"', () => {
    // ⚠️ `metas_biddable: null` é ignorância; `[]` é conclusão. As duas pedem
    // coisas opostas, e uma frase única apagaria a diferença.
    expect(
      textoDaMetaEfetiva(meta({ nivel_decidido: false, metas_biddable: null })),
    ).toMatch(/não se sabe/);
    expect(textoDaMetaEfetiva(meta({ metas_biddable: null }))).toMatch(
      /não foram lidas/,
    );
    expect(textoDaMetaEfetiva(meta({ metas_biddable: [] }))).toMatch(
      /nenhuma meta/,
    );
  });

  it('diz o objetivo E de que nível ele vem', () => {
    expect(textoDaMetaEfetiva(meta())).toBe('PURCHASE/WEBSITE (da conta)');
    expect(textoDaMetaEfetiva(meta({ nivel: 'CAMPAIGN' }))).toBe(
      'PURCHASE/WEBSITE (da campanha)',
    );
  });

  it('meta customizada não é lida como meta resolvida', () => {
    expect(
      textoDaMetaEfetiva(
        meta({ usa_meta_customizada: true, custom_conversion_goal: 'x' }),
      ),
    ).toMatch(/customizada/);
  });

  it('"nunca recebeu conversão" não vira "sem dados"', () => {
    // ⚠️ É o fato mais caro desta tela: a ação existe, a janela foi consultada,
    // e nada chegou. Um "sem dados" faria isso parecer uma leitura que faltou.
    expect(
      textoDoFrescor({
        estado: 'vazio_confirmado',
        janela_dias: null,
        ultima_conversao_em: null,
        dias_desde_a_ultima: null,
        conversoes_na_janela: 0,
        conversion_action_id: '1',
        comprovado: false,
        causa: null,
      }),
    ).toBe('nunca recebeu conversão');
  });

  it('não inventa distância quando ninguém contou os dias', () => {
    expect(
      textoDoFrescor({
        estado: 'com_dados',
        janela_dias: null,
        ultima_conversao_em: '2026-08-30',
        dias_desde_a_ultima: null,
        conversoes_na_janela: 1,
        conversion_action_id: '1',
        comprovado: true,
        causa: null,
      }),
    ).toBe('última conversão em 2026-08-30');
  });

  it('a fonte do sinal mostra o ID NUMÉRICO e o dono, não só o nome', () => {
    // ⚠️ É por ele que o destino de conversão offline é resolvido. Mostrar só o
    // nome ensinaria o operador a identificar a ação pelo campo errado — o
    // mesmo campo que a Data Manager não aceita.
    const texto = textoDaFonteDoSinal({
      versao: 1,
      customer_id: '5478096539',
      login_customer_id: '6016739364',
      campaign_id: null,
      chave_intencao: null,
      meta_efetiva: meta(),
      acoes: [],
      acoes_estado: 'com_dados',
      acao_alvo: {
        id: '7466919994',
        resource_name: 'customers/5478096539/conversionActions/7466919994',
        owner_customer_id: '5478096539',
        nome: 'Compra no site',
        categoria: 'PURCHASE',
        origem: 'WEBSITE',
        tipo: 'WEBPAGE',
        status: 'ENABLED',
        primaria: true,
        primaria_efetiva: true,
        incluida_em_metricas: true,
        semantica: 'PURCHASE/WEBSITE',
        aceita_como_destino: true,
      },
      acao_alvo_causa: null,
      destino: {
        resolvido: true,
        operating_account_id: '5478096539',
        product_destination_id: '7466919994',
        conversion_action_resource: 'x',
        tipo_da_acao: 'WEBPAGE',
        causa: null,
      },
      frescor: {
        estado: 'com_dados',
        janela_dias: null,
        ultima_conversao_em: '2026-08-30',
        dias_desde_a_ultima: 2,
        conversoes_na_janela: 1,
        conversion_action_id: '7466919994',
        comprovado: true,
        causa: null,
      },
      marcacao: {
        estado: 'com_dados',
        auto_tagging: true,
        conversion_tracking_id: null,
        conversion_tracking_owner_id: null,
        cross_account_conversion_tracking_id: null,
        conversion_tracking_status: null,
        aceitou_termos_de_dados: true,
        enhanced_conversions_for_leads: false,
        acoes_de_ga4: [],
        acoes_com_tag: ['7466919994'],
        click_ids_suportados: ['gclid', 'gbraid', 'wbraid'],
      },
      proposta_de_acao: null,
      completo: true,
      bloqueadores: [],
      impressao: 'a'.repeat(64),
    });
    expect(texto).toContain('#7466919994');
    expect(texto).toContain('5478096539');
  });

  it('os sete estados de leitura têm rótulo próprio, sem colapso', () => {
    const rotulos = Object.values(ROTULO_DA_LEITURA);
    expect(new Set(rotulos).size).toBe(rotulos.length);
    // ⚠️ "li e não há nenhum" e "ninguém pediu" pedem coisas opostas.
    expect(ROTULO_DA_LEITURA.vazio_confirmado).not.toBe(
      ROTULO_DA_LEITURA.nao_coletado,
    );
  });

  it('os cinco estados de prontidão têm rótulo próprio, sem colapso', () => {
    const rotulos = Object.values(ROTULO_DA_MENSURACAO);
    expect(new Set(rotulos).size).toBe(rotulos.length);
    expect(ROTULO_DA_MENSURACAO.INDETERMINADO).not.toBe(
      ROTULO_DA_MENSURACAO.NAO_PRONTO,
    );
  });
});
