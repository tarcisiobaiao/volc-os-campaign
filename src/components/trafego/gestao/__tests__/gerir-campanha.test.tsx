// @vitest-environment jsdom
/**
 * "GERIR CAMPANHA" COM DADOS DO CONTRATO (GADS-GESTAO v1 §3).
 *
 * As provas:
 *  - permissão: quem não é admin não vê aprovar nem aplicar; o admin com a
 *    escrita fechada vê o gesto FECHADO com o motivo, e não some;
 *  - aprovar manda como `diff_apresentado` exatamente o gravado;
 *  - recusar e reverter exigem motivo antes da rede;
 *  - a proposta passa pela confirmação antes → depois, e o 409 vira frase;
 *  - `campanha_nao_importada` oferece importar;
 *  - recomendações avisam que não há ensaio e viram proposta.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { PropostaDoPainel } from '@/types/gestao';

const api = vi.hoisted(() => ({
  propostas: vi.fn(),
  propor: vi.fn(),
  aprovar: vi.fn(),
  recusar: vi.fn(),
  aplicar: vi.fn(),
  verificar: vi.fn(),
  reverter: vi.fn(),
  importarCampanha: vi.fn(),
  recomendacoes: vi.fn(),
}));
const casa = vi.hoisted(() => ({ capacidades: vi.fn() }));

vi.mock('@/lib/trafego/gestaoApi', () => ({ gestaoApi: api }));
vi.mock('@/lib/pautadorApi', () => ({ pautadorApi: casa }));

import { GerirCampanha } from '../GerirCampanha';

const CUSTOMER = '5478096539';
const CAMPANHA = '24278665189';
const VOLC = '7f6b9a52-0000-4000-8000-000000000001';

/** A linha de §3.1, como o contrato a publica. */
function proposta(parcial: Partial<PropostaDoPainel> = {}): PropostaDoPainel {
  return {
    proposta_id: 'p-1',
    volc_campaign_id: VOLC,
    alvo_nivel: 'campanha',
    alvo_chave: `google_ads:${CUSTOMER}:campanha:${CAMPANHA}`,
    operacao: 'orcamento.diario',
    valor_atual: { verba_diaria_micros: 30_000_000, budget_id: 15886629542, compartilhado: false },
    valor_proposto: { verba_diaria_micros: 33_000_000, budget_id: 15886629542 },
    valor_atual_lido_em: '2026-10-08T21:30:00+00:00',
    delta_pct: 10.0,
    delta_absoluto_micros: 3_000_000,
    moeda: 'BRL',
    estado: 'aguardando_aprovacao',
    criada_em: '2026-10-08T21:30:05+00:00',
    expira_em: '2026-10-09T21:30:05+00:00',
    regra_chave: 'gestao_manual_google',
    regra_versao: 1,
    regra_objetivo: 'Limitar e registrar ajustes',
    regra_responsavel: 'dono',
    nivel_autonomia: 'T1',
    condicao_rollback: 'o operador declara piora',
    sintoma: 'pedido humano: orcamento.diario',
    explicacao: 'CPA estável há 14 dias; verba limita entrega',
    confianca: null,
    severidade: null,
    evidencia_colhida_em: '2026-10-08T21:30:04+00:00',
    evidencia_suficiencia: 'suficiente',
    janela_inicio: '2026-10-01',
    janela_fim: '2026-10-07',
    aprovacao_decisao: null,
    aprovacao_por: null,
    aprovacao_em: null,
    aplicacao_id: null,
    aplicacao_desfecho: null,
    aplicacao_enviada_em: null,
    vencida: false,
    proximo_passo: 'aguardar_humano',
    ...parcial,
  };
}

const capacidades = (is_admin: boolean, google_mutate: boolean) => ({
  is_admin,
  lab_mode: false,
  google_read: true,
  google_validate_only: true,
  google_mutate,
  porque_sem_mutacao: google_mutate ? null : 'a trava de escrita está fechada neste servidor',
});

const erro409 = (codigo: string, detalhe?: unknown) =>
  Object.assign(new Error(`servidor: ${codigo}`), { status: 409, codigo, corpo: { codigo, mensagem: 'x', detalhe } });

function montar(props: Partial<React.ComponentProps<typeof GerirCampanha>> = {}) {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}>
      <GerirCampanha
        customerId={CUSTOMER}
        campaignId={CAMPANHA}
        volcCampaignId={VOLC}
        canal="SEARCH"
        procedencia="volc_os"
        leitura={{ estadoExterno: 'ENABLED', verbaDiariaMicros: 30_000_000, estrategia: 'MAXIMIZE_CONVERSIONS', moeda: 'BRL' }}
        {...props}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  casa.capacidades.mockReset();
  api.propostas.mockResolvedValue({ propostas: [], total: 0 });
});
afterEach(cleanup);

describe('permissões vêm de useCapacidades', () => {
  it('não-admin não vê aprovar, recusar nem aplicar', async () => {
    casa.capacidades.mockResolvedValue(capacidades(false, false));
    api.propostas.mockResolvedValue({
      propostas: [proposta(), proposta({ proposta_id: 'p-2', estado: 'aprovada', proximo_passo: 'aplicar', aprovacao_decisao: 'aprovada' })],
      total: 2,
    });
    montar();
    await screen.findByText('aguardando decisão de um administrador');
    expect(screen.getByText('aprovada; aguardando um administrador aplicar')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Aprovar' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Recusar' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Aplicar no Google' })).toBeNull();
  });

  it('enquanto as capacidades não chegam, ninguém pode', async () => {
    casa.capacidades.mockReturnValue(new Promise(() => {}));
    api.propostas.mockResolvedValue({ propostas: [proposta()], total: 1 });
    montar();
    await screen.findByText('aguardando decisão de um administrador');
    expect(screen.queryByRole('button', { name: 'Aprovar' })).toBeNull();
  });

  it('admin com a escrita fechada vê aplicar FECHADO e o porquê', async () => {
    casa.capacidades.mockResolvedValue(capacidades(true, false));
    api.propostas.mockResolvedValue({
      propostas: [proposta({ estado: 'aprovada', proximo_passo: 'aplicar', aprovacao_decisao: 'aprovada' })],
      total: 1,
    });
    montar();
    const fechado = await screen.findByRole('button', { name: 'Aplicar no Google' });
    expect((fechado as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('a trava de escrita está fechada neste servidor')).toBeTruthy();
  });
});

describe('a fila: diff, decisão e desfecho', () => {
  it('mostra o antes → depois gravado, em dinheiro', async () => {
    casa.capacidades.mockResolvedValue(capacidades(false, false));
    api.propostas.mockResolvedValue({ propostas: [proposta()], total: 1 });
    montar();
    const tabela = await screen.findByRole('table', { name: /orçamento diário/ });
    expect(within(tabela).getByText('verba diária')).toBeTruthy();
    expect(within(tabela).getByText('R$ 30,00')).toBeTruthy();
    expect(within(tabela).getByText('R$ 33,00')).toBeTruthy();
  });

  it('aprovar manda o diff gravado, sem retoque', async () => {
    casa.capacidades.mockResolvedValue(capacidades(true, true));
    const p = proposta();
    api.propostas.mockResolvedValue({ propostas: [p], total: 1 });
    api.aprovar.mockResolvedValue({ aprovacao: {}, proposta: { estado: 'aprovada' }, ja_existia: false });
    montar();
    fireEvent.click(await screen.findByRole('button', { name: 'Aprovar' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar aprovação' }));
    await waitFor(() => expect(api.aprovar).toHaveBeenCalledTimes(1));
    expect(api.aprovar).toHaveBeenCalledWith('p-1', {
      diff_apresentado: { valor_atual: p.valor_atual, valor_proposto: p.valor_proposto, delta_pct: 10 },
    });
    await screen.findByText(/Decisão registrada: aprovada/);
  });

  it('recusar sem motivo não sai da tela', async () => {
    casa.capacidades.mockResolvedValue(capacidades(true, false));
    api.propostas.mockResolvedValue({ propostas: [proposta()], total: 1 });
    api.recusar.mockResolvedValue({ aprovacao: {}, proposta: { estado: 'recusada' }, ja_existia: false });
    montar();
    fireEvent.click(await screen.findByRole('button', { name: 'Recusar' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar recusa' }));
    expect(screen.getByText('Recusa exige motivo.')).toBeTruthy();
    expect(api.recusar).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('motivo'), { target: { value: 'verba do mês acabou' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar recusa' }));
    await waitFor(() => expect(api.recusar).toHaveBeenCalledTimes(1));
    expect(api.recusar.mock.calls[0][1].motivo).toBe('verba do mês acabou');
  });

  it('aplicar mostra o desfecho; 409 antes_divergiu vira frase', async () => {
    casa.capacidades.mockResolvedValue(capacidades(true, true));
    api.propostas.mockResolvedValue({
      propostas: [proposta({ estado: 'aprovada', proximo_passo: 'aplicar', aprovacao_decisao: 'aprovada' })],
      total: 1,
    });
    api.aplicar.mockRejectedValueOnce(erro409('antes_divergiu', { campos: ['verba_diaria_micros'] }));
    montar();
    fireEvent.click(await screen.findByRole('button', { name: 'Aplicar no Google' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar aplicação' }));
    await screen.findByText('A conta mudou desde a proposta. Nada foi enviado.');
    expect(screen.getByText(/Mudou: verba_diaria_micros/)).toBeTruthy();

    api.aplicar.mockResolvedValueOnce({
      aplicacao: { aplicacao_id: 'a-1', desfecho: 'sucesso' },
      proposta: { estado: 'aplicada' },
      desfecho: 'sucesso',
      ja_aplicada: false,
    });
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar no Google' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar aplicação' }));
    await screen.findByText('Desfecho: aplicada com sucesso.');
  });

  it('em `verificar` ninguém reaplica: qualquer usuário só verifica', async () => {
    casa.capacidades.mockResolvedValue(capacidades(false, false));
    api.propostas.mockResolvedValue({
      propostas: [
        proposta({ estado: 'aprovada', proximo_passo: 'verificar', aplicacao_id: 'a-9', aplicacao_desfecho: 'sem_resposta' }),
      ],
      total: 1,
    });
    api.verificar.mockResolvedValue({
      acompanhamento: { acompanhamento_id: 'c-1', confere: true, motivo: 'verba lida 33000000, pedida 33000000' },
      confere: true,
      motivo: 'verba lida 33000000, pedida 33000000',
      aplicacao: {},
      proposta: { estado: 'aplicada' },
    });
    montar();
    fireEvent.click(await screen.findByRole('button', { name: 'Verificar na conta' }));
    expect(screen.queryByRole('button', { name: 'Aplicar no Google' })).toBeNull();
    await waitFor(() => expect(api.verificar).toHaveBeenCalledWith('a-9'));
    await screen.findByText(/a conta confere com o proposto/);
  });

  it('reverter é de admin com escrita, só após sucesso, e exige motivo', async () => {
    casa.capacidades.mockResolvedValue(capacidades(true, true));
    api.propostas.mockResolvedValue({
      propostas: [proposta({ estado: 'aplicada', proximo_passo: 'acompanhar', aplicacao_id: 'a-1', aplicacao_desfecho: 'sucesso' })],
      total: 1,
    });
    api.reverter.mockResolvedValue({ reversao: { reversao_id: 'r-1', desfecho: 'sucesso' }, proposta: { estado: 'revertida' }, ja_revertida: false });
    montar();
    fireEvent.click(await screen.findByRole('button', { name: 'Reverter' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar reversão' }));
    expect(screen.getByText('Reversão exige motivo.')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('motivo'), { target: { value: 'CPA piorou' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar reversão' }));
    await waitFor(() => expect(api.reverter).toHaveBeenCalledWith('a-1', { motivo: 'CPA piorou' }));
  });
});

describe('propor: formulário → antes/depois → proposta', () => {
  it('orçamento: confirma com o antes lido e manda o payload do contrato', async () => {
    casa.capacidades.mockResolvedValue(capacidades(false, false));
    api.propor.mockResolvedValue({ proposta: { proposta_id: 'p-9', estado: 'aguardando_aprovacao' }, ja_existia: false });
    montar();
    fireEvent.click(screen.getByRole('button', { name: 'Orçamento diário' }));
    fireEvent.change(screen.getByLabelText('nova verba diária'), { target: { value: '33,00' } });
    fireEvent.click(screen.getByRole('button', { name: 'Revisar antes de propor' }));
    const confirmar = screen.getByRole('group', { name: 'confirmar proposta' });
    expect(within(confirmar).getByText('R$ 30,00')).toBeTruthy();
    expect(within(confirmar).getByText('R$ 33,00')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Enviar proposta' }));
    expect(screen.getByText(/diga por que mudar/)).toBeTruthy();
    expect(api.propor).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('motivo'), { target: { value: 'verba limita entrega' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar proposta' }));
    await waitFor(() => expect(api.propor).toHaveBeenCalledTimes(1));
    expect(api.propor).toHaveBeenCalledWith({
      customer_id: CUSTOMER,
      acao: { tipo: 'orcamento.diario', campaign_id: CAMPANHA, amount_micros: 33_000_000, compartilhado_ciente: false },
      motivo: 'verba limita entrega',
    });
    await screen.findByText(/Proposta registrada/);
  });

  it('validação local recusa antes da rede', () => {
    casa.capacidades.mockResolvedValue(capacidades(false, false));
    montar();
    fireEvent.click(screen.getByRole('button', { name: 'Exclusão de IP' }));
    fireEvent.change(screen.getByLabelText('IPs, um por linha'), { target: { value: '10.0.0.0/16' } });
    fireEvent.click(screen.getByRole('button', { name: 'Revisar antes de propor' }));
    expect(screen.getByText(/faixa de IP aceita só IPv4 \/24 a \/32/)).toBeTruthy();
    expect(screen.queryByRole('group', { name: 'confirmar proposta' })).toBeNull();
  });

  it('alvo de lance mostra o campo da estratégia lida', () => {
    casa.capacidades.mockResolvedValue(capacidades(false, false));
    montar({ leitura: { estadoExterno: 'ENABLED', verbaDiariaMicros: null, estrategia: 'MAXIMIZE_CONVERSION_VALUE', moeda: 'BRL' } });
    fireEvent.click(screen.getByRole('button', { name: 'Alvo de lance' }));
    expect(screen.getByLabelText('novo ROAS desejado')).toBeTruthy();
  });

  it('409 regra_ausente e regra_exige_delta viram frase humana', async () => {
    casa.capacidades.mockResolvedValue(capacidades(false, false));
    api.propor.mockRejectedValueOnce(erro409('regra_ausente'));
    montar();
    fireEvent.click(screen.getByRole('button', { name: 'Orçamento diário' }));
    fireEvent.change(screen.getByLabelText('nova verba diária'), { target: { value: '40' } });
    fireEvent.click(screen.getByRole('button', { name: 'Revisar antes de propor' }));
    fireEvent.change(screen.getByLabelText('motivo'), { target: { value: 'teste' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar proposta' }));
    await screen.findByText('Não há regra de gestão publicada para esta conta.');

    api.propor.mockRejectedValueOnce(erro409('regra_exige_delta', { operacao: 'status' }));
    fireEvent.click(screen.getByRole('button', { name: 'Status' }));
    fireEvent.change(screen.getByLabelText('novo status'), { target: { value: 'PAUSED' } });
    fireEvent.click(screen.getByRole('button', { name: 'Revisar antes de propor' }));
    fireEvent.change(screen.getByLabelText('motivo'), { target: { value: 'pausar no fim de semana' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar proposta' }));
    await screen.findByText('Este tipo de ação ainda não é aceito pelo ledger.');
    expect(api.propor.mock.calls[1][0].acao).toEqual({ tipo: 'status', nivel: 'campanha', ident: CAMPANHA, status: 'PAUSED' });
  });

  it('campanha_nao_importada oferece importar, e importar manda conta e campanha', async () => {
    casa.capacidades.mockResolvedValue(capacidades(false, false));
    api.propor.mockRejectedValueOnce(erro409('campanha_nao_importada'));
    api.importarCampanha.mockResolvedValue({
      campanha: { volc_campaign_id: VOLC, customer_id: CUSTOMER, campaign_id: CAMPANHA, procedencia: 'descoberta' },
      google: { nome: 'BR - Search', status: 'ENABLED', canal: 'SEARCH', moeda: 'BRL' },
      ja_existia: false,
      procedencia_resolvida: false,
    });
    montar();
    expect(screen.queryByRole('button', { name: 'Importar campanha para a gestão' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Orçamento diário' }));
    fireEvent.change(screen.getByLabelText('nova verba diária'), { target: { value: '40' } });
    fireEvent.click(screen.getByRole('button', { name: 'Revisar antes de propor' }));
    fireEvent.change(screen.getByLabelText('motivo'), { target: { value: 'teste' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar proposta' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Importar campanha para a gestão' }));
    await waitFor(() => expect(api.importarCampanha).toHaveBeenCalledWith({ customer_id: CUSTOMER, campaign_id: CAMPANHA }));
    await screen.findByText(/Campanha importada/);
  });

  it('procedência desconhecida já oferece importar de saída', () => {
    casa.capacidades.mockResolvedValue(capacidades(false, false));
    montar({ procedencia: 'desconhecida' });
    expect(screen.getByRole('button', { name: 'Importar campanha para a gestão' })).toBeTruthy();
  });
});

describe('recomendações', () => {
  const rn = `customers/${CUSTOMER}/recommendations/abc123`;
  it('avisam que não há ensaio, só leem sob demanda e viram proposta', async () => {
    casa.capacidades.mockResolvedValue(capacidades(false, false));
    api.recomendacoes.mockResolvedValue({
      recomendacoes: [
        {
          recurso: rn,
          tipo: 'SITELINK_ASSET',
          campanha: `customers/${CUSTOMER}/campaigns/${CAMPANHA}`,
          orcamento: null,
          grupo: null,
          dispensada: false,
          impacto: { base: { impressoes: 100, cliques: 5, custo_micros: 1_000_000, conversoes: 1 }, potencial: { impressoes: 120 } },
          acoes: [
            { tipo: 'recomendacao.aplicar', recurso: rn },
            { tipo: 'recomendacao.dispensar', recurso: rn },
          ],
        },
        {
          recurso: `customers/${CUSTOMER}/recommendations/orc1`,
          tipo: 'CAMPAIGN_BUDGET',
          campanha: `customers/${CUSTOMER}/campaigns/${CAMPANHA}`,
          orcamento: null,
          grupo: null,
          dispensada: false,
          impacto: null,
          acoes: [],
        },
      ],
      total: 2,
    });
    api.propor.mockResolvedValue({ proposta: { proposta_id: 'p-r', estado: 'aguardando_aprovacao' }, ja_existia: false });
    montar();
    fireEvent.click(screen.getByRole('button', { name: 'Recomendações' }));
    expect(screen.getByText(/não tem ensaio \(validate_only\) para recomendação/)).toBeTruthy();
    expect(api.recomendacoes).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Ler recomendações do Google' }));
    const lista = await screen.findByRole('list', { name: 'recomendações' });
    const itens = within(lista).getAllByRole('listitem');
    // A de orçamento não oferece "aplicar": é monetária.
    expect(within(itens[1]).queryByRole('button', { name: 'Aplicar recomendação' })).toBeNull();

    fireEvent.click(within(itens[0]).getByRole('button', { name: 'Aplicar recomendação' }));
    fireEvent.change(within(itens[0]).getByLabelText('motivo'), { target: { value: 'sitelinks ajudam o CTR' } });
    fireEvent.click(within(itens[0]).getByRole('button', { name: 'Enviar proposta' }));
    await waitFor(() =>
      expect(api.propor).toHaveBeenCalledWith({
        customer_id: CUSTOMER,
        acao: { tipo: 'recomendacao.aplicar', recurso: rn },
        motivo: 'sitelinks ajudam o CTR',
      }),
    );
  });
});
