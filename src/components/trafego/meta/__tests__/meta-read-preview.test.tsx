// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { MetaReadPreview } from '@/components/trafego/meta/MetaReadPreview';

const { api } = vi.hoisted(() => ({
  api: {
    estadoMetaLocal: vi.fn(),
    contasMetaLocal: vi.fn(),
    preflightMetaLocal: vi.fn(),
    prepararSyncMetaLocal: vi.fn(),
    persistirSnapshotMetaLocal: vi.fn(),
    contasMetaReadModel: vi.fn(),
    ultimoReciboMetaLocal: vi.fn(),
  },
}));

vi.mock('@/lib/pautadorApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/pautadorApi')>()),
  pautadorApi: api,
}));

const conta = {
  referencia_opaca: 'meta-account:opaque',
  nome: 'Conta de prova',
  id_mascarado: '••••1426',
  status: '1',
  moeda: 'BRL',
  fuso: 'America/Sao_Paulo',
  prontidao_leitura: 'READY_FOR_READ' as const,
  business: null,
};

beforeEach(() => {
  api.estadoMetaLocal.mockReset().mockResolvedValue({
    configurado: true,
    armazenamento: 'macOS Keychain',
    api_version: 'v26.0',
  });
  api.contasMetaLocal.mockReset().mockResolvedValue({
    ok: true,
    api_version: 'v26.0',
    armazenamento: 'macOS Keychain',
    contas: [conta],
    contas_acessiveis: 1,
    proxima_acao: 'preflight_somente_leitura',
  });
  api.preflightMetaLocal.mockReset().mockResolvedValue({
    ok: true,
    api_version: 'v26.0',
    referencia_opaca: conta.referencia_opaca,
    conta,
    contagens: { campaign: 2, adset: 3, ad: 4, creative: 5, custom_conversion: 1 },
    estados: { readiness: 'READY_FOR_READ', persistencia: 'NAO_PERSISTIDO' },
    capacidades_disponiveis: ['META_READ_CAMPAIGNS', 'META_READ_CUSTOM_CONVERSIONS'],
    capacidades_ausentes: [],
    frescor: '2026-09-04T12:00:00Z',
    paginas_lidas: 4,
    erros: [],
    mensuracao: {
      pixels_ou_datasets: 1,
      conversoes_personalizadas: [{
        referencia_opaca: 'meta-custom-conversion:opaque',
        id_mascarado: '••••9911',
        nome: 'Leitura de artigo qualificada',
        custom_event_type: 'OTHER',
        event_source_type: 'PIXEL',
        event_source_id_mascarado: '••••1200',
        first_fired_time: '2026-09-01T10:00:00Z',
        last_fired_time: '2026-09-04T11:00:00Z',
        estado: 'AVAILABLE_FIRED',
      }],
    },
    proxima_acao: 'revisar_e_persistir_em_janela_separada',
  });
  api.prepararSyncMetaLocal.mockReset().mockResolvedValue({ ok: true, persistencia: 'NAO_PERSISTIDO' });
  api.persistirSnapshotMetaLocal.mockReset().mockRejectedValue(Object.assign(new Error('bloqueada'), { corpo: { escrita: 'bloqueada', snapshot_hash: 'meta_snapshot_abc123' } }));
  api.contasMetaReadModel.mockReset().mockResolvedValue({ ok: true, has_snapshot: false, contas: [] });
  api.ultimoReciboMetaLocal.mockReset().mockResolvedValue({ ok: true, has_snapshot: false, recibo: null });
});

afterEach(cleanup);

describe('MetaReadPreview', () => {
  it('só consulta a Meta após ação explícita e mostra a prova sanitizada', async () => {
    render(<MetaReadPreview />);

    expect(api.contasMetaLocal).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole('button', { name: 'Ler contas reais' }));

    expect(await screen.findByText('Conta de prova')).toBeTruthy();
    expect(api.contasMetaLocal).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: /provar/i }));

    expect(await screen.findByText('Leitura real concluída')).toBeTruthy();
    expect(screen.getByText('Leitura de artigo qualificada')).toBeTruthy();
    expect(screen.getByText('disparando')).toBeTruthy();
    expect(screen.getByText('somente leitura')).toBeTruthy();
    expect(api.preflightMetaLocal).toHaveBeenCalledWith('meta-account:opaque');
    fireEvent.click(screen.getByRole('button', { name: 'Preparar sincronização' }));
    await waitFor(() => expect(api.prepararSyncMetaLocal).toHaveBeenCalledWith('meta-account:opaque'));
    fireEvent.click(screen.getByRole('button', { name: 'Persistir snapshot' }));
    await waitFor(() => expect(screen.getByText(/Persistência bloqueada/)).toBeTruthy());
    expect(api.persistirSnapshotMetaLocal).toHaveBeenCalledWith('meta-account:opaque');
  });

  it('não fica travado após a configuração ser concluída em outra superfície', async () => {
    api.estadoMetaLocal.mockResolvedValueOnce({
      configurado: false,
      armazenamento: 'macOS Keychain',
      api_version: 'v26.0',
    });
    render(<MetaReadPreview />);

    const botao = await screen.findByRole('button', { name: 'Ler contas reais' });
    await waitFor(() => expect(screen.getByText(/Abra a engrenagem/)).toBeTruthy());
    expect((botao as HTMLButtonElement).disabled).toBe(false);
  });
});
