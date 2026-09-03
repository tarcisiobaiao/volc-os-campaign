// @vitest-environment jsdom
/**
 * O cockpit manda o contrato TIPADO — e ele descreve o que a tela mostrou.
 *
 * ⚠️ O defeito que este arquivo trava: a tela não tinha onde escrever uma
 * exclusão, e o match type que ela exibia era derivado da estratégia, igual
 * para todas as keywords. O que o operador via e o que ia para o Google eram
 * duas coisas diferentes, e nada denunciava a diferença.
 *
 * O `Lancamento` é substituído por um espião: o que se prova aqui é o PEDIDO
 * que a página monta, não o diálogo de lançamento — e provar o pedido é provar
 * que a revisão na tela e o payload contam a mesma história.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import type { Cockpit, PedidoDeProvaSearch } from '@/types/trafego';

const { cockpitDeTrafego, pedidoEspiado, KW } = vi.hoisted(() => ({
  cockpitDeTrafego: vi.fn(),
  pedidoEspiado: { atual: null as PedidoDeProvaSearch | null },
  KW: ['saque anual fgts', 'valor do saque anual'],
}));

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// O espião do pedido. Não renderiza diálogo nenhum — só guarda o que recebeu.
vi.mock('@/components/trafego/Lancamento', () => ({
  Lancamento: ({ pedido }: { pedido: PedidoDeProvaSearch }) => {
    pedidoEspiado.atual = pedido;
    return <div data-testid="lancamento-aberto" />;
  },
}));

vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: {
    cockpitDeTrafego,
    estadoDaTrava: async () => ({
      escrita_permitida: false, destravado_no_codigo: false, env_presente: false,
      motivo: '', explicacao: 'A trava é de dois fatores.',
    }),
    verticaisEPortoes: async () => ({ verticais: [] }),
    // A copy PRONTA — sem ela o botão de lançar nasce desabilitado e o
    // pedido nunca é montado, que era o que este arquivo quer inspecionar.
    lerCopy: async () => ({
      existe: true, status: 'done', perdida: false,
      opportunity_id: 73, run_id: 6, keywords: [...KW],
      copy: { headlines: ['Saque Anual 2026'], descriptions: ['Veja as regras.'],
              sitelinks: [], callouts: [], snippet: null },
      aceita: true, pendentes: [], diario: [],
      geracoes_conjunto: 1, geracoes_asset: 0,
      fatos_usados: 3, fatos_descartados: [],
      medicao: { chamadas: 1, falhas: 0, por_papel: {}, ilegiveis: 0,
                 tokens_entrada: 100, tokens_saida: 100, latencia_s: 10,
                 custo_usd: null, sem_custo: 1, motivo_sem_custo: '' },
      segundos: 10, erro: null,
      criado_em: '2026-08-27T00:00:00Z', atualizado_em: '2026-08-27T00:00:00Z',
    }),
    escreverCopy: vi.fn(),
    provarCampanha: vi.fn(),
    subirCampanha: vi.fn(),
  },
  PautadorApiError: class extends Error { corpo?: unknown; status = 0; },
}));

import NovaCampanhaPage from '../NovaCampanhaPage';
import { reciboApto } from '@/lib/landing-policy/__tests__/recibos';

afterEach(() => {
  cleanup();
  pedidoEspiado.atual = null;
  vi.clearAllMocks();
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
      // O RECIBO DO PORTÃO DE DESTINO PAGO — pela mesma razão que a copy chega
      // pronta neste arquivo: sem ele o botão de lançar nasce desabilitado e o
      // pedido nunca é montado, que é o que este teste quer inspecionar. Um
      // destino publicado e sem avaliação é INDETERMINADO, e indeterminado não
      // abre nada.
      landing_policy_receipt: reciboApto({
        url: 'https://creditoup.com.br/r/saque/',
      }, { agora_epoch: Date.now() / 1000 }),
    },
    triagem: {
      analisadas: 100, aprovadas_anuncio: 2, para_conteudo: 0, descartadas: 98,
      breakdown: {}, volume_total: 28700, volume_da_fila: 28700,
    },
    grupos: [{
      tipo: 'ACESSO', descricao: 'acesso',
      keywords: [
        { texto: KW[0], volume: 27100, cpc: null, competicao: '',
          tendencia: null, tags: [], motivo: '', tambem_em_conteudo: false },
        { texto: KW[1], volume: 1600, cpc: null, competicao: '',
          tendencia: null, tags: [], motivo: '', tambem_em_conteudo: false },
      ],
      volume: 28700, cpc_simples: null, cpc_ponderado: null,
      volume_declarado: null, keywords_declaradas: null, fora_da_fila: [],
    }],
    descartadas: [], procedencia: { servicos_declarados: [], engine: '' } as never,
    avisos: [],
    conta: {
      project_id: 2, dominio: 'creditoup.com.br', customer_id: '8017851692',
      login_customer_id: '6016739364', vinculada: true, motivo: null,
    },
    campanhas_lancadas: [],
  } as unknown as Cockpit;
}

const renderizar = () =>
  render(
    <MemoryRouter initialEntries={['/trafego/nova/73']}>
      <Routes>
        <Route path="/trafego/nova/:opportunityId" element={<NovaCampanhaPage />} />
      </Routes>
    </MemoryRouter>,
  );

async function abrirMesa() {
  cockpitDeTrafego.mockResolvedValue(cockpitLimpo());
  renderizar();
  // As keywords vêm pré-marcadas pela triagem, então a mesa monta sozinha.
  await waitFor(() => expect(screen.getByLabelText('Palavras que ativam')).toBeTruthy());
}

describe('o pedido que a página monta', () => {
  it('a mesa aparece assim que existe keyword marcada', async () => {
    await abrirMesa();
    expect(screen.getByLabelText('Palavras a excluir')).toBeTruthy();
    expect(screen.getByLabelText('Revisão')).toBeTruthy();
  });

  it('leva as positivas tipadas, uma por keyword marcada', async () => {
    await abrirMesa();
    fireEvent.click(screen.getByRole('button', { name: /Lançar campanha/i }));

    await waitFor(() => expect(pedidoEspiado.atual).toBeTruthy());
    const crits = pedidoEspiado.atual!.criterios ?? [];
    const positivas = crits.filter((c) => !c.negativa);
    expect(positivas.map((c) => c.texto).sort()).toEqual([...KW].sort());
    // sob MANUAL_CPC (o padrão da casa) o match type é PHRASE
    expect(positivas.every((c) => c.match_type === 'PHRASE')).toBe(true);
    expect(positivas.every((c) => c.grupo === 'ACESSO')).toBe(true);
  });

  it('leva a exclusão que o operador escreveu, com nível e match type dela', async () => {
    await abrirMesa();

    fireEvent.change(screen.getByLabelText('Termo a excluir'), {
      target: { value: 'simulador' },
    });
    fireEvent.change(screen.getByLabelText('Correspondência da exclusão'), {
      target: { value: 'EXACT' },
    });
    fireEvent.change(screen.getByLabelText(/^Motivo/), {
      target: { value: 'nao vendemos simulacao' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Adicionar exclusão/ }));

    fireEvent.click(screen.getByRole('button', { name: /Lançar campanha/i }));
    await waitFor(() => expect(pedidoEspiado.atual).toBeTruthy());

    const negativas = (pedidoEspiado.atual!.criterios ?? []).filter((c) => c.negativa);
    expect(negativas).toHaveLength(1);
    expect(negativas[0]).toMatchObject({
      texto: 'simulador', match_type: 'EXACT', nivel: 'CAMPAIGN',
      grupo: null, origem: 'MANUAL', motivo: 'nao vendemos simulacao',
    });
    expect(negativas[0].evidencia).toBeNull();
  });

  it('o match type trocado numa keyword sobrevive até o pedido', async () => {
    await abrirMesa();
    fireEvent.change(screen.getByLabelText(`Correspondência de ${KW[0]}`), {
      target: { value: 'EXACT' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Lançar campanha/i }));
    await waitFor(() => expect(pedidoEspiado.atual).toBeTruthy());

    const crits = pedidoEspiado.atual!.criterios ?? [];
    const porTexto = Object.fromEntries(crits.map((c) => [c.texto, c.match_type]));
    expect(porTexto[KW[0]]).toBe('EXACT');
    // e a OUTRA keyword continua no padrão — trocar uma não troca todas
    expect(porTexto[KW[1]]).toBe('PHRASE');
  });

  it('desmarcar uma keyword a tira do contrato tipado', async () => {
    await abrirMesa();
    // desmarca a primeira keyword na lista de seleção
    const ativam = screen.getByLabelText('Palavras que ativam');
    expect(ativam.textContent).toContain(KW[1]);

    fireEvent.click(screen.getByRole('button', { name: `marcar todas de ACESSO` }));
    await waitFor(() => expect(screen.queryByLabelText('Palavras que ativam')).toBeNull());
  });

  it('continua mandando `match_type` como padrão do pedido', async () => {
    await abrirMesa();
    fireEvent.click(screen.getByRole('button', { name: /Lançar campanha/i }));
    await waitFor(() => expect(pedidoEspiado.atual).toBeTruthy());
    // o campo antigo continua no pedido: é ele que preenche a lacuna de quem
    // não declara critério, e o backend só ignora quando `criterios` vem cheio
    expect(pedidoEspiado.atual!.match_type).toBe('PHRASE');
  });
});
