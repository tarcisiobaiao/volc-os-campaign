// @vitest-environment jsdom
/**
 * O painel da mensuração — e as cinco formas de ele mentir.
 *
 * ## O buraco que ele fecha
 *
 * O servidor emitia os portões e a tela DESCARTAVA quase tudo:
 * `data_manager_status` e `observability_status` estavam declarados em
 * `src/lib/trafego/canais.ts` e não apareciam em JSX nenhum; `activation_blockers`
 * e `smart_bidding_eligible` não tinham consumidor; e os doze campos de
 * `InventarioDeMarcacao` — cobertura de click IDs, auto-tagging, dono do
 * tracking — nunca chegaram à tela.
 *
 * ## As cinco mentiras que este arquivo cobra
 *
 * 1. **verde por configuração** — auto-tagging ligado, ou `PARCIAL`, virando
 *    selo positivo;
 * 2. **"sem dados"** no lugar de três frases que pedem coisas opostas: zero
 *    MEDIDO, ninguém leu, e a leitura falhou;
 * 3. **bloqueadores numa lista só** — política e medição misturadas, fazendo o
 *    operador tentar consertar autorização com instrumentação;
 * 4. **ausência de perfil lida como "não mede nada"**;
 * 5. **dado de usuário na tela** — `gclid` cru, chave inteira, identidade
 *    copiável.
 */
import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import {
  portoesDaProntidao,
  separarBloqueadores,
  textoDaCoberturaDeClickIds,
  textoDaFonte,
  textoDaRegraDeValor,
  tomDoEstado,
  type PerfilDeMensuracao,
  type PortoesDaMensuracao,
} from '@/lib/trafego/portoes';
import type { MetaEfetiva, PlanoDeMensuracao } from '@/lib/trafego/canais';
import {
  PainelDaMensuracao,
  textoDaProcedenciaDaMeta,
  textoDoUltimoMomento,
} from '@/components/trafego/canais/PainelDaMensuracao';

afterEach(cleanup);

const CONTA = '5478096539';

function portoes(over: Partial<PortoesDaMensuracao> = {}): PortoesDaMensuracao {
  return {
    creation_plan_ready: 'PRONTO',
    campaign_birth: 'NAO_PRONTO',
    measurement_ready: 'INDETERMINADO',
    observability_ready: 'INDETERMINADO',
    activation_ready: 'INDETERMINADO',
    smart_bidding_ready: 'INDETERMINADO',
    data_manager_ready: 'NAO_PRONTO',
    ...over,
  };
}

function perfil(over: Partial<PerfilDeMensuracao> = {}): PerfilDeMensuracao {
  return {
    negocio: 'portal-mundo-mais',
    intencao: 'bpc-loas',
    funil: 'acao',
    evento: 'lead-qualificado',
    acao_owner_id: '1234567890',
    acao_id: '7498530235',
    semantica: 'PURCHASE/WEBSITE',
    regra_de_valor: { modo: 'sem_valor', valor: null, moeda: null },
    janela: {
      estado: 'nao_declarada',
      dias_de_clique: null,
      dias_de_engajamento: null,
      modelo: null,
      causa: 'ninguém declarou janela nem modelo de atribuição.',
    },
    fonte_do_sinal: 'caminho_declarado',
    consentimento: 'nao_declarado',
    causa_sem_acao: null,
    aplicavel_a_ativacao: true,
    aplicavel_a_smart_bidding: false,
    aplicavel_a_envio_offline: false,
    chave: 'd'.repeat(64),
    ...over,
  };
}

function meta(over: Partial<MetaEfetiva> = {}): MetaEfetiva {
  return {
    nivel: 'CUSTOMER',
    nivel_estado: 'inelegivel',
    nivel_decidido: true,
    nivel_herdado: true,
    custom_conversion_goal: null,
    usa_meta_customizada: false,
    campaign_id: null,
    metas_da_conta: [],
    metas_da_conta_estado: 'com_dados',
    metas_da_campanha: [],
    metas_da_campanha_estado: 'inelegivel',
    metas_que_mandam: [],
    metas_biddable: [],
    resolvida: false,
    causa: null,
    ...over,
  } as MetaEfetiva;
}

function plano(over: Partial<PlanoDeMensuracao> = {}): PlanoDeMensuracao {
  return {
    versao: 1,
    customer_id: CONTA,
    login_customer_id: '1234567890',
    campaign_id: null,
    chave_intencao: 'c'.repeat(64),
    meta_efetiva: meta(),
    acoes: [],
    acoes_estado: 'com_dados',
    acao_alvo: null,
    acao_alvo_causa: 'nenhuma ação da conta tem a semântica desta campanha.',
    destino: {
      resolvido: false,
      operating_account_id: null,
      product_destination_id: null,
      conversion_action_resource: null,
      tipo_da_acao: null,
      causa: 'sem ação eleita não há destino endereçável.',
    },
    frescor: {
      estado: 'nao_coletado',
      janela_dias: null,
      ultima_conversao_em: null,
      dias_desde_a_ultima: null,
      conversoes_na_janela: null,
      conversion_action_id: null,
      comprovado: false,
      causa: 'o frescor não foi consultado nesta sessão.',
    },
    marcacao: {
      estado: 'com_dados',
      auto_tagging: true,
      conversion_tracking_id: '123',
      conversion_tracking_owner_id: '1234567890',
      cross_account_conversion_tracking_id: null,
      conversion_tracking_status: 'CONVERSION_TRACKING_MANAGED_BY_SELF',
      fuso: 'America/Sao_Paulo',
      aceitou_termos_de_dados: null,
      enhanced_conversions_for_leads: null,
      acoes_de_ga4: [],
      acoes_com_tag: ['7498530235'],
      click_ids_suportados: ['gclid', 'gbraid', 'wbraid'],
    },
    proposta_de_acao: null,
    completo: false,
    bloqueadores: ['nenhuma ação de conversão mede o que esta campanha persegue.'],
    impressao: 'a'.repeat(64),
    ...over,
  } as PlanoDeMensuracao;
}

function montar(over: Partial<React.ComponentProps<typeof PainelDaMensuracao>> = {}) {
  return render(
    <PainelDaMensuracao
      portoes={portoes()}
      perfil={perfil()}
      plano={plano()}
      bloqueadores={[]}
      customerId={CONTA}
      persistido={false}
      {...over}
    />,
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// MENTIRA 1 — verde por configuração
// ═══════════════════════════════════════════════════════════════════════════

describe('verde só com prova', () => {
  it('só PRONTO produz tom positivo', () => {
    expect(tomDoEstado('PRONTO')).toBe('provado');
    expect(tomDoEstado('PARCIAL')).toBe('ignorado');
    expect(tomDoEstado('INDETERMINADO')).toBe('ignorado');
    expect(tomDoEstado('NAO_PRONTO')).toBe('negado');
  });

  it('PARCIAL não é um degrau para o verde', () => {
    // ⚠️ PARCIAL é "li alguma coisa verdadeira e não o bastante". Pintá-lo de
    // verde-claro ensinaria o operador a lê-lo como quase-pronto.
    expect(tomDoEstado('PARCIAL')).not.toBe('provado');
  });

  it('auto-tagging ligado aparece dizendo que não é conversão', () => {
    montar();
    const texto = screen.getByText(/auto-tagging ligado/i).textContent ?? '';
    expect(texto).toMatch(/não é conversão/i);
  });

  it('auto-tagging não lido não vira desligado', () => {
    // ⚠️ Os dois pedem coisas opostas: um pede ler a conta, o outro pede ligar
    // o auto-tagging. Colapsá-los mandaria o operador mexer na conta certa pelo
    // motivo errado.
    expect(textoDaCoberturaDeClickIds(['gclid'], null)).toMatch(/não lido/);
    expect(textoDaCoberturaDeClickIds(['gclid'], false)).toMatch(/DESLIGADO/);
    expect(textoDaCoberturaDeClickIds(['gclid'], null)).not.toMatch(/DESLIGADO/);
  });

  it('caminho declarado não é lido como sinal chegando', () => {
    expect(textoDaFonte('caminho_declarado')).toMatch(/nenhuma conversão/i);
    montar();
    expect(
      screen.getByText(/instrumentação a conferir/i),
    ).toBeTruthy();
  });

  it('todo portão fechado mostra a EXIGÊNCIA, e o aberto não repete', () => {
    const { container } = montar({
      portoes: portoes({ measurement_ready: 'PRONTO' }),
    });
    const medicao = container.querySelector('[data-portao="measurement_ready"]');
    const ativacao = container.querySelector('[data-portao="activation_ready"]');
    expect(medicao?.textContent).not.toMatch(/exige/i);
    expect(ativacao?.textContent).toMatch(/exige/i);
  });

  it('os sete portões aparecem, e cada um com seu estado', () => {
    const { container } = montar();
    expect(container.querySelectorAll('[data-portao]')).toHaveLength(7);
    expect(
      container.querySelector('[data-portao="smart_bidding_ready"]')
        ?.getAttribute('data-estado'),
    ).toBe('INDETERMINADO');
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// MENTIRA 2 — "sem dados"
// ═══════════════════════════════════════════════════════════════════════════

describe('três frases, nunca "sem dados"', () => {
  it('zero MEDIDO não é ausência de leitura', () => {
    const texto = textoDoUltimoMomento(
      plano({
        frescor: {
          ...plano().frescor,
          estado: 'vazio_confirmado',
          conversoes_na_janela: 0,
        },
      }),
    );
    expect(texto).toMatch(/zero MEDIDO/);
    expect(texto).not.toMatch(/sem dados/i);
  });

  it('ninguém leu e a leitura falhou são frases diferentes', () => {
    const naoLido = textoDoUltimoMomento(plano());
    const falhou = textoDoUltimoMomento(
      plano({ frescor: { ...plano().frescor, estado: 'falhou' } }),
    );
    expect(naoLido).not.toBe(falhou);
    expect(naoLido).toMatch(/ninguém leu/i);
    expect(falhou).toMatch(/falhou/i);
  });

  it('dias desconhecidos nunca viram um número', () => {
    // ⚠️ Um `999` no lugar de `null` viraria um gráfico com cara de dado.
    const texto = textoDoUltimoMomento(
      plano({
        frescor: {
          ...plano().frescor,
          estado: 'com_dados',
          ultima_conversao_em: '2026-08-20',
          dias_desde_a_ultima: null,
          conversoes_na_janela: 3,
          comprovado: false,
        },
      }),
    );
    expect(texto).toMatch(/não se sabe/);
    expect(texto).not.toMatch(/\d+ d\)/);
  });

  it('a data e os dias aparecem quando os dois existem', () => {
    expect(
      textoDoUltimoMomento(
        plano({
          frescor: {
            ...plano().frescor,
            estado: 'com_dados',
            ultima_conversao_em: '2026-08-31',
            dias_desde_a_ultima: 2,
            conversoes_na_janela: 14,
            comprovado: true,
          },
        }),
      ),
    ).toBe('2026-08-31 (há 2 d)');
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// MENTIRA 3 — bloqueadores numa lista só
// ═══════════════════════════════════════════════════════════════════════════

describe('bloqueadores separados por natureza', () => {
  const MEDIR = 'nenhuma fonte de sinal de conversão comprovada';
  const POLITICA = 'a autorização em vigor cobre criar pausada e nada além';

  it('medição e política aparecem em grupos diferentes', () => {
    montar({ bloqueadores: [MEDIR, POLITICA], bloqueadoresMateriais: [MEDIR] });
    expect(screen.getByTestId('bloqueadores-medicao').textContent).toContain(MEDIR);
    expect(screen.getByTestId('bloqueadores-outros').textContent).toContain(
      POLITICA,
    );
  });

  it('sem a lista MATERIAL do servidor, nada é classificado como medição', () => {
    // ⚠️ Um servidor que não respondeu a distinção não pode fazer a tela
    // afirmar que uma razão é de medição. Classificar por palavra seria
    // adivinhar a natureza de uma frase que o servidor já sabia.
    const { medicao, outros } = separarBloqueadores([MEDIR, POLITICA], undefined);
    expect(medicao).toEqual([]);
    expect(outros).toEqual([MEDIR, POLITICA]);
  });

  it('lista vazia não desenha caixa nenhuma', () => {
    montar({ bloqueadores: [] });
    expect(screen.queryByTestId('bloqueadores-medicao')).toBeNull();
    expect(screen.queryByTestId('bloqueadores-outros')).toBeNull();
  });

  it('todas as razões aparecem, e não só a primeira', () => {
    montar({
      bloqueadores: [MEDIR, POLITICA, 'observabilidade não provada'],
      bloqueadoresMateriais: [MEDIR, 'observabilidade não provada'],
    });
    expect(screen.getByTestId('bloqueadores-medicao').querySelectorAll('li'))
      .toHaveLength(2);
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// MENTIRA 4 — ausência de perfil lida como "não mede nada"
// ═══════════════════════════════════════════════════════════════════════════

describe('perfil de mensuração', () => {
  it('perfil ausente diz o que a ausência significa', () => {
    montar({ perfil: null });
    const texto = screen.getByTestId('perfil-ausente').textContent ?? '';
    expect(texto).toMatch(/não significa que a campanha não mede/i);
    expect(texto).toMatch(/ninguém disse qual oferta/i);
  });

  it('mostra oferta, funil e evento de negócio', () => {
    montar();
    expect(screen.getByText(/bpc-loas/)).toBeTruthy();
    expect(screen.getByText(/funil de ação/)).toBeTruthy();
    expect(screen.getByText('lead-qualificado')).toBeTruthy();
  });

  it('a conta DONA aparece quando não é a que roda a campanha', () => {
    montar({ perfil: perfil({ acao_owner_id: '7777777777' }) });
    expect(screen.getByText(/conta 7777777777.*centralizada/i)).toBeTruthy();
  });

  it('a própria conta é dita como própria, e não repetida como id', () => {
    montar({ perfil: perfil({ acao_owner_id: CONTA }) });
    expect(screen.getByText(/da própria conta/)).toBeTruthy();
  });

  it('sem ação eleita, mostra a CAUSA e não um vazio', () => {
    montar({
      perfil: perfil({
        acao_id: null,
        acao_owner_id: null,
        semantica: null,
        causa_sem_acao: 'nenhuma ação habilitada corresponde ao objetivo.',
      }),
    });
    expect(
      screen.getByText(/nenhuma ação habilitada corresponde/),
    ).toBeTruthy();
  });

  it('"sem valor" é decisão declarada, e não lacuna', () => {
    expect(textoDaRegraDeValor({ modo: 'sem_valor', valor: null, moeda: null }))
      .toBe('sem valor declarado');
    expect(
      textoDaRegraDeValor({ modo: 'fixo', valor: '49.90', moeda: 'BRL' }),
    ).toBe('valor fixo de 49.90 BRL');
  });

  it('o consentimento é dito como da CONTA, não do visitante', () => {
    montar();
    expect(
      screen.getByText(/aceite de termos do anunciante, não o consentimento do visitante/i),
    ).toBeTruthy();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// MENTIRA 5 — dado sensível na tela
// ═══════════════════════════════════════════════════════════════════════════

describe('o que a tela NÃO mostra', () => {
  it('a chave do perfil aparece truncada', () => {
    const { container } = montar();
    expect(container.textContent).not.toContain('d'.repeat(64));
    expect(container.textContent).toContain('dddddddddddd…');
  });

  it('a impressão do plano não vai para a tela', () => {
    const { container } = montar();
    expect(container.textContent).not.toContain('a'.repeat(64));
  });

  it('a chave de intenção inteira não vai para a tela', () => {
    const { container } = montar();
    expect(container.textContent).not.toContain('c'.repeat(64));
  });

  it('o plano_id aparece truncado', () => {
    const { container } = montar({
      persistido: true,
      planoId: '11111111-2222-3333-4444-555555555555',
    });
    expect(container.textContent).not.toContain(
      '11111111-2222-3333-4444-555555555555',
    );
    expect(container.textContent).toContain('11111111…');
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// Procedência da meta — herdada, da campanha, ou customizada
// ═══════════════════════════════════════════════════════════════════════════

describe('herdada ou específica da campanha', () => {
  it('herança INFERIDA é dita como inferida', () => {
    expect(textoDaProcedenciaDaMeta(plano())).toMatch(/INFERIDA/);
  });

  it('nível lido do recurso é dito como lido', () => {
    expect(
      textoDaProcedenciaDaMeta(
        plano({
          meta_efetiva: meta({
            nivel: 'CAMPAIGN',
            nivel_estado: 'com_dados',
            nivel_herdado: false,
          }),
        }),
      ),
    ).toBe('da campanha — lida do recurso');
  });

  it('meta customizada tira as listas do comando, e a tela diz isso', () => {
    expect(
      textoDaProcedenciaDaMeta(
        plano({ meta_efetiva: meta({ usa_meta_customizada: true }) }),
      ),
    ).toMatch(/não respeita primary_for_goal/);
  });

  it('nível não decidido não vira herança', () => {
    expect(
      textoDaProcedenciaDaMeta(
        plano({ meta_efetiva: meta({ nivel_decidido: false }) }),
      ),
    ).toMatch(/não se sabe qual nível manda/);
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// Registro do plano
// ═══════════════════════════════════════════════════════════════════════════

describe('registro', () => {
  it('não gravado vem com a razão do servidor', () => {
    montar({ persistido: false, porque: '/provar não escreve.' });
    expect(screen.getByText('/provar não escreve.')).toBeTruthy();
  });

  it('gravado não inventa razão', () => {
    montar({ persistido: true, planoId: 'abcdef00-1111-2222-3333-444444444444' });
    expect(screen.getByText(/gravado/)).toBeTruthy();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// A adaptação da resposta de /provar — falha FECHADA
// ═══════════════════════════════════════════════════════════════════════════

describe('portoesDaProntidao', () => {
  it('ausência de campo vira INDETERMINADO, e nunca PRONTO', () => {
    // ⚠️ Um servidor anterior a 02/09/2026 não emite os nomes canônicos.
    // Tratar a ausência como pronto pintaria de verde um portão que ninguém
    // avaliou; deixá-la vazar como `undefined` quebraria o Record de cores.
    const p = portoesDaProntidao({});
    expect(Object.values(p).every((e) => e === 'INDETERMINADO')).toBe(true);
  });

  it('prontidão nula não explode e falha fechada', () => {
    expect(portoesDaProntidao(null).activation_ready).toBe('INDETERMINADO');
    expect(portoesDaProntidao(undefined).smart_bidding_ready).toBe('INDETERMINADO');
  });

  it('um estado que este código não conhece vira INDETERMINADO', () => {
    // Um servidor futuro que invente `QUASE_PRONTO` não pinta nada de verde.
    expect(
      portoesDaProntidao({ measurement_ready: 'QUASE_PRONTO' }).measurement_ready,
    ).toBe('INDETERMINADO');
  });

  it('os nomes canônicos têm precedência sobre os antigos', () => {
    expect(
      portoesDaProntidao({
        measurement_ready: 'PRONTO',
        measurement_readiness: 'NAO_PRONTO',
      }).measurement_ready,
    ).toBe('PRONTO');
  });

  it('os nomes antigos são o fallback enquanto existirem', () => {
    const p = portoesDaProntidao({
      measurement_readiness: 'PARCIAL',
      observability_status: 'PRONTO',
      data_manager_status: 'NAO_PRONTO',
    });
    expect(p.measurement_ready).toBe('PARCIAL');
    expect(p.observability_ready).toBe('PRONTO');
    expect(p.data_manager_ready).toBe('NAO_PRONTO');
  });
});
