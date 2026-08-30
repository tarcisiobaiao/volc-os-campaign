// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DecisionIntelligenceLab } from '../DecisionIntelligenceLab';
import { fotografiaDouradaBudgetLimited, PROVAS_L6 } from '../fixtures';
import { MARCA_SHADOW_FUTURO, MARCA_SHADOW_REAL, MARCA_SINTETICA } from '../projection';

function montar() {
  return render(
    <MemoryRouter>
      <DecisionIntelligenceLab
        scenarioId="budget-limited-healthy"
        resposta={fotografiaDouradaBudgetLimited()}
        carregando={false}
        erro={null}
        aoEscolher={vi.fn()}
      />
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe('provas obrigatórias L6', () => {
  it.each(PROVAS_L6.map((prova) => [prova.prova_id, prova.rotulo, prova.modo] as const))(
    'renderiza a prova %s sem CTA de aplicação',
    (id) => {
      montar();
      fireEvent.change(screen.getByLabelText('Cenário de replay'), { target: { value: id } });
      expect(screen.queryByRole('button', { name: /aplicar/i })).toBeNull();
      expect(screen.queryByRole('button', { name: /aprovar/i })).toBeNull();
      expect(screen.queryByText(/googleads/i)).toBeNull();
    },
  );

  it('sintético completo identifica o laboratório e bloqueia ação', () => {
    montar();
    fireEvent.change(screen.getByLabelText('Cenário de replay'), { target: { value: 'prova-l6-sintetico-completo' } });
    expect(screen.getAllByText(new RegExp(MARCA_SINTETICA)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/nenhuma ação será executada/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/proposta, não executada/i).length).toBeGreaterThan(0);
  });

  it('proposta bloqueada mostra o bloqueio e não o executor', () => {
    montar();
    fireEvent.change(screen.getByLabelText('Cenário de replay'), { target: { value: 'prova-l6-proposta-bloqueada' } });
    expect(screen.getAllByText(/sem executor/i).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /aplicar/i })).toBeNull();
  });

  it('evidência parcial diz a insuficiência antes da hipótese', () => {
    montar();
    fireEvent.change(screen.getByLabelText('Cenário de replay'), { target: { value: 'prova-l6-evidencia-parcial' } });
    const insuficiencia = screen.getByText(/A evidência ainda não é suficiente/i);
    const hipotese = screen.getByRole('heading', { name: /Leitura parcial não autoriza decisão/i });
    expect(insuficiencia.compareDocumentPosition(hipotese) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('leitura antiga permanece visível e não autoriza', () => {
    montar();
    fireEvent.change(screen.getByLabelText('Cenário de replay'), { target: { value: 'prova-l6-leitura-antiga' } });
    expect(screen.getAllByText(/antiga/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/não autoriza decisão/i).length).toBeGreaterThan(0);
  });

  it('indisponível sem último bom não inventa fotografia', () => {
    montar();
    fireEvent.change(screen.getByLabelText('Cenário de replay'), { target: { value: 'prova-l6-indisponivel-sem-ultimo-bom' } });
    expect(screen.getByRole('heading', { name: /Falha sem fotografia anterior/i })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Demanda limitada por orçamento' })).toBeNull();
  });

  it('indisponível com último bom preserva a fotografia anterior', () => {
    montar();
    fireEvent.change(screen.getByLabelText('Cenário de replay'), { target: { value: 'prova-l6-indisponivel-com-ultimo-bom' } });
    expect(screen.getByText(/A tentativa mais recente falhou/i)).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Demanda limitada por orçamento' })).toBeTruthy();
  });

  it('lista observada e vazia não vira ausência', () => {
    montar();
    fireEvent.change(screen.getByLabelText('Cenário de replay'), { target: { value: 'prova-l6-lista-vazia' } });
    expect(screen.getAllByText(/lista vazia/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/lista observada e vazia/i).length).toBeGreaterThan(0);
  });

  it('campo ausente é distinto de zero', () => {
    montar();
    fireEvent.change(screen.getByLabelText('Cenário de replay'), { target: { value: 'prova-l6-campo-ausente' } });
    expect(screen.getAllByText(/campo ausente/i).length).toBeGreaterThan(0);
  });

  it('não aplicável permanece distinto de ausência e de zero', () => {
    montar();
    fireEvent.change(screen.getByLabelText('Cenário de replay'), { target: { value: 'prova-l6-nao-aplicavel' } });
    expect(screen.getByText('lance alvo')).toBeTruthy();
    expect(screen.getAllByText(/^não aplicável$/i).length).toBeGreaterThan(0);
    expect(screen.queryByText('zero medido')).toBeNull();
  });

  it('zero medido permanece zero', () => {
    montar();
    fireEvent.change(screen.getByLabelText('Cenário de replay'), { target: { value: 'prova-l6-zero-medido' } });
    expect(screen.getAllByText(/zero medido/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText('0').length).toBeGreaterThan(0);
  });

  it('conflito entre evidências aparece antes da proposta', () => {
    montar();
    fireEvent.change(screen.getByLabelText('Cenário de replay'), { target: { value: 'prova-l6-conflito' } });
    expect(screen.getAllByText(/O contrato registrou o conflito/i).length).toBeGreaterThan(0);
  });

  it('shadow futuro fica separado do sintético e não finge fotografia de backend', () => {
    montar();
    fireEvent.change(screen.getByLabelText('Cenário de replay'), { target: { value: 'prova-l6-shadow-futuro' } });
    expect(screen.getAllByText(MARCA_SHADOW_FUTURO).length).toBeGreaterThan(0);
    expect(screen.queryByText(MARCA_SHADOW_REAL)).toBeNull();
    expect(screen.queryByText(/dados reais/i)).toBeNull();
    expect(screen.queryByText(/conta teste/i)).toBeNull();
    expect(screen.queryByText(/leitura da conta/i)).toBeNull();
    expect(screen.getAllByText(/sem fotografia de backend/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/ROAS/i)).toBeNull();
  });

  it('provas locais não pedem o servidor', () => {
    const aoEscolher = vi.fn();
    render(
      <MemoryRouter>
        <DecisionIntelligenceLab
          scenarioId="budget-limited-healthy"
          resposta={fotografiaDouradaBudgetLimited()}
          carregando={false}
          erro={null}
          aoEscolher={aoEscolher}
        />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText('Cenário de replay'), { target: { value: 'prova-l6-zero-medido' } });
    expect(aoEscolher).not.toHaveBeenCalled();
  });
});
