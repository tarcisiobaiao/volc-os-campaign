// @vitest-environment jsdom
/**
 * A Bancada dos quatro canais, montada com o contrato GADS-CRIACAO-CANAIS-v1.
 *
 * Duas coisas são provadas aqui, na PÁGINA (e não só na montagem pura):
 *
 * 1. **Search ponta a ponta:** com Maximizar conversões e CPA alvo 4,5, o
 *    `/provar` recebe `configuracao_search.lance.target_cpa = 4.5`, SEM
 *    `cpc_inicial`, e com `match_por_keyword`; quando o servidor devolve 422 com
 *    `loc`, o erro aparece na Revisão (com o caminho) e NO CAMPO do CPA alvo,
 *    na parada Economia.
 * 2. **Cada canal abre com os controles do contrato** — é a prova de tela por
 *    renderização, com o esquema vivo servido pelo fixture gerado do backend.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import type { Cockpit } from '@/types/trafego';
import esquemaFixture from '@/lib/trafego/configuracao/__tests__/esquema-canais.fixture.json';

const { cockpitDeTrafego, provarCampanha, KW, ErroDaApi } = vi.hoisted(() => {
  class ErroDaApi extends Error {
    status: number;
    corpo?: unknown;
    constructor(message: string, status: number, corpo?: unknown) {
      super(message);
      this.status = status;
      this.corpo = corpo;
    }
  }
  return {
    cockpitDeTrafego: vi.fn(),
    provarCampanha: vi.fn(),
    KW: ['saque anual fgts', 'valor do saque anual'],
    ErroDaApi,
  };
});

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const CONJUNTO = {
  opportunity_id: 73, cluster_id: 4,
  selecionadas: KW.map((termo) => ({
    termo, termo_normalizado: termo, match_type: 'PHRASE' as const,
    subintencao: 'ACESSO', volume: 27100, cpc: null, motivo: null,
  })),
  excluidas: [], em_revisao_humana: [], negativas: [],
  selected_set_sha256: 'b'.repeat(64),
  approved_set_sha256: 'b'.repeat(64),
  aprovado_por: 'operador@volc', selection_policy_version: 'v1',
  blockers: [], alertas: [], pode_aprovar: false, porque_nao: 'já aprovado',
};

vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: {
    cockpitDeTrafego,
    estadoDaTrava: async () => ({
      escrita_permitida: false, destravado_no_codigo: false, env_presente: false,
      motivo: '', explicacao: 'A trava é de dois fatores.',
    }),
    verticaisEPortoes: async () => ({
      verticais: [{ id: 'informativo', titulo: 'Informativo', descricao: '', exige: null, severidade: null, paises_exigem: [] }],
    }),
    revisarConjuntoPago: async () => CONJUNTO,
    aprovarConjuntoPago: vi.fn(),
    planoDeMensuracaoVigente: async () => { throw new Error('sem plano gravado'); },
    lerCopy: async () => ({
      existe: true, status: 'done', perdida: false,
      opportunity_id: 73, run_id: null, keywords: [...KW],
      copy: { headlines: ['Saque Anual 2026'], descriptions: ['Veja as regras.'], sitelinks: [], callouts: [], snippet: null },
      aceita: true, pendentes: [], diario: [], geracoes_conjunto: 1, geracoes_asset: 0,
      fatos_usados: 3, fatos_descartados: [],
      medicao: { chamadas: 1, falhas: 0, por_papel: {}, ilegiveis: 0, tokens_entrada: 1, tokens_saida: 1,
                 latencia_s: 1, custo_usd: null, sem_custo: 1, motivo_sem_custo: '' },
      segundos: 1, erro: null, criado_em: '2026-10-08T00:00:00Z', atualizado_em: '2026-10-08T00:00:00Z',
    }),
    salvarCopyEditada: vi.fn(),
    escreverCopy: vi.fn(),
    provarCampanha,
    subirCampanha: vi.fn(),
    capacidades: async () => ({ is_admin: false }),
    esquemaDosCanais: async () => esquemaFixture,
  },
  PautadorApiError: ErroDaApi,
}));

import NovaCampanhaPage from '../NovaCampanhaPage';
import { reciboApto } from '@/lib/landing-policy/__tests__/recibos';
import { esquecerEsquemaDosCanais } from '@/lib/trafego/configuracao/useEsquemaDosCanais';

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  vi.clearAllMocks();
  esquecerEsquemaDosCanais();
});

function cockpitLimpo(): Cockpit {
  return {
    opportunity_id: 73, cluster_id: 4,
    origem: {
      opportunity_id: 73, run_id: 6, project_id: 2,
      url_final: 'https://creditoup.com.br/r/saque/',
      url_procedencia: 'wp', status_wp: 'publish', post_type: 'r',
      dominio: 'https://creditoup.com.br', nicho: 'Saque Anual',
      slug: 'saque', pais: 'BR', idioma: 'pt', idioma_declarado: 'pt',
      vertical: 'informativo', vertical_declarada: 'informativo',
      resumo_da_pesquisa: '', fatos: [], tem_texto_da_lp: true,
      landing_policy_receipt: reciboApto({ url: 'https://creditoup.com.br/r/saque/' }, { agora_epoch: Date.now() / 1000 }),
    },
    triagem: null, grupos: [], descartadas: [],
    procedencia: { servicos_declarados: [], engine: '' } as never,
    avisos: [],
    conta: {
      project_id: 2, dominio: 'creditoup.com.br', customer_id: '8017851692',
      login_customer_id: '6016739364', vinculada: true, motivo: null,
      meta_conversao: { primaria: { id: '7466930854', nome: 'lead', categoria: 'SUBMIT_LEAD_FORM' } },
    },
    campanhas_lancadas: [],
  } as unknown as Cockpit;
}

const renderizar = (canal: string, etapa: string) =>
  render(
    <MemoryRouter initialEntries={[`/trafego/nova/73?canal=${canal}&etapa=${etapa}`]}>
      <Routes>
        <Route path="/trafego/nova/:opportunityId" element={<NovaCampanhaPage />} />
      </Routes>
    </MemoryRouter>,
  );

describe('Search, ponta a ponta: o pedido e o 422 no campo', () => {
  it('Maximizar conversões manda tCPA na configuração, sem cpc_inicial, com match_por_keyword — e o 422 marca o campo', async () => {
    window.sessionStorage.setItem('volc.bancada.rascunho.73.sem-run', JSON.stringify({
      orcamento: '20', lance: '', estrategia: 'MAXIMIZE_CONVERSIONS', graduacao: 30,
      certificacoes: [], keywordsFora: [], vertical: null, modeloDaCopy: '',
      matchPorKeyword: { 'saque anual fgts': 'EXACT' },
      cfgSearch: { parceiros: false, expansaoDisplay: false, lance: { tcpa: '4,5' } },
    }));
    provarCampanha.mockRejectedValue(new ErroDaApi('erro de forma', 422, [{
      type: 'configuracao_invalida',
      loc: ['body', 'configuracao_search', 'lance', 'target_cpa'],
      msg: 'tCPA acima do teto da casa para esta conta',
      input: null,
      ctx: { codigo: 'CONFIGURACAO_INVALIDA', caminho: 'configuracao_search.lance.target_cpa' },
    }]));
    cockpitDeTrafego.mockResolvedValue(cockpitLimpo());
    renderizar('SEARCH', 'revisao');

    // A Revisão já mostra o resumo das escolhas e o aviso previsto da troca.
    expect(await screen.findByText('Suas escolhas de Search')).toBeTruthy();
    expect(screen.getAllByText('MATCH_TYPE_ESCOLHIDO_NA_TELA').length).toBeGreaterThan(0);

    const botao = await screen.findByRole('button', { name: /Provar contra a conta/ });
    await waitFor(() => expect((botao as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(botao);
    await waitFor(() => expect(provarCampanha).toHaveBeenCalled());

    const pedido = provarCampanha.mock.calls[0][0];
    expect(pedido.configuracao_search.lance).toEqual({ estrategia: 'MAXIMIZE_CONVERSIONS', target_cpa: 4.5 });
    expect('cpc_inicial' in pedido).toBe(false);
    expect(pedido.estrategia_lance).toBe('MAXIMIZE_CONVERSIONS');
    expect(pedido.match_por_keyword).toEqual({ 'saque anual fgts': 'EXACT' });
    expect(pedido.rede).toEqual({ google_search: true, search_partners: false, display_expansion: false });

    // A escada não cola o JSON: manda o operador ao campo.
    expect((await screen.findAllByText(/O servidor recusou a forma do pedido. Feche esta escada/)).length).toBeGreaterThan(0);
    // A Revisão lista o erro com o caminho do contrato…
    const lista = await screen.findByRole('alert', { name: 'erros de forma' });
    expect(within(lista).getByText('configuracao_search.lance.target_cpa')).toBeTruthy();

    // …e o campo do CPA alvo, na Economia, mostra a frase do servidor.
    fireEvent.click(screen.getByRole('link', { name: /Economia/ }));
    const campo = await screen.findByLabelText('CPA alvo');
    expect((campo as HTMLInputElement).value).toBe('4,5');
    const alerta = within(campo.closest('label')!).getByRole('alert');
    expect(alerta.getAttribute('data-caminho')).toBe('configuracao_search.lance.target_cpa');
    expect(alerta.textContent).toContain('tCPA acima do teto da casa para esta conta');
  });

  it('sem decidir a rede, a Revisão não deixa provar e diz o que falta', async () => {
    window.sessionStorage.setItem('volc.bancada.rascunho.73.sem-run', JSON.stringify({
      orcamento: '20', lance: '0,30', estrategia: 'MANUAL_CPC', graduacao: 30,
      certificacoes: [], keywordsFora: [], vertical: null, modeloDaCopy: '', matchPorKeyword: {},
    }));
    cockpitDeTrafego.mockResolvedValue(cockpitLimpo());
    renderizar('SEARCH', 'revisao');
    const botao = await screen.findByRole('button', { name: /Provar contra a conta/ });
    expect((botao as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getAllByText(/decidir sobre os parceiros de pesquisa/).length).toBeGreaterThan(0);
  });
});

describe('a bancada de cada canal abre com os controles do contrato', () => {
  it('Search · Alcance: rede como escolha explícita, AI Max, geo, programação, dispositivos e datas', async () => {
    cockpitDeTrafego.mockResolvedValue(cockpitLimpo());
    renderizar('SEARCH', 'alcance');
    expect(await screen.findByText('Onde, quando e com qual automação o anúncio aparece?')).toBeTruthy();
    for (const t of ['Parceiros de pesquisa', 'Expansão para Display', 'AI Max', 'Geografia e idioma',
      'Programação de anúncios', 'Dispositivos', 'Datas']) {
      expect(screen.getAllByText(t).length).toBeGreaterThan(0);
    }
    // Sem decisão, o contrato não tem default — a tela diz isso.
    expect(screen.getAllByText(/Sem decisão — o contrato não tem default aqui/)).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: 'Ligar a expansão' }));
    expect(await screen.findByText(/sempre gera aviso no plano/)).toBeTruthy();
  });

  it('Search · Economia: as cinco estratégias, cada uma com os campos dela', async () => {
    cockpitDeTrafego.mockResolvedValue(cockpitLimpo());
    renderizar('SEARCH', 'economia');
    await screen.findByText('Quanto isto pode gastar por dia?');
    for (const e of ['CPC manual', 'Maximizar cliques', 'Maximizar conversões', 'Maximizar valor de conversão', 'Parcela de impressões']) {
      expect(screen.getByRole('button', { name: new RegExp(e) })).toBeTruthy();
    }
    fireEvent.click(screen.getByRole('button', { name: /Parcela de impressões/ }));
    expect(await screen.findByLabelText('onde aparecer')).toBeTruthy();
    expect(screen.getByLabelText('parcela de impressões')).toBeTruthy();
    expect(screen.getByLabelText('teto de CPC')).toBeTruthy();
    // As opções de local vêm do esquema vivo.
    await waitFor(() => expect(within(screen.getByLabelText('onde aparecer')).getAllByRole('option')).toHaveLength(4));
    expect(screen.queryByLabelText('lance por clique')).toBeNull();
  });

  it('Display · Brand safety: exclusões de nascimento já marcadas', async () => {
    cockpitDeTrafego.mockResolvedValue(cockpitLimpo());
    renderizar('DISPLAY', 'display_inventario');
    expect(await screen.findByText('Proteções antes de ganhar alcance')).toBeTruthy();
    expect((screen.getByLabelText(/Excluir todos os apps/) as HTMLInputElement).checked).toBe(true);
    const grupo = screen.getByRole('group', { name: 'Rótulos de conteúdo excluídos' });
    const marcados = within(grupo).getAllByRole('button').filter((b) => b.getAttribute('aria-pressed') === 'true');
    expect(marcados).toHaveLength(6);
    expect(await screen.findByText(/Padrão de nascimento \(servidor\): PARKED_DOMAIN/)).toBeTruthy();
  });

  it('Display · Economia: lance, frequência; CPC manual pede o lance do grupo', async () => {
    cockpitDeTrafego.mockResolvedValue(cockpitLimpo());
    renderizar('DISPLAY', 'display_economia');
    await screen.findByText('Compra e medição');
    fireEvent.change(screen.getByLabelText('Estratégia de lance'), { target: { value: 'MANUAL_CPC' } });
    expect(await screen.findByLabelText(/Lance por clique do grupo/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Adicionar/ }));
    expect(screen.getByLabelText(/^impressões/)).toBeTruthy();
  });

  it('Demand Gen · Kit: carrossel desabilitado com o motivo do esquema; vídeo pede ids e logo', async () => {
    cockpitDeTrafego.mockResolvedValue(cockpitLimpo());
    renderizar('DEMAND_GEN', 'demand_kit');
    const carrossel = await screen.findByRole('button', { name: /Carrossel/ });
    expect((carrossel as HTMLButtonElement).disabled).toBe(true);
    await waitFor(() => expect(screen.getByTestId('motivo-carrossel').textContent)
      .toMatch(/fronteira HTTP ainda não transporta asset remoto aprovado/i));
    fireEvent.click(screen.getByRole('button', { name: /Vídeo responsivo/ }));
    expect(await screen.findByLabelText(/Vídeos do YouTube/)).toBeTruthy();
    expect(screen.getByText(/exatamente um no vídeo responsivo/)).toBeTruthy();
  });

  it('Demand Gen · Economia: lance com alvo e automações só do formato', async () => {
    cockpitDeTrafego.mockResolvedValue(cockpitLimpo());
    renderizar('DEMAND_GEN', 'demand_economia');
    await screen.findByText('Economia e medição');
    fireEvent.change(screen.getByLabelText(/Estratégia de lance/), { target: { value: 'TARGET_CPC' } });
    expect(await screen.findByLabelText(/^CPC alvo/)).toBeTruthy();
    expect(screen.getByText('Gerar versões de design das imagens')).toBeTruthy();
    expect(screen.queryByText('Versões mais curtas do vídeo')).toBeNull();
  });

  it('PMax · Expansão e marca: as sete automações, desligadas até alguém ligar', async () => {
    cockpitDeTrafego.mockResolvedValue(cockpitLimpo());
    renderizar('PERFORMANCE_MAX', 'pmax_marca');
    await screen.findByText('O Google pode combinar assets, não trocar o destino');
    // As sete vêm do esquema vivo; todas nascem desligadas (OPTED_OUT).
    await waitFor(() => expect(screen.getAllByRole('button', { name: /^Ligar / })).toHaveLength(7));
    fireEvent.click(screen.getByRole('button', { name: /Ligar Busca automática de vídeos/ }));
    expect(screen.getAllByRole('button', { name: /^Desligar / })).toHaveLength(1);
    expect(screen.getByText(/Declaro que a casa tem direito sobre os vídeos/)).toBeTruthy();
  });

  it('PMax · Asset Group: grupos adicionais com sinais, URL e opções de URL próprios', async () => {
    cockpitDeTrafego.mockResolvedValue(cockpitLimpo());
    renderizar('PERFORMANCE_MAX', 'pmax_asset_group');
    await screen.findByRole('heading', { name: 'Asset groups adicionais' });
    fireEvent.click(screen.getByRole('button', { name: /Adicionar asset group/ }));
    expect(await screen.findByText('asset group 2')).toBeTruthy();
    expect(screen.getByLabelText(/Confirmo os sinais deste grupo/)).toBeTruthy();
    // O grupo adicional tem as PRÓPRIAS opções de URL (as do principal ficam na parada Destino).
    expect(screen.getAllByLabelText(/^Modelo de rastreamento/)).toHaveLength(1);
  });

  it('PMax · Revisão: resumo, avisos e a prova em validate_only', async () => {
    cockpitDeTrafego.mockResolvedValue(cockpitLimpo());
    renderizar('PERFORMANCE_MAX', 'pmax_revisao');
    expect(await screen.findByText('Suas escolhas de Performance Max')).toBeTruthy();
    expect(screen.getByText(/Avisos que o servidor vai emitir/)).toBeTruthy();
    expect(screen.getByRole('button', { name: /Provar no Google/ })).toBeTruthy();
  });
});
