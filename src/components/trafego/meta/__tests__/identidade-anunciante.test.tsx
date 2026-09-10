// @vitest-environment jsdom
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { IdentidadeDoAnunciante } from '../IdentidadeDoAnunciante';
const api = vi.hoisted(() => ({ identidadesRegulatoriasMeta: vi.fn() }));
vi.mock('@/lib/pautadorApi', () => ({ pautadorApi: api }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const item = {reference: 'metareg_example', label: 'Empresa anunciante', beneficiary_name: 'Empresa anunciante', payer_name: 'Empresa pagadora', names_available: true, category: 'BRAZIL_REGULATION'};
const conjunto = { key: 'adset-001', nome: 'Brasil', regulatoryIdentityRef: undefined } as any;
describe('identificação explícita do anunciante', () => {
  it('consulta automaticamente, mas confirma responsáveis com a pessoa', async () => {
    api.identidadesRegulatoriasMeta.mockResolvedValue({complete: true, items: [item]});
    const change = vi.fn();
    render(<IdentidadeDoAnunciante accountRef="conta-a" conjunto={conjunto} onChange={change} />);
    expect(api.identidadesRegulatoriasMeta).toHaveBeenCalledWith('conta-a');
    await screen.findByText('Empresa anunciante');
    expect(change).not.toHaveBeenCalled();
    expect(screen.queryByRole('combobox')).toBeNull();
    expect(screen.queryByText(/conjuntos de origem/i)).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Confirmar anunciante e pagador'}));
    expect(change).toHaveBeenCalledWith(item.reference);
  });
  it('não oferece seleção de lista incompleta', async () => {
    api.identidadesRegulatoriasMeta.mockResolvedValue({complete: false, items: [item]});
    render(<IdentidadeDoAnunciante accountRef="conta-a" conjunto={conjunto} onChange={vi.fn()} />);
    await screen.findByRole('alert');
    expect(screen.queryByRole('combobox')).toBeNull();
  });
  it('descarta resposta da conta anterior e preserva seleção salva', async () => {
    let resolve!: (value: any) => void;
    api.identidadesRegulatoriasMeta.mockReturnValue(new Promise(r => { resolve = r; }));
    const {rerender} = render(<IdentidadeDoAnunciante accountRef="conta-a" conjunto={conjunto} onChange={vi.fn()} />);
    api.identidadesRegulatoriasMeta.mockResolvedValue({complete: true, items: []});
    rerender(<IdentidadeDoAnunciante accountRef="conta-b" conjunto={{...conjunto, regulatoryIdentityRef: 'salva'}} onChange={vi.fn()} />);
    resolve({complete: true, items: [item]});
    await waitFor(() => expect(screen.queryByRole('combobox')).toBeNull());
    expect(screen.queryByText('Empresa anunciante')).toBeNull();
  });
  it('não consulta em demonstração', () => {
    render(<IdentidadeDoAnunciante accountRef="conta-a" conjunto={conjunto} onChange={vi.fn()} demo />);
    expect(api.identidadesRegulatoriasMeta).not.toHaveBeenCalled();
  });
  it('várias identidades exigem escolha e confirmação, sem copiar conjunto', async () => {
    const other = {...item, reference: 'metareg_other', label: 'Outra empresa', beneficiary_name: 'Outra empresa'};
    api.identidadesRegulatoriasMeta.mockResolvedValue({complete: true, items: [item, other]});
    const change = vi.fn();
    render(<IdentidadeDoAnunciante accountRef="conta-a" conjunto={conjunto} onChange={change} />);
    await screen.findByRole('combobox');
    fireEvent.change(screen.getByRole('combobox'), {target: {value: other.reference}});
    expect(change).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Confirmar anunciante e pagador'}));
    expect(change).toHaveBeenCalledWith(other.reference);
  });
});
