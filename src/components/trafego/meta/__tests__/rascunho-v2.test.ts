/**
 * O contrato do rascunho V2, provado sem DOM.
 *
 * Cada teste aqui fixa uma regra que o backend cobra com nome próprio, e que a
 * tela não pode descobrir tarde: a união discriminada do orçamento, a escolha
 * explícita de expansão, a identidade estável do conjunto e a prontidão que o
 * trilho e o botão precisam ler do MESMO lugar.
 */
import { describe, expect, it } from 'vitest';

import {
  CAPACIDADES_FECHADAS, ConjuntoDraft, Draft, LIMITE_CONJUNTOS, conjuntoInicial,
  contratoDoPlano, paraPlano, paraPlanoV2, prometeAlcanceExclusivo, prontidaoDasEtapas,
  prontoParaCompilar, proximaChave, publicoInicial, variacaoInicial,
} from '../rascunho';

const CAPACIDADES = { ...CAPACIDADES_FECHADAS, loteEstatico: true, validateOnly: true };

function rascunho(troca: Partial<Draft> = {}): Draft {
  const conjunto = conjuntoInicial('adset-001', 'Brasil · Amplo', '2026-10-01T10:00', '10,00');
  return {
    recipeId: 'TRAFFIC_WEBSITE_LPV_STATIC',
    accountRef: 'metaacct_conta', pageRef: 'metaobj_pagina', instagramActorRef: '',
    campaignName: 'Campanha', destinationUrl: 'https://focogenial.com/',
    nivelDeOrcamento: 'ADSET', periodoDeOrcamento: 'DAILY', budgetBrl: '10,00',
    categoryConfirmed: true,
    creativeMode: 'single',
    conjuntos: [conjunto],
    variations: [{
      ...variacaoInicial('variation-001', 1, 'adset-001'),
      assetRef: 'metaasset_um',
      assetRightsConfirmed: true,
      thirdPartyIdentityCleared: true,
      assetPolicyConfirmedAt: '2026-10-01T09:00:00.000Z',
    }],
    ...troca,
  };
}

function comDoisConjuntos(): Draft {
  const base = rascunho();
  const segundo: ConjuntoDraft = conjuntoInicial(
    'adset-002', 'São Paulo · Raio', '2026-10-01T10:00', '25,00');
  return {
    ...base,
    creativeMode: 'batch',
    conjuntos: [base.conjuntos[0], segundo],
    variations: [
      base.variations[0],
      {
        ...base.variations[0],
        key: 'variation-002',
        adsetKey: 'adset-002',
        creativeName: 'Criativo 2',
        adName: 'Anúncio 2',
      },
    ],
  };
}

// ── F04/F06: a união discriminada do orçamento ──────────────────────────────

describe('orçamento: ABO e CBO nunca viajam juntos', () => {
  it('ABO põe verba em cada conjunto e nenhuma na campanha', () => {
    const corpo = paraPlanoV2(comDoisConjuntos());
    expect(corpo.campaign_budget).toBeNull();
    expect(corpo.adsets.map((item) => item.budget?.amount_minor)).toEqual([1000, 2500]);
    expect(corpo.adsets.every((item) => item.budget?.nivel === 'ADSET')).toBe(true);
  });

  it('CBO põe verba na campanha e NENHUMA em conjunto nenhum', () => {
    const corpo = paraPlanoV2({
      ...comDoisConjuntos(), nivelDeOrcamento: 'CAMPAIGN', budgetBrl: '99,00',
    });
    expect(corpo.campaign_budget).toEqual({
      nivel: 'CAMPAIGN', periodo: 'DAILY', amount_minor: 9900, currency: 'BRL',
    });
    // ⚠️ `null` explícito, não ausência: os dois níveis juntos são 409
    // META_BUDGET_DUPLICATED, e um `budget` sobrevivente do modo anterior é
    // exatamente como isso aconteceria.
    expect(corpo.adsets.every((item) => item.budget === null)).toBe(true);
  });

  it('trocar o período não converte o número que a pessoa escreveu', () => {
    const diario = paraPlanoV2(rascunho());
    const total = paraPlanoV2({ ...rascunho(), periodoDeOrcamento: 'LIFETIME' });
    expect(diario.adsets[0].budget?.amount_minor)
      .toBe(total.adsets[0].budget?.amount_minor);
    expect(total.adsets[0].budget?.periodo).toBe('LIFETIME');
  });
});

// ── F19/A16: a expansão viaja sempre ────────────────────────────────────────

describe('expansão Advantage+', () => {
  it('viaja SEMPRE, mesmo recusada — omitir ligaria a expansão na Meta', () => {
    const corpo = paraPlanoV2(rascunho());
    expect('expansion' in corpo.adsets[0].audience).toBe(true);
    expect(corpo.adsets[0].audience.expansion).toBe(false);
  });

  it('viaja como true quando o operador aceita', () => {
    const base = rascunho();
    const corpo = paraPlanoV2({
      ...base,
      conjuntos: [{
        ...base.conjuntos[0],
        publico: { ...publicoInicial(), expansao: true },
      }],
    });
    expect(corpo.adsets[0].audience.expansion).toBe(true);
  });

  it('com expansão ligada, nenhum público promete alcance exclusivo', () => {
    const comPublico = { ...publicoInicial(), incluirRefs: ['metaaud_um'] };
    expect(prometeAlcanceExclusivo(comPublico)).toBe(true);
    expect(prometeAlcanceExclusivo({ ...comPublico, expansao: true })).toBe(false);
    // Sem público próprio também não há exclusividade a prometer.
    expect(prometeAlcanceExclusivo(publicoInicial())).toBe(false);
  });
});

// ── F10/F34: identidade estável e mapa anúncio → conjunto ───────────────────

describe('conjuntos e anúncios', () => {
  it('cada anúncio aponta para o conjunto escolhido, na ordem em que está', () => {
    const corpo = paraPlanoV2(comDoisConjuntos());
    expect(corpo.ads.map((item) => [item.variation_key, item.adset_key])).toEqual([
      ['variation-001', 'adset-001'],
      ['variation-002', 'adset-002'],
    ]);
  });

  it('reordenar a lista não muda nenhuma chave nem o pai de nenhum anúncio', () => {
    const antes = comDoisConjuntos();
    const depois: Draft = { ...antes, conjuntos: [antes.conjuntos[1], antes.conjuntos[0]] };
    const corpoAntes = paraPlanoV2(antes);
    const corpoDepois = paraPlanoV2(depois);
    expect(corpoDepois.adsets.map((item) => item.adset_key)).toEqual(['adset-002', 'adset-001']);
    expect(corpoDepois.ads).toEqual(corpoAntes.ads);
  });

  it('a chave de conjunto e a de anúncio vivem em espaços separados', () => {
    expect(proximaChave(['adset-001'], 'adset')).toBe('adset-002');
    expect(proximaChave(['adset-001'], 'variation')).toBe('variation-001');
  });
});

// ── A escolha do contrato ───────────────────────────────────────────────────

describe('qual contrato o rascunho fala', () => {
  it('a receita provada, com um conjunto e verba diária, continua V1', () => {
    const { contrato, motivos } = contratoDoPlano(rascunho());
    expect(contrato).toBe('V1');
    expect(motivos).toEqual([]);
  });

  it.each([
    ['dois conjuntos', comDoisConjuntos()],
    ['CBO', { ...rascunho(), nivelDeOrcamento: 'CAMPAIGN' as const }],
    ['verba total', { ...rascunho(), periodoDeOrcamento: 'LIFETIME' as const }],
  ])('%s leva o plano para o V2, com o motivo escrito', (_nome, draft) => {
    const { contrato, motivos } = contratoDoPlano(draft as Draft);
    expect(contrato).toBe('V2');
    expect(motivos.length).toBeGreaterThan(0);
  });

  it('o corpo V1 continua com os campos de topo que aquele DTO exige', () => {
    // ⚠️ Não é duplicação por descuido: `PedidoPlanoMetaPausado` exige
    // `asset_ref`, `creative_name` e companhia no topo. É a forma daquele
    // contrato, e é por isso que o V2 não a tem.
    const corpo = paraPlano(rascunho());
    expect(corpo.asset_ref).toBe('metaasset_um');
    expect(corpo.adset_name).toBe('Brasil · Amplo');
    expect(corpo.daily_budget_minor).toBe(1000);
    expect(corpo.is_adset_budget_sharing_enabled).toBe(false);
    expect(corpo.special_ad_categories).toEqual([]);
  });
});

// ── Prontidão: um cálculo só para o trilho e para o botão ───────────────────

describe('prontidão das etapas', () => {
  it('público deixou de ser "pronto" incondicional', () => {
    const base = rascunho();
    const semLugar: Draft = {
      ...base,
      conjuntos: [{
        ...base.conjuntos[0],
        publico: {
          ...publicoInicial(),
          geo: { paisesTexto: '', exclusoesTexto: '', pontos: [], lugares: [] },
        },
      }],
    };
    const estados = prontidaoDasEtapas(semLugar, {
      capacidades: CAPACIDADES, compilado: false, validado: false,
    });
    expect(estados.publico).toBe('pendente');
    // ⚠️ O botão precisa concordar com o glifo. Antes eram dois lugares, e a
    // etapa aparecia "pronta" enquanto o botão nem a consultava.
    expect(prontoParaCompilar(semLugar, CAPACIDADES)).toBe(false);
  });

  it('um conjunto sem anúncio impede compilar, com o glifo concordando', () => {
    const base = comDoisConjuntos();
    const orfao: Draft = { ...base, variations: [base.variations[0]] , creativeMode: 'single' };
    const estados = prontidaoDasEtapas(orfao, {
      capacidades: CAPACIDADES, compilado: false, validado: false,
    });
    expect(estados.conjunto).toBe('pendente');
    expect(prontoParaCompilar(orfao, CAPACIDADES)).toBe(false);
  });

  it('vídeo bloqueia mesmo com a capacidade do servidor aberta', () => {
    const base = rascunho();
    const comVideo: Draft = {
      ...base,
      variations: [{ ...base.variations[0], midia: 'video', videoRef: 'metaasset_video' }],
    };
    const estados = prontidaoDasEtapas(comVideo, {
      capacidades: { ...CAPACIDADES, video: true }, compilado: false, validado: false,
    });
    // Nenhum dos dois corpos tem campo de vídeo: liberar aqui emitiria peça vazia.
    expect(estados.criativo).toBe('bloqueado');
  });

  it('verba total exige término em todos os conjuntos', () => {
    const total: Draft = { ...comDoisConjuntos(), periodoDeOrcamento: 'LIFETIME' };
    const estados = prontidaoDasEtapas(total, {
      capacidades: CAPACIDADES, compilado: false, validado: false,
    });
    expect(estados.orcamento).toBe('pendente');
  });

  it('o rascunho padrão de dois conjuntos compila', () => {
    expect(prontoParaCompilar(comDoisConjuntos(), CAPACIDADES)).toBe(true);
  });

  it('o limite de conjuntos espelha o do contrato', () => {
    expect(LIMITE_CONJUNTOS).toBe(10);
  });
});
