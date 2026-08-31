import { describe, expect, it } from 'vitest';

import {
  idDoResourceName, idExternoDaCampanha, indeterminacaoDeclarada, proximoAtoSeguro,
  recusaDeclarada,
} from '@/lib/trafego/lancamento';
import type { ReciboDeLancamento } from '@/types/trafego';

const recibo = (extra: Partial<ReciboDeLancamento> = {}): ReciboDeLancamento => ({
  estado: 'CRIADA', carimbo: '20260831_120000',
  customer_id: '5478096539', login_customer_id: '6016739364',
  nome_campanha: 'VOLC-CANARY-abc', n_operacoes: 72, impressao: 'a'.repeat(64),
  motivo: 'canário pausado', criados: [], request_id: 'req-1',
  falha: null, explicacao: '', ...extra,
});

describe('indeterminacaoDeclarada', () => {
  it('reconhece o 504 estruturado que o /subir devolve quando a resposta se perde', () => {
    const lido = indeterminacaoDeclarada({
      status: 504,
      corpo: {
        estado: 'indeterminado',
        mensagem: 'A chamada de criação não teve resposta.',
        recibo_id: 'recibo-1', item_id: 'item-1', reenvio_permitido: false,
      },
    });
    expect(lido).not.toBeNull();
    expect(lido!.reenvio_permitido).toBe(false);
    expect(lido!.recibo_id).toBe('recibo-1');
  });

  it('aceita `reenvio_permitido: false` mesmo sem o rótulo de estado', () => {
    // A trava é o campo que PROÍBE, não o rótulo que descreve. Depender só do
    // rótulo faria uma renomeação futura reabrir o caminho de reenvio.
    expect(indeterminacaoDeclarada({ corpo: { reenvio_permitido: false } })).not.toBeNull();
  });

  it('não inventa indeterminação a partir de um 409 comum', () => {
    expect(indeterminacaoDeclarada({ status: 409, corpo: { mensagem: 'não passou na prova' } }))
      .toBeNull();
  });

  it('não inventa indeterminação a partir de um erro sem corpo', () => {
    expect(indeterminacaoDeclarada(new Error('caiu a rede'))).toBeNull();
    expect(indeterminacaoDeclarada(undefined)).toBeNull();
  });

  it('preserva ausência de mensagem como string vazia, não como texto inventado', () => {
    const lido = indeterminacaoDeclarada({ corpo: { estado: 'indeterminado' } });
    expect(lido!.mensagem).toBe('');
    expect(lido!.recibo_id).toBeNull();
  });
});

describe('idExternoDaCampanha', () => {
  it('prefere o id carimbado pelo ledger', () => {
    expect(idExternoDaCampanha(recibo({
      ledger: { registrado: true, desfecho: 'sucesso', id_externo: '24183717006' },
      criados: [{ posicao: 0, tipo: 'campaign_result',
                  resource_name: 'customers/5478096539/campaigns/99999999999' }],
    }))).toBe('24183717006');
  });

  it('cai para o resource_name quando o ledger não estava disponível', () => {
    expect(idExternoDaCampanha(recibo({
      ledger: { registrado: false, motivo: 'ledger indisponível' },
      criados: [{ posicao: 0, tipo: 'campaign_result',
                  resource_name: 'customers/5478096539/campaigns/24183717006' }],
    }))).toBe('24183717006');
  });

  it('NÃO lê `campaign_id`, que a projeção do recibo nunca produziu', () => {
    // Este é o defeito que o tipo largo escondia: a leitura antiga procurava uma
    // chave inexistente e devolvia `undefined` para sempre, em silêncio.
    const comChaveFantasma = {
      ...recibo({ criados: [{ posicao: 0, tipo: 'campaign_result',
                              resource_name: 'customers/1/campaigns/777' }] }),
      campaign_id: '111',
    } as unknown as ReciboDeLancamento;
    expect(idExternoDaCampanha(comChaveFantasma)).toBe('777');
  });

  it('devolve vazio quando não há id — e vazio não é "não criou"', () => {
    expect(idExternoDaCampanha(recibo())).toBe('');
    expect(idExternoDaCampanha(null)).toBe('');
  });

  it('ignora recursos que não são campanha', () => {
    expect(idDoResourceName([
      { posicao: 0, tipo: 'budget_result',
        resource_name: 'customers/1/campaignBudgets/55' },
      { posicao: 1, tipo: 'campaign_result',
        resource_name: 'customers/1/campaigns/24183717006' },
    ])).toBe('24183717006');
  });
});

describe('proximoAtoSeguro', () => {
  it('sucesso com id carimbado libera conferir a política', () => {
    expect(proximoAtoSeguro(recibo({
      ledger: { registrado: true, desfecho: 'sucesso', id_externo: '24183717006' },
    }))).toBe('conferir_politica');
  });

  it('falha CONFIRMADA pela plataforma permite corrigir e reenviar', () => {
    expect(proximoAtoSeguro(recibo({
      ledger: { registrado: true, desfecho: 'erro' },
    }))).toBe('corrigir_e_reenviar');
  });

  it.each([
    ['sem_resposta', { registrado: true, desfecho: 'sem_resposta' as const }],
    ['em_voo', { registrado: true, desfecho: 'em_voo' as const }],
    ['sucesso sem id carimbado', { registrado: true, desfecho: 'sucesso' as const }],
    ['sem registro nenhum', { registrado: false }],
  ])('ignorância (%s) NUNCA vira reenvio', (_rotulo, ledger) => {
    expect(proximoAtoSeguro(recibo({ ledger }))).toBe('reconciliar_na_conta');
  });

  it('recibo ausente é ignorância, não sucesso', () => {
    expect(proximoAtoSeguro(null)).toBe('reconciliar_na_conta');
  });
});

describe('recusaDeclarada', () => {
  // ⚠️ O 502 estruturado nasceu em 31/08/2026, quando `/subir` passou a ler
  // `recibo.estado`. Antes disso uma recusa RESPONDIDA pelo Google chegava aqui
  // como 200 dizendo que a campanha existia. Agora ela chega com identidade e
  // motivo, e a tela precisa distinguir isso de "não deu para concluir".
  it('reconhece o 502 estruturado de uma recusa respondida', () => {
    const lido = recusaDeclarada({
      status: 502,
      corpo: {
        estado: 'recusado',
        mensagem: 'headline excede 30 caracteres',
        erro_codigo: 'AdError.HEADLINE_TOO_LONG',
        request_id: 'req-1', recibo_id: 'recibo-1', item_id: 'item-1',
        reenvio_permitido: true,
      },
    });
    expect(lido).not.toBeNull();
    expect(lido!.reenvio_permitido).toBe(true);
    expect(lido!.erro_codigo).toBe('AdError.HEADLINE_TOO_LONG');
    expect(lido!.recibo_id).toBe('recibo-1');
  });

  it('não confunde recusa com indeterminação — elas têm saídas opostas', () => {
    const indeterminado = {
      status: 504,
      corpo: { estado: 'indeterminado', reenvio_permitido: false,
               recibo_id: 'r-1', item_id: 'i-1', mensagem: 'sem resposta' },
    };
    expect(recusaDeclarada(indeterminado)).toBeNull();
    expect(indeterminacaoDeclarada(indeterminado)).not.toBeNull();
  });

  it('e a recusa não é lida como indeterminação pelo caminho inverso', () => {
    const recusado = {
      status: 502,
      corpo: { estado: 'recusado', reenvio_permitido: true,
               recibo_id: 'r-1', item_id: 'i-1', mensagem: 'recusado' },
    };
    expect(indeterminacaoDeclarada(recusado)).toBeNull();
    expect(recusaDeclarada(recusado)).not.toBeNull();
  });

  it('não inventa recusa a partir de um erro sem corpo', () => {
    expect(recusaDeclarada(new Error('caiu a rede'))).toBeNull();
    expect(recusaDeclarada(undefined)).toBeNull();
    expect(recusaDeclarada({ status: 409, corpo: { mensagem: 'não passou' } })).toBeNull();
  });

  it('nunca deixa `reenvio_permitido` virar true por omissão', () => {
    // Se o servidor não disse que pode reenviar, a tela não pode supor que pode.
    const lido = recusaDeclarada({ corpo: { estado: 'recusado' } });
    expect(lido!.reenvio_permitido).toBe(false);
  });
});
