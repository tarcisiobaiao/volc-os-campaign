/**
 * A projeção das paradas — a régua única de prontidão.
 *
 * ## O que estes testes trancam
 *
 * A tela anterior recalculava prontidão em TRÊS lugares que discordavam entre
 * si: um array `pendencias` montado a cada render, uma expressão booleana ad-hoc
 * por cartão, e o trilho do topo — que passava `origem` como literal `true` e
 * ficava verde com o destino BLOQUEADO, e marcava a copy como pronta para
 * `status: 'running'`, `'error'` e para uma linha `perdida`.
 *
 * Aqui a régua é uma só, e ela não inventa veredito: cada estado sai de um fato
 * que o servidor emitiu.
 */
import { describe, expect, it } from 'vitest';

import {
  bloqueiosDoCockpit, faltasDaBancada, faltasDaParada, politicaBarra,
  primeiraNaoConfirmada, projetarParadas, SEM_PARADA_ATUAL, type FatosDaBancada,
} from '../paradas';
import { leituraDoDestinoPago } from '@/lib/landing-policy/prontidao';
import { reciboApto } from '@/lib/landing-policy/__tests__/recibos';
import type { Cockpit, CopyPersistida, RevisaoDoConjuntoPago } from '@/types/trafego';

const DESTINO_APTO = leituraDoDestinoPago(
  { landing_policy_receipt: reciboApto({}, { agora_epoch: 1_756_900_000 }) },
  { agora_epoch: 1_756_900_000, status_wp: 'publish', exige_ponto_de_campanha: true },
);
const DESTINO_SEM_RECIBO = leituraDoDestinoPago(
  {}, { status_wp: 'publish', exige_ponto_de_campanha: true },
);

const cockpit = (over: Record<string, unknown> = {}): Cockpit => ({
  opportunity_id: 73, cluster_id: 4,
  origem: { vertical: 'informativo', pais: 'BR', status_wp: 'publish' },
  triagem: null, grupos: [], descartadas: [], procedencia: null,
  avisos: [],
  conta: { project_id: 2, dominio: 'x', customer_id: '1', login_customer_id: '2',
           vinculada: true, motivo: null },
  ...over,
} as unknown as Cockpit);

const VERTICAL_LIMPA = [{
  id: 'informativo', titulo: 'Informativo', descricao: '', exige: null,
  severidade: null, paises_exigem: [],
}] as never;

const CONJUNTO_OK = {
  selecionadas: [{ termo: 'a' }], excluidas: [], em_revisao_humana: [], negativas: [],
  selected_set_sha256: 'a', approved_set_sha256: 'a', aprovado_por: 'x',
  blockers: [], alertas: [],
} as unknown as RevisaoDoConjuntoPago;

const COPY_OK = { status: 'done', copy: { headlines: [], descriptions: [] } } as unknown as CopyPersistida;

const TUDO_PRONTO: FatosDaBancada = {
  cockpit: cockpit(), destino: DESTINO_APTO, conjunto: CONJUNTO_OK,
  copy: COPY_OK, verticais: VERTICAL_LIMPA, orcamento: 10, lance: 0.12,
  certificacoes: [],
};

describe('a severidade tem uma régua só, e limitacao BARRA', () => {
  it('`limitacao` barra tanto quanto `bloqueio`', () => {
    // ⚠️ `PortaoDePolitica.tsx:159` escrevia que a campanha "sobe com
    // restrição", enquanto `volc_ads/campanha/conteudo.py:56` já punha
    // `limitacao` entre as severidades que barram — o efeito FULLY_LIMITED
    // deixou 57 anúncios sem veicular em 39 contas. Anúncio que não veicula é
    // reprovação com outro nome.
    // O portão só existe quando a vertical EXIGE algo neste país — ver o teste
    // do país logo abaixo. Aqui o que se isola é a severidade.
    const exigindo = (severidade: string | null) => ({
      id: 'x', titulo: 'X', descricao: '', exige: 'habilitacao_x',
      severidade, paises_exigem: ['BR'],
    }) as never;
    expect(politicaBarra(exigindo('limitacao'), 'BR', [])).toBe(true);
    expect(politicaBarra(exigindo('bloqueio'), 'BR', [])).toBe(true);
    expect(politicaBarra(exigindo(null), 'BR', [])).toBe(false);
    expect(politicaBarra(null, 'BR', [])).toBe(false);
    // Sem `exige`, não há portão nenhum a cumprir.
    expect(politicaBarra({ severidade: 'bloqueio', exige: null } as never, 'BR', []))
      .toBe(false);
  });

  it('prefere os `bloqueios` que o servidor já filtrou', () => {
    const c = cockpit({
      avisos: [{ codigo: 'X', severidade: 'atencao', titulo: 'x', detalhe: '' }],
      bloqueios: [{ codigo: 'Y', severidade: 'bloqueio', titulo: 'y', detalhe: '' }],
    });
    expect(bloqueiosDoCockpit(c).map((b) => b.codigo)).toEqual(['Y']);
  });

  it('sem `bloqueios` no payload, refiltra FAIL-CLOSED', () => {
    // Ausência do campo é "este servidor é mais antigo", nunca "não há
    // bloqueio". Severidade desconhecida barra até alguém decidir o contrário.
    const c = cockpit({
      avisos: [
        { codigo: 'A', severidade: 'atencao', titulo: '', detalhe: '' },
        { codigo: 'B', severidade: 'limitacao', titulo: '', detalhe: '' },
        { codigo: 'C', severidade: 'severidade_nova_do_servidor', titulo: '', detalhe: '' },
      ],
    });
    expect(bloqueiosDoCockpit(c).map((b) => b.codigo).sort()).toEqual(['B', 'C']);
  });
});

describe('o portão de política é POR PAÍS, e a certificação o satisfaz', () => {
  const FINANCEIRO = [{
    id: 'financeiro', titulo: 'Financeiro', descricao: '',
    exige: 'verificacao_servicos_financeiros', severidade: 'bloqueio',
    paises_exigem: ['BR', 'MX'],
  }] as never;

  it('vertical que NÃO exige neste país não barra', () => {
    // ⚠️ Verificar no Brasil não habilita o México — e o inverso também vale:
    // uma vertical marcada `bloqueio` que não exige AQUI não barra nada.
    // A primeira versão de `politicaBarra` olhava só a severidade e barrava
    // sempre, criando um bloqueio que o operador não tinha como resolver.
    expect(politicaBarra(FINANCEIRO[0], 'PT', [])).toBe(false);
    expect(politicaBarra(FINANCEIRO[0], 'BR', [])).toBe(true);
  });

  it('a certificação declarada CUMPRE o portão', () => {
    expect(politicaBarra(FINANCEIRO[0], 'BR', ['verificacao_servicos_financeiros']))
      .toBe(false);
  });

  it('a parada some da lista de faltas quando o operador declara a habilitação', () => {
    const base = {
      ...TUDO_PRONTO, verticais: FINANCEIRO,
      cockpit: cockpit({ origem: { vertical: 'financeiro', pais: 'BR', status_wp: 'publish' } }),
    };
    expect(faltasDaParada('politica', base)).toHaveLength(1);
    expect(faltasDaParada('politica', {
      ...base, certificacoes: ['verificacao_servicos_financeiros'],
    })).toHaveLength(0);
  });
});

describe('ausência de regra NUNCA é verde', () => {
  it('portões de política não lidos deixam a parada indeterminada', () => {
    const f = { ...TUDO_PRONTO, verticais: [] };
    const faltas = faltasDaParada('politica', f);
    expect(faltas).toHaveLength(1);
    expect(faltas[0].indeterminada).toBe(true);
    expect(faltas[0].texto).toMatch(/ler os portões de política/);
  });

  it('vertical que o servidor não adjudicou é indeterminada, não liberada', () => {
    const f = {
      ...TUDO_PRONTO,
      cockpit: cockpit({ origem: { vertical: 'financeiro', pais: 'BR', status_wp: 'publish' } }),
    };
    const faltas = faltasDaParada('politica', f);
    expect(faltas[0].indeterminada).toBe(true);
    expect(faltas[0].texto).toMatch(/adjudicar a vertical/);
  });
});

describe('o anúncio tem UMA regra de pronto, e ela é o status do servidor', () => {
  it.each([
    ['running', /esperar a escrita/],
    ['error', /reescrever o anúncio/],
  ])('status %s NÃO é pronto', (status, esperado) => {
    // ⚠️ O trilho antigo usava `copy={!!escrita}` e ficava verde nos três.
    const f = { ...TUDO_PRONTO, copy: { status, copy: null } as unknown as CopyPersistida };
    expect(faltasDaParada('anuncio', f)[0].texto).toMatch(esperado);
  });

  it('`done` sem copy no payload também não é pronto', () => {
    const f = { ...TUDO_PRONTO, copy: { status: 'done', copy: null } as unknown as CopyPersistida };
    expect(faltasDaParada('anuncio', f)).toHaveLength(1);
  });

  it('`done` com copy é a única forma de pronto', () => {
    expect(faltasDaParada('anuncio', TUDO_PRONTO)).toHaveLength(0);
  });
});

describe('o destino entra INTEIRO, e indeterminado não abre nada', () => {
  it('sem recibo, a falta é de AVALIAÇÃO e é indeterminada', () => {
    // ⚠️ Testar só `bloqueadores.length` ignoraria os `desconhecidos` — a
    // verificação exigida que não pôde ser concluída.
    const f = { ...TUDO_PRONTO, destino: DESTINO_SEM_RECIBO };
    const faltas = faltasDaParada('destino', f);
    expect(faltas.length).toBeGreaterThan(0);
    expect(faltas[0].indeterminada).toBe(true);
  });
});

describe('a economia exige o que o operador declarou', () => {
  it('orçamento e lance ausentes são faltas, e não zeros', () => {
    const f = { ...TUDO_PRONTO, orcamento: null, lance: null };
    const textos = faltasDaParada('economia', f).map((x) => x.texto);
    expect(textos).toContain('declarar o orçamento diário');
    expect(textos).toContain('declarar o lance inicial');
  });

  it('conta não vinculada é falta', () => {
    const f = {
      ...TUDO_PRONTO,
      cockpit: cockpit({ conta: { vinculada: false, project_id: 2, dominio: 'x',
                                  customer_id: null, login_customer_id: null, motivo: null } }),
    };
    expect(faltasDaParada('economia', f).map((x) => x.texto))
      .toContain('vincular a conta de anúncio ao projeto');
  });
});

describe('os termos: o ato que falta é APROVAR, não escolher', () => {
  it('conjunto não aprovado pede o ato de aprovação', () => {
    const f = {
      ...TUDO_PRONTO,
      conjunto: { ...CONJUNTO_OK, approved_set_sha256: null } as RevisaoDoConjuntoPago,
    };
    expect(faltasDaParada('termos', f)[0].texto).toBe('aprovar o conjunto positivo');
  });

  it('conjunto não lido é indeterminado, não "falta escolher"', () => {
    const f = { ...TUDO_PRONTO, conjunto: null };
    expect(faltasDaParada('termos', f)[0].indeterminada).toBe(true);
  });
});

describe('o mapa das paradas', () => {
  it('com tudo pronto, nada falta e a Revisão fica confirmada', () => {
    expect(faltasDaBancada(TUDO_PRONTO)).toHaveLength(0);
    // Projetado SEM viés: a parada em que o operador está vira `atual`, e
    // `atual` é diferente de `confirmada` de propósito — o mapa precisa dizer
    // onde ele está, não só o que já ficou pronto.
    const paradas = projetarParadas(TUDO_PRONTO, SEM_PARADA_ATUAL);
    expect(paradas.every((p) => p.estado === 'confirmada')).toBe(true);
    expect(projetarParadas(TUDO_PRONTO, 'revisao')
      .find((p) => p.parada === 'revisao')?.estado).toBe('atual');
  });

  it('enquanto o cockpit não chegou, NADA é confirmado', () => {
    // ⚠️ Pintar verde sobre payload ausente é o defeito de origem desta tela.
    const paradas = projetarParadas({ ...TUDO_PRONTO, cockpit: null }, 'destino');
    expect(paradas.every((p) => p.estado === 'indeterminada')).toBe(true);
  });

  it('a Revisão NUNCA é bloqueada — ela é a tela que explica o bloqueio', () => {
    const f = { ...TUDO_PRONTO, orcamento: null };
    const revisao = projetarParadas(f, 'destino').find((p) => p.parada === 'revisao');
    expect(revisao?.estado).toBe('pendente');
    expect(revisao?.estado).not.toBe('bloqueada');
  });

  it('estar OLHANDO um bloqueio não o resolve', () => {
    // A parada atual sobrepõe `pendente`, mas nunca `indeterminada`.
    const f = { ...TUDO_PRONTO, destino: DESTINO_SEM_RECIBO };
    const destino = projetarParadas(f, 'destino').find((p) => p.parada === 'destino');
    expect(destino?.estado).toBe('indeterminada');
  });

  it('a primeira não confirmada é onde a URL sem `etapa` cai', () => {
    // ⚠️ O DEFEITO QUE ISTO IMPEDE: projetando com `atual: 'destino'`, a
    // primeira não confirmada seria sempre `destino` — mesmo com o destino
    // resolvido —, e a entrada sem `?etapa` ficaria presa na primeira parada.
    const f = { ...TUDO_PRONTO, copy: null };
    expect(primeiraNaoConfirmada(projetarParadas(f, SEM_PARADA_ATUAL))).toBe('anuncio');
    expect(primeiraNaoConfirmada(projetarParadas(f, 'destino'))).toBe('anuncio');
  });

  it('os bloqueios do servidor entram na conta da Revisão, e não somem numa parada', () => {
    const f = {
      ...TUDO_PRONTO,
      cockpit: cockpit({
        bloqueios: [{ codigo: 'SEM_LP', severidade: 'bloqueio', titulo: 'Sem LP', detalhe: '' }],
      }),
    };
    expect(faltasDaBancada(f).map((x) => x.texto)).toContain('sem lp');
  });
});
