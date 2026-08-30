// @vitest-environment jsdom
/**
 * A CAIXA, O DIFF E O PORTÃO.
 *
 * As provas que importam:
 *
 *  - `leitura: null` (não apurei) e `propostas: []` (apurei e não há) NÃO
 *    produzem a mesma tela. Achatá-las manda o operador embora achando que está
 *    tudo bem quando ninguém olhou;
 *  - `antes: null` no diff aparece como travessão. `0 → 50` lê-se como "passa a
 *    gastar"; `— → 50` lê-se como "não sei quanto gasta hoje", que é o que
 *    autoriza perguntar em vez de aprovar;
 *  - ação indisponível explica a dependência REAL, em uma frase. Nunca cinza mudo;
 *  - o portão guarda quem, quando e O QUÊ — e diz quando o "o quê" falta.
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { derivarDiagnostico } from '@/lib/diagnostico/derivar';
import { evidenciaDeProva, ID_FGTS, ID_MAQUININHA } from '@/lib/diagnostico/fixtureDeEvidencia';
import { proporMudancas } from '@/lib/diagnostico/propor';
import type { Aprovacao, CaixaDePropostas as Contrato } from '@/types/diagnostico';
import { PropostaDeAcao } from '@/components/trafego/hub/PropostaDeAcao';

import { CaixaDePropostas } from '../CaixaDePropostas';

const AGORA = new Date('2026-08-26T18:10:11.000Z');
const caixaDe = (id: string, opcoes = {}) =>
  proporMudancas(derivarDiagnostico(evidenciaDeProva(opcoes), id, { agora: AGORA }));

afterEach(cleanup);

describe('⚠️ "não apurei" e "não há" são duas telas', () => {
  it('sem leitura, a tela diz que ninguém olhou', () => {
    const caixa: Contrato = { ...caixaDe(ID_FGTS), leitura: null, propostas: [] };
    render(<CaixaDePropostas caixa={caixa} />);
    expect(screen.getByRole('heading', { name: /Não foi possível apurar propostas/ })).toBeTruthy();
    expect(screen.getByText(/Fila vazia aqui significa que\s+ninguém olhou/)).toBeTruthy();
  });

  it('com leitura e lista vazia, a tela diz que é um fato medido', () => {
    const caixa = caixaDe(ID_FGTS, { perdaPorVerba: 0.02 });
    expect(caixa.propostas).toEqual([]);
    render(<CaixaDePropostas caixa={caixa} />);
    expect(screen.getByRole('heading', { name: /Nenhuma mudança recomendada/ })).toBeTruthy();
    expect(screen.getByText(/Isto é um fato medido, não uma fila\s+que não carregou/)).toBeTruthy();
  });
});

describe('cada linha carrega origem, confiança, janela e amostra', () => {
  it('a proposta de verba mostra de onde veio e sobre que janela', () => {
    render(<CaixaDePropostas caixa={caixaDe(ID_FGTS)} />);
    expect(screen.getByText(/veio do degrau orçamento · .*últimos 30 dias/)).toBeTruthy();
  });

  /**
   * ⚠️ A regressão que este teste guarda, e que ele mesmo provava antes.
   *
   * `subir-verba` nasce com `confianca: 'alta'` E `amostra.insuficiente: true`.
   * A versão anterior deste teste afirmava `getByText('confiança alta')` na
   * linha FECHADA — e passava, porque o chip dizia exatamente isso, com a
   * descrição "a evidência sustenta esta mudança sozinha, com amostra
   * suficiente". A ressalva contrária só existia dentro da linha ABERTA.
   *
   * O operador que varre a fila lia "confiança alta", aprovava sem expandir, e
   * nunca via o desmentido — na proposta que AUMENTA gasto. Confiança e amostra
   * são dois eixos, e o chip fechado precisa carregar os dois.
   */
  it('confiança alta com amostra curta não se apresenta como suficiente', () => {
    render(<CaixaDePropostas caixa={caixaDe(ID_FGTS)} />);
    expect(screen.queryByText('confiança alta')).toBeNull();
    const chip = screen.getByText(/confiança alta, amostra curta/);
    expect(chip).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/com amostra suficiente/);
  });

  it('amostra insuficiente é dita, e a proposta continua na fila', () => {
    render(<CaixaDePropostas caixa={caixaDe(ID_FGTS)} abertoInicial="subir-verba" />);
    expect(
      screen.getByText(/A amostra não sustenta esta recomendação sozinha/),
    ).toBeTruthy();
  });

  it('amostra não apurada não vira zero', () => {
    render(<CaixaDePropostas caixa={caixaDe(ID_MAQUININHA)} />);
    expect(screen.getByText(/amostra não apurada/)).toBeTruthy();
  });
});

describe('o diff', () => {
  it('mostra antes e depois em colunas alinhadas, com o que NÃO muda declarado', () => {
    render(<CaixaDePropostas caixa={caixaDe(ID_MAQUININHA)} abertoInicial="ligar-campanha" />);
    const tabela = screen.getByRole('table');
    expect(within(tabela).getByText('PAUSED')).toBeTruthy();
    expect(within(tabela).getByText('ENABLED')).toBeTruthy();
    expect(screen.getByText(/não muda: orçamento, lance, keywords, anúncios/)).toBeTruthy();
  });

  it('⚠️ `depois` ainda não digitado aparece como travessão, nunca como zero', () => {
    render(<CaixaDePropostas caixa={caixaDe(ID_FGTS)} abertoInicial="subir-verba" />);
    const tabela = screen.getByRole('table');
    expect(within(tabela).getAllByText('—').length).toBeGreaterThan(0);
    expect(within(tabela).queryByText('R$ 0,00')).toBeNull();
  });

  it('gasto não estimado é dito com todas as letras', () => {
    render(<CaixaDePropostas caixa={caixaDe(ID_FGTS)} abertoInicial="subir-verba" />);
    expect(
      screen.getByText(/efeito no gasto diário não estimado/),
    ).toBeTruthy();
  });
});

describe('ação indisponível explica a dependência real', () => {
  it('o botão diz "indisponível nesta tela" e a frase acima diz por quê', () => {
    render(<CaixaDePropostas caixa={caixaDe(ID_FGTS)} abertoInicial="subir-verba" />);
    expect(
      screen.getByText(/passa por um endereço privilegiado que ainda não está ligado/),
    ).toBeTruthy();
    expect(screen.getByText('depende de um endereço seguro que ainda não está ligado.')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'indisponível nesta tela' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('proposta liberada com quem submeta oferece o gesto — e ele NÃO escreve na conta', () => {
    const caixa = caixaDe(ID_FGTS);
    const liberada = {
      ...caixa,
      propostas: caixa.propostas.map((p) => ({ ...p, bloqueio: null })),
    };
    const aoSubmeter = vi.fn();
    render(
      <CaixaDePropostas caixa={liberada} abertoInicial="subir-verba" aoSubmeter={aoSubmeter} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'submeter para aprovação' }));
    expect(aoSubmeter).toHaveBeenCalledTimes(1);
    expect(aoSubmeter.mock.calls[0][0].id).toBe('subir-verba');
  });

  it('sem quem aprove, o botão diz que aguarda — e não fica cinza sem palavra', () => {
    const caixa = caixaDe(ID_FGTS);
    const liberada = {
      ...caixa,
      propostas: caixa.propostas.map((p) => ({ ...p, bloqueio: null })),
    };
    render(<CaixaDePropostas caixa={liberada} abertoInicial="subir-verba" />);
    expect(screen.getByRole('button', { name: 'aguardando quem aprova' })).toBeTruthy();
  });
});

describe('o portão de aprovação guarda quem, quando e o quê', () => {
  const aprovada: Aprovacao = {
    estado: 'aprovada',
    por: 'tarcisio@agenciavolc.com.br',
    em: '2026-08-26T14:02:00.000Z',
    impressao: 'b468513e616f020f8156ff680f7a669887de58f4e6d5550252965817f39e302e',
    motivo: 'demanda comprovada e verba do mês disponível',
    vale_ate: null,
  };

  it('mostra os três, e a impressão é o "o quê"', () => {
    render(<PropostaDeAcao acao="orcamento" aprovacao={aprovada} />);
    expect(screen.getByText('aprovada')).toBeTruthy();
    expect(screen.getByText('tarcisio@agenciavolc.com.br')).toBeTruthy();
    expect(screen.getByText('o que foi aprovado')).toBeTruthy();
    expect(screen.getByText(/b468513e616f/)).toBeTruthy();
  });

  it('⚠️ aprovação SEM impressão é denunciada — "aprovado" sem objeto não prova nada', () => {
    render(<PropostaDeAcao acao="orcamento" aprovacao={{ ...aprovada, impressao: null }} />);
    expect(
      screen.getByText(/Sem ela não dá para\s+provar que o que sair é o que foi autorizado/),
    ).toBeTruthy();
  });

  it('estado de aprovação desconhecido não vira "aprovada"', () => {
    render(
      <PropostaDeAcao
        acao="orcamento"
        aprovacao={{ ...aprovada, estado: 'carimbada' as Aprovacao['estado'] }}
      />,
    );
    expect(screen.getByText('estado de aprovação não reconhecido')).toBeTruthy();
    expect(screen.queryByText('aprovada')).toBeNull();
  });

  it('quem e quando ausentes aparecem como travessão', () => {
    render(
      <PropostaDeAcao
        acao="orcamento"
        aprovacao={{ ...aprovada, estado: 'aguardando', por: null, em: null }}
      />,
    );
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(2);
  });
});

describe('compatibilidade com a chamada antiga', () => {
  it('`antes`/`depois` soltos continuam funcionando, e o botão segue indisponível', () => {
    render(<PropostaDeAcao acao="lance" antes="R$ 2,50" depois="R$ 3,20" />);
    expect(screen.getByText('R$ 2,50')).toBeTruthy();
    expect(screen.getByText('R$ 3,20')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'indisponível nesta tela' })).toBeTruthy();
  });
});
