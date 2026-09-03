// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';

// Sem arquivo de setup global no projeto, a limpeza é explícita: sem ela cada
// render acumula no body e `getByText` acha o elemento do teste anterior.
afterEach(cleanup);
import { TeseDaOportunidade } from '../TeseDaOportunidade';
import { ComparadorDeOportunidades } from '../ComparadorDeOportunidades';
import type { TeseDeOportunidade, TesesResposta } from '@/types/pautadorOportunidade';

const tese = (over: Partial<TeseDeOportunidade> = {}): TeseDeOportunidade => ({
  opportunity_id: 1,
  tema: 'FGTS',
  decisao: 'aprofundar',
  porque: 'Ramifica de verdade.',
  versao_do_contrato: 'oportunidade/1',
  formato_de_funil: 'ferramenta_de_elegibilidade',
  observaveis_do_formato: ['max condicoes_pessoais 3', 'max ramos_de_acao 3'],
  fatos: ['volume (demanda medida): alto — medido por sensor'],
  hipoteses: [],
  desconhecidos: [],
  contradicoes: [],
  proximo_experimento: null,
  indice_citado: 0.72,
  cobertura: 1.0,
  perfil_citado: 'alvo',
  comparavel: true,
  motivo_incomparavel: null,
  ...over,
});

describe('TeseDaOportunidade', () => {
  it('nunca mostra a decisão só por cor: há glifo e palavra', () => {
    render(<TeseDaOportunidade tese={tese()} />);
    expect(screen.getByText('Aprofundar')).toBeTruthy();
  });

  it('o formato cita os observáveis que o produziram, com número', () => {
    render(<TeseDaOportunidade tese={tese()} />);
    expect(screen.getByText('Ferramenta de elegibilidade')).toBeTruthy();
    expect(screen.getByText('max ramos_de_acao 3')).toBeTruthy();
  });

  it('fato, hipótese e desconhecido ficam em blocos SEPARADOS e visíveis', () => {
    render(<TeseDaOportunidade tese={tese({
      fatos: ['volume: alto — medido por sensor'],
      hipoteses: ['[prior webgo/x · confiança baixa] algo'],
      desconhecidos: ['vacuo: não medido — sem_trafego'],
    })} />);
    // os três títulos coexistem: nada está atrás de aba, acordeão ou tooltip
    expect(screen.getByText('Fatos')).toBeTruthy();
    expect(screen.getByText('Hipóteses')).toBeTruthy();
    expect(screen.getByText('Desconhecidos')).toBeTruthy();
  });

  it('desconhecido NUNCA é renderizado como zero', () => {
    render(<TeseDaOportunidade tese={tese({
      desconhecidos: ['volume (demanda medida): não medido — sem_credencial_dataforseo'],
    })} />);
    const bloco = screen.getByText('Desconhecidos').closest('section')!;
    expect(within(bloco).getByText(/não medido/)).toBeTruthy();
    expect(within(bloco).queryByText(/^0$/)).toBeNull();
  });

  it('contradição aparece e diz que ninguém resolveu', () => {
    render(<TeseDaOportunidade tese={tese({
      contradicoes: ['o resumo diz apto=true mas há portão disparado: engajamento'],
    })} />);
    expect(screen.getByText('Contradições')).toBeTruthy();
    expect(screen.getByText(/portão disparado/)).toBeTruthy();
  });

  it('declara que cita a medição em vez de recalculá-la', () => {
    render(<TeseDaOportunidade tese={tese()} />);
    expect(screen.getByText(/derivado do que já foi medido/)).toBeTruthy();
  });

  it('card nunca medido não vira veredito sobre o tema', () => {
    render(<TeseDaOportunidade tese={tese({
      decisao: 'sem_validacao', formato_de_funil: null, observaveis_do_formato: [],
      fatos: [], indice_citado: null, cobertura: null, comparavel: false,
      motivo_incomparavel: 'sem medição registrada',
      porque: 'Este card não passou pela coluna de validação.',
    })} />);
    expect(screen.getByText('Nunca medido')).toBeTruthy();
  });

  it('ausente não é o mesmo que tese ausente: sem tese, não renderiza nada', () => {
    const { container } = render(<TeseDaOportunidade tese={null} />);
    expect(container.innerHTML).toBe('');
  });
});

describe('ComparadorDeOportunidades', () => {
  const dados = (over: Partial<TesesResposta> = {}): TesesResposta => ({
    teses: [], total: 2,
    ranking: [tese({ opportunity_id: 1, tema: 'boa' })],
    fora_do_ranking: [tese({
      opportunity_id: 2, tema: 'magra', decisao: 'retido',
      comparavel: false, cobertura: 0.2,
      motivo_incomparavel: 'cobertura 0.2 abaixo do mínimo 0.5',
    })],
    ...over,
  });

  it('é uma TABELA, não uma grade de cartões', () => {
    render(<ComparadorDeOportunidades dados={dados()} />);
    expect(screen.getAllByRole('table').length).toBeGreaterThan(0);
  });

  it('card sem cobertura NÃO some da tela e traz o motivo', () => {
    render(<ComparadorDeOportunidades dados={dados()} />);
    expect(screen.getByText('magra')).toBeTruthy();
    expect(screen.getByText(/abaixo do mínimo/)).toBeTruthy();
  });

  it('o incomparável não entra no ranking ordenado', () => {
    render(<ComparadorDeOportunidades dados={dados()} />);
    const ranking = screen.getAllByRole('table')[0];
    expect(within(ranking).getByText('boa')).toBeTruthy();
    expect(within(ranking).queryByText('magra')).toBeNull();
  });

  it('não inventa coluna de nota: não existe cabeçalho "score"', () => {
    render(<ComparadorDeOportunidades dados={dados()} />);
    expect(screen.queryByText(/score/i)).toBeNull();
  });

  it('a linha é acionável por teclado e expõe papel e estado', () => {
    const onSelecionar = vi.fn();
    render(<ComparadorDeOportunidades dados={dados()} onSelecionar={onSelecionar} />);
    const linha = screen.getByText('boa').closest('tr')!;
    expect(linha.getAttribute('tabindex')).toBe('0');
    expect(linha.getAttribute('role')).toBe('button');
    fireEvent.keyDown(linha, { key: 'Enter' });
    expect(onSelecionar).toHaveBeenCalledWith(expect.objectContaining({ tema: 'boa' }));
    fireEvent.keyDown(linha, { key: ' ' });
    expect(onSelecionar).toHaveBeenCalledTimes(2);
  });

  it('falha de leitura não apaga o que estava na tela sem avisar', () => {
    render(<ComparadorDeOportunidades dados={null} erro="timeout" />);
    expect(screen.getByText(/pode estar desatualizado/)).toBeTruthy();
  });

  it('vazio ensina o que fazer em vez de dizer "nada aqui"', () => {
    render(<ComparadorDeOportunidades dados={{ teses: [], ranking: [], fora_do_ranking: [], total: 0 }} />);
    expect(screen.getByText(/Arraste cards para/)).toBeTruthy();
  });
});
