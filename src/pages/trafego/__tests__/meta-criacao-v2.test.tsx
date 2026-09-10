// @vitest-environment jsdom
/**
 * A bancada Meta no contrato V2: orçamento, conjuntos, público e mensuração.
 *
 * ## O que cada prova defende
 *
 *   ABO ↔ CBO             → o corpo nunca leva verba nos dois níveis
 *   troca com confirmação → nenhum valor se move em silêncio
 *   foco no orçamento     → o campo não desmonta no primeiro dígito (`A31`)
 *   N conjuntos           → reordenar não troca identidade nem pai de anúncio
 *   expansão              → a escolha viaja SEMPRE, nunca por omissão
 *   alcance               → a tela não promete o que o provedor não garante (`A16`)
 *   conversão UNKNOWN     → "não sei" nunca vira elegível (`A12`)
 *   editar invalida       → resumo e validação caem juntos (`A33`)
 *   nascimento pausado    → o V2 exige aprovação durável antes de criar
 */
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import MetaCriacaoPage from '@/pages/trafego/MetaCriacaoPage';
import type { PlanoMetaV2Input } from '@/lib/pautadorApi';

Object.defineProperty(window, 'scrollTo', { value: vi.fn(), writable: true });
Object.defineProperty(window, 'ResizeObserver', {
  value: class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
  writable: true,
});
Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
  value: vi.fn(),
  writable: true,
});

const { api, packApi, businessApi } = vi.hoisted(() => ({
  api: {
    capacidadesMidiaMeta: vi.fn().mockResolvedValue({ inspecao_de_imagem: { disponivel: false, capacidades_ausentes: ['marca_visual'] }, registro_de_imagem: 'DISABLED' }),
    trackingAutomaticoMeta: vi.fn().mockRejectedValue(new Error('Prévia indisponível neste dublê')),
    estadoMetaLocal: vi.fn(),
    contasMetaLocal: vi.fn(),
    capacidadesCriacaoMeta: vi.fn(),
    ativosCriacaoMeta: vi.fn(),
    previewAtivoMeta: vi.fn(),
    preflightMetaLocal: vi.fn(),
    catalogoDePublicosMeta: vi.fn(),
    catalogoDeMensuracaoMeta: vi.fn(),
    catalogoDeGeografiaMeta: vi.fn(),
    receitasCriacaoMetaV2: vi.fn(),
    compilarPlanoMeta: vi.fn(),
    validarPlanoMeta: vi.fn(),
    compilarPlanoMetaV2: vi.fn(),
    validarPlanoMetaV2: vi.fn(),
    aprovarCriacaoMeta: vi.fn(),
    criarCampanhaPausadaMeta: vi.fn(),
    reciboCriacaoMeta: vi.fn(),
    reconciliarCriacaoMeta: vi.fn(),
  },
  packApi: {
    lerPack: vi.fn().mockRejectedValue(new Error('Galeria indisponível neste teste de seleção')),
    listarSelecoesDePack: vi.fn(),
    fixarPackNoConjunto: vi.fn(),
    retirarPackDoConjunto: vi.fn(),
    listarPacks: vi.fn(),
    importarMidiaPrivada: vi.fn(),
    salvarPack: vi.fn(),
  },
  businessApi: vi.fn(),
}));

// Persistence has its own real-hook/API/CAS tests. These tests isolate the wizard contract.
vi.mock('@/hooks/useMetaCampaignDraft', () => ({
  useMetaCampaignDraft: () => ({ loading: false, saving: false, saved: true, version: 1,
    error: null, conflict: false, saveNow: async () => true, reload: async () => {} }),
}));

vi.mock('@/lib/pautadorApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/pautadorApi')>()),
  pautadorApi: api,
}));

vi.mock('@/features/creative-studio/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/creative-studio/api')>()),
  ...packApi,
}));
vi.mock('@/features/creative-studio/componentes/PackVisual', () => ({
  CapaPack: () => <div>Prévia do pack</div>,
  caminhoPack: (id: string) => `/trafego/meta/packs/${id}`,
}));
vi.mock('@/components/settings/MetaBusinessConnections', () => ({ businessRequest: businessApi }));

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

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

const imagem = (sufixo: string) => ({
  referencia_opaca: `metaasset_${sufixo}`,
  nome: `Imagem ${sufixo}`,
  tipo: 'image_asset' as const,
  id_mascarado: null,
  largura: 1080,
  altura: 1080,
  preview_disponivel: false,
});

const MODOS = [
  { id: 'ADSET_DAILY', nivel: 'ADSET' as const, periodo: 'DAILY' as const, prova: 'REMOTE_VALIDATE_ACCEPTED', criar_liberado: true },
  { id: 'ADSET_LIFETIME', nivel: 'ADSET' as const, periodo: 'LIFETIME' as const, prova: 'FIELD_SHAPE_ONLY', criar_liberado: false },
  { id: 'CAMPAIGN_DAILY', nivel: 'CAMPAIGN' as const, periodo: 'DAILY' as const, prova: 'FIELD_SHAPE_ONLY', criar_liberado: false },
  { id: 'CAMPAIGN_LIFETIME', nivel: 'CAMPAIGN' as const, periodo: 'LIFETIME' as const, prova: 'FIELD_SHAPE_ONLY', criar_liberado: false },
];

const CAPACIDADE_PAUSADA = {
  implementada: true,
  fluxo: 'VALIDAR_APROVAR_CRIAR_PAUSADA',
  estado_ao_nascer: 'PAUSED',
  autoriza_ativacao: false,
  exige_recibo_exato_do_plano: true,
  cobertura_previa: 'INDEPENDENT_ROOTS_ONLY',
  dependentes_validados_antes_de_criar: true,
  exige_aprovacao_humana: true,
  exige_capacidades_do_servidor: true,
  exige_prova_de_destino: true,
  prova_historica_nao_e_capacidade: true,
};

const CATALOGO = {
  ok: true as const,
  api_version: 'v26.0' as const,
  receita_padrao: 'TRAFFIC_WEBSITE_LPV_STATIC',
  receitas: [
    {
      id: 'TRAFFIC_WEBSITE_LPV_STATIC',
      rotulo: 'Tráfego · visualizações da página de destino',
      descricao: 'Leva o clique para a landing page.',
      objetivo: 'OUTCOME_TRAFFIC',
      otimizacao: 'LANDING_PAGE_VIEWS',
      exige_fonte_de_conversao: false,
      propositos_de_mensuracao: ['REPORT_ONLY'] as Array<'REPORT_ONLY' | 'OPTIMIZE'>,
      prova: 'REMOTE_VALIDATE_ACCEPTED',
      criar_liberado: true,
      motivo_sem_prova: null,
      modos_de_orcamento: MODOS,
    },
    {
      id: 'WEB_SALES_CONVERSION',
      rotulo: 'Vendas no site · conversão',
      descricao: 'Otimiza por uma conversão do seu site.',
      objetivo: 'OUTCOME_SALES',
      otimizacao: 'OFFSITE_CONVERSIONS',
      exige_fonte_de_conversao: true,
      propositos_de_mensuracao: ['REPORT_ONLY', 'OPTIMIZE'] as Array<'REPORT_ONLY' | 'OPTIMIZE'>,
      prova: 'FIELD_SHAPE_ONLY',
      criar_liberado: false,
      motivo_sem_prova: 'A elegibilidade do evento desta conta não foi provada.',
      modos_de_orcamento: MODOS,
    },
  ],
  limites: {
    conjuntos: 10, anuncios_por_conjunto: 10, anuncios_total: 50,
    classificacao: 'limites operacionais do produto',
  },
  idade: { min: 18, max: 65, motivo: 'limite do produto, não da Meta.' },
};

function resumo(troca: { exclusivo?: boolean; cbo?: boolean; conjuntos?: number } = {}) {
  const total = troca.conjuntos ?? 1;
  return {
    receita: {
      id: 'TRAFFIC_WEBSITE_LPV_STATIC',
      rotulo: 'Tráfego · visualizações da página de destino',
      objetivo: 'OUTCOME_TRAFFIC',
      otimizacao: 'LANDING_PAGE_VIEWS',
      prova: 'REMOTE_VALIDATE_ACCEPTED',
    },
    orcamento: {
      nivel: (troca.cbo ? 'CAMPAIGN' : 'ADSET') as 'CAMPAIGN' | 'ADSET',
      periodo: 'DAILY' as const,
      modo: troca.cbo ? 'CAMPAIGN_DAILY' : 'ADSET_DAILY',
      prova: 'FIELD_SHAPE_ONLY',
      onde_a_verba_mora: troca.cbo ? 'na campanha (CBO)' : 'em cada conjunto (ABO)',
    },
    conjuntos: Array.from({ length: total }, (_, i) => ({
      adset_key: `adset-00${i + 1}`,
      nome: i === 0 ? 'Brasil · Amplo · LPV · Automático' : `Conjunto ${i + 1}`,
      orcamento_minor: troca.cbo ? null : 1000,
      publico_modo: 'BROAD',
      publicos_incluidos: 0,
      publicos_excluidos: 0,
      expansao_advantage: false,
      promete_alcance_exclusivo: troca.exclusivo ?? false,
      posicionamentos: ['facebook'],
      mensuracao_proposito: 'REPORT_ONLY',
      mensuracao_altera_entrega: false,
      anuncios: [`variation-00${i + 1}`],
    })),
    bloqueios_para_criar: [],
  };
}

/** O envelope do backend, inteiro. Reduzi-lo aqui esconderia justamente os
 *  campos cuja distinção `A11` cobra. */
function envelope<T>(catalogo: string, items: T[], troca: Record<string, unknown> = {}) {
  return {
    ok: true,
    catalogo,
    api_version: 'v26.0',
    referencia_opaca_da_conta: conta.referencia_opaca,
    estado: items.length ? 'COM_ITENS' : 'VAZIO_COMPLETO',
    motivo: null,
    retryable: false,
    items,
    total: items.length,
    invalidos: 0,
    desconhecidos: 0,
    completo: true,
    paginas_lidas: 1,
    observado_em: '2026-09-07T12:00:00+00:00',
    ttl_s: 300,
    expira_em: '2026-09-07T12:05:00+00:00',
    estado_do_catalogo: 'VIGENTE',
    ...troca,
  };
}

const PUBLICOS = [
  {
    referencia_opaca: 'metaaud_visitantes', id_mascarado: '••••31', nome: 'Visitantes 30 dias',
    subtype: 'WEBSITE', delivery_status_code: 200, operation_status_code: 200,
    tamanho_aproximado_min: 1000, tamanho_aproximado_max: 5000,
    estado: 'AVAILABLE' as const,
  },
  {
    referencia_opaca: 'metaaud_semelhante', id_mascarado: '••••32', nome: 'Semelhante 1%',
    subtype: 'LOOKALIKE', delivery_status_code: 200, operation_status_code: 200,
    tamanho_aproximado_min: null, tamanho_aproximado_max: null,
    estado: 'AVAILABLE' as const,
  },
  {
    referencia_opaca: 'metaaud_incerto', id_mascarado: '••••33', nome: 'Público sem flag',
    subtype: 'CUSTOM', delivery_status_code: null, operation_status_code: null,
    tamanho_aproximado_min: null, tamanho_aproximado_max: null,
    estado: 'UNKNOWN' as const, motivo_desconhecido: 'DELIVERY_STATUS_AUSENTE',
  },
];

const LUGARES = [
  {
    key: '3844', name: 'Curitiba', type: 'city', country_code: 'BR', region: 'Paraná',
    supports_region: true, supports_city: true, estado: 'AVAILABLE' as const,
  },
  {
    key: null, name: 'Lugar ilegível', type: 'city', country_code: null, region: null,
    supports_region: null, supports_city: null, estado: 'INVALID' as const,
    motivo_desconhecido: 'CONTRATO_DO_ITEM_INVALIDO',
  },
];

const FONTES = [
  {
    referencia_opaca: 'metapixel_principal', id_mascarado: '••••77', nome: 'Pixel do site',
    source_kind: 'PIXEL' as const, last_fired_time: '2026-09-06T10:00:00Z',
    estado: 'AVAILABLE' as const,
  },
  {
    referencia_opaca: 'metapixel_incerto', id_mascarado: '••••78', nome: 'Fonte sem tipo',
    source_kind: 'UNKNOWN' as const, last_fired_time: null,
    estado: 'AVAILABLE' as const,
  },
];

const CONVERSOES = [
  {
    referencia_opaca: 'metaobj_conv_viva', id_mascarado: '••••11', nome: 'Compra concluída',
    custom_event_type: 'PURCHASE', event_source_type: 'PIXEL',
    event_source_id_mascarado: '••••99', first_fired_time: null,
    last_fired_time: '2026-09-01T10:00:00Z', estado: 'AVAILABLE_FIRED' as const,
  },
  {
    referencia_opaca: 'metaobj_conv_incerta', id_mascarado: '••••22', nome: 'Lead sem flag',
    custom_event_type: 'LEAD', event_source_type: null,
    event_source_id_mascarado: null, first_fired_time: null, last_fired_time: null,
    estado: 'UNKNOWN' as const, motivo_desconhecido: 'DELIVERY_STATUS_AUSENTE',
  },
];

const PLANO_COMPILADO = {
  account_ref: conta.referencia_opaca,
  destination_url: 'https://focogenial.com/',
  api_version: 'v26.0' as const,
  plano_sha256: 'a'.repeat(64),
  estado_ao_nascer: 'PAUSED' as const,
  operacoes: [],
};

beforeEach(() => {
  businessApi.mockReset().mockResolvedValue({
    selected_id: 'bm-prova',
    connections: [{ id: 'bm-prova', name: 'BM de prova', enabled: true }],
  });
  packApi.listarSelecoesDePack.mockReset().mockResolvedValue({
    draft_ref: '00000000-0000-4000-8000-000000000001', selections: [],
  });
  packApi.listarPacks.mockReset().mockResolvedValue({
    packs: [{
      id: '00000000-0000-4000-8000-000000000111', nome: 'Pack Encceja',
      manifest_sha256: 'a'.repeat(64), created_at: '2026-09-08T00:00:00Z',
      manifest: { source: 'STUDIO', launch_authorized: false, items: [{ master_ref: '00000000-0000-4000-8000-000000000222' }] },
    }], has_more: false,
  });
  packApi.importarMidiaPrivada.mockReset().mockResolvedValue({
    referencia: 'import-1', estado: 'CONCLUIDA',
    entradas: [{ nome: 'troca.png', estado: 'ACEITO', mime: 'image/png',
      masterId: '00000000-0000-4000-8000-000000000333', largura: 1080, altura: 1350,
      previewUrl: null, motivoRecusa: null, detalhe: null }],
    registroRemoto: { estado: 'NAO_INICIADO', explicacao: 'A Meta não foi chamada.' },
  });
  packApi.salvarPack.mockReset().mockResolvedValue({
    id: '00000000-0000-4000-8000-000000000444', nome: 'Upload · troca',
    manifest_sha256: 'b'.repeat(64), created_at: '2026-09-10T00:00:00Z',
    manifest: { source: 'STUDIO', launch_authorized: false,
      items: [{ master_ref: '00000000-0000-4000-8000-000000000333' }] },
  });
  packApi.fixarPackNoConjunto.mockReset().mockImplementation(
    async (draftRef: string, adsetKey: string, packId: string, expectedVersion: number) => ({
      draft_ref: draftRef, adset_key: adsetKey, pack_id: packId,
      pack_name: 'Pack Encceja', manifest_sha256: 'a'.repeat(64),
      master_refs: ['00000000-0000-4000-8000-000000000222'],
      version: expectedVersion + 1, state: 'LOCKED',
      selected_at: '2026-09-08T00:00:00Z', launch_authorized: false,
      scope: 'DRAFT_MEDIA_ONLY',
    }),
  );
  packApi.retirarPackDoConjunto.mockReset().mockResolvedValue({ state: 'REMOVED' });
  api.estadoMetaLocal.mockReset().mockResolvedValue({
    configurado: true, armazenamento: 'macOS Keychain', api_version: 'v26.0',
  });
  api.contasMetaLocal.mockReset().mockResolvedValue({
    ok: true, api_version: 'v26.0', armazenamento: 'macOS Keychain', contas: [conta],
  });
  api.capacidadesCriacaoMeta.mockReset().mockResolvedValue({
    ok: true, api_version: 'v26.0', validate_only: 'ENABLED',
    single_static: 'AVAILABLE', static_batch: 'AVAILABLE_UP_TO_10',
    video_creative: 'BLOCKED_UNTIL_VIDEO_CONTRACT_PROVEN',
    flexible_creative: 'BLOCKED_UNTIL_ASSET_FEED_SPEC_PROVEN',
    // ⚠️ ABERTA DE PROPÓSITO. O ponto do último teste é que nem com a criação
    // liberada no servidor um plano V2 ganha um botão que cria.
    create_paused: 'ENABLED',
  });
  api.ativosCriacaoMeta.mockReset().mockResolvedValue({
    ok: true, api_version: 'v26.0', account_ref: conta.referencia_opaca, conta,
    paginas: [{
      referencia_opaca: 'metaobj_pagina', nome: 'Página de prova', tipo: 'page' as const,
      id_mascarado: '••••7788', largura: null, altura: null, preview_disponivel: false,
    }],
    imagens: [imagem('um'), imagem('dois')],
    videos: [],
    receita: 'OUTCOME_TRAFFIC_WEBSITE_LPV_STATIC_PAUSED',
  });
  api.previewAtivoMeta.mockReset().mockRejectedValue(new Error('sem prévia no teste'));
  api.receitasCriacaoMetaV2.mockReset().mockResolvedValue(CATALOGO);
  api.preflightMetaLocal.mockReset();
  api.catalogoDePublicosMeta.mockReset()
    .mockResolvedValue(envelope('custom_audiences', PUBLICOS));
  api.catalogoDeMensuracaoMeta.mockReset().mockResolvedValue({
    ok: true,
    fontes: envelope('measurement_sources', FONTES),
    conversoes: envelope('custom_conversions', CONVERSOES),
  });
  api.catalogoDeGeografiaMeta.mockReset()
    .mockResolvedValue(envelope('geolocations', LUGARES));
  api.compilarPlanoMetaV2.mockReset().mockResolvedValue({
    ok: true, contrato: 'V2', efeito_externo: 'NENHUM',
    plano: PLANO_COMPILADO, resumo: resumo(),
  });
  api.validarPlanoMetaV2.mockReset().mockResolvedValue({
    ok: true, contrato: 'V2', cobertura: 'INDEPENDENT_ROOTS_ONLY',
    cobertura_explicada: 'apenas as raízes independentes',
    operacoes_validadas: ['campaign'], operacoes_dependentes_pendentes: ['adset'],
    plano_sha256: 'a'.repeat(64), objetos_criados: 0,
    resumo: resumo(), prova_duravel: { registrada: true, validation_id: 'v-1' },
  });
  api.compilarPlanoMeta.mockReset().mockResolvedValue({
    ok: true, efeito_externo: 'NENHUM', plano: PLANO_COMPILADO,
  });
  api.validarPlanoMeta.mockReset();
});

afterEach(cleanup);

function abrir(etapa: string) {
  const tela = render(
    <MemoryRouter initialEntries={[`/trafego/meta/nova?etapa=${etapa}`]}>
      <MetaCriacaoPage />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByText('Ver etapas e editar respostas'));
  return tela;
}

/** A BM selecionada carrega as contas automaticamente; a pessoa escolhe apenas
 * a conta de anúncios. Não existe botão intermediário de sincronização. */
async function comConta(etapa: string) {
  abrir('base');
  await waitFor(() => expect(api.contasMetaLocal).toHaveBeenCalled());
  fireEvent.change(screen.getByLabelText(/conta de anúncios/i), { target: { value: conta.referencia_opaca } });
  await waitFor(() => expect(api.ativosCriacaoMeta).toHaveBeenCalledWith(conta.referencia_opaca));
  await waitFor(() => expect(api.receitasCriacaoMetaV2).toHaveBeenCalled());
  if (etapa !== 'base') ir(etapa);
}

const NOME_DA_ETAPA: Record<string, RegExp> = {
  base: /^Conta$/i, campanha: /^Resultado$/i, orcamento: /^Orçamento/i, conjunto: /^Conjunto/i,
  publico: /^Público/i, criativo: /^Criativos$/i, mensuracao: /^Conversão$/i, revisao: /^Revisão/i,
};

function ir(etapa: string) {
  fireEvent.click(screen.getByRole('button', { name: NOME_DA_ETAPA[etapa] }));
  for (const summary of document.querySelectorAll('main details > summary')) {
    if (!summary.parentElement!.hasAttribute('open')) fireEvent.click(summary);
  }
}

/** Confirma as declarações que a bancada exige antes de liberar a conferência. */
function confirmarDeclaracoes() {
  ir('campanha');
  fireEvent.click(screen.getByRole('button', { name: /^Destino$/i }));
  fireEvent.change(screen.getByLabelText('Endereço da página'), { target: { value: 'https://focogenial.com/' } });
  fireEvent.change(screen.getByLabelText('Como vamos chamar esta campanha?'), { target: { value: 'Campanha de prova' } });
  fireEvent.click(screen.getByRole('button', { name: /^Resultado$/i }));
  fireEvent.change(screen.getByLabelText(/campanha envolve crédito, emprego/i), { target: { value: 'none' } });
  ir('criativo');
  fireEvent.click(screen.getByRole('checkbox', { name: /peça é própria ou licenciada/i }));
  fireEvent.click(screen.getByRole('checkbox', { name: /marcas, logos e identidades/i }));
}

/** Troca o modo de orçamento de verdade: escolher e CONFIRMAR. */
function trocarOrcamento(nome: RegExp) {
  ir('orcamento');
  fireEvent.click(screen.getByRole('radio', { name: nome }));
  fireEvent.click(screen.getByRole('button', { name: /confirmar a troca/i }));
}

/** Confere o plano e devolve o CORPO desta chamada.
 *
 * ⚠️ A contagem anterior é lida antes do clique. Sem ela, `toHaveBeenCalled`
 * passaria por causa de uma compilação anterior e o teste leria o corpo velho —
 * exatamente o defeito que ele existe para detectar. */
async function compilarV2() {
  const antes = api.compilarPlanoMetaV2.mock.calls.length;
  ir('revisao');
  await waitFor(
    () => expect(api.compilarPlanoMetaV2.mock.calls.length).toBe(antes + 1));
  return api.compilarPlanoMetaV2.mock.calls.at(-1)![0] as PlanoMetaV2Input;
}

// ═══════════════════════════════════════════════════════════════════════════
// F04/F05/F06 — orçamento
// ═══════════════════════════════════════════════════════════════════════════

describe('Orçamento ABO ↔ CBO', () => {
  it('o corpo enviado nunca tem orçamento nos dois níveis', async () => {
    // Dois conjuntos mantêm o plano no contrato V2 nas DUAS pontas da troca:
    // com um só, voltar para ABO diário devolveria o plano ao V1 e o teste
    // estaria comparando corpos de contratos diferentes.
    await comDoisConjuntos();

    const abo = await compilarV2();
    expect(abo.campaign_budget).toBeNull();
    expect(abo.adsets.every((item) => item.budget !== null)).toBe(true);
    expect(abo.adsets.every((item) => item.budget?.nivel === 'ADSET')).toBe(true);

    trocarOrcamento(/na campanha \(CBO\)/i);
    const cbo = await compilarV2();
    expect(cbo.campaign_budget).not.toBeNull();
    expect(cbo.campaign_budget?.nivel).toBe('CAMPAIGN');
    expect(cbo.adsets.every((item) => item.budget === null)).toBe(true);
  });

  it('trocar de modo pede confirmação e não move valor em silêncio', async () => {
    await comConta('orcamento');
    const antes = screen.getByLabelText('Orçamento diário em reais');
    expect(antes.getAttribute('id')).toBe('meta-budget-adset-001');

    fireEvent.click(screen.getByRole('radio', { name: /na campanha \(CBO\)/i }));

    // Nada mudou ainda: o campo continua sendo o do conjunto, com o mesmo valor.
    expect(screen.getByLabelText('Orçamento diário em reais').getAttribute('id'))
      .toBe('meta-budget-adset-001');
    expect(screen.getByLabelText('Orçamento diário em reais')).toHaveProperty('value', '10,00');

    // E a consequência está escrita antes do segundo clique.
    const confirmacao = screen.getByRole('group', { name: /confirmar a troca do modo/i });
    expect(within(confirmacao).getByText(/A verba deixa de ser de cada conjunto/i)).toBeTruthy();
    expect(within(confirmacao).getByText(/Nenhum valor é movido agora/i)).toBeTruthy();

    // Desistir mantém tudo como estava.
    fireEvent.click(screen.getByRole('button', { name: /manter como está/i }));
    expect(screen.queryByRole('group', { name: /confirmar a troca do modo/i })).toBeNull();
    expect(screen.getByLabelText('Orçamento diário em reais').getAttribute('id'))
      .toBe('meta-budget-adset-001');
  });

  it('trocar diário por total não converte o número escrito', async () => {
    await comConta('orcamento');
    fireEvent.change(screen.getByLabelText('Orçamento diário em reais'), {
      target: { value: '30,00' },
    });
    trocarOrcamento(/total do período/i);
    expect(screen.getByLabelText('Orçamento total em reais')).toHaveProperty('value', '30,00');
  });

  it('o campo de orçamento não perde o foco depois do primeiro dígito', async () => {
    await comConta('orcamento');
    const campo = screen.getByLabelText('Orçamento diário em reais') as HTMLInputElement;
    campo.focus();
    expect(document.activeElement).toBe(campo);

    fireEvent.change(campo, { target: { value: '1' } });

    // ⚠️ `A31`: identidade do nó E foco. Um componente declarado dentro do
    // render remontaria a subárvore e o segundo dígito cairia fora do campo.
    const depois = screen.getByLabelText('Orçamento diário em reais') as HTMLInputElement;
    expect(depois).toBe(campo);
    expect(document.activeElement).toBe(campo);
    expect(depois.value).toBe('1');

    fireEvent.change(depois, { target: { value: '12' } });
    expect(screen.getByLabelText('Orçamento diário em reais')).toBe(campo);
    expect(document.activeElement).toBe(campo);
    expect((screen.getByLabelText('Orçamento diário em reais') as HTMLInputElement).value)
      .toBe('12');
    // E o valor interpretado aparece ao lado, sem reescrever o que foi digitado.
    expect(screen.getAllByText(/R\$\s*12,00/).length).toBeGreaterThan(0);
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// F10/F34 — conjuntos e o mapa anúncio → conjunto
// ═══════════════════════════════════════════════════════════════════════════

/** Monta dois conjuntos e dois anúncios, o segundo apontando para o segundo. */
async function comDoisConjuntos() {
  await comConta('conjunto');
  fireEvent.click(screen.getByRole('button', { name: /adicionar outro conjunto/i }));
  await waitFor(() => expect(screen.getAllByTestId('conjunto-chave')).toHaveLength(2));

  ir('campanha');
  fireEvent.click(screen.getByRole('button', { name: /^Destino$/i }));
  fireEvent.change(screen.getByLabelText('Endereço da página'), { target: { value: 'https://focogenial.com/' } });
  fireEvent.change(screen.getByLabelText('Como vamos chamar esta campanha?'), { target: { value: 'Campanha de prova' } });
  fireEvent.click(screen.getByRole('button', { name: /^Resultado$/i }));
  fireEvent.change(screen.getByLabelText(/campanha envolve crédito, emprego/i), { target: { value: 'none' } });
  ir('criativo');
  fireEvent.click(screen.getByRole('checkbox', { name: /peça é própria ou licenciada/i }));
  fireEvent.click(screen.getByRole('checkbox', { name: /marcas, logos e identidades/i }));
  fireEvent.change(screen.getByLabelText('Reutilizar este criativo em outro conjunto'), { target: { value: 'adset-002' } });
  fireEvent.click(screen.getByRole('button', { name: 'Criar cópia no conjunto escolhido' }));
  fireEvent.click(within(screen.getByRole('group', { name: 'Escolher conjunto dos anúncios' })).getByRole('button', { name: /Conjunto 2/ }));
  await waitFor(() => expect(screen.getAllByTestId('variacao-chave')).toHaveLength(1));
  expect(screen.getByTestId('variacao-conjunto').textContent).toBe('adset-002');
  const direitos = screen.getAllByRole('checkbox', { name: /peça é própria ou licenciada/i });
  const identidades = screen.getAllByRole('checkbox', { name: /marcas, logos e identidades/i });
  expect(direitos[0]).toHaveProperty('checked', false);
  expect(identidades[0]).toHaveProperty('checked', false);
  fireEvent.click(direitos[0]); fireEvent.click(identidades[0]);
}

describe('Vários conjuntos e o mapa de anúncios', () => {
  it('não avança nem compila anúncio antigo enquanto o pack selecionado aguarda envio', async () => {
    await comDoisConjuntos();
    fireEvent.click(screen.getByRole('radio', { name: /usar pack salvo/i }));
    fireEvent.click(await screen.findByRole('button', { name: 'Usar este pack' }));
    await screen.findByText(/Pack vinculado neste conjunto/i);
    fireEvent.click(screen.getByRole('button', { name: /^Continuar$/ }));
    expect(screen.getByRole('heading', { name: 'Vamos dar forma à campanha?' })).toBeTruthy();
    expect(screen.getByText(/Os anúncios anteriores não substituem o pack escolhido/)).toBeTruthy();
    ir('revisao');
    expect(screen.queryByRole('checkbox', { name: /Aprovo o uso da imagem/ })).toBeNull();
    expect(screen.getByText(/Voltar ao pack e concluir envio/i)).toBeTruthy();
    expect(api.compilarPlanoMetaV2).not.toHaveBeenCalled();
    expect(api.compilarPlanoMeta).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Voltar ao pack e concluir envio' })).toBeTruthy();
  });

  it('uma falha na recuperação dos packs não vira lista vazia autorizada', async () => {
    packApi.listarSelecoesDePack.mockRejectedValue(new Error('Selection service unavailable'));
    await comConta('criativo');
    fireEvent.click(screen.getByRole('button', { name: /^Continuar$/ }));
    expect(screen.getByText(/Não foi possível recuperar os packs deste rascunho/)).toBeTruthy();
    ir('revisao');
    expect(screen.getAllByText(/Não foi possível recuperar os packs deste rascunho/i).length).toBeGreaterThan(0);
    expect(api.compilarPlanoMeta).not.toHaveBeenCalled();
  });

  it('a revisão final exige ato humano para o anúncio atual e invalida quando o texto muda', async () => {
    await comConta('criativo');
    ir('revisao');
    const consent = screen.getByRole('checkbox', { name: /Aprovo o uso da imagem no anúncio 1/ });
    expect(consent).toHaveProperty('checked', false);
    fireEvent.click(consent);
    expect(consent).toHaveProperty('checked', true);
    ir('criativo');
    expect(screen.getByRole('checkbox', { name: /peça é própria ou licenciada/i })).toHaveProperty('checked', true);
    expect(screen.getByRole('checkbox', { name: /marcas, logos e identidades/i })).toHaveProperty('checked', true);
    fireEvent.change(screen.getByLabelText('Texto principal'), { target: { value: 'Texto novo exige nova revisão.' } });
    ir('revisao');
    expect(screen.getByRole('checkbox', { name: /Aprovo o uso da imagem no anúncio 1/ })).toHaveProperty('checked', false);
  });

  it('persiste e restaura um pack diferente por conjunto sem seleção fantasma', async () => {
    await comDoisConjuntos();
    fireEvent.click(screen.getByRole('radio', { name: /usar pack salvo/i }));
    fireEvent.click(await screen.findByRole('button', { name: 'Usar este pack' }));
    await screen.findByText(/Pack vinculado neste conjunto/i);
    expect(packApi.fixarPackNoConjunto.mock.calls.at(-1)?.[1]).toBe('adset-002');

    const trilho = screen.getByRole('group', { name: 'Escolher conjunto dos anúncios' });
    fireEvent.click(within(trilho).getByRole('button', { name: /Brasil/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Usar este pack' }));
    await waitFor(() => expect(packApi.fixarPackNoConjunto.mock.calls.at(-1)?.[1]).toBe('adset-001'));

    fireEvent.click(within(trilho).getByRole('button', { name: /Conjunto 2/ }));
    expect(await screen.findByText(/Pack vinculado neste conjunto/i)).toBeTruthy();
    expect(screen.getAllByText(/Pack Encceja vinculado/i)).toHaveLength(2);
  });
  it('edita somente o anúncio do conjunto selecionado, preservando o índice original', async () => {
    await comDoisConjuntos();
    fireEvent.change(screen.getByLabelText('Título', { selector: '#meta-headline-1' }), { target: { value: 'Título só do segundo' } });
    fireEvent.click(within(screen.getByRole('group', { name: 'Escolher conjunto dos anúncios' })).getByRole('button', { name: /Brasil/ }));
    expect(screen.getByLabelText('Título', { selector: '#meta-headline-0' })).not.toHaveProperty('value', 'Título só do segundo');
    expect(screen.queryByLabelText('Título', { selector: '#meta-headline-1' })).toBeNull();
    fireEvent.click(within(screen.getByRole('group', { name: 'Escolher conjunto dos anúncios' })).getByRole('button', { name: /Conjunto 2/ }));
    expect(screen.getByLabelText('Título', { selector: '#meta-headline-1' })).toHaveProperty('value', 'Título só do segundo');
  });
  it('duplica a copy, abre o slot vazio para upload e não oferece Dark Post', async () => {
    await comConta('criativo');
    expect(screen.queryByText(/Dark Post/i)).toBeNull();
    expect(screen.queryByText(/publicação existente/i)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /Duplicar e trocar imagem/i }));
    const alvos = await screen.findAllByText(/Clique para enviar uma imagem/i);
    expect(alvos).toHaveLength(2);
    const input = alvos.at(-1)!.closest('label')!.querySelector('input[type="file"]')!;
    const arquivo = new File(['png'], 'troca.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [arquivo] } });

    await waitFor(() => expect(packApi.importarMidiaPrivada).toHaveBeenCalledWith(
      arquivo, expect.stringContaining('Anúncio estático')));
    await waitFor(() => expect(packApi.salvarPack).toHaveBeenCalledWith(
      'Upload · troca', ['00000000-0000-4000-8000-000000000333']));
    await waitFor(() => expect(packApi.fixarPackNoConjunto).toHaveBeenCalledWith(
      expect.any(String), 'adset-001', '00000000-0000-4000-8000-000000000444', 0));
  });
  it('reordenar não troca a identidade do conjunto nem o pai do anúncio', async () => {
    await comDoisConjuntos();

    const antes = await compilarV2();
    expect(antes.adsets.map((item) => item.adset_key)).toEqual(['adset-001', 'adset-002']);
    expect(antes.ads.map((item) => item.adset_key)).toEqual(['adset-001', 'adset-002']);

    ir('conjunto');
    fireEvent.click(screen.getByRole('button', { name: /mover o conjunto 2 para cima/i }));
    await waitFor(() => expect(
      screen.getAllByTestId('conjunto-chave').map((no) => no.textContent),
    ).toEqual(['adset-002', 'adset-001']));

    const depois = await compilarV2();
    // A ordem de apresentação mudou; nenhuma chave mudou.
    expect(depois.adsets.map((item) => item.adset_key)).toEqual(['adset-002', 'adset-001']);
    // E cada anúncio continua no conjunto que o operador escolheu.
    expect(depois.ads.map((item) => [item.variation_key, item.adset_key])).toEqual([
      ['variation-001', 'adset-001'],
      ['variation-002', 'adset-002'],
    ]);
  });

  it('um conjunto sem anúncio impede a conferência e diz qual é', async () => {
    await comConta('conjunto');
    confirmarDeclaracoes();
    ir('conjunto');
    fireEvent.click(screen.getByRole('button', { name: /adicionar outro conjunto/i }));
    ir('revisao');
    expect(screen.getAllByText(/Nenhum anúncio aponta para o conjunto/i).length)
      .toBeGreaterThan(0);
    expect(api.compilarPlanoMetaV2).not.toHaveBeenCalled();
  });

  it('a revisão mostra o mapa peça → conjunto → anúncio vindo do resumo', async () => {
    api.compilarPlanoMetaV2.mockResolvedValue({
      ok: true, contrato: 'V2', efeito_externo: 'NENHUM',
      plano: PLANO_COMPILADO, resumo: resumo({ conjuntos: 2 }),
    });
    await comDoisConjuntos();
    await compilarV2();
    const linhas = await screen.findAllByTestId('linha-do-mapa');
    expect(linhas).toHaveLength(2);
    expect(linhas[0].textContent).toContain('adset-001 → variation-001');
    expect(linhas[1].textContent).toContain('adset-002 → variation-002');
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// F11..F21 — público
// ═══════════════════════════════════════════════════════════════════════════

describe('Público', () => {
  it('a escolha de expansão viaja sempre no corpo, aceita ou recusada', async () => {
    await comConta('orcamento');
    confirmarDeclaracoes();
    // CBO só para levar o plano ao contrato V2, sem tocar no público.
    trocarOrcamento(/na campanha \(CBO\)/i);

    const recusada = await compilarV2();
    expect('expansion' in recusada.adsets[0].audience).toBe(true);
    expect(recusada.adsets[0].audience.expansion).toBe(false);

    ir('publico');
    fireEvent.click(screen.getByRole('checkbox', { name: /Aceitar o público Advantage\+/i }));
    const aceita = await compilarV2();
    expect(aceita.adsets[0].audience.expansion).toBe(true);
  });

  it('país e idade viajam como o operador escolheu, não como a receita fixava', async () => {
    await comConta('publico');
    confirmarDeclaracoes();
    ir('publico');
    fireEvent.click(screen.getByLabelText(/países alcançados/i));
    fireEvent.click(await screen.findByText('Portugal'));
    fireEvent.click(screen.getByLabelText(/países excluídos/i));
    fireEvent.click(await screen.findByText('Paraguai'));
    fireEvent.change(screen.getByLabelText(/idade mínima/i), { target: { value: '25' } });

    const corpo = await compilarV2();
    expect(corpo.adsets[0].audience.geo.countries).toEqual(['BR', 'PT']);
    expect(corpo.adsets[0].audience.geo.excluded_countries).toEqual(['PY']);
    expect(corpo.adsets[0].audience.age_min).toBe(25);
  });

  it('com promete_alcance_exclusivo falso a tela NÃO afirma alcance exclusivo', async () => {
    api.compilarPlanoMetaV2.mockResolvedValue({
      ok: true, contrato: 'V2', efeito_externo: 'NENHUM',
      plano: PLANO_COMPILADO, resumo: resumo({ exclusivo: false }),
    });
    await comConta('orcamento');
    confirmarDeclaracoes();
    trocarOrcamento(/na campanha \(CBO\)/i);
    await compilarV2();

    // Na revisão, que renderiza o resumo do servidor.
    expect(screen.queryByText(/Somente o público selecionado será alcançado/i)).toBeNull();
    expect(screen.getAllByText(/pode alcançar pessoas fora do público selecionado/i).length)
      .toBeGreaterThan(0);

    // E na etapa de público, que lê o mesmo campo do mesmo resumo.
    ir('publico');
    expect(screen.queryByText(/Somente o público selecionado será alcançado/i)).toBeNull();
    expect(screen.getByText(/não promete alcance exclusivo/i)).toBeTruthy();
  });

  it('o Instagram fica fechado enquanto não houver identidade, com a causa escrita', async () => {
    await comConta('publico');
    fireEvent.click(screen.getByRole('radio', { name: /escolher à mão/i }));
    const instagram = screen.getByRole('checkbox', { name: /^Instagram/i });
    expect(instagram).toHaveProperty('disabled', true);
    expect(screen.getAllByText(/exige uma identidade validada/i).length).toBeGreaterThan(0);
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// F22..F25 — mensuração e o tri-state
// ═══════════════════════════════════════════════════════════════════════════

describe('Mensuração', () => {
  async function lerMensuracao() {
    await comConta('mensuracao');
    // Mensuração é contexto obrigatório da conta e chega automaticamente ao
    // entrar na etapa; o botão restante serve apenas para atualizar/repetir.
    await waitFor(() => expect(api.catalogoDeMensuracaoMeta).toHaveBeenCalledTimes(1));
  }

  it('uma conversão UNKNOWN aparece com a causa e NUNCA como elegível', async () => {
    await lerMensuracao();

    const seletor = await screen.findByLabelText(/conversão personalizada/i) as HTMLSelectElement;
    const opcoes = [...seletor.options].map((item) => item.value);
    expect(opcoes).toContain('metaobj_conv_viva');
    // ⚠️ `A12`: "não sei" não pode ser oferecido como escolha.
    expect(opcoes).not.toContain('metaobj_conv_incerta');

    // Mas ela não some: aparece com a palavra própria e a causa fechada.
    expect(screen.getByText('Lead sem flag')).toBeTruthy();
    expect(screen.getAllByText(/não sei dizer/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/não trouxe o status de entrega/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/não pode ser escolhida/i).length).toBeGreaterThan(0);
  });

  it('pixel e conversão viajam em catálogos SEPARADOS, com seletores separados', async () => {
    await lerMensuracao();
    expect(screen.getByText(/Pixels e datasets desta conta/i)).toBeTruthy();
    expect(screen.getByText(/Conversões personalizadas desta conta/i)).toBeTruthy();

    const fontes = await screen.findByLabelText(/fonte do evento/i) as HTMLSelectElement;
    const opcoes = [...fontes.options].map((item) => item.value);
    expect(opcoes).toContain('metapixel_principal');
    // ⚠️ `source_kind: UNKNOWN` é "a resposta não disse se é pixel ou dataset".
    // Ele não pode virar nenhum dos dois, então não é oferecido.
    expect(opcoes).not.toContain('metapixel_incerto');
    expect(screen.getByText(/a resposta não disse se é pixel ou dataset/i)).toBeTruthy();
  });

  it('a fonte escolhida leva o source_kind do ITEM, não uma escolha de tela', async () => {
    await lerMensuracao();
    fireEvent.change(await screen.findByLabelText(/fonte do evento/i), {
      target: { value: 'metapixel_principal' },
    });
    confirmarDeclaracoes();
    const corpo = await compilarV2();
    expect(corpo.adsets[0].measurement.source_ref).toBe('metapixel_principal');
    expect(corpo.adsets[0].measurement.source_kind).toBe('PIXEL');
  });

  it('a leitura da mensuração é da conta e começa automaticamente na etapa', async () => {
    await comConta('mensuracao');
    await waitFor(() => expect(api.catalogoDeMensuracaoMeta).toHaveBeenCalledTimes(1));
    expect(await screen.findByLabelText(/fonte do evento/i)).toBeTruthy();
    expect(screen.getAllByRole('button', { name: /atualizar lista/i }).length).toBeGreaterThan(0);
  });

  it('relatar e otimizar são separados, e a receita decide qual existe', async () => {
    await comConta('mensuracao');
    const otimizar = screen.getByRole('radio', { name: /^Otimizar/i });
    // A receita padrão admite só relatório: otimizar não pode nem parecer aberto.
    expect(otimizar).toHaveProperty('disabled', true);
    expect(screen.getByText(/Relatar não muda a entrega/i)).toBeTruthy();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// F12..F16 — catálogos da conta
// ═══════════════════════════════════════════════════════════════════════════

describe('Catálogos da conta', () => {
  it('mensuração e públicos chegam automaticamente; lugares continuam sob busca', async () => {
    await comConta('publico');
    ir('mensuracao');
    await waitFor(() => expect(api.catalogoDeMensuracaoMeta).toHaveBeenCalledTimes(1));
    ir('publico');
    ir('conjunto');
    ir('publico');
    await waitFor(() => expect(api.catalogoDePublicosMeta).toHaveBeenCalledTimes(1));
    expect(api.catalogoDeGeografiaMeta).not.toHaveBeenCalled();
    expect(api.catalogoDeMensuracaoMeta).toHaveBeenCalledTimes(1);
    expect(api.catalogoDePublicosMeta).toHaveBeenCalledWith(conta.referencia_opaca);
    // Ler um catálogo não arrasta os outros junto.
    expect(api.catalogoDeGeografiaMeta).not.toHaveBeenCalled();
    expect(api.catalogoDeMensuracaoMeta).toHaveBeenCalledTimes(1);
  });

  it('o público escolhido viaja como referencia_opaca, no campo do subtipo certo', async () => {
    await comConta('publico');
    confirmarDeclaracoes();
    ir('publico');
    await waitFor(() => expect(api.catalogoDePublicosMeta).toHaveBeenCalled());

    // Público amplo não aceita público salvo: a escolha do modo é explícita.
    fireEvent.click(screen.getByRole('radio', { name: /^Manual/i }));
    fireEvent.change(
      await screen.findByLabelText('Decisão sobre o público Visitantes 30 dias'),
      { target: { value: 'incluir' } });
    fireEvent.change(screen.getByLabelText('Decisão sobre o público Semelhante 1%'),
      { target: { value: 'incluir' } });

    const corpo = await compilarV2();
    const audiencia = corpo.adsets[0].audience;
    // ⚠️ O que viaja é a referência OPACA do item do catálogo, nunca texto.
    expect(audiencia.include_custom_refs).toEqual(['metaaud_visitantes']);
    // E o semelhante vai para o campo dele, decidido pelo `subtype` da Meta.
    expect(audiencia.lookalike_refs).toEqual(['metaaud_semelhante']);
    expect(audiencia.exclude_custom_refs).toEqual([]);
  });

  it('um público UNKNOWN não pode ser escolhido', async () => {
    await comConta('publico');
    await waitFor(() => expect(api.catalogoDePublicosMeta).toHaveBeenCalled());
    expect(await screen.findByLabelText('Decisão sobre o público Público sem flag'))
      .toHaveProperty('disabled', true);
    expect(screen.getByLabelText('Decisão sobre o público Visitantes 30 dias'))
      .toHaveProperty('disabled', false);
  });

  it('público salvo com modo Amplo é recusado antes do 409 da Meta', async () => {
    await comConta('publico');
    confirmarDeclaracoes();
    ir('publico');
    await waitFor(() => expect(api.catalogoDePublicosMeta).toHaveBeenCalled());
    fireEvent.change(
      await screen.findByLabelText('Decisão sobre o público Visitantes 30 dias'),
      { target: { value: 'incluir' } });

    expect(screen.getByText(/Público amplo não aceita público salvo/i)).toBeTruthy();
    expect(screen.getAllByText(/META_AUDIENCE_MODE_CONFLICT/).length).toBeGreaterThan(0);
    ir('revisao');
    expect(screen.queryByRole('button', { name: /tentar conferência novamente/i })).toBeNull();
    expect(api.compilarPlanoMetaV2).not.toHaveBeenCalled();
  });

  it('texto livre JAMAIS vira chave de geografia; só a key do catálogo viaja', async () => {
    await comConta('publico');
    confirmarDeclaracoes();
    // CBO só para manter o plano no contrato V2 na primeira compilação, quando
    // ainda não há nenhum lugar escolhido para levá-lo até lá.
    trocarOrcamento(/na campanha \(CBO\)/i);
    ir('publico');
    // O operador digita e até busca — mas não escolhe nada da lista.
    fireEvent.change(screen.getByLabelText(/buscar um lugar no catálogo/i), {
      target: { value: 'Curitiba' },
    });
    fireEvent.click(screen.getByRole('button', { name: /ler lugares desta conta/i }));
    await waitFor(() => expect(api.catalogoDeGeografiaMeta).toHaveBeenCalled());
    expect(api.catalogoDeGeografiaMeta).toHaveBeenCalledWith(
      expect.objectContaining({ termo: 'Curitiba' }));

    const semEscolha = await compilarV2();
    expect(semEscolha.adsets[0].audience.geo.city_keys).toEqual([]);
    expect(JSON.stringify(semEscolha)).not.toContain('Curitiba');

    // Agora ele ESCOLHE o item, e é a `key` do catálogo que viaja.
    ir('publico');
    fireEvent.click(screen.getAllByRole('button', { name: /^Incluir$/i })[0]);
    const comEscolha = await compilarV2();
    expect(comEscolha.adsets[0].audience.geo.city_keys).toEqual(['3844']);
    expect(comEscolha.adsets[0].audience.geo.excluded_city_keys).toEqual([]);
  });

  it('um lugar sem chave canônica não pode ser escolhido', async () => {
    await comConta('publico');
    fireEvent.change(screen.getByLabelText(/buscar um lugar no catálogo/i), {
      target: { value: 'Curitiba' },
    });
    fireEvent.click(screen.getByRole('button', { name: /ler lugares desta conta/i }));
    await waitFor(() => expect(api.catalogoDeGeografiaMeta).toHaveBeenCalled());
    const incluir = await screen.findAllByRole('button', { name: /^Incluir$/i });
    expect(incluir[0]).toHaveProperty('disabled', false);
    expect(incluir[1]).toHaveProperty('disabled', true);
    expect(screen.getByText(/veio sem chave canônica/i)).toBeTruthy();
  });

  it('excluir um lugar viaja no campo de exclusão, não no de inclusão', async () => {
    await comConta('publico');
    confirmarDeclaracoes();
    ir('publico');
    fireEvent.change(screen.getByLabelText(/buscar um lugar no catálogo/i), {
      target: { value: 'Curitiba' },
    });
    fireEvent.click(screen.getByRole('button', { name: /ler lugares desta conta/i }));
    await waitFor(() => expect(api.catalogoDeGeografiaMeta).toHaveBeenCalled());
    fireEvent.click((await screen.findAllByRole('button', { name: /^Excluir$/i }))[0]);

    const corpo = await compilarV2();
    expect(corpo.adsets[0].audience.geo.excluded_city_keys).toEqual(['3844']);
    expect(corpo.adsets[0].audience.geo.city_keys).toEqual([]);
  });

  it('trocar de conta apaga o catálogo carregado e a seleção feita nele', async () => {
    const outra = { ...conta, referencia_opaca: 'metaacct_outra', nome: 'Outra conta' };
    api.contasMetaLocal.mockResolvedValue({
      ok: true, api_version: 'v26.0', armazenamento: 'macOS Keychain', contas: [conta, outra],
    });
    abrir('base');
    await waitFor(() => expect(api.contasMetaLocal).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText(/conta de anúncios/i), {
      target: { value: conta.referencia_opaca },
    });
    await waitFor(() => expect(api.ativosCriacaoMeta).toHaveBeenCalled());

    ir('publico');
    await waitFor(() => expect(api.catalogoDePublicosMeta).toHaveBeenCalled());
    fireEvent.change(
      await screen.findByLabelText('Decisão sobre o público Visitantes 30 dias'),
      { target: { value: 'incluir' } });
    expect(screen.getByText('Visitantes 30 dias')).toBeTruthy();

    // O operador troca de conta. A lista pertencia à conta anterior.
    ir('base');
    fireEvent.change(screen.getByLabelText(/conta de anúncios/i), {
      target: { value: outra.referencia_opaca },
    });
    await waitFor(() => expect(api.ativosCriacaoMeta).toHaveBeenCalledWith(outra.referencia_opaca));

    ir('publico');
    expect(screen.queryByText('Visitantes 30 dias')).toBeNull();
    await waitFor(() => expect(api.catalogoDePublicosMeta).toHaveBeenLastCalledWith(outra.referencia_opaca));
    expect(screen.queryByText('Visitantes 30 dias')).toBeTruthy();
    // E a seleção feita na conta anterior saiu junto: ela não resolveria aqui.
    expect(screen.getByText(/0 incluídos · 0 excluídos/)).toBeTruthy();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// F03 / F37 / A33 — receita, resumo e invalidação
// ═══════════════════════════════════════════════════════════════════════════

describe('Receita e revisão', () => {
  it('não acusa URL válida quando a pendência é a fonte da conversão', async () => {
    await comConta('campanha');
    fireEvent.click(screen.getByRole('radio', { name: /Vendas no site/i }));
    fireEvent.click(screen.getByRole('button', { name: /^Destino$/i }));
    fireEvent.change(screen.getByLabelText('Endereço da página'), { target: { value: 'https://exemplo.com/materia' } });
    ir('revisao');
    expect(screen.getAllByText(/Escolha o pixel ou dataset da conta/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Informe uma URL de destino HTTPS/)).toBeNull();
    expect(api.validarPlanoMetaV2).not.toHaveBeenCalled();
  });

  it('catálogo legado sem capacidade não converte evidência histórica em autorização', async () => {
    await comConta('campanha');
    fireEvent.click(screen.getByRole('radio', { name: /Vendas no site/i }));
    expect(screen.getByText(/O catálogo não confirmou a disponibilidade da criação pausada/i)).toBeTruthy();
    expect(screen.getByText(/elegibilidade do evento desta conta não foi provada/i)).toBeTruthy();
    // A conferência automática não transforma um catálogo histórico em
    // capacidade operacional e não expõe um botão manual para contornar isso.
    ir('revisao');
    expect(screen.queryByRole('button', { name: /validar na meta/i })).toBeNull();
    expect(api.validarPlanoMetaV2).not.toHaveBeenCalled();
  });

  it('fluxo pausado implementado não aparece fechado por falta de prova histórica', async () => {
    api.receitasCriacaoMetaV2.mockResolvedValue({
      ...CATALOGO,
      receitas: CATALOGO.receitas.map((item) => ({ ...item,
        capacidade_pausada: CAPACIDADE_PAUSADA,
        modos_de_orcamento: item.modos_de_orcamento.map((modo) => ({ ...modo,
          capacidade_pausada: CAPACIDADE_PAUSADA,
        })),
      })),
    });
    await comConta('campanha');
    fireEvent.click(screen.getByRole('radio', { name: /Vendas no site/i }));
    expect(screen.getByText('fluxo pausado disponível')).toBeTruthy();
    expect(screen.getByText(/elegibilidade do evento desta conta não foi provada/i)).toBeTruthy();
    expect(screen.queryByText(/criar fechado|criar liberado/i)).toBeNull();
    expect(screen.queryByText(/catálogo não confirmou/i)).toBeNull();
    ir('orcamento');
    trocarOrcamento(/na campanha \(CBO\)/i);
    expect(screen.queryByText(/Confira a disponibilidade deste modo de orçamento/i)).toBeNull();
    ir('revisao');
    expect((screen.getByRole('button', { name: /criar campanha PAUSED/i }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.aprovarCriacaoMeta).not.toHaveBeenCalled();
    expect(api.criarCampanhaPausadaMeta).not.toHaveBeenCalled();
  });

  it('capacidade explicitamente indisponível prevalece sobre criar_liberado legado', async () => {
    api.receitasCriacaoMetaV2.mockResolvedValue({
      ...CATALOGO,
      receitas: CATALOGO.receitas.map((item) => ({ ...item, criar_liberado: true,
        capacidade_pausada: { ...CAPACIDADE_PAUSADA, implementada: false },
      })),
    });
    await comConta('campanha');
    expect(screen.getByText('conferir disponibilidade')).toBeTruthy();
    expect(screen.queryByText('fluxo pausado disponível')).toBeNull();
    expect(screen.queryByText('criar liberado')).toBeNull();
  });

  it('mudar um campo depois de validar derruba a prova e o resumo do servidor', async () => {
    await comConta('orcamento');
    confirmarDeclaracoes();
    trocarOrcamento(/na campanha \(CBO\)/i);
    await compilarV2();
    await waitFor(() => expect(api.validarPlanoMetaV2).toHaveBeenCalled());
    expect(await screen.findByText(/Resultado da validação remota/i)).toBeTruthy();
    expect(screen.getByText(/Validação concluída nas operações independentes/)).toBeTruthy();
    expect(screen.getAllByTestId('linha-do-mapa').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /^Destino$/i }));
    fireEvent.change(screen.getByLabelText('Como vamos chamar esta campanha?'), {
      target: { value: 'Outra campanha inteira' },
    });
    ir('revisao');

    // ⚠️ `A33`: o resumo descrevia o plano anterior. Ele cai com a validação.
    expect(screen.queryByText(/Resultado da validação remota/i)).toBeNull();
    expect(screen.getByText(/O plano mudou. Confira e valide novamente/)).toBeTruthy();
    expect(screen.queryAllByTestId('linha-do-mapa')).toHaveLength(0);
    expect(screen.getByText(/O plano mudou. Confira e valide novamente/i)).toBeTruthy();
  });

  it('a revisão diz por que este plano usa o contrato V2', async () => {
    await comConta('orcamento');
    confirmarDeclaracoes();
    trocarOrcamento(/na campanha \(CBO\)/i);
    ir('revisao');
    expect(screen.getByText(/Por que este plano usa o contrato V2/i)).toBeTruthy();
    expect(screen.getByText(/a verba mora na campanha \(CBO\)/i)).toBeTruthy();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// A regra de ouro: sem aprovação durável não cria; nenhum botão ativa
// ═══════════════════════════════════════════════════════════════════════════

describe('Nascimento V2 condicionado à aprovação durável', () => {
  it('capacidade e validação sozinhas não habilitam criação', async () => {
    await comConta('orcamento');
    confirmarDeclaracoes();
    trocarOrcamento(/na campanha \(CBO\)/i);
    await compilarV2();
    await waitFor(() => expect(api.validarPlanoMetaV2).toHaveBeenCalled());

    const criar = screen.getByRole('button', { name: /criar campanha PAUSED/i });
    expect((criar as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(criar);
    expect(api.aprovarCriacaoMeta).not.toHaveBeenCalled();
    expect(api.criarCampanhaPausadaMeta).not.toHaveBeenCalled();
  });

  it('nenhum botão da tela ativa coisa nenhuma', async () => {
    await comConta('revisao');
    const botoes = screen.getAllByRole('button').map((no) => no.textContent ?? '');
    expect(botoes.some((texto) => /ativar|publicar|ligar campanha/i.test(texto))).toBe(false);
    expect(screen.getByText(/Ativar continua sendo outro ato/i)).toBeTruthy();
  });
});
