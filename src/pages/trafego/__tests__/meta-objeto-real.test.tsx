// @vitest-environment jsdom
/**
 * `/trafego/meta/:tipo/:objetoId` — identidade real por padrão.
 *
 * ⚠️ Antes, a página resolvia o identificador SÓ contra o dicionário fictício e
 * fazia `<Navigate>` quando não achava. Um `metaobj_…` recém-entregue por um
 * recibo de criação — a identidade que o executor devolve — nunca casava, então
 * clicar no objeto criado levava de volta à lista, sem uma palavra. Cada teste
 * aqui falha contra aquela versão.
 */
import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import MetaObjetoPage from '@/pages/trafego/MetaObjetoPage';

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

const CONTA = {
  cofre_ativo_id: 'meta_account_h1',
  conta_ref: 'meta-account:h1',
  id_mascarado: '••••1426',
  nome_observado: 'Conta Foco Genial',
  moeda: 'BRL',
  timezone_name: 'America/Sao_Paulo',
  ultima_leitura_ok_em: '2026-09-07T09:00:00Z',
};

const CAMPANHA = {
  meta_campaign_id: 'c-uuid-1',
  entity_ref: 'metaobj_campanha_1',
  id_mascarado: '••••7781',
  nome: 'Encceja · leitura real',
  status: 'ACTIVE',
  effective_status: 'ACTIVE',
  objetivo: 'OUTCOME_TRAFFIC',
  observado_em: '2026-09-07T09:00:00Z',
};

const CONJUNTO = {
  meta_adset_id: 'a-uuid-1',
  meta_campaign_id: 'c-uuid-1',
  entity_ref: 'metaobj_conjunto_1',
  id_mascarado: '••••3312',
  nome: 'Brasil · amplo',
  effective_status: 'PAUSED',
  optimization_goal: 'LANDING_PAGE_VIEWS',
  observado_em: '2026-09-07T09:00:00Z',
};

const pagina = (entidade: string, items: Array<Record<string, unknown>>) => ({
  ok: true as const,
  has_snapshot: items.length > 0,
  estado: (items.length > 0 ? 'COM_SNAPSHOT' : 'SEM_SNAPSHOT') as never,
  entidade,
  conta_ref: CONTA.conta_ref,
  moeda: 'BRL',
  fuso: 'America/Sao_Paulo',
  frescor: '2026-09-07T09:00:00Z',
  items,
  completo: true,
  has_more: false,
  proximo_cursor: null,
  motivo: null,
});

const Bussola: React.FC = () => {
  const { pathname, search } = useLocation();
  return <div data-testid="rota">{`${pathname}${search}`}</div>;
};

function abrir(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Bussola />
      <Routes>
        <Route path="/trafego/meta/:tipo/:objetoId" element={<MetaObjetoPage />} />
        <Route path="/trafego" element={<div>HUB DE TRÁFEGO</div>} />
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
    item: CAMPANHA,
    conta_ref: CONTA.conta_ref,
  });
  api.inventarioMetaReadModel.mockReset().mockImplementation((entidade: string) =>
    Promise.resolve(pagina(entidade, entidade === 'conjuntos' ? [CONJUNTO] : [])),
  );
});

afterEach(cleanup);

describe('MetaObjetoPage — identidade real', () => {
  it('resolve o `metaobj_…` do recibo contra o read model e não redireciona', async () => {
    abrir('/trafego/meta/campanhas/metaobj_campanha_1');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Encceja · leitura real' }),
    ).toBeTruthy();
    expect(screen.getByTestId('rota').textContent).toBe('/trafego/meta/campanhas/metaobj_campanha_1');
    expect(screen.queryByText('HUB DE TRÁFEGO')).toBeNull();
    // Nada do cenário fictício entra por aqui.
    expect(screen.queryByText('Guia Encceja · Descoberta')).toBeNull();
    expect(screen.queryByRole('note', { name: 'cenário demonstrativo' })).toBeNull();
    expect(api.detalheMetaReadModel).toHaveBeenCalledWith(
      'campanhas',
      'metaobj_campanha_1',
      CONTA.conta_ref,
    );
  });

  it('a identidade pública aparece, e o id cru da Meta continua fora da tela', async () => {
    abrir('/trafego/meta/campanhas/metaobj_campanha_1');
    await screen.findByRole('heading', { level: 1, name: 'Encceja · leitura real' });
    expect(screen.getAllByText('metaobj_campanha_1').length).toBeGreaterThan(0);
    expect(screen.getByText('••••7781')).toBeTruthy();
  });

  it('um objeto fora do escopo vira frase nomeada, não demonstração', async () => {
    api.detalheMetaReadModel.mockResolvedValue({
      ok: true,
      has_snapshot: false,
      estado: 'NAO_ENCONTRADO_ESCOPO_PARCIAL',
      entidade: 'campanhas',
      item: null,
      conta_ref: CONTA.conta_ref,
    });
    abrir('/trafego/meta/campanhas/campanha-descoberta-01');

    expect(await screen.findByText(/a leitura foi parcial/i)).toBeTruthy();
    expect(screen.queryByText('Guia Encceja · Descoberta')).toBeNull();
    expect(screen.queryByText('HUB DE TRÁFEGO')).toBeNull();
  });

  it('falha de leitura é falha, com código copiável, e não queda para a demonstração', async () => {
    api.detalheMetaReadModel.mockRejectedValue(
      Object.assign(new Error('sem rede'), { status: 500 }),
    );
    abrir('/trafego/meta/campanhas/metaobj_campanha_1');

    expect(await screen.findByText('Não consegui ler o inventário')).toBeTruthy();
    expect(screen.getByText('código da ocorrência')).toBeTruthy();
    expect(screen.queryByText('Guia Encceja · Descoberta')).toBeNull();
  });

  it('um nível desconhecido diz o que não reconheceu, em vez de trocar de página', () => {
    abrir('/trafego/meta/planetas/qualquer-coisa');
    expect(screen.getByText('Nível Meta não reconhecido')).toBeTruthy();
    expect(screen.queryByText('HUB DE TRÁFEGO')).toBeNull();
  });

  it('não oferece editar, pausar nem alterar configuração', async () => {
    abrir('/trafego/meta/campanhas/metaobj_campanha_1');
    await screen.findByRole('heading', { level: 1, name: 'Encceja · leitura real' });
    for (const proibido of [/editar/i, /pausar/i, /alterar configuração/i, /ativar/i]) {
      expect(screen.queryByRole('button', { name: proibido })).toBeNull();
    }
  });
});
