// @vitest-environment jsdom
/**
 * A etapa de Revisão quando a criação PAUSED existe de verdade.
 *
 * ## O que estas provas defendem
 *
 * A bancada passou a poder criar objetos numa conta real. Cada teste aqui fixa
 * um portão que, se cair, custa dinheiro ou credibilidade:
 *
 *   flags fechadas          → a criação não pode nem PARECER disponível
 *   confirmação literal     → "criar pausada" não é "CRIAR PAUSADA"
 *   edição invalida         → aprovar um plano e editar outro não pode criar
 *   duplo clique            → um gesto, um pedido
 *   nenhum ENABLE           → não existe botão de ativar, em lugar nenhum
 *   recibo sanitizado       → id da Meta não aparece na tela
 *
 * ⚠️ O teste de duplo clique dispara os dois cliques dentro de UM `act`. Fora
 * dele, o `fireEvent` do testing-library já teria descarregado o `setOcupado`
 * do primeiro clique e o botão chegaria desabilitado ao segundo — o teste
 * passaria sem que a trava síncrona existisse, que é exatamente o defeito que
 * ele precisa detectar.
 */
import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import MetaCriacaoPage from '@/pages/trafego/MetaCriacaoPage';

Object.defineProperty(window, 'scrollTo', { value: vi.fn(), writable: true });

const { api } = vi.hoisted(() => ({
  api: {
    estadoMetaLocal: vi.fn(),
    contasMetaLocal: vi.fn(),
    capacidadesCriacaoMeta: vi.fn(),
    ativosCriacaoMeta: vi.fn(),
    previewAtivoMeta: vi.fn(),
    compilarPlanoMeta: vi.fn(),
    validarPlanoMeta: vi.fn(),
    aprovarCriacaoMeta: vi.fn(),
    criarCampanhaPausadaMeta: vi.fn(),
    reconciliarCriacaoMeta: vi.fn(),
  },
}));

vi.mock('@/lib/pautadorApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/pautadorApi')>()),
  pautadorApi: api,
}));

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const HASH = 'b'.repeat(64);
/** O id que a Meta devolveria. Ele NUNCA pode aparecer na tela. */
const ID_META_CRU = '120210000000012345';

const conta = {
  referencia_opaca: 'metaacct_conta_de_prova',
  nome: 'Conta de prova',
  id_mascarado: '••••1426',
  status: '1',
  moeda: 'BRL',
  fuso: 'America/Sao_Paulo',
  prontidao_leitura: 'READY_FOR_READ' as const,
  business: null,
};

const MOTIVO_FECHADO =
  'A criação de objetos reais está fechada neste servidor. Um administrador precisa '
  + 'liberá-la explicitamente antes de qualquer nascimento.';

function capacidades(criacaoAberta: boolean) {
  return {
    ok: true, api_version: 'v26.0', validate_only: 'ENABLED',
    single_static: 'AVAILABLE', static_batch: 'AVAILABLE_UP_TO_10',
    video_creative: 'BLOCKED_UNTIL_VIDEO_CONTRACT_PROVEN',
    flexible_creative: 'BLOCKED_UNTIL_ASSET_FEED_SPEC_PROVEN',
    create_paused: criacaoAberta ? 'ENABLED' : 'BLOCKED_BY_SERVER_FLAG',
    activation: 'NOT_IMPLEMENTED',
    bloqueios: { create_paused: MOTIVO_FECHADO },
  };
}

const validacaoAceita = {
  ok: true,
  cobertura: 'INDEPENDENT_ROOTS_ONLY' as const,
  operacoes_validadas: ['campaign', 'creative:variation-001'],
  operacoes_dependentes_pendentes: ['adset', 'ad:variation-001'],
  plano_sha256: HASH,
  objetos_criados: 0 as const,
  prova_duravel: {
    registrada: true,
    validation_id: 'validation-0001',
    validated_at: '2026-09-05T12:00:00+00:00',
  },
};

const aprovacaoCriada = {
  ok: true as const,
  efeito_externo: 'NENHUM' as const,
  aprovacao: {
    approval_id: 'approval-0001',
    plano_sha256: HASH,
    expires_at: '2026-09-05T12:15:00+00:00',
    operacoes: 4,
    manifesto: ['campaign', 'adset', 'creative:variation-001', 'ad:variation-001'],
    orcamento_diario_minor: 1000,
    moeda: 'BRL' as const,
    nascimento_pausado_confirmado: true as const,
  },
};

function passo(name: string) {
  return { name, state: 'CREATED' as const, has_external_id: true, error_code: null };
}

const nascimentoFeito = {
  ok: true as const,
  desfecho: 'CREATED_PAUSED' as const,
  plano_sha256: HASH,
  referencias_opacas: {
    campaign: 'metaobj_aaaaaaaaaaaaaaaaaaaaaaaa',
    adset: 'metaobj_bbbbbbbbbbbbbbbbbbbbbbbb',
  },
  read_back: {
    campaign: { veiculavel: true, status: 'PAUSED', effective_status: 'PAUSED' },
    adset: { veiculavel: true, status: 'PAUSED', effective_status: 'PAUSED' },
    'creative:variation-001': { veiculavel: false, status: 'ACTIVE', effective_status: 'ACTIVE' },
    'ad:variation-001': { veiculavel: true, status: 'PAUSED', effective_status: 'PAUSED' },
  },
  recibo: {
    approval_id: 'approval-0001',
    plan_sha256: HASH,
    capability: 'META_CREATE_PAUSED' as const,
    state: 'APPROVED',
    expires_at: '2026-09-05T12:15:00+00:00',
    operations_expected: 4,
    daily_budget_minor: 1000,
    currency: 'BRL',
    paused_birth_confirmed: true,
    steps: [
      passo('campaign'), passo('adset'),
      passo('creative:variation-001'), passo('ad:variation-001'),
    ],
  },
  retry_permitido: false as const,
};

beforeEach(() => {
  api.estadoMetaLocal.mockReset().mockResolvedValue({
    configurado: true, armazenamento: 'macOS Keychain', api_version: 'v26.0',
  });
  api.contasMetaLocal.mockReset().mockResolvedValue({
    ok: true, api_version: 'v26.0', armazenamento: 'macOS Keychain', contas: [conta],
  });
  api.capacidadesCriacaoMeta.mockReset().mockResolvedValue(capacidades(true));
  api.ativosCriacaoMeta.mockReset().mockResolvedValue({
    ok: true, api_version: 'v26.0', account_ref: conta.referencia_opaca, conta,
    paginas: [{
      referencia_opaca: 'metaobj_pagina', nome: 'Página de prova', tipo: 'page' as const,
      id_mascarado: '••••7788', largura: null, altura: null, preview_disponivel: false,
    }],
    imagens: [{
      referencia_opaca: 'metaasset_um', nome: 'Imagem um', tipo: 'image_asset' as const,
      id_mascarado: null, largura: 1080, altura: 1080, preview_disponivel: false,
    }],
    videos: [],
    receita: 'OUTCOME_TRAFFIC_WEBSITE_LPV_STATIC_PAUSED',
  });
  api.previewAtivoMeta.mockReset().mockRejectedValue(new Error('sem prévia no teste'));
  api.compilarPlanoMeta.mockReset().mockResolvedValue({
    ok: true, efeito_externo: 'NENHUM',
    plano: {
      account_ref: conta.referencia_opaca, destination_url: 'https://focogenial.com/',
      api_version: 'v26.0', plano_sha256: HASH, estado_ao_nascer: 'PAUSED',
      operacoes: [],
    },
  });
  api.validarPlanoMeta.mockReset().mockResolvedValue(validacaoAceita);
  api.aprovarCriacaoMeta.mockReset().mockResolvedValue(aprovacaoCriada);
  api.criarCampanhaPausadaMeta.mockReset().mockResolvedValue(nascimentoFeito);
  api.reconciliarCriacaoMeta.mockReset();
});

afterEach(cleanup);

function abrir() {
  return render(
    <MemoryRouter initialEntries={['/trafego/meta/nova?etapa=base']}>
      <MetaCriacaoPage />
    </MemoryRouter>,
  );
}

/** Leva a bancada até uma validação aceita, que é o pré-requisito de aprovar. */
async function ateAValidacao() {
  abrir();
  await waitFor(() => expect(api.ativosCriacaoMeta).toHaveBeenCalled());
  fireEvent.click(screen.getByRole('button', { name: /^Campanha/i }));
  fireEvent.click(screen.getByRole('checkbox', { name: /não é de crédito, emprego/i }));
  fireEvent.click(screen.getByRole('button', { name: /^Revisão/i }));
  fireEvent.click(await screen.findByRole('button', { name: /conferir o plano/i }));
  await waitFor(() => expect(api.compilarPlanoMeta).toHaveBeenCalled());
  fireEvent.click(await screen.findByRole('button', { name: /validar na meta/i }));
  await waitFor(() => expect(api.validarPlanoMeta).toHaveBeenCalled());
}

/** Marca a caixa e digita a frase exata. */
async function confirmar(frase = 'CRIAR PAUSADA') {
  fireEvent.click(await screen.findByRole('checkbox', { name: /Confirmo a criação real/i }));
  fireEvent.change(screen.getByLabelText(/Digite CRIAR PAUSADA/i), {
    target: { value: frase },
  });
}

async function aprovarEcriar() {
  await confirmar();
  fireEvent.click(screen.getByRole('button', { name: /^Aprovar plano$/i }));
  await waitFor(() => expect(api.aprovarCriacaoMeta).toHaveBeenCalled());
  fireEvent.click(await screen.findByRole('button', { name: /^Criar campanha PAUSED$/i }));
  await waitFor(() => expect(api.criarCampanhaPausadaMeta).toHaveBeenCalled());
}


describe('Revisão Meta — criação fechada por padrão', () => {
  it('não oferece criação nenhuma quando o servidor não autoriza', async () => {
    api.capacidadesCriacaoMeta.mockResolvedValue(capacidades(false));
    await ateAValidacao();

    expect(await screen.findByText(/Criação PAUSED ainda fechada neste servidor/i))
      .toBeTruthy();
    // A causa aparece; o nome da variável de ambiente, nunca.
    expect(screen.getByText(new RegExp(MOTIVO_FECHADO.slice(0, 40), 'i'))).toBeTruthy();
    expect(document.body.textContent).not.toContain('META_CREATE_PAUSED_ENABLED');

    // Nenhum controle de criação existe — nem desabilitado. Um botão cinzento
    // ainda ensinaria que a criação está a um clique de distância.
    expect(screen.queryByRole('button', { name: /Aprovar plano/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Criar campanha PAUSED/i })).toBeNull();
    expect(screen.queryByRole('checkbox', { name: /Confirmo a criação real/i })).toBeNull();
  });

  it('nunca oferece ativar, nem com a criação liberada', async () => {
    await ateAValidacao();
    await confirmar();
    const botoes = screen.getAllByRole('button').map((item) => item.textContent ?? '');
    for (const proibido of [/ativar/i, /enable/i, /publicar/i, /ligar campanha/i]) {
      expect(botoes.some((texto) => proibido.test(texto))).toBe(false);
    }
    expect(screen.getByText(/Ativar continua sendo outro ato/i)).toBeTruthy();
  });
});


describe('Revisão Meta — a confirmação humana', () => {
  it('não aprova sem a frase exata, e diz o que falta', async () => {
    await ateAValidacao();
    fireEvent.click(await screen.findByRole('checkbox', { name: /Confirmo a criação real/i }));

    for (const quase of ['criar pausada', 'CRIAR PAUSADO', 'Criar Pausada', 'SIM']) {
      fireEvent.change(screen.getByLabelText(/Digite CRIAR PAUSADA/i), {
        target: { value: quase },
      });
      const botao = screen.getByRole('button', { name: /^Aprovar plano$/i });
      expect(botao).toHaveProperty('disabled', true);
      fireEvent.click(botao);
    }
    expect(api.aprovarCriacaoMeta).not.toHaveBeenCalled();
    expect(screen.getByText(/Digite CRIAR PAUSADA exatamente como está escrito/i)).toBeTruthy();
  });

  it('não aprova com a frase certa e a caixa desmarcada', async () => {
    await ateAValidacao();
    fireEvent.change(await screen.findByLabelText(/Digite CRIAR PAUSADA/i), {
      target: { value: 'CRIAR PAUSADA' },
    });
    expect(screen.getByRole('button', { name: /^Aprovar plano$/i }))
      .toHaveProperty('disabled', true);
    expect(screen.getByText(/Marque a confirmação de criação real/i)).toBeTruthy();
    expect(api.aprovarCriacaoMeta).not.toHaveBeenCalled();
  });

  it('manda a frase digitada ao servidor, em vez de um booleano', async () => {
    await ateAValidacao();
    await confirmar();
    fireEvent.click(screen.getByRole('button', { name: /^Aprovar plano$/i }));
    await waitFor(() => expect(api.aprovarCriacaoMeta).toHaveBeenCalled());
    // ⚠️ Se a tela mandasse `true`, o portão do servidor viraria decoração: a
    // comparação literal precisa acontecer com o texto que a pessoa escreveu.
    expect(api.aprovarCriacaoMeta.mock.calls[0][0].confirmacaoDigitada).toBe('CRIAR PAUSADA');
    expect(api.aprovarCriacaoMeta.mock.calls[0][0].validationId).toBe('validation-0001');
    expect(api.aprovarCriacaoMeta.mock.calls[0][0].planoSha256).toBe(HASH);
  });

  it('recusa aprovar quando a validação não virou prova durável', async () => {
    api.validarPlanoMeta.mockResolvedValue({
      ...validacaoAceita,
      prova_duravel: {
        registrada: false,
        codigo: 'META_CREATE_LEDGER_WRITE_BLOCKED',
        motivo: 'o ledger de criacao Meta permanece fechado neste servidor',
      },
    });
    await ateAValidacao();
    await confirmar();
    expect(screen.getByRole('button', { name: /^Aprovar plano$/i }))
      .toHaveProperty('disabled', true);
    expect(screen.getByText(/A prova da validação não foi gravada no servidor/i)).toBeTruthy();
    expect(api.aprovarCriacaoMeta).not.toHaveBeenCalled();
  });
});


describe('Revisão Meta — aprovar e criar são dois atos', () => {
  it('não deixa criar antes de aprovar', async () => {
    await ateAValidacao();
    await confirmar();
    const criar = screen.getByRole('button', { name: /^Criar campanha PAUSED$/i });
    expect(criar).toHaveProperty('disabled', true);
    expect(screen.getByText(/Aprove o plano antes de criar/i)).toBeTruthy();
    fireEvent.click(criar);
    expect(api.criarCampanhaPausadaMeta).not.toHaveBeenCalled();
  });

  it('manda só referências ao criar — nunca o payload Meta', async () => {
    await ateAValidacao();
    await aprovarEcriar();
    expect(api.criarCampanhaPausadaMeta).toHaveBeenCalledWith('approval-0001', HASH);
  });

  it('bloqueia o duplo clique dentro do mesmo tique do evento', async () => {
    await ateAValidacao();
    await confirmar();
    const botao = screen.getByRole('button', { name: /^Aprovar plano$/i });
    // Dois cliques SEM render entre eles: só a trava síncrona os separa.
    await act(async () => {
      botao.click();
      botao.click();
    });
    expect(api.aprovarCriacaoMeta).toHaveBeenCalledTimes(1);

    const criar = await screen.findByRole('button', { name: /^Criar campanha PAUSED$/i });
    await act(async () => {
      criar.click();
      criar.click();
    });
    expect(api.criarCampanhaPausadaMeta).toHaveBeenCalledTimes(1);
  });
});


describe('Revisão Meta — editar o rascunho invalida a aprovação', () => {
  it('derruba compilação, validação e aprovação quando o plano muda', async () => {
    await ateAValidacao();
    await confirmar();
    fireEvent.click(screen.getByRole('button', { name: /^Aprovar plano$/i }));
    await waitFor(() => expect(api.aprovarCriacaoMeta).toHaveBeenCalled());
    expect(await screen.findByText(/Aprovação registrada/i)).toBeTruthy();

    // O operador volta e muda o orçamento. A aprovação descrevia outro hash.
    fireEvent.click(screen.getByRole('button', { name: /^Orçamento/i }));
    fireEvent.change(screen.getByLabelText(/Orçamento diário/i), {
      target: { value: '99,00' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Revisão/i }));

    // A aprovação sumiu. O painel de criação CONTINUA na tela — o servidor
    // segue autorizando o ato — mas não há mais nada aprovado para criar.
    expect(screen.queryByText(/Aprovação registrada/i)).toBeNull();
    const criar = screen.getByRole('button', { name: /^Criar campanha PAUSED$/i });
    expect(criar).toHaveProperty('disabled', true);
    expect(screen.getByText(/Aprove o plano antes de criar/i)).toBeTruthy();
    fireEvent.click(criar);
    expect(api.criarCampanhaPausadaMeta).not.toHaveBeenCalled();

    // A caixa e a frase também voltam ao zero: reaproveitá-las faria a
    // confirmação valer para um plano que a pessoa não leu.
    expect(screen.getByRole('checkbox', { name: /Confirmo a criação real/i }))
      .toHaveProperty('checked', false);
    expect(screen.getByLabelText(/Digite CRIAR PAUSADA/i)).toHaveProperty('value', '');
    // E aprovar de novo exige validar de novo: a validação anterior descrevia
    // o plano antigo.
    expect(screen.getByRole('button', { name: /^Aprovar plano$/i }))
      .toHaveProperty('disabled', true);
    expect(screen.getByText(/Valide o plano na Meta antes de aprovar/i)).toBeTruthy();
  });
});


describe('Revisão Meta — o recibo sanitizado', () => {
  it('mostra o read-back de cada objeto sem entregar identificador da Meta', async () => {
    await ateAValidacao();
    await aprovarEcriar();

    const recibo = await screen.findByText(/Recibo do nascimento/i);
    expect(recibo).toBeTruthy();
    expect(screen.getByText(/Criada pausada/i)).toBeTruthy();
    expect(screen.getByText(/4 de 4/)).toBeTruthy();

    const tabela = screen.getByRole('table', { name: /Leitura de volta/i });
    const linhaCampanha = within(tabela).getByRole('rowheader', { name: 'campaign' })
      .closest('tr') as HTMLElement;
    expect(within(linhaCampanha).getByText('PAUSED')).toBeTruthy();
    expect(within(linhaCampanha).getByText(/Sim · pausado/)).toBeTruthy();

    // O criativo não é veiculável, e a tela diz isso em vez de afirmar
    // "pausado" sobre um objeto que a Meta nunca pausa.
    const linhaCriativo = within(tabela)
      .getByRole('rowheader', { name: 'creative:variation-001' }).closest('tr') as HTMLElement;
    expect(within(linhaCriativo).getByText('Não')).toBeTruthy();

    // ⚠️ Nenhum identificador cru da Meta atravessa a tela.
    expect(document.body.textContent).not.toContain(ID_META_CRU);
    expect(document.body.textContent).not.toMatch(/\b120\d{15}\b/);
  });

  it('não oferece criar de novo depois de a aprovação ter nascido', async () => {
    await ateAValidacao();
    await aprovarEcriar();
    const criar = await screen.findByRole('button', { name: /^Criar campanha PAUSED$/i });
    expect(criar).toHaveProperty('disabled', true);
    expect(screen.getByText(/Esta aprovação já criou os objetos/i)).toBeTruthy();
  });

  it('reconcilia por leitura e declara efeito externo nenhum', async () => {
    api.reconciliarCriacaoMeta.mockResolvedValue({
      ok: true, efeito_externo: 'NENHUM', passos_ambiguos: 1,
      conclusoes: [{
        passo: 'adset', tipo: 'adset', conclusao: 'PERMANECE_AMBIGUO',
        explicacao: 'a conta tem mais de um objeto com este nome',
      }],
      recibo: nascimentoFeito.recibo,
    });
    await ateAValidacao();
    await confirmar();
    fireEvent.click(screen.getByRole('button', { name: /^Aprovar plano$/i }));
    await waitFor(() => expect(api.aprovarCriacaoMeta).toHaveBeenCalled());

    fireEvent.click(await screen.findByRole('button', { name: /Reconciliar por leitura/i }));
    await waitFor(() => expect(api.reconciliarCriacaoMeta).toHaveBeenCalledWith('approval-0001'));
    expect(await screen.findByText(/Nenhum · apenas leitura/i)).toBeTruthy();
    expect(screen.getByText(/a conta tem mais de um objeto com este nome/i)).toBeTruthy();
  });
});
