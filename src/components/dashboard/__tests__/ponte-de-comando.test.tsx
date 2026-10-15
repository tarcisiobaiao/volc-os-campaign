// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PonteDeComando, type ValoresDaPonte } from '@/components/dashboard/PonteDeComando';

afterEach(cleanup);

const valores: ValoresDaPonte = {
  lucroLiquido: 16046.72,
  investimento: 74210,
  receitaLiquida: 98340,
  roas: 98340 / 74210,
  roiFinal: 16046.72 / 74210,
};

const montar = (extra: Partial<React.ComponentProps<typeof PonteDeComando>> = {}) =>
  render(
    <PonteDeComando
      nome="Ana Exemplo"
      periodo="today"
      seletorDePeriodo={<span>período</span>}
      valores={valores}
      carregando={false}
      falhou={false}
      lidoEm={null}
      onRecarregar={vi.fn()}
      onPedirAtualizacao={vi.fn()}
      pedidoEmCurso={false}
      rodape={<span>8 campanhas</span>}
      {...extra}
    />,
  );

describe('ponte de comando da home', () => {
  it('mostra o lucro como métrica dominante e o ROAS como razão, não como excedente', () => {
    montar();
    expect(screen.getByRole('heading', { level: 1 }).textContent).toMatch(/, Ana$/);
    expect(document.body.textContent).toContain('Lucro líquido');
    expect(document.body.textContent).toMatch(/1,33×/);
  });

  it('leitura falha não vira zero: some todo número e a contagem do rodapé', () => {
    montar({ falhou: true });
    expect(screen.getByText('A leitura do resultado falhou')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/R\$\s?0,00/);
    expect(document.body.textContent).not.toContain('8 campanhas');
    expect(screen.getByRole('button', { name: 'Tentar ler de novo' })).toBeTruthy();
  });

  it('valor ausente é travessão, nunca R$ 0,00', () => {
    montar({ valores: { lucroLiquido: null, investimento: null, receitaLiquida: null, roas: null, roiFinal: null } });
    expect(document.body.textContent).not.toMatch(/R\$\s?0,00/);
    expect(document.body.textContent).toContain('—');
  });

  it('variação não medida (NaN ou zero do serviço) não desenha seta', () => {
    montar({ valores: { ...valores, variacao: { lucro: NaN, investimento: 0, receita: undefined } } });
    expect(document.body.textContent).not.toMatch(/[▲▼]/);
  });

  it('há um único botão de atualizar, e ele nomeia os dois atos no menu', () => {
    montar();
    expect(screen.getAllByRole('button', { name: /Atualizar dados/ })).toHaveLength(1);
  });
});
