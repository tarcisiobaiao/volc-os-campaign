// @vitest-environment jsdom
/**
 * Preparar: os cinco estados vêm do contrato, não do nome do funil.
 */
import { cleanup, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { EstadoDaTrava, QuadroDeTrafego } from '@/types/trafego';
import QuadroDeOportunidades from '@/components/trafego/oportunidades/QuadroDeOportunidades';
import {
  candidatoEmConflito,
  candidatoSemCampanha,
  candidatoSomenteHistorico,
  fgtsCorrespondencia,
  fgtsSemReconciliacao,
  fgtsVinculada,
  lancadaSemReconciliacao,
  maquininhaCorrespondencia,
  maquininhaVinculada,
  rascunhoComAviso,
  reconciliacaoNula,
  semCampanhaSemPodeMontar,
} from '@/components/trafego/hub/fixtureMulticanal';
import { fraseDeReconciliacao } from '@/components/trafego/preparar/estados';
import { RECONCILIACAO_PENDENTE, REVISAO_DE_CONFLITO } from '@/components/trafego/preparar/estados';

const quadroDeTrafego = vi.hoisted(() => vi.fn());
const estadoDaTrava = vi.hoisted(() => vi.fn());

vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: { quadroDeTrafego, estadoDaTrava },
}));

const portaoFechado: EstadoDaTrava = {
  escrita_permitida: false,
  destravado_no_codigo: false,
  env_presente: false,
  motivo: '',
  explicacao: 'texto de máquina que não pode chegar à tela',
};

function montar() {
  const cliente = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter>
        <QuadroDeOportunidades />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.defineProperty(window, 'innerWidth', { value: 1440, writable: true, configurable: true });
  estadoDaTrava.mockResolvedValue(portaoFechado);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('o contrato decide o que já existe', () => {
  it('FGTS e Maquininha com campanhas_lancadas aparecem como existentes', async () => {
    const quadro: QuadroDeTrafego = {
      prontos: [maquininhaVinculada, fgtsVinculada, candidatoSemCampanha],
      totais: { funis_publicados: 3, com_cluster: 3, keywords_disponiveis: 48 },
      sem_metrica: true,
      por_que: 'não existe camada de métrica no motor de anúncios.',
    };
    quadroDeTrafego.mockResolvedValue(quadro);
    montar();
    await screen.findByText('Maquininha de cartão para MEI');
    expect(screen.getAllByText('1 campanha no ar').length).toBe(2);
    const maquininha = screen.getByText('Maquininha de cartão para MEI').closest('tr');
    const fgts = screen.getByText('FGTS saque-aniversário').closest('tr');
    expect(maquininha && within(maquininha).getByRole('link', { name: /abrir o que existe/ })).toBeTruthy();
    expect(fgts && within(fgts).getByRole('link', { name: /abrir o que existe/ })).toBeTruthy();
    const novo = screen.getByText('Empréstimo com garantia').closest('tr');
    expect(novo && within(novo).getByRole('link', { name: /montar campanha/ })).toBeTruthy();
  });

  it('o mesmo nome sem contrato não vira campanha existente', () => {
    const semContrato = {
      ...fgtsVinculada,
      opportunity_id: 999,
      campanhas_lancadas: 0,
      reconciliacao: undefined,
      titulo: 'FGTS saque-aniversário',
    };
    const frase = fraseDeReconciliacao(semContrato);
    expect(frase.estado).toBe('pendente');
    expect(frase.podeMontar).toBe(false);
  });
});

describe('Preparar falha fechado', () => {
  it('só reconciliacao: sem_campanha libera montar', () => {
    expect(fraseDeReconciliacao(candidatoSemCampanha).podeMontar).toBe(true);
    expect(fraseDeReconciliacao(candidatoSemCampanha).estado).toBe('sem_campanha');
  });

  it('FGTS sem reconciliação nunca recebe ação de montagem', async () => {
    expect(fraseDeReconciliacao(fgtsSemReconciliacao).podeMontar).toBe(false);
    expect(fraseDeReconciliacao(fgtsSemReconciliacao).estado).toBe('pendente');

    quadroDeTrafego.mockResolvedValue({
      prontos: [fgtsSemReconciliacao, candidatoSemCampanha],
      totais: { funis_publicados: 2, com_cluster: 2, keywords_disponiveis: 25 },
      sem_metrica: true,
      por_que: 'não existe camada de métrica no motor de anúncios.',
    });
    montar();
    await screen.findByText('FGTS saque-aniversário');
    const fgts = screen.getByText('FGTS saque-aniversário').closest('tr');
    expect(fgts && within(fgts).queryByRole('link', { name: /montar campanha/ })).toBeNull();
    expect(fgts?.textContent).toMatch(/reconciliação ainda não concluída/i);
    expect(fgts && within(fgts).queryByRole('link', { name: /abrir o que existe/ })).toBeNull();

    const novo = screen.getByText('Empréstimo com garantia').closest('tr');
    expect(novo && within(novo).getByRole('link', { name: /montar campanha/ })).toBeTruthy();
  });

  it('qualquer candidato sem reconciliação fica bloqueado', async () => {
    const semDeclaracao = {
      ...candidatoSemCampanha,
      opportunity_id: 404,
      titulo: 'Antecipação do IR',
      reconciliacao: undefined,
    };
    expect(fraseDeReconciliacao(semDeclaracao).podeMontar).toBe(false);

    quadroDeTrafego.mockResolvedValue({
      prontos: [semDeclaracao],
      totais: { funis_publicados: 1, com_cluster: 1, keywords_disponiveis: 7 },
      sem_metrica: true,
      por_que: 'não existe camada de métrica no motor de anúncios.',
    });
    montar();
    await screen.findByText('Antecipação do IR');
    expect(screen.queryByRole('link', { name: /montar campanha/ })).toBeNull();
    expect(screen.getByText(RECONCILIACAO_PENDENTE)).toBeTruthy();
  });

  it('campanhas_lancadas > 0 sem reconciliação impede duplicar e não afirma vínculo', () => {
    const frase = fraseDeReconciliacao(lancadaSemReconciliacao);
    expect(frase.estado).toBe('pendente');
    expect(frase.podeMontar).toBe(false);
    expect(frase.palavra).not.toMatch(/campanha no ar/);
    expect(frase.acao).not.toBe('abrir o que existe');
    expect(frase.acao).not.toBe('montar campanha');
  });
});

describe('conflito e somente histórico', () => {
  it('conflito bloqueia a montagem e pede revisão', async () => {
    quadroDeTrafego.mockResolvedValue({
      prontos: [candidatoEmConflito],
      totais: { funis_publicados: 1, com_cluster: 1, keywords_disponiveis: 11 },
      sem_metrica: true,
      por_que: 'não existe camada de métrica no motor de anúncios.',
    });
    montar();
    await screen.findByText('Portabilidade de consignado');
    expect(screen.getByText('conflito')).toBeTruthy();
    expect(screen.getByText(REVISAO_DE_CONFLITO)).toBeTruthy();
    expect(screen.queryByRole('link', { name: /montar campanha/ })).toBeNull();
    expect(fraseDeReconciliacao(candidatoEmConflito).podeMontar).toBe(false);
  });

  it('somente histórico oferece relançamento declarado', async () => {
    quadroDeTrafego.mockResolvedValue({
      prontos: [candidatoSomenteHistorico],
      totais: { funis_publicados: 1, com_cluster: 1, keywords_disponiveis: 9 },
      sem_metrica: true,
      por_que: 'não existe camada de métrica no motor de anúncios.',
    });
    montar();
    await screen.findByText('Cartão de crédito consignado');
    const link = screen.getByRole('link', { name: /relançar \(declarado\)/ });
    expect(link.getAttribute('href')).toMatch(/relancar=1/);
    expect(fraseDeReconciliacao(candidatoSomenteHistorico).podeRelancar).toBe(true);
    expect(fraseDeReconciliacao(candidatoSomenteHistorico).podeMontar).toBe(false);
  });
});

describe('contrato final da reconciliação', () => {
  it('reconciliacao null bloqueia e não vira sem_campanha', async () => {
    expect(fraseDeReconciliacao(reconciliacaoNula).estado).toBe('pendente');
    expect(fraseDeReconciliacao(reconciliacaoNula).podeMontar).toBe(false);
    expect(fraseDeReconciliacao(reconciliacaoNula).palavra).not.toMatch(/sem campanha/);

    quadroDeTrafego.mockResolvedValue({
      prontos: [reconciliacaoNula],
      totais: { funis_publicados: 1, com_cluster: 1, keywords_disponiveis: 18 },
      sem_metrica: true,
      por_que: 'não existe camada de métrica no motor de anúncios.',
    });
    montar();
    await screen.findByText('FGTS saque-aniversário');
    expect(screen.queryByRole('link', { name: /montar campanha/ })).toBeNull();
    expect(screen.getByText(RECONCILIACAO_PENDENTE)).toBeTruthy();
  });

  it('FGTS e Maquininha com correspondencia_provavel não recebem montar campanha', async () => {
    expect(fraseDeReconciliacao(fgtsCorrespondencia).podeMontar).toBe(false);
    expect(fraseDeReconciliacao(maquininhaCorrespondencia).podeMontar).toBe(false);

    quadroDeTrafego.mockResolvedValue({
      prontos: [fgtsCorrespondencia, maquininhaCorrespondencia],
      totais: { funis_publicados: 2, com_cluster: 2, keywords_disponiveis: 41 },
      sem_metrica: true,
      por_que: 'não existe camada de métrica no motor de anúncios.',
    });
    montar();
    await screen.findByText('FGTS saque-aniversário');
    const fgts = screen.getByText('FGTS saque-aniversário').closest('tr');
    const maquininha = screen.getByText('Maquininha de cartão para MEI').closest('tr');
    expect(fgts && within(fgts).queryByRole('link', { name: /montar campanha/ })).toBeNull();
    expect(maquininha && within(maquininha).queryByRole('link', { name: /montar campanha/ })).toBeNull();
    expect(fgts && within(fgts).getByRole('button', { name: /confirmar vínculo/ })).toBeTruthy();
    expect(maquininha && within(maquininha).getByRole('button', { name: /confirmar vínculo/ })).toBeTruthy();
  });

  it('sem_campanha só libera conforme pode_montar, e o aviso de rascunho permanece visível', async () => {
    expect(fraseDeReconciliacao(candidatoSemCampanha).podeMontar).toBe(true);
    expect(fraseDeReconciliacao(semCampanhaSemPodeMontar).podeMontar).toBe(false);
    expect(fraseDeReconciliacao(rascunhoComAviso).podeMontar).toBe(true);
    expect(fraseDeReconciliacao(rascunhoComAviso).palavra).toMatch(/confirmação pendente/);

    quadroDeTrafego.mockResolvedValue({
      prontos: [rascunhoComAviso, semCampanhaSemPodeMontar],
      totais: { funis_publicados: 2, com_cluster: 2, keywords_disponiveis: 11 },
      sem_metrica: true,
      por_que: 'não existe camada de métrica no motor de anúncios.',
    });
    montar();
    await screen.findByText('Funil em rascunho');
    const rascunho = screen.getByText('Funil em rascunho').closest('tr');
    const bloqueado = screen.getByText('Antecipação do IR').closest('tr');
    expect(rascunho && within(rascunho).getByRole('link', { name: /montar campanha/ })).toBeTruthy();
    expect(rascunho?.textContent).toMatch(/aviso permanece visível/i);
    expect(bloqueado && within(bloqueado).queryByRole('link', { name: /montar campanha/ })).toBeNull();
  });

  it('nome, URL ou campanhas_lancadas isoladamente nunca liberam montagem', () => {
    const soNome = {
      ...fgtsCorrespondencia,
      reconciliacao: null,
      campanhas_lancadas: null,
      lp_url: 'https://creditoup.com.br/r/fgts/',
    };
    const soLancadas = {
      ...fgtsCorrespondencia,
      reconciliacao: undefined,
      campanhas_lancadas: 3,
    };
    expect(fraseDeReconciliacao(soNome).podeMontar).toBe(false);
    expect(fraseDeReconciliacao(soLancadas).podeMontar).toBe(false);
    expect(fraseDeReconciliacao(soLancadas).palavra).not.toMatch(/campanha no ar/);
  });
});
