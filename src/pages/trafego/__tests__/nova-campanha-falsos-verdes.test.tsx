// @vitest-environment jsdom
/**
 * Os falsos verdes do cockpit de lançamento.
 *
 * Esta tela é a que GASTA. Ela lê três coisas no load — o cockpit, a trava de
 * escrita e o portão de política — e, até 02/09/2026, duas dessas leituras
 * podiam FALHAR sem que a tela dissesse uma palavra:
 *
 *  - `verticaisEPortoes().catch(() => ({ verticais: [] }))` mais o
 *    `verticais.length > 0` na renderização faziam o painel que "pode barrar
 *    tudo" sumir em silêncio. Ausência de portão lê-se como "não há portão".
 *  - `estadoDaTrava().catch(() => null)` colapsava três estados em dois:
 *    "liberada" e "não consegui verificar" produziam a MESMA tela.
 *
 * E, mesmo com a leitura boa, o veredito do portão nunca entrava em
 * `podeLancar`: a nota vermelha aparecia e o botão continuava clicável.
 *
 * O quarto caso é o número-herói: `k.volume || 0` transformava keyword sem
 * volume medido em zero dentro de uma soma apresentada como medição.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import type { Cockpit, CopyPersistida } from '@/types/trafego';

const { cockpitDeTrafego, lerCopy, estadoDaTrava, verticaisEPortoes } = vi.hoisted(() => ({
  cockpitDeTrafego: vi.fn(),
  lerCopy: vi.fn(),
  estadoDaTrava: vi.fn(),
  verticaisEPortoes: vi.fn(),
}));

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: {
    cockpitDeTrafego,
    estadoDaTrava,
    verticaisEPortoes,
    lerCopy,
    escreverCopy: vi.fn(),
    salvarCopyEditada: vi.fn(),
    provarCampanha: vi.fn(),
    subirCampanha: vi.fn(),
  },
  PautadorApiError: class extends Error { corpo?: unknown; status = 0; },
}));

import NovaCampanhaPage from '../NovaCampanhaPage';

const KW = ['banco pan telefone', 'cartão de crédito caixa telefone'];

/** As verticais como o servidor as devolve — `financeiro` barra em BR. */
const VERTICAIS = [
  { id: 'informativo', titulo: 'Informativo', descricao: 'O site explica e compara.',
    exige: null, severidade: null, paises_exigem: [] },
  { id: 'financeiro', titulo: 'Financeiro', descricao: 'Verificação obrigatória por país.',
    exige: 'verificacao_servicos_financeiros', severidade: 'bloqueio',
    paises_exigem: ['BR', 'MX'] },
];

const TRAVA_FECHADA = {
  escrita_permitida: false, destravado_no_codigo: false, env_presente: false,
  motivo: '', explicacao: 'A trava é de dois fatores.',
};

function cockpitDeProva(over: {
  avisos?: unknown[];
  vertical?: string;
  volumes?: (number | null)[];
} = {}): Cockpit {
  const volumes = over.volumes ?? [27100, 1600];
  return {
    opportunity_id: 73,
    cluster_id: 4,
    origem: {
      opportunity_id: 73, run_id: 6, project_id: 2,
      url_final: 'https://creditoup.com.br/cartao-para-negativado',
      url_procedencia: 'wp', status_wp: 'publish', post_type: 'r',
      dominio: 'https://creditoup.com.br', nicho: 'Cartão para Negativado',
      slug: 'cartao', pais: 'BR', idioma: 'pt', idioma_declarado: 'pt-BR',
      vertical: over.vertical ?? 'financeiro',
      vertical_declarada: over.vertical ?? 'financeiro',
      resumo_da_pesquisa: '', fatos: [], tem_texto_da_lp: true,
    },
    triagem: {
      analisadas: 100, aprovadas_anuncio: 23, para_conteudo: 25, descartadas: 63,
      breakdown: {}, volume_total: 37400, volume_da_fila: 37400,
    },
    grupos: [{
      tipo: 'ACESSO', descricao: 'contatos e meios digitais',
      keywords: KW.map((texto, i) => ({
        texto, volume: volumes[i] ?? null, cpc: null, competicao: '',
        tendencia: null, tags: [], motivo: '', tambem_em_conteudo: false,
      })),
      volume: 28700, cpc_simples: null, cpc_ponderado: null,
      volume_declarado: null, keywords_declaradas: null, fora_da_fila: [],
    }],
    descartadas: [],
    procedencia: { servicos_declarados: [], engine: '' } as never,
    avisos: over.avisos ?? [],
    conta: {
      project_id: 2, dominio: 'creditoup.com.br', customer_id: '8017851692',
      login_customer_id: '6016739364', vinculada: true, motivo: null,
    },
  } as unknown as Cockpit;
}

function copiaPronta(): CopyPersistida {
  return {
    existe: true, status: 'done', perdida: false,
    opportunity_id: 73, run_id: 6, keywords: [...KW],
    copy: { headlines: ['Cartão para Negativado'], descriptions: ['Veja as regras.'],
            sitelinks: [], callouts: [], snippet: null },
    aceita: true, pendentes: [], diario: [],
    geracoes_conjunto: 2, geracoes_asset: 0,
    fatos_usados: 6, fatos_descartados: [],
    medicao: { chamadas: 2, falhas: 0, por_papel: {}, ilegiveis: 0,
               tokens_entrada: 1, tokens_saida: 1, latencia_s: 174,
               custo_usd: null, sem_custo: 2, motivo_sem_custo: 'preço não configurado' },
    segundos: 174, erro: null,
    criado_em: new Date().toISOString(), atualizado_em: new Date().toISOString(),
  } as CopyPersistida;
}

const renderizar = () =>
  render(
    <MemoryRouter initialEntries={['/trafego/nova/73?run=6']}>
      <Routes>
        <Route path="/trafego/nova/:opportunityId" element={<NovaCampanhaPage />} />
      </Routes>
    </MemoryRouter>,
  );

beforeEach(() => {
  cockpitDeTrafego.mockResolvedValue(cockpitDeProva());
  lerCopy.mockResolvedValue({ existe: false });
  estadoDaTrava.mockResolvedValue(TRAVA_FECHADA);
  verticaisEPortoes.mockResolvedValue({ verticais: VERTICAIS });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// ── #1 ──────────────────────────────────────────────────────────────────────

describe('#1 · a falha de leitura do portão de política não vira ausência de portão', () => {
  it('quando `verticaisEPortoes` falha, a tela DIZ que não leu o portão', async () => {
    verticaisEPortoes.mockRejectedValue(new Error('502 Bad Gateway'));
    renderizar();

    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());

    // O que não pode acontecer é o silêncio: hoje a seção some sem uma palavra.
    expect(screen.getByText(/Não foi possível ler o portão de política/)).toBeTruthy();
    // A frase da casa (PainelDeCanais.tsx:428-455): falha de leitura NÃO é
    // afirmação sobre o objeto lido.
    expect(
      screen.getByText(/falha de leitura, e não uma afirmação sobre a política/),
    ).toBeTruthy();
  });

  it('lista vazia LIDA é dita como resposta do servidor, não como silêncio', async () => {
    verticaisEPortoes.mockResolvedValue({ verticais: [] });
    renderizar();

    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());
    expect(screen.getByText(/não declarou nenhuma vertical/)).toBeTruthy();
  });

  it('com a leitura boa, o painel do portão continua na tela como sempre esteve', async () => {
    renderizar();
    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());
    expect(screen.getByLabelText('portão de política')).toBeTruthy();
    expect(screen.queryByText(/Não foi possível ler o portão de política/)).toBeNull();
  });
});

// ── #2 ──────────────────────────────────────────────────────────────────────

describe('#2 · `trava === null` não pode ser igual a "escrita liberada"', () => {
  it('quando `estadoDaTrava` falha, a tela diz "permissão não verificada"', async () => {
    estadoDaTrava.mockRejectedValue(new Error('sem resposta'));
    renderizar();

    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());
    // Duas superfícies desta mesma tela falavam da trava: o cartão "conta e
    // lance" e o painel "o que vai ser criado". As duas silenciavam a falha.
    expect(screen.getAllByText(/permissão não verificada/).length).toBe(2);
    // E nenhuma pode dizer a frase do portão FECHADO: não sabemos se ele está.
    expect(screen.queryByText(/A trava de escrita está fechada/)).toBeNull();
  });

  it('trava lida e fechada continua dizendo o que sempre disse', async () => {
    renderizar();
    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());
    expect(screen.getAllByText(/A trava de escrita está fechada/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/permissão não verificada/)).toBeNull();
  });

  it('trava lida e ABERTA não emite frase de falha de leitura', async () => {
    estadoDaTrava.mockResolvedValue({ ...TRAVA_FECHADA, env_presente: true });
    renderizar();
    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());
    expect(screen.queryByText(/permissão não verificada/)).toBeNull();
    expect(screen.queryByText(/A trava de escrita está fechada/)).toBeNull();
    expect(screen.getByText(/A trava de escrita está ABERTA/)).toBeTruthy();
  });
});

// ── #5 ──────────────────────────────────────────────────────────────────────

describe('#5 · o veredito do portão de política entra em `podeLancar`', () => {
  it('vertical que EXIGE habilitação não declarada barra o botão', async () => {
    lerCopy.mockResolvedValue(copiaPronta());
    renderizar();

    await waitFor(() => expect(screen.getByText(/O lançamento está barrado/)).toBeTruthy());

    const lancar = await screen.findByRole('button', { name: /Lançar campanha/ });
    expect((lancar as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/portão de política/)).toBeTruthy();
  });

  it('declarar a certificação libera o botão — é o portão que barrava, e só ele', async () => {
    lerCopy.mockResolvedValue(copiaPronta());
    renderizar();

    await waitFor(() => expect(screen.getByText(/O lançamento está barrado/)).toBeTruthy());
    const painel = screen.getByLabelText('portão de política');
    fireEvent.click(within(painel).getByRole('checkbox'));

    await waitFor(() => {
      const lancar = screen.getByRole('button', { name: /Lançar campanha/ });
      expect((lancar as HTMLButtonElement).disabled).toBe(false);
    });
  });

  it('portão NÃO VERIFICADO também barra: não saber não é permissão', async () => {
    verticaisEPortoes.mockRejectedValue(new Error('502 Bad Gateway'));
    lerCopy.mockResolvedValue(copiaPronta());
    renderizar();

    await waitFor(() =>
      expect(screen.getByText(/Não foi possível ler o portão de política/)).toBeTruthy());

    const lancar = screen.getByRole('button', { name: /Lançar campanha/ });
    expect((lancar as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/verificar o portão de política/)).toBeTruthy();
  });

  it('lista LIDA e vazia não barra — `vazio_confirmado` não é `falhou`', async () => {
    // ⚠️ Os dois estados são distintos de propósito. O servidor que respondeu
    // e não declarou vertical nenhuma DISSE algo; a tela diz o que ele disse e
    // não inventa uma exigência que ninguém emitiu. Quem barra é a leitura que
    // não concluiu.
    verticaisEPortoes.mockResolvedValue({ verticais: [] });
    lerCopy.mockResolvedValue(copiaPronta());
    renderizar();

    await waitFor(() => {
      const lancar = screen.getByRole('button', { name: /Lançar campanha/ });
      expect((lancar as HTMLButtonElement).disabled).toBe(false);
    });
    expect(screen.queryByText(/verificar o portão de política/)).toBeNull();
  });

  it('lista com conteúdo em que a vertical escolhida não aparece BARRA', async () => {
    // Resposta parcial: veio lista, e a vertical desta oportunidade não está
    // nela. Não dá para afirmar que ela não tem portão.
    verticaisEPortoes.mockResolvedValue({ verticais: [VERTICAIS[0]] });
    lerCopy.mockResolvedValue(copiaPronta());
    renderizar();

    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());
    const lancar = screen.getByRole('button', { name: /Lançar campanha/ });
    expect((lancar as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/verificar o portão de política/)).toBeTruthy();
  });

  it('vertical sem portão no país deixa o botão livre', async () => {
    cockpitDeTrafego.mockResolvedValue(cockpitDeProva({ vertical: 'informativo' }));
    lerCopy.mockResolvedValue(copiaPronta());
    renderizar();

    await waitFor(() => {
      const lancar = screen.getByRole('button', { name: /Lançar campanha/ });
      expect((lancar as HTMLButtonElement).disabled).toBe(false);
    });
  });
});

// ── #8 ──────────────────────────────────────────────────────────────────────

/** O número-herói, lido pelo rótulo — `—` aparece em vários lugares da tela. */
const heroi = () =>
  screen.getByText('volume/mês selecionado').nextElementSibling?.textContent;


describe('#8 · ausência de volume não vira zero no número-herói', () => {
  it('keyword sem volume medido faz do total um PISO, dito na tela', async () => {
    cockpitDeTrafego.mockResolvedValue(cockpitDeProva({ volumes: [27100, null] }));
    renderizar();

    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());
    // O total dos MEDIDOS, marcado como piso — nunca 28.700 nem "27,1k" seco.
    expect(heroi()).toBe('27,1k+');
    expect(screen.getByText(/1 sem volume medido/)).toBeTruthy();
  });

  it('nenhum volume medido não vira 0: vira ausência', async () => {
    cockpitDeTrafego.mockResolvedValue(cockpitDeProva({ volumes: [null, null] }));
    renderizar();

    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());
    expect(heroi()).toBe('—');
    expect(screen.getByText(/nenhuma das 2 tem volume medido/)).toBeTruthy();
  });

  it('todos medidos continuam somando como sempre, sem o sinal de piso', async () => {
    renderizar();
    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());
    expect(heroi()).toBe('28,7k');
    expect(screen.queryByText(/sem volume medido/)).toBeNull();
  });
});
