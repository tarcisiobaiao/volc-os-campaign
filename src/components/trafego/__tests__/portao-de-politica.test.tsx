// @vitest-environment jsdom
/**
 * Provas do portão de política.
 *
 * O que estas provas protegem é a honestidade da tela numa decisão que tem
 * consequência fora do sistema: declarar a vertical errada não engana o Google,
 * troca "barrado antes de gastar" por "reprovado depois de veicular".
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PortaoDePolitica } from '../PortaoDePolitica';
import type { VerticalDePolitica } from '@/types/trafego';

afterEach(cleanup);

const VERTICAIS: VerticalDePolitica[] = [
  { id: 'informativo', titulo: 'Informativo',
    descricao: 'O site explica e compara. Não presta o serviço.',
    exige: null, severidade: null, paises_exigem: [] },
  { id: 'financeiro', titulo: 'Financeiro',
    descricao: 'Verificação obrigatória por PAÍS de segmentação.',
    exige: 'verificacao_servicos_financeiros', severidade: 'bloqueio',
    paises_exigem: ['BR', 'MX'] },
  { id: 'governo_documentos', titulo: 'Governo documentos',
    descricao: 'Sem certificação o anúncio fica FULLY_LIMITED.',
    exige: 'certificacao_servicos_oficiais', severidade: 'limitacao',
    paises_exigem: ['BR'] },
];

const montar = (props: Partial<React.ComponentProps<typeof PortaoDePolitica>> = {}) =>
  render(
    <PortaoDePolitica
      verticais={VERTICAIS} escolhida="financeiro" onEscolher={vi.fn()}
      certificacoes={[]} onCertificacoes={vi.fn()}
      pais="BR" sugeridaPelaEntidade="financeiro"
      {...props}
    />,
  );

describe('PortaoDePolitica', () => {
  it('barra quando a vertical exige habilitação e a conta não a declara', () => {
    montar();
    expect(screen.getByText(/O lançamento está barrado/)).toBeTruthy();
  });

  it('libera ao trocar para a vertical sem portão', () => {
    montar({ escolhida: 'informativo' });
    expect(screen.queryByText(/O lançamento está barrado/)).toBeNull();
    expect(screen.getByText(/Sem portão de habilitação em BR/)).toBeTruthy();
  });

  it('libera ao declarar a certificação que a conta tem', () => {
    montar({ certificacoes: ['verificacao_servicos_financeiros'] });
    expect(screen.queryByText(/O lançamento está barrado/)).toBeNull();
  });

  it('avisa que declarar sem ter só adia a reprovação — não engana o Google', () => {
    montar();
    expect(screen.getByText(/não engana o Google/)).toBeTruthy();
  });

  it('distingue limitação de bloqueio: governo_documentos sobe, mas limitado', () => {
    montar({ escolhida: 'governo_documentos' });
    expect(screen.queryByText(/O lançamento está barrado/)).toBeNull();
    expect(screen.getByText(/APPROVED_LIMITED/)).toBeTruthy();
  });

  it('o portão é por PAÍS — a mesma vertical não barra onde não é exigida', () => {
    // `financeiro` exige em BR e MX; em CL não está na lista.
    montar({ pais: 'CL' });
    expect(screen.queryByText(/O lançamento está barrado/)).toBeNull();
    expect(screen.getByText(/Sem portão de habilitação em CL/)).toBeTruthy();
  });

  it('registra a divergência entre o que a entidade disse e o que foi marcado', () => {
    montar({ escolhida: 'informativo', sugeridaPelaEntidade: 'financeiro' });
    expect(screen.getByText(/A entidade classificou como/)).toBeTruthy();
  });

  it('não acusa divergência quando o operador mantém o que a entidade disse', () => {
    montar();
    expect(screen.queryByText(/A entidade classificou como/)).toBeNull();
  });

  it('escolher uma vertical avisa quem controla o estado', () => {
    const onEscolher = vi.fn();
    montar({ onEscolher });
    fireEvent.click(screen.getByRole('button', { name: /Informativo/ }));
    expect(onEscolher).toHaveBeenCalledWith('informativo');
  });

  it('marcar a certificação adiciona à lista sem duplicar', () => {
    const onCertificacoes = vi.fn();
    montar({ onCertificacoes });
    fireEvent.click(screen.getByRole('checkbox'));
    expect(onCertificacoes).toHaveBeenCalledWith(['verificacao_servicos_financeiros']);
  });
});
