// @vitest-environment jsdom
/**
 * A PROJEÇÃO DE ATENÇÃO, sintoma por sintoma — e o que ela recusa contar.
 *
 * Esta é a prova que impede duas telas de discordarem sobre o mesmo fato: o
 * sino e a aba Atenção consomem a MESMA função, e o que está travado aqui é o
 * que as duas dizem.
 *
 * Três regras atravessam o arquivo inteiro:
 *
 *  A. **indisponibilidade não é condição.** "Não consegui perguntar" e
 *     "perguntei e há três problemas" levam a ações opostas, e por isso a conta
 *     que não pôde ser lida sai do contador e entra numa lista própria.
 *  B. **sem vínculo e sem procedência não pedem atenção.** São verdade sobre
 *     quase todo o registro no primeiro dia; um sino que acende para tudo é um
 *     sino que ninguém lê na segunda semana.
 *  C. **uma campanha aparece UMA vez**, sob o sintoma que pede a ação mais
 *     urgente das que valem para ela.
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { LeituraDoInventario } from '@/hooks/useInventario';
import type { QuadroDeAlertas } from '@/types/trafego';

import { FilaDeAtencao } from '@/components/trafego/inventario/FilaDeAtencao';
import {
  SINTOMAS,
  motivoOperacional,
  projetarAtencao,
  sintomaDaCampanha,
  urlNoGoogleAds,
  DECISOES_SEM_SENSOR,
  FAMILIAS,
  familiaDoSintoma,
} from '@/components/trafego/atencao/projecao';
import {
  SEM_CONTA,
  alertaDaMaquininha,
  alertaDoFgts,
  campanhaDeContaQueFalhou,
  campanhaNaoEncontrada,
  campanhaRemovida,
  campanhaSemContaIdentificada,
  creditoUp,
  fgts,
  fgtsDeTeste,
  inventarioDeAusencias,
  inventarioDeProva,
  inventarioSaudavel,
  maquininha,
  pmundo,
  quadroDeAlertasDeProva,
  semConta,
  campanhaSaudavel,} from '@/components/trafego/inventario/fixtureDeProvas';

// ── dublês, só para as provas de render ─────────────────────────────────────

const leituraBase: LeituraDoInventario = {
  inventario: inventarioSaudavel(),
  carregando: false,
  atualizando: false,
  falhou: false,
  motivoDaFalha: null,
  temMais: false,
  carregandoMais: false,
  carregarMais: vi.fn(),
  recarregar: vi.fn(),
};

let leitura: LeituraDoInventario = leituraBase;
let notificacoes: {
  data: QuadroDeAlertas | null;
  isLoading: boolean;
  isError: boolean;
  isFetching: boolean;
  error: unknown;
  refetch: () => void;
};

vi.mock('@/hooks/useInventario', () => ({
  useInventario: () => leitura,
  usePedirLeituraDaConta: () => ({ pedir: vi.fn(), contaEmLeitura: null, recados: {} }),
}));

vi.mock('@/hooks/useNotificacoes', () => ({
  useNotificacoes: () => notificacoes,
  INTERVALO_NOTIFICACOES_MS: 600_000,
  CHAVE_NOTIFICACOES: ['notificacoes', 'trafego'],
}));

beforeEach(() => {
  leitura = { ...leituraBase, inventario: inventarioSaudavel() };
  notificacoes = {
    data: quadroDeAlertasDeProva(),
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  };
  Object.defineProperty(window, 'innerWidth', { value: 1440, writable: true, configurable: true });
});
afterEach(cleanup);

// ── os sintomas, um a um ────────────────────────────────────────────────────

describe('cada sintoma nomeia o que foi OBSERVADO', () => {
  it('campanha ligada sem entrega vem da varredura, com a ordem de revisão certa', () => {
    const p = projetarAtencao({
      alertas: quadroDeAlertasDeProva({ alertas: [alertaDaMaquininha, alertaDoFgts], contas: [] }),
      inventario: null,
    });
    expect(p.itens).toHaveLength(2);
    expect(p.itens.every((i) => i.sintoma === 'ligada_sem_impressao')).toBe(true);
    // Os dois sintomas de entrega pedem olhares OPOSTOS, e a próxima ação diz
    // isso: lance para quem não entrou no leilão, anúncio para quem entrou.
    expect(SINTOMAS.ligada_sem_impressao.proximaAcao).toMatch(/lance do grupo/);
    expect(SINTOMAS.ligada_sem_clique.proximaAcao).toMatch(/página de destino/);
  });

  it('sincronização falhou é UMA por conta, não uma por campanha no escuro', () => {
    const conta = { ...pmundo, campanhas: [campanhaDeContaQueFalhou], quantidade: 1 };
    const p = projetarAtencao({
      alertas: null,
      inventario: inventarioDeProva({ contas: [conta], faltou: [], parcial: false }),
    });
    const doSintoma = p.itens.filter((i) => i.sintoma === 'sincronizacao_falhou');
    // Quarenta linhas idênticas dizendo "a conta não respondeu" não informam
    // quarenta vezes mais: informam uma vez e escondem os outros sintomas.
    expect(doSintoma).toHaveLength(1);
    expect(doSintoma[0].escopo).toBe('conta');
    expect(doSintoma[0].chave).toBe('3849678045');
    expect(doSintoma[0].evidencia.join(' ')).toMatch(/BR - Consignado INSS/);
  });

  it('leitura desatualizada é da CONTA, e não acusa problema onde só passou tempo', () => {
    const conta = { ...creditoUp, frescor: 'velho' as const };
    const p = projetarAtencao({
      alertas: null,
      inventario: inventarioDeProva({ contas: [conta], faltou: [], parcial: false }),
    });
    const item = p.itens.find((i) => i.sintoma === 'leitura_desatualizada');
    expect(item?.escopo).toBe('conta');
    expect(SINTOMAS.leitura_desatualizada.afirma).toMatch(/nada deu errado/);
  });

  it('removida é acordo e fica fora; não encontrada é divergência e entra', () => {
    const p = projetarAtencao({ alertas: null, inventario: inventarioDeAusencias() });
    const porChave = new Map(p.itens.map((i) => [i.chave, i.sintoma]));

    // ⚠️ `removida` NÃO entra. A conta diz que removeu e nós registramos: é
    // ACORDO, e acordo não se confere. A campanha continua visível no
    // inventário, com o selo na linha — só não vira notificação.
    //
    // Medido em 25/08/2026: das 84 campanhas reais, 79 estavam removidas. Com
    // elas na fila, a aba dizia 53 e a fonte de verdade dizia 2.
    expect(porChave.has('8017851692-24099887766')).toBe(false);

    // `nao_encontrada` entra, e a diferença é exatamente esta: a leitura foi
    // BOA e a campanha não estava lá. Nosso registro e a conta DISCORDAM.
    expect(porChave.get('8017851692-24070001122')).toBe('campanha_nao_encontrada');
    expect(porChave.get(`${SEM_CONTA}-7781`)).toBe('conta_nao_identificada');
    // ⚠️ A Maquininha (…-24155134757) ENTRA, e não é exceção a esta prova: ela
    // está ligada com 1 impressão e ZERO clique, que é sintoma de entrega. Uma
    // campanha viva só fica fora quando é de fato saudável — ver
    // `campanhaSaudavel`, que tem 412 impressões e 9 cliques.
    expect(porChave.get('8017851692-24155134757')).toBe('ligada_sem_impressao');
    expect(sintomaDaCampanha(campanhaSaudavel)).toBeNull();
  });

  it('estado desconhecido cobre tanto a palavra nova quanto o estado não lido', () => {
    expect(
      sintomaDaCampanha({
        ...fgts,
        presenca: 'em_revisao_de_politica' as typeof fgts.presenca,
      }),
    ).toBe('estado_desconhecido');
    expect(sintomaDaCampanha({ ...fgts, estado_externo: null })).toBe('estado_desconhecido');
  });

  it('ligada e sem MEDIDA é diferente de ligada e sem impressão', () => {
    // Uma é "não sei quanto está gastando"; a outra é "medi, e foi zero". Elas
    // pedem coisas opostas: pedir leitura contra revisar lance.
    const semMedida = {
      ...maquininha,
      entrega: { ...maquininha.entrega, leitura: null },
    };
    expect(sintomaDaCampanha(semMedida)).toBe('ligada_sem_medida');
    // A Maquininha MEDIU: 1 impressão, 0 clique. Ela não é "não sei quanto
    // gastou" — é "medi, e não teve clique". Sintoma diferente, ação diferente.
    expect(sintomaDaCampanha(maquininha)).toBe('ligada_sem_impressao');
    // E a saudável, que mediu e foi clicada, não pede nada.
    expect(sintomaDaCampanha(campanhaSaudavel)).toBeNull();
  });

  it('campanha pausada não entra por não entregar — ela não deveria entregar', () => {
    expect(sintomaDaCampanha(fgtsDeTeste)).toBeNull();
  });
});

// ── as três regras ──────────────────────────────────────────────────────────

describe('A · indisponibilidade não é condição ativa', () => {
  it('conta sem leitura sai do contador e entra na lista própria', () => {
    const p = projetarAtencao({
      alertas: quadroDeAlertasDeProva({ alertas: [], contas: [
        { customer_id: '3849678045', nome: 'PMUNDO+', erro: 'a conta não respondeu' },
      ] }),
      inventario: null,
    });
    expect(p.itens).toHaveLength(0);
    expect(p.semLeitura).toHaveLength(1);
    expect(p.semLeitura[0].conta).toBe('PMUNDO+');
  });

  it('o que faltou no inventário também entra ali, sem duplicar a conta', () => {
    const p = projetarAtencao({
      alertas: quadroDeAlertasDeProva({ alertas: [], contas: [
        { customer_id: '3849678045', nome: 'PMUNDO+', erro: 'a conta não respondeu' },
      ] }),
      inventario: inventarioDeProva(),
    });
    expect(p.semLeitura.filter((s) => s.contaId === '3849678045')).toHaveLength(1);
  });
});

describe('B · sem vínculo e sem procedência NÃO pedem atenção', () => {
  it('a campanha sem funil confirmado e sem procedência fica fora da fila', () => {
    // A prova isola a variável: uma campanha SAUDÁVEL (mediu e foi clicada) à
    // qual se tira o vínculo e a procedência continua fora da fila. Se vínculo
    // ou procedência virassem condição, ela apareceria — e no primeiro dia o
    // sino marcaria o registro inteiro, porque quase tudo é assim.
    const saudavelSemVinculo: typeof campanhaSaudavel = {
      ...campanhaSaudavel,
      vinculo: null,
      procedencia: 'desconhecida',
    };
    expect(saudavelSemVinculo.vinculo).toBeNull();
    expect(saudavelSemVinculo.procedencia).toBe('desconhecida');
    expect(sintomaDaCampanha(saudavelSemVinculo)).toBeNull();

    // E o contraste que separa as duas causas: a FGTS também está sem vínculo e
    // sem procedência, mas ENTRA — pelo sintoma de ENTREGA (5 impressões, zero
    // clique), nunca pelo vínculo.
    expect(fgts.vinculo).toBeNull();
    expect(sintomaDaCampanha(fgts)).toBe('ligada_sem_impressao');
  });

  it('e a palavra "sem vínculo" não aparece na fila renderizada', () => {
    leitura = { ...leituraBase, inventario: inventarioSaudavel() };
    render(<FilaDeAtencao foco={null} />);
    expect(screen.queryByText(/sem vínculo/i)).toBeNull();
    expect(screen.queryByText(/sem procedência/i)).toBeNull();
  });
});

describe('C · uma campanha, um item', () => {
  it('a campanha que está na varredura E no inventário aparece uma vez só', () => {
    const p = projetarAtencao({
      alertas: quadroDeAlertasDeProva({ alertas: [alertaDaMaquininha], contas: [] }),
      inventario: inventarioDeProva({
        contas: [{ ...creditoUp, campanhas: [{ ...maquininha, presenca: 'removida' }] }],
        faltou: [],
        parcial: false,
      }),
    });
    const daMaquininha = p.itens.filter((i) => i.chave === '8017851692-24155134757');
    expect(daMaquininha).toHaveLength(1);
    // A varredura mediu o leilão; o inventário só descreve o registro. Quem
    // traz a ordem de revisão pronta ganha.
    expect(daMaquininha[0].sintoma).toBe('ligada_sem_impressao');
  });

  it('a campanha no escuro é contada na conta, e não também sozinha', () => {
    const p = projetarAtencao({
      alertas: null,
      inventario: inventarioDeProva({
        contas: [{ ...pmundo, campanhas: [campanhaDeContaQueFalhou] }],
        faltou: [],
        parcial: false,
      }),
    });
    expect(p.itens).toHaveLength(1);
  });
});

// ── ordem e endereço ────────────────────────────────────────────────────────

describe('a ordem é quanto dinheiro pode estar saindo enquanto ninguém olha', () => {
  it('ligada e sem impressão vem antes de removida e de leitura antiga', () => {
    const p = projetarAtencao({
      alertas: quadroDeAlertasDeProva({ alertas: [alertaDaMaquininha], contas: [] }),
      inventario: inventarioDeProva({
        contas: [
          { ...creditoUp, frescor: 'velho', campanhas: [campanhaRemovida, campanhaNaoEncontrada] },
        ],
        faltou: [],
        parcial: false,
      }),
    });
    // `campanha_removida` saiu da ordem porque saiu da fila: ver o teste
    // "removida é acordo e fica fora" acima.
    expect(p.grupos.map((g) => g.sintoma)).toEqual([
      'ligada_sem_impressao',
      'campanha_nao_encontrada',
      'leitura_desatualizada',
    ]);
  });
});

describe('o endereço externo só existe quando há conta em que procurar', () => {
  it('linha sem conta utilizável não ganha link para o Google Ads', () => {
    // Um link que abre a conta errada é pior que link nenhum: o operador
    // confere a campanha errada e conclui que está tudo bem.
    expect(urlNoGoogleAds(SEM_CONTA, '7781')).toBeNull();
    expect(urlNoGoogleAds('8017851692', '24155134757')).toContain('__c=8017851692');
  });

  it('e a linha sem conta continua listada, com a próxima ação certa', () => {
    const p = projetarAtencao({
      alertas: null,
      inventario: inventarioDeProva({
        contas: [{ ...semConta, campanhas: [campanhaSemContaIdentificada], quantidade: 1 }],
        faltou: [],
        parcial: false,
      }),
    });
    const item = p.itens.find((i) => i.sintoma === 'conta_nao_identificada');
    expect(item?.urlExterna).toBeNull();
    expect(SINTOMAS.conta_nao_identificada.proximaAcao).toMatch(/Descubra a conta/);
  });
});

// ── a fila renderizada ──────────────────────────────────────────────────────

describe('a fila, na tela', () => {
  it('cada item abre no lugar, com aria-expanded — nunca em modal', () => {
    leitura = { ...leituraBase, inventario: inventarioSaudavel() };
    render(<FilaDeAtencao foco={null} />);

    const grupo = screen.getByRole('region', { name: 'ligada e sem impressão' });
    const [gatilho] = within(grupo).getAllByRole('button', { expanded: false });
    expect(gatilho.getAttribute('aria-controls')).toBe('alerta-8017851692-24155134757');
    expect(document.querySelector('[role="dialog"]')).toBeNull();

    fireEvent.click(gatilho);
    expect(gatilho.getAttribute('aria-expanded')).toBe('true');
    expect(document.getElementById('alerta-8017851692-24155134757')).toBeTruthy();
  });

  it('o item indicado pelo sino chega REVELADO, focado e destacado', () => {
    leitura = { ...leituraBase, inventario: inventarioSaudavel() };
    const foco = '8017851692-24156373085';
    render(<FilaDeAtencao foco={foco} />);

    const alvo = document.getElementById(`alerta-${foco}`);
    expect(alvo).toBeTruthy();
    expect(document.activeElement).toBe(alvo);
    // Destacado sem depender de cor: a linha inteira ganha anel e o leitor de
    // tela recebe a frase que diz por que aquele item está ali.
    expect(screen.getByText('Este é o item indicado pela notificação.')).toBeTruthy();
  });

  it('a lista incompleta é dita, e o contador vira piso em vez de total', () => {
    leitura = { ...leituraBase, inventario: inventarioSaudavel(), temMais: true };
    render(<FilaDeAtencao foco={null} />);
    expect(screen.getByText(/condições ativas encontradas até agora/)).toBeTruthy();
    expect(screen.getByText(/O contador acima é o que\s+deu para ver, não um total/)).toBeTruthy();
  });
});

// ── o texto do servidor ─────────────────────────────────────────────────────

describe('texto livre do servidor não vira tela do operador', () => {
  it('frase de operação passa inteira', () => {
    expect(motivoOperacional('a conta não respondeu à última tentativa de leitura')).toBe(
      'a conta não respondeu à última tentativa de leitura',
    );
  });

  it('despejo técnico é descartado INTEIRO, e sobra uma frase útil', () => {
    // O filtro é por FORMA, não por lista de palavras: uma lista precisa ser
    // atualizada toda vez que o servidor inventa um erro novo, e é sempre
    // atualizada tarde demais.
    const generico = /não veio em linguagem de operação/;
    expect(motivoOperacional('GET http://api.interno/trafego/alertas devolveu 502')).toMatch(generico);
    expect(motivoOperacional('faltou SUPABASE_SERVICE_ROLE_KEY no ambiente')).toMatch(generico);
    expect(motivoOperacional('Traceback (most recent call last)')).toMatch(generico);
    expect(motivoOperacional('{"detail": "erro"}')).toMatch(generico);
    expect(motivoOperacional('`destravar()` no código')).toMatch(generico);
    expect(motivoOperacional(null)).toMatch(generico);
  });

  it('e o descarte chega à fila, não só à função', () => {
    const p = projetarAtencao({
      alertas: quadroDeAlertasDeProva({
        alertas: [],
        contas: [{
          customer_id: '3849678045',
          nome: 'PMUNDO+',
          erro: 'GET http://api.interno/x devolveu 502',
        }],
      }),
      inventario: null,
    });
    expect(p.semLeitura[0].motivo).not.toMatch(/http/);
  });
});

describe('a fila declara o que NAO cobre — inclusive quando esta vazia', () => {
  /**
   * ⚠️ Achado por revisão adversarial em 27/08/2026.
   *
   * O aviso existia só no ramo com condições e sumia na tela vazia — que é
   * exatamente onde o operador conclui "está tudo bem". Uma fila vazia sem a
   * ressalva afirma, em silêncio, que não há problema de política, de orçamento
   * nem de rastreamento: três famílias de decisão que a SPEC §11 lista e para
   * as quais nenhum sensor existe.
   */
  it('lista as quatro decisoes sem sensor', () => {
    expect(DECISOES_SEM_SENSOR.map((d) => d.titulo)).toEqual([
      'Orçamento e lance',
      'Política e aprovação',
      'Rastreamento e conversão',
      'Criativo e inventário',
    ]);
    // Cada uma diz POR QUE não é coberta — sem isso, a lista viraria uma
    // promessa de roadmap em vez de uma declaração de limite.
    for (const d of DECISOES_SEM_SENSOR) expect(d.porque.length).toBeGreaterThan(20);
  });

  it('sintoma desconhecido cai em nao_classificada, nunca em entrega', () => {
    // O padrão importa: uma condição não classificada aparecendo como problema
    // de entrega faria o operador mexer em lance por causa de algo que ninguém
    // classificou.
    expect(familiaDoSintoma('sintoma_que_ninguem_viu')).toBe('nao_classificada');
    expect(familiaDoSintoma('ligada_sem_impressao')).toBe('entrega');
    expect(familiaDoSintoma('sincronizacao_falhou')).toBe('leitura_da_conta');
    expect(familiaDoSintoma('legado_nao_reconciliado')).toBe('vinculo');
  });

  it('existência não é propriedade, e estado desconhecido não é falta de classificação', () => {
    // ⚠️ Duas classificações erradas, achadas por revisão adversarial.
    //
    // `campanha_nao_encontrada` e `campanha_removida` afirmam que a conta foi
    // lida e a campanha não estava lá — fato de EXISTÊNCIA. Enquadrados como
    // "sabemos de quem é esta campanha?", mandavam o operador procurar um funil
    // quando a pergunta é se a campanha ainda existe.
    expect(familiaDoSintoma('campanha_nao_encontrada')).toBe('existencia');
    expect(familiaDoSintoma('campanha_removida')).toBe('existencia');

    // `estado_desconhecido` é um dos doze sintomas NOMEADOS. Pô-lo em
    // "ainda sem classificação" fazia a tela afirmar que não conhece o que
    // conhece — o estado veio da conta e é este pacote que não o traduz.
    expect(familiaDoSintoma('estado_desconhecido')).toBe('leitura_da_conta');
    expect(familiaDoSintoma('condicao_nao_reconhecida')).toBe('nao_classificada');
  });

  it('toda família usada por um sintoma existe em FAMILIAS', () => {
    // Uma família órfã derrubaria a fila com `familia.titulo` de `undefined`,
    // porque a tela procura a descrição pela chave que o mapa devolve.
    const chaves = new Set(FAMILIAS.map((f) => f.chave));
    for (const sintoma of Object.keys(SINTOMAS)) {
      expect(chaves.has(familiaDoSintoma(sintoma))).toBe(true);
    }
  });
});
