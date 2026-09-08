// @vitest-environment jsdom
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { TrackingAutomatico } from '../TrackingAutomatico';
import { GestaoDaCampanha } from '../GestaoDaCampanha';
import { destinoValido } from '../rascunho';
import { pautadorApi } from '@/lib/pautadorApi';

vi.mock('@/lib/pautadorApi', () => ({ pautadorApi: {
  trackingAutomaticoMeta: vi.fn(), planejarGestaoMeta: vi.fn(),
} }));
afterEach(cleanup);
beforeEach(() => vi.resetAllMocks());

const tracking = {
  template: 'utm_campaign={{adset.id}}&utm_content={{ad.id}}',
  parametros: [{ nome: 'utm_campaign', valor: '{{adset.id}}' }, { nome: 'utm_content', valor: '{{ad.id}}' }],
  revenue_join: 'GAM.utm_campaign_value = adset_id', grao: 'ADSET' as const,
  campo_api: 'AdCreative.url_tags', previa_url: 'https://example.com/?utm_campaign={{adset.id}}',
  destino_valido: true, erro: null, prova: 'TEMPLATE_LOCAL' as const, efeito_externo: 'NENHUM' as const,
};
const campanha = { nome: 'Campanha', entity_ref: 'metaobj_campaign', status: 'ACTIVE' };
const conjuntos = [{ nome: 'Amplo', entity_ref: 'metaobj_adset', status: 'ACTIVE' }];
function montar() {
  return render(<GestaoDaCampanha contaRef="metaacct_test" campanhaRef="metaobj_campaign" campanha={campanha} conjuntos={conjuntos} completo />);
}

it('mostra o template fornecido pelo servidor, sem simular prova de clique', async () => {
  vi.mocked(pautadorApi.trackingAutomaticoMeta).mockResolvedValue(tracking);
  render(<TrackingAutomatico destino="https://example.com/" />);
  await screen.findByText('utm_campaign = {{adset.id}}');
  expect(pautadorApi.trackingAutomaticoMeta).toHaveBeenCalledWith('https://example.com/');
  expect(screen.getByText(/não comprova clique/)).toBeTruthy();
  expect(pautadorApi.planejarGestaoMeta).not.toHaveBeenCalled();
});

it('falha de template nunca exibe configuração como verificada', async () => {
  vi.mocked(pautadorApi.trackingAutomaticoMeta).mockRejectedValue(new Error('offline'));
  render(<TrackingAutomatico destino="https://example.com/" />);
  await screen.findByText(/Não foi possível carregar a prévia/);
  expect(screen.queryByText('utm_campaign = {{adset.id}}')).toBeNull();
});

describe('validação local do destino', () => {
  it.each(['utm_campaign=fixed', '%75tm_campaign=fixed', 'UTM_CONTENT=123', 'placement=feed'])('recusa conflito %s', query => {
    expect(destinoValido(`https://example.com/?${query}`)).toBe(false);
  });
  it('preserva parâmetros da página e recusa credenciais', () => {
    expect(destinoValido('https://example.com/?lang=pt#artigo')).toBe(true);
    expect(destinoValido('https://user:pass@example.com/')).toBe(false);
  });
});

it('gestão não planeja ao montar; orçamento só aceita inteiro em centavos após clique', async () => {
  montar();
  fireEvent.click(screen.getByText('Gestão da campanha'));
  expect(pautadorApi.planejarGestaoMeta).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Onde alterar'), { target: { value: 'metaobj_adset' } });
  fireEvent.change(screen.getByLabelText('Alteração proposta'), { target: { value: 'ORCAMENTO_DIARIO' } });
  fireEvent.change(screen.getByLabelText(/Novo orçamento diário/), { target: { value: '25,50' } });
  fireEvent.click(screen.getByRole('button', { name: 'Conferir proposta sem aplicar' }));
  await waitFor(() => expect(pautadorApi.planejarGestaoMeta).toHaveBeenCalledWith({
    conta_ref: 'metaacct_test', campanha_ref: 'metaobj_campaign', entidade: 'conjunto', referencia: 'metaobj_adset', acao: 'ORCAMENTO_DIARIO', valor_minor: 2550,
  }));
});

it('cópia só aparece para conjunto e nunca oferece ativar', () => {
  montar(); fireEvent.click(screen.getByText('Gestão da campanha'));
  expect(screen.queryByRole('option', { name: 'Duplicar conjunto com anúncios' })).toBeNull();
  fireEvent.change(screen.getByLabelText('Onde alterar'), { target: { value: 'metaobj_adset' } });
  expect(screen.getByRole('option', { name: 'Duplicar conjunto com anúncios' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: /ativar|aplicar na meta/i })).toBeNull();
});

it('leitura parcial bloqueia planejamento', () => {
  render(<GestaoDaCampanha contaRef="metaacct_test" campanhaRef="metaobj_campaign" campanha={campanha} conjuntos={conjuntos} completo={false} />);
  fireEvent.click(screen.getByText('Gestão da campanha'));
  expect((screen.getByRole('button', { name: 'Conferir proposta sem aplicar' }) as HTMLButtonElement).disabled).toBe(true);
});
