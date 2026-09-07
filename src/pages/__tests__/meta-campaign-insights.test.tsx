// @vitest-environment jsdom
/**
 * O ROTEAMENTO: identidade real lê o read model; demonstração só por porta.
 *
 * ⚠️ O DEFEITO QUE ESTES TESTES FIXAM.
 *
 * A página procurava o `campaignId` dentro de `META_DEMO` e, quando não achava,
 * fazia `<Navigate to="/settings/campaigns?rede=meta">`. Como o dicionário
 * fictício era a única fonte que ela conhecia, TODA campanha real caía no
 * redirecionamento e sumia sem uma palavra — o operador conclui que a campanha
 * não existe. Cada caso abaixo falha contra aquela versão.
 */
import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { SeletorRedeCampanhas } from '@/components/campaign/SeletorRedeCampanhas';
import MetaCampaignInsightPage from '@/pages/MetaCampaignInsightPage';

const { api } = vi.hoisted(() => ({
  api: {
    contasMetaReadModel: vi.fn(),
    inventarioMetaReadModel: vi.fn(),
    detalheMetaReadModel: vi.fn(),
  },
}));

vi.mock('@/lib/pautadorApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/pautadorApi')>()),
  pautadorApi: api,
}));

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// recharts' <ResponsiveContainer> needs a real ResizeObserver, absent from jsdom.
beforeAll(() => {
  if (!('ResizeObserver' in window)) {
    class ResizeObserverStub {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    // @ts-expect-error jsdom has no ResizeObserver; recharts only needs the shape above.
    window.ResizeObserver = ResizeObserverStub;
  }
});

const CONTA = {
  cofre_ativo_id: 'meta_account_h1',
  conta_ref: 'meta-account:h1',
  id_mascarado: '••••1426',
  nome_observado: 'Conta Foco Genial',
  moeda: 'BRL',
  timezone_name: 'America/Sao_Paulo',
  observado_em: '2026-09-07T09:00:00Z',
  ultima_leitura_ok_em: '2026-09-07T09:00:00Z',
};

const CAMPANHA_REAL = {
  meta_campaign_id: 'c-uuid-1',
  entity_ref: 'metaobj_campanha_1',
  id_mascarado: '••••7781',
  nome: 'Encceja · leitura real',
  status: 'ACTIVE',
  effective_status: 'ACTIVE',
  objetivo: 'OUTCOME_TRAFFIC',
  observado_em: '2026-09-07T09:00:00Z',
};

const vazia = (entidade: string) => ({
  ok: true as const,
  has_snapshot: false,
  estado: 'SEM_SNAPSHOT' as never,
  entidade,
  conta_ref: CONTA.conta_ref,
  moeda: 'BRL',
  fuso: 'America/Sao_Paulo',
  frescor: '2026-09-07T09:00:00Z',
  items: [] as Array<Record<string, unknown>>,
  completo: true,
  has_more: false,
  proximo_cursor: null,
  motivo: null,
});

/** Onde a rota parou. Sem isto, "não redirecionou" seria uma suposição. */
const Bussola: React.FC = () => {
  const { pathname, search } = useLocation();
  return <div data-testid="rota">{`${pathname}${search}`}</div>;
};

function abrir(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Bussola />
      <Routes>
        <Route path="/dashboard/campaign/:campaignId" element={<MetaCampaignInsightPage />} />
        <Route path="/settings/campaigns" element={<div>LISTA DE CAMPANHAS</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  api.contasMetaReadModel.mockReset().mockResolvedValue({
    ok: true,
    has_snapshot: true,
    estado: 'COM_SNAPSHOT',
    contas: [CONTA],
  });
  api.detalheMetaReadModel.mockReset().mockResolvedValue({
    ok: true,
    has_snapshot: true,
    estado: 'COM_SNAPSHOT',
    entidade: 'campanhas',
    item: CAMPANHA_REAL,
    conta_ref: CONTA.conta_ref,
  });
  api.inventarioMetaReadModel
    .mockReset()
    .mockImplementation((entidade: string) => Promise.resolve(vazia(entidade)));
});

afterEach(cleanup);

describe('identidade REAL — o caminho padrão', () => {
  it('lê o read model, não redireciona e não toca no cenário fictício', async () => {
    abrir('/dashboard/campaign/metaobj_campanha_1?rede=meta');

    expect(await screen.findByText('Encceja · leitura real')).toBeTruthy();

    // ⚠️ A prova do defeito: a rota NÃO mudou.
    expect(screen.getByTestId('rota').textContent).toBe(
      '/dashboard/campaign/metaobj_campanha_1?rede=meta',
    );
    expect(screen.queryByText('LISTA DE CAMPANHAS')).toBeNull();

    // Nada de demonstração: nem os nomes fictícios, nem a faixa, nem o selo.
    expect(screen.queryByText('Guia Encceja · Descoberta')).toBeNull();
    expect(screen.queryByRole('note', { name: 'cenário demonstrativo' })).toBeNull();
    expect(screen.queryByText('Dados demonstrativos')).toBeNull();

    expect(api.detalheMetaReadModel).toHaveBeenCalledWith(
      'campanhas',
      'metaobj_campanha_1',
      CONTA.conta_ref,
    );
  });

  it('um id do cenário fictício SEM `modo=demo` continua sendo pergunta ao read model', async () => {
    api.detalheMetaReadModel.mockResolvedValue({
      ok: true,
      has_snapshot: false,
      estado: 'NAO_ENCONTRADO_NO_ESCOPO',
      entidade: 'campanhas',
      item: null,
      conta_ref: CONTA.conta_ref,
    });
    abrir('/dashboard/campaign/campanha-descoberta-01?rede=meta');

    expect(await screen.findByText(/não pertence a esta conta/i)).toBeTruthy();
    // O mesmo identificador abre um cenário fictício quando a URL pede — aqui
    // ela não pediu, e a demonstração não entra pela porta dos fundos.
    expect(screen.queryByText('Guia Encceja · Descoberta')).toBeNull();
    expect(screen.getByTestId('rota').textContent).toContain('/dashboard/campaign/');
  });

  it('uma falha de leitura é falha NOMEADA — nunca queda para a demonstração', async () => {
    api.contasMetaReadModel.mockRejectedValue(
      Object.assign(new Error('backend fora'), { status: 503 }),
    );
    abrir('/dashboard/campaign/metaobj_campanha_1?rede=meta');

    expect(await screen.findByText('Não consegui ler o inventário')).toBeTruthy();
    expect(screen.getByText('O registro de campanhas não respondeu.')).toBeTruthy();
    expect(screen.getByText('código da ocorrência')).toBeTruthy();
    expect(screen.queryByText('Guia Encceja · Descoberta')).toBeNull();
    expect(screen.queryByText('LISTA DE CAMPANHAS')).toBeNull();
    expect(screen.getByTestId('rota').textContent).toBe(
      '/dashboard/campaign/metaobj_campanha_1?rede=meta',
    );
  });

  it('métrica não medida sai como AUSENTE, e não como zero', async () => {
    abrir('/dashboard/campaign/metaobj_campanha_1?rede=meta');
    await screen.findByText('Encceja · leitura real');

    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(4);
    expect(screen.queryByText('R$ 0,00')).toBeNull();
    expect(screen.queryByText('0,0%')).toBeNull();
  });

  it('não oferece ativar, editar, pausar nem orçamento', async () => {
    abrir('/dashboard/campaign/metaobj_campanha_1?rede=meta');
    await screen.findByText('Encceja · leitura real');
    for (const proibido of [/configurar/i, /ativar/i, /editar/i, /pausar/i, /orçamento/i]) {
      expect(screen.queryByRole('button', { name: proibido })).toBeNull();
    }
  });
});

describe('a demonstração — só atrás de `?modo=demo`, e dizendo que é', () => {
  it('abre a espinha do dashboard e se declara demonstração na tela', async () => {
    abrir('/dashboard/campaign/campanha-descoberta-01?rede=meta&modo=demo');

    expect(screen.getByRole('heading', { level: 1 }).textContent).toContain('Dashboard da Campanha');
    expect(screen.getByRole('heading', { name: 'Guia Encceja · Descoberta' })).toBeTruthy();

    // A mesma espinha econômica do Google, com a unidade dita no rótulo.
    expect(screen.getByText('Investimento Total')).toBeTruthy();
    expect(screen.getByText('Revenue')).toBeTruthy();
    expect(screen.getByText('Retorno excedente (%)')).toBeTruthy();
    expect(screen.getByText('Lucro Bruto')).toBeTruthy();
    expect(screen.getByText('Landing Page Views')).toBeTruthy();
    expect(screen.getByText('Janela de Atribuição')).toBeTruthy();

    // ⚠️ O caráter fictício é CONTEÚDO FIXO, não um chip que passa despercebido.
    const faixa = screen.getByRole('note', { name: 'cenário demonstrativo' });
    expect(faixa.textContent).toContain('nada aqui é real');
    expect(faixa.textContent).toContain('Nenhuma conta Meta foi consultada');
    expect(screen.getByText('Dados demonstrativos')).toBeTruthy();

    // A demonstração NÃO fala com o backend. Nem uma requisição.
    expect(api.contasMetaReadModel).not.toHaveBeenCalled();
    expect(api.detalheMetaReadModel).not.toHaveBeenCalled();
  });

  it('id inexistente no cenário fictício vira frase, não redirecionamento', () => {
    abrir('/dashboard/campaign/metaobj_campanha_1?rede=meta&modo=demo');
    expect(
      screen.getByText(/Este identificador não existe no cenário demonstrativo/i),
    ).toBeTruthy();
    expect(screen.queryByText('LISTA DE CAMPANHAS')).toBeNull();
    expect(screen.getByTestId('rota').textContent).toContain('modo=demo');
  });

  it('não mostra um controle desabilitado para um ato que não existe', () => {
    abrir('/dashboard/campaign/campanha-descoberta-01?rede=meta&modo=demo');
    expect(screen.queryByRole('button', { name: /configurar/i })).toBeNull();
  });
});

describe('troca de rede', () => {
  it('troca a rede pela decisão explícita do operador', () => {
    const mudar = vi.fn();
    render(<SeletorRedeCampanhas rede="meta" onChange={mudar} />);
    fireEvent.click(screen.getByRole('button', { name: 'Google Ads' }));
    expect(mudar).toHaveBeenCalledWith('google');
  });
});
