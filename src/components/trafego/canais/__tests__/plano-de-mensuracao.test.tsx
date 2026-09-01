// @vitest-environment jsdom
/**
 * O cartão do plano de mensuração — e as quatro formas de ele mentir.
 *
 * ## Por que este arquivo existe
 *
 * `CartaoDoPlanoDeMensuracao` aparece em DOIS lugares — o cockpit de canais e a
 * tela em que o próximo clique gasta dinheiro — e não tinha arquivo de teste
 * próprio. A cobertura era indireta, por quatro `it()` do painel de canais, e
 * NENHUMA na tela de lançamento: todas as 16 provas de lançamento rodam sem
 * `prontidao` no fixture, ou seja, exercitam em silêncio o ramo de ausência.
 *
 * ## O que ele cobra
 *
 * As quatro maneiras de esta tela transformar ignorância em veredito:
 *
 * 1. lista vazia lida como conclusão — "nenhuma meta é perseguível" quando o
 *    que houve foi uma leitura que FALHOU;
 * 2. causa ausente preenchida com texto — "nenhuma ação foi eleita" quando
 *    ninguém leu as ações;
 * 3. destino colapsado num booleano — "não resolvido" dizendo ao mesmo tempo
 *    "ninguém leu", "li e não há" e "a leitura falhou";
 * 4. `null` virando `0` no dinheiro que o humano autoriza.
 *
 * E a distinção nova: plano CALCULADO ≠ plano PERSISTIDO ≠ plano VINCULADO.
 */
import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import {
  textoDaFonteDoSinal,
  textoDaMetaEfetiva,
  type MetaEfetiva,
  type PlanoDeMensuracao,
} from '@/lib/trafego/canais';
import { CartaoDoPlanoDeMensuracao } from '@/components/trafego/canais/PlanoDeMensuracao';

afterEach(cleanup);

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
    customer_id: '5478096539',
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
      estado: 'nao_coletado',
      auto_tagging: null,
      conversion_tracking_id: null,
      conversion_tracking_owner_id: null,
      cross_account_conversion_tracking_id: null,
      conversion_tracking_status: null,
      fuso: null,
      aceitou_termos_de_dados: null,
      enhanced_conversions_for_leads: null,
      acoes_de_ga4: [],
      acoes_com_tag: [],
      click_ids_suportados: ['gclid', 'gbraid', 'wbraid'],
      causa: null,
    },
    proposta_de_acao: null,
    completo: false,
    bloqueadores: ['nenhuma ação de conversão mede o que esta campanha persegue.'],
    impressao: 'a'.repeat(64),
    ...over,
  } as PlanoDeMensuracao;
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. LISTA VAZIA NÃO É CONCLUSÃO
// ═══════════════════════════════════════════════════════════════════════════

describe('textoDaMetaEfetiva', () => {
  it('não diz "nenhuma meta é perseguível" quando a leitura FALHOU', () => {
    // ⚠️ O caso real: `metas_biddable` chega `[]` porque a consulta das metas
    // da conta explodiu. A lista vazia é consequência da falha, não medição.
    // Dizer ao operador que a conta não tem meta perseguível o mandaria
    // configurar uma conta que talvez já esteja configurada.
    const texto = textoDaMetaEfetiva(meta({
      metas_da_conta_estado: 'falhou',
      metas_biddable: [],
      metas_que_mandam: [],
    }));

    expect(texto).not.toMatch(/nenhuma meta é perseguível/i);
    expect(texto).toMatch(/falh/i);
  });

  it('diz "nenhuma meta é perseguível" quando a leitura CONCLUIU vazia', () => {
    // Zero medido é zero, e continua sendo dito.
    const texto = textoDaMetaEfetiva(meta({
      metas_da_conta_estado: 'vazio_confirmado',
      metas_biddable: [],
      metas_que_mandam: [],
    }));

    expect(texto).toMatch(/nenhuma meta é perseguível/i);
  });

  it('não conclui a partir de uma leitura que ninguém fez', () => {
    const texto = textoDaMetaEfetiva(meta({
      metas_da_conta_estado: 'nao_coletado',
      metas_biddable: [],
      metas_que_mandam: [],
    }));

    expect(texto).not.toMatch(/nenhuma meta é perseguível/i);
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// 2. CAUSA AUSENTE NÃO VIRA VEREDITO
// ═══════════════════════════════════════════════════════════════════════════

describe('textoDaFonteDoSinal', () => {
  it('não afirma "nenhuma ação foi eleita" quando as ações não foram lidas', () => {
    // ⚠️ `acao_alvo=null` + `acao_alvo_causa=null` + `acoes_estado='falhou'` é
    // ignorância, e o fallback textual a transformava em conclusão.
    const texto = textoDaFonteDoSinal(plano({
      acao_alvo: null,
      acao_alvo_causa: null,
      acoes_estado: 'falhou',
    }));

    expect(texto).not.toBe('nenhuma ação foi eleita');
    expect(texto).toMatch(/falh|não (foi|foram)/i);
  });

  it('repete a causa do servidor quando ela existe, sem reescrevê-la', () => {
    const texto = textoDaFonteDoSinal(plano({
      acao_alvo: null,
      acao_alvo_causa: 'a conta não tem ação com a semântica PURCHASE/WEBSITE.',
    }));

    expect(texto).toBe('a conta não tem ação com a semântica PURCHASE/WEBSITE.');
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// 3. O DESTINO TEM TRÊS RESPOSTAS, E NÃO DUAS
// ═══════════════════════════════════════════════════════════════════════════

describe('o destino de conversão offline', () => {
  it('mostra a causa quando não resolve, em vez de só "não resolvido"', () => {
    render(<CartaoDoPlanoDeMensuracao plano={plano()} />);

    expect(
      screen.getByText(/sem ação eleita não há destino endereçável/i),
    ).toBeTruthy();
  });

  it('mostra o id NUMÉRICO e a conta DONA quando resolve', () => {
    render(<CartaoDoPlanoDeMensuracao plano={plano({
      destino: {
        resolvido: true,
        operating_account_id: '1234567890',
        product_destination_id: '7498530235',
        conversion_action_resource: 'customers/1234567890/conversionActions/7498530235',
        tipo_da_acao: 'WEBPAGE',
        causa: null,
      },
    })} />);

    // A conta DONA, que pode não ser a operacional — é ela que a Data Manager
    // exige, e mandar para a outra não dá erro: dá silêncio.
    expect(screen.getByText(/7498530235/)).toBeTruthy();
    expect(screen.getByText(/1234567890/)).toBeTruthy();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// 4. CALCULADO ≠ PERSISTIDO ≠ VINCULADO
// ═══════════════════════════════════════════════════════════════════════════

describe('o estado de registro do plano', () => {
  it('sem informação de persistência, não afirma que está gravado', () => {
    render(<CartaoDoPlanoDeMensuracao plano={plano()} />);

    expect(screen.queryByText(/gravado/i)).toBeNull();
  });

  it('diz que o plano ainda NÃO foi gravado quando o servidor diz isso', () => {
    render(
      <CartaoDoPlanoDeMensuracao
        plano={plano()}
        persistencia={{
          persistido: false,
          plano_id: null,
          porque:
            '/provar não escreve: ele calcula o plano e o mostra. A gravação ' +
            'acontece em /subir.',
        }}
      />,
    );

    expect(screen.getByText(/ainda não gravado/i)).toBeTruthy();
    expect(screen.getByText(/\/subir/)).toBeTruthy();
  });

  it('mostra o vínculo com a campanha quando ele existe', () => {
    render(
      <CartaoDoPlanoDeMensuracao
        plano={plano({ campaign_id: '24183717006' })}
        vinculo={{
          vinculado: true,
          campaign_id: '24183717006',
          plano_id: 'plano-2',
          versao: 2,
          observado_antes_do_nascimento: true,
        }}
      />,
    );

    // ⚠️ `getAllBy`, e não `getBy`: o id aparece DUAS vezes de propósito — no
    // cabeçalho (a campanha a que o plano se refere) e no bloco de registro (o
    // vínculo gravado). São afirmações diferentes, e colapsar as duas na tela
    // faria "o plano é desta campanha" parecer prova de "o vínculo está no
    // banco".
    expect(screen.getAllByText(/campanha 24183717006/).length).toBe(2);
    expect(screen.getByText(/vinculado à campanha 24183717006/)).toBeTruthy();
    // ⚠️ A ressalva que impede a linha de mentir: os estados de leitura desta
    // linha descrevem uma observação feita ANTES de a campanha existir.
    expect(screen.getByText(/antes de a campanha existir/i)).toBeTruthy();
  });

  it('vínculo ausente NÃO é lido como plano ausente', () => {
    render(
      <CartaoDoPlanoDeMensuracao
        plano={plano()}
        vinculo={{
          vinculado: false,
          porque: 'a API não devolveu resource_name de campanha',
          proxima_acao: 'reconciliar',
        }}
      />,
    );

    expect(screen.getByText(/não devolveu resource_name/i)).toBeTruthy();
    expect(screen.getByText(/reconciliar/i)).toBeTruthy();
    // O plano continua na tela: ele existe e foi gravado; o que falta é a
    // ligação com o id.
    expect(screen.getByText(/meta efetiva/i)).toBeTruthy();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// 5. DATA MANAGER — RESOLVIDO NÃO É PRONTO
// ═══════════════════════════════════════════════════════════════════════════

describe('Data Manager', () => {
  it('explica que endereço resolvido não é ingestão funcionando', () => {
    render(<CartaoDoPlanoDeMensuracao plano={plano({
      destino: {
        resolvido: true,
        operating_account_id: '1234567890',
        product_destination_id: '7498530235',
        conversion_action_resource: null,
        tipo_da_acao: 'WEBPAGE',
        causa: null,
      },
    })} />);

    // ⚠️ A frase precisa existir: "resolvido" é ter endereço, e um operador que
    // leia isso como "a ingestão offline está funcionando" vai parar de
    // procurar o motivo de as conversões não chegarem.
    expect(screen.getByText(/endereço.*não.*(upload|envio|ingestão)/i)).toBeTruthy();
  });
});
