// @vitest-environment jsdom
/**
 * O recibo PERMANECE, e ele nunca oferece reenvio.
 *
 * ## O defeito que estes testes trancam
 *
 * Até 03/09/2026 o recibo era `useState` do modal de Ignição
 * (`Lancamento.tsx:93`), e `onFechar` fazia `setLancando(false)` — o que
 * DESMONTA o componente e joga tudo fora. O único dado que sobrevivia era o id
 * da campanha, e ele só servia para montar o veredito de política.
 *
 * Quem fechasse a escada por reflexo perdia `request_id`, `recibo_id`,
 * `item_id`, a impressão do plano e o motivo declarado — exatamente o conjunto
 * de que se precisa quando o desfecho é `indeterminado` e a única saída é
 * reconciliar por identidade. E havia uma segunda superfície de recibo já
 * escrita, mais completa que a do modal (`CartaoDeRecibo.tsx` mostra "motivo
 * declarado" e "impressão do pedido"), sem nenhum consumidor de produção.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { ReciboDaBancada, desfechoDoRecibo } from '../ReciboDaBancada';
import type { ReciboDeLancamento } from '@/types/trafego';

afterEach(() => cleanup());

const base = (over: Partial<ReciboDeLancamento> = {}): ReciboDeLancamento => ({
  estado: 'ACEITO',
  carimbo: '20260903_120000',
  customer_id: '8017851692',
  login_customer_id: '6016739364',
  nome_campanha: 'FORGE · Cartão',
  n_operacoes: 72,
  impressao: 'f'.repeat(64),
  motivo: 'canário na conta da casa',
  criados: [{ posicao: 0, tipo: 'campaign', resource_name: 'customers/8017851692/campaigns/24155134757' }],
  request_id: 'req-abc-123',
  falha: null,
  explicacao: '',
  ...over,
} as ReciboDeLancamento);

describe('o desfecho é LIDO do ledger, nunca inferido da demora', () => {
  it('sem registro no ledger o desfecho é "não sei se criou", não "criada"', () => {
    // ⚠️ Fail-closed. "Não sei" é mais barato que um "criada" otimista sobre uma
    // campanha que talvez não exista — o segundo faz o operador parar de
    // procurar.
    expect(desfechoDoRecibo(base())).toBe('sem_resposta');
    expect(desfechoDoRecibo(base({ ledger: { registrado: false } }))).toBe('sem_resposta');
  });

  it('cada desfecho do ledger tem o seu, e eles não se misturam', () => {
    expect(desfechoDoRecibo(base({ ledger: { registrado: true, desfecho: 'sucesso' } }))).toBe('sucesso');
    expect(desfechoDoRecibo(base({ ledger: { registrado: true, desfecho: 'erro' } }))).toBe('erro');
    expect(desfechoDoRecibo(base({ ledger: { registrado: true, desfecho: 'em_voo' } }))).toBe('em_voo');
    expect(desfechoDoRecibo(base({ ledger: { registrado: true, desfecho: 'sem_resposta' } }))).toBe('sem_resposta');
  });
});

describe('o recibo na página', () => {
  it('no sucesso, diz PAUSED literalmente e mostra o id copiável inteiro', () => {
    render(<ReciboDaBancada
      canal="SEARCH" podeReconciliar={false}
      recibo={base({ ledger: { registrado: true, desfecho: 'sucesso', id_externo: '24155134757' } })}
    />);
    expect(screen.getByText('criada, pausada')).toBeTruthy();
    expect(screen.getByText('PAUSED')).toBeTruthy();
    // ⚠️ O id vai INTEIRO. Um id truncado parece um id e não é — quem for
    // conferir na conta precisa do valor completo.
    //
    // `getAllBy…` porque o cartão completo, recolhido em `<details>`, continua
    // no DOM e repete o valor. A grade de cima é a que o torna COPIÁVEL, e é
    // isso que o botão abaixo prova.
    expect(screen.getAllByText('24155134757').length).toBeGreaterThan(0);
    expect(screen.getAllByText('req-abc-123').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /copiar id da campanha na conta/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /copiar request id/ })).toBeTruthy();
  });

  it('PAUSED NÃO é afirmado num desfecho que ninguém leu', () => {
    // Escrever "PAUSED" num recibo indeterminado seria afirmar um estado que
    // ninguém observou — e é o estado que decide se dinheiro sai ou não.
    render(<ReciboDaBancada
      canal="SEARCH" podeReconciliar={false}
      recibo={base({ ledger: { registrado: true, desfecho: 'em_voo', item_id: 'it-1' } })}
    />);
    expect(screen.queryByText('PAUSED')).toBeNull();
    expect(screen.getByText('em voo')).toBeTruthy();
  });

  it('NUNCA oferece reenvio, em desfecho nenhum', () => {
    // ⚠️ Uma chamada pode estar a caminho, e a segunda criaria a campanha duas
    // vezes no mesmo leilão. É a mesma doutrina de `proximoAtoSeguro`.
    for (const desfecho of ['sucesso', 'erro', 'em_voo', 'sem_resposta'] as const) {
      cleanup();
      render(<ReciboDaBancada
        canal="SEARCH" podeReconciliar
        onReconciliar={() => {}}
        recibo={base({ ledger: { registrado: true, desfecho, item_id: 'it-1' } })}
      />);
      expect(screen.queryByRole('button', { name: /reenviar|tentar de novo|enviar de novo/i })).toBeNull();
    }
  });

  it('quando reconciliar exige admin, diz QUEM pode — não some com a saída', () => {
    // ⚠️ `POST /reconciliar` exige admin enquanto o resto exige só usuário: o
    // operador não fecha o próprio recibo. Esconder o fato deixaria alguém
    // esperando por um botão que nunca vai aparecer.
    render(<ReciboDaBancada
      canal="SEARCH" podeReconciliar={false}
      recibo={base({ ledger: { registrado: true, desfecho: 'em_voo', item_id: 'it-1' } })}
    />);
    expect(screen.getByText(/exige perfil de administrador/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Reconciliar na conta' })).toBeNull();
  });

  it('com permissão, o botão de reconciliar aparece — e a frase explica o que ele faz', () => {
    render(<ReciboDaBancada
      canal="SEARCH" podeReconciliar onReconciliar={() => {}}
      recibo={base({ ledger: { registrado: true, desfecho: 'em_voo', item_id: 'it-1' } })}
    />);
    expect(screen.getByRole('button', { name: 'Reconciliar na conta' })).toBeTruthy();
    expect(screen.getByText(/Ela não reenvia o pedido/)).toBeTruthy();
  });

  it('a região é retornável por âncora — o recibo não é estado de modal', () => {
    const { container } = render(<ReciboDaBancada
      canal="SEARCH" podeReconciliar={false}
      recibo={base({ ledger: { registrado: true, desfecho: 'sucesso', id_externo: '2' } })}
    />);
    expect(container.querySelector('#recibo')).toBeTruthy();
  });

  it('identificador ausente vira "não declarado", nunca vazio nem zero', () => {
    render(<ReciboDaBancada
      canal="SEARCH" podeReconciliar={false}
      recibo={base({ request_id: '', ledger: { registrado: true, desfecho: 'sucesso' } })}
    />);
    expect(screen.getAllByText('não declarado').length).toBeGreaterThan(0);
  });
});
