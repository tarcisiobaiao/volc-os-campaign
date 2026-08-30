// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { RespostaDoDecisionLab } from '@/types/inteligenciaDecisao';

import { DecisionIntelligenceLab } from '../DecisionIntelligenceLab';
import { fotografiaDouradaBudgetLimited } from '../fixtures';

function resultado(): RespostaDoDecisionLab {
  return fotografiaDouradaBudgetLimited();
}

function montar(props: Partial<React.ComponentProps<typeof DecisionIntelligenceLab>> = {}) {
  const padrao = {
    scenarioId: 'budget-limited-healthy',
    resposta: resultado(),
    carregando: false,
    atualizando: false,
    erro: null,
    aoEscolher: vi.fn(),
  };
  return render(<MemoryRouter><DecisionIntelligenceLab {...padrao} {...props} /></MemoryRouter>);
}

afterEach(cleanup);

describe('Decision Intelligence Lab', () => {
  it('mostra uma cadeia causal, um veredito dominante e o rail sempre bloqueado', () => {
    montar();
    expect(screen.getAllByText(/PROTÓTIPO · DADOS SINTÉTICOS/i).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole('heading', { name: 'Demanda limitada por orçamento' })).toBeTruthy();
    expect(screen.getByText(/evidência utilizável/i)).toBeTruthy();
    expect(screen.getByText(/decisão bloqueada/i)).toBeTruthy();
    expect(screen.getByText(/mutações executadas/i).nextElementSibling?.textContent).toBe('0');
    expect(screen.getByText('8/8 cenários passaram')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /aplicar/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /aprovar/i })).toBeNull();
  });

  it('mantém conflitos no documento antes do diagnóstico e da proposta', () => {
    montar();
    const conflitos = screen.getByRole('heading', { name: /veto venceu a arbitragem/i });
    const diagnostico = screen.getByRole('heading', { name: /hipótese principal, não um fato/i });
    const propostas = screen.getByRole('heading', { name: /proposta/i });
    expect(conflitos.compareDocumentPosition(diagnostico) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(diagnostico.compareDocumentPosition(propostas) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('preserva loading como estado e mantém as duas marcas na captura', () => {
    montar({ resposta: null, carregando: true });
    expect(screen.getByRole('status').textContent).toMatch(/Carregando o replay sintético/i);
    expect(screen.getAllByText(/PROTÓTIPO · DADOS SINTÉTICOS/i).length).toBeGreaterThanOrEqual(2);
  });

  it('renderiza vazio confirmado sem chamá-lo de falha', () => {
    const base = resultado();
    const vazio = {
      ...base,
      versao_contrato: 1,
      scenario_id: 'empty-confirmed',
      rotulo: 'Vazio confirmado',
      estado_da_superficie: 'vazio_confirmado',
      marcas: ['PROTÓTIPO', 'DADOS SINTÉTICOS'],
      confirmacao: { fonte: 'dataset sintético', lido_em: '2026-08-28T11:00:00Z', linhas: 0 },
    } as unknown as RespostaDoDecisionLab;
    montar({ scenarioId: 'empty-confirmed', resposta: vazio });
    expect(screen.getByRole('heading', { name: /Vazio confirmado pelo dataset/i })).toBeTruthy();
    expect(screen.queryByText(/Falha sem fotografia anterior/i)).toBeNull();
  });

  it.each([
    ['stale', 'stale', 'leitura antiga'],
    ['parcial', 'parcial', 'leitura parcial'],
  ])('torna %s visível e mantém o health gate fechado', (estado, gate, rotulo) => {
    const base = resultado();
    const resposta = {
      ...base,
      estado_da_superficie: estado,
      estado_da_leitura: estado,
      health_gate: { estado: gate, rotulo, motivo: `A fotografia está ${estado}.` },
    } as RespostaDoDecisionLab;
    montar({ resposta });
    expect(screen.getAllByText(new RegExp(rotulo, 'i')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/decisão bloqueada/i).length).toBeGreaterThan(0);
  });

  it('preserva a última fotografia quando a tentativa mais recente falha', () => {
    const boa = resultado();
    const falha = {
      ...boa,
      scenario_id: 'failure-last-good',
      rotulo: 'Falha com último bom',
      estado_da_superficie: 'falha_ultimo_bom',
      ultima_fotografia: boa,
      falha: { codigo: 'LAB-FALHA-SINTETICA', mensagem: 'A tentativa falhou.' },
    } as unknown as RespostaDoDecisionLab;
    montar({ scenarioId: 'failure-last-good', resposta: falha });
    expect(screen.getByText(/A tentativa mais recente falhou/i)).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Demanda limitada por orçamento' })).toBeTruthy();
  });

  it.each([
    ['falha_sem_fotografia', 'Falha sem fotografia anterior'],
    ['versao_desconhecida', 'Versão de contrato desconhecida'],
  ])('mostra o estado %s sem assumir sucesso', (estado, titulo) => {
    const base = resultado();
    const resposta = {
      ...base,
      versao_contrato: estado === 'versao_desconhecida' ? 999 : 1,
      estado_da_superficie: estado,
      ultima_fotografia: null,
      falha: { codigo: 'LAB-SEM-FOTO-SINTETICA', mensagem: 'A leitura falhou.' },
      versao_recebida: 'lab-future-999',
    } as unknown as RespostaDoDecisionLab;
    montar({ resposta });
    expect(screen.getByRole('heading', { name: titulo })).toBeTruthy();
  });

  it('navega somente por scenarioId do catálogo sintético', () => {
    const aoEscolher = vi.fn();
    montar({ aoEscolher });
    fireEvent.change(screen.getByLabelText('Cenário de replay'), { target: { value: 'partial-read' } });
    expect(aoEscolher).toHaveBeenCalledWith('partial-read');
  });

  it('não dispara fetch nem Google Ads no render da bancada', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    montar();
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
