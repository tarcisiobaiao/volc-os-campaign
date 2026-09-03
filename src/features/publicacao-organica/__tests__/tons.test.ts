/**
 * CONTRAPROVA M — nenhum estado parcial ou indeterminado pode aparecer verde.
 *
 * Este arquivo não testa a tela: testa a única função que escolhe cor. Ela é
 * pura de propósito, porque a alternativa (um `className` condicional espalhado
 * por componentes) é exatamente o que envelhece sem ninguém perceber, até o dia
 * em que um operador vê verde num `indeterminado` e para de conferir.
 *
 * A varredura é exaustiva: TODOS os estados do contrato × TODOS os tons, mais os
 * casos que o contrato não prevê — tom fora do vocabulário, estado fora do
 * vocabulário, `leitura` ausente e um backend que se contradiz.
 */
import { describe, expect, it } from 'vitest';
import {
  CLASSE_DO_TOM,
  ESTADOS,
  ESTADOS_INCERTOS,
  ESTADOS_TERMINAIS,
  MODOS,
  TOKENS_DE_SUCESSO,
  TONS,
  aguardaODestino,
  classeDoTom,
  ehTerminal,
  estadoConhecido,
  hashAbreviado,
  horarioLocalLegivel,
  horarioLocalValido,
  idAbreviado,
  incertoSeguro,
  proximaAcaoDe,
  revisaoLegivel,
  rotuloDe,
  tomSeguro,
  versaoDaPeca,
  type LeituraDoEstado,
  type TomDaLeitura,
} from '../contract';

/** Um fragmento de "deu certo" apareceu onde não podia? */
function temTokenDeSucesso(classe: string): boolean {
  return TOKENS_DE_SUCESSO.some((token) => classe.includes(token));
}

/**
 * O que o backend manda para cada estado, copiado de
 * `dominio._LEITURAS` (02/09/2026).
 *
 * ⚠️ Isto é FIXTURE, não segunda fonte de verdade: serve para provar que a
 * função se comporta com o dado REAL, e não só com combinações sintéticas. A
 * autoridade continua em `dominio.py`, e o teste que a compara com a migration
 * mora no backend.
 */
const LEITURA_DO_BACKEND: Record<string, LeituraDoEstado> = {
  rascunho: { rotulo: 'Rascunho local', tom: 'neutro', proxima_acao: 'Revise e libere para despacho.', incerto: false, terminal: false },
  pronto: { rotulo: 'Pronto para despachar', tom: 'neutro', proxima_acao: 'Aguardando o despachante assumir.', incerto: false, terminal: false },
  em_voo: { rotulo: 'Em voo', tom: 'aguardando', proxima_acao: 'Não reenvie.', incerto: true, terminal: false },
  rascunho_externo: { rotulo: 'Rascunho criado no destino', tom: 'aguardando', proxima_acao: 'Reconcilie para confirmar.', incerto: false, terminal: false },
  agendado: { rotulo: 'Agendado no destino', tom: 'aguardando', proxima_acao: 'Aguardando o horário.', incerto: false, terminal: false },
  publicacao_solicitada: { rotulo: 'Publicacao solicitada', tom: 'atencao', proxima_acao: 'Reconcilie antes de considerar publicado.', incerto: true, terminal: false },
  publicado: { rotulo: 'Publicado (sem prova fechada)', tom: 'atencao', proxima_acao: 'Reconcilie para trazer URL e horário.', incerto: false, terminal: false },
  reconciliado: { rotulo: 'Publicado e conferido', tom: 'sucesso', proxima_acao: 'Nada a fazer.', incerto: false, terminal: true },
  falha: { rotulo: 'Falhou', tom: 'falha', proxima_acao: 'Leia o erro e crie um job novo.', incerto: false, terminal: false },
  indeterminado: { rotulo: 'Indeterminado', tom: 'atencao', proxima_acao: 'Reconcilie antes de tentar de novo.', incerto: true, terminal: false },
  cancelado: { rotulo: 'Cancelado', tom: 'neutro', proxima_acao: 'Nada a fazer.', incerto: false, terminal: true },
};

describe('vocabulário — o espelho de dominio.py', () => {
  it('tem os onze estados, na ordem em que a operação os encontra', () => {
    expect([...ESTADOS]).toEqual([
      'rascunho', 'pronto', 'em_voo', 'rascunho_externo', 'agendado',
      'publicacao_solicitada', 'publicado', 'reconciliado', 'falha',
      'indeterminado', 'cancelado',
    ]);
  });

  it('tem os cinco tons, e um só deles é verde', () => {
    expect([...TONS]).toEqual(['neutro', 'aguardando', 'atencao', 'sucesso', 'falha']);
    const verdes = TONS.filter((t) => temTokenDeSucesso(CLASSE_DO_TOM[t]));
    expect(verdes).toEqual(['sucesso']);
  });

  it('tem os três modos do contrato', () => {
    expect([...MODOS]).toEqual(['draft', 'schedule', 'now']);
  });

  it('a fixture do backend cobre todos os estados — senão a varredura mente', () => {
    for (const estado of ESTADOS) {
      expect(LEITURA_DO_BACKEND[estado], `falta a leitura de ${estado}`).toBeTruthy();
    }
  });
});

describe('CONTRAPROVA M — a varredura de todos os estados', () => {
  it('nenhum estado com leitura.incerto recebe token de sucesso, em tom nenhum', () => {
    const verdesIndevidos: string[] = [];
    for (const estado of ESTADOS) {
      for (const tom of TONS) {
        // A hipótese hostil: o backend manda QUALQUER tom para este estado,
        // inclusive `sucesso`, e ainda assim marca `incerto`.
        const incerto = ESTADOS_INCERTOS.has(estado);
        const classe = classeDoTom({ estado, leitura: { tom, incerto } });
        if (incerto && temTokenDeSucesso(classe)) verdesIndevidos.push(`${estado}/${tom}`);
      }
    }
    expect(verdesIndevidos).toEqual([]);
  });

  it('com o dado REAL do backend, só `reconciliado` fica verde', () => {
    const verdes = ESTADOS.filter((estado) =>
      temTokenDeSucesso(classeDoTom({ estado, leitura: LEITURA_DO_BACKEND[estado] })));
    expect(verdes).toEqual(['reconciliado']);
  });

  it('um backend que se contradiz não ganha o verde', () => {
    // `indeterminado` com tom `sucesso` só pode ser defeito do servidor. A tela
    // recusa em vez de repetir: repetir seria transformar um bug de uma linha
    // no backend num post que ninguém sabe se saiu.
    const contraditorio = { estado: 'indeterminado', leitura: { tom: 'sucesso' as TomDaLeitura, incerto: true, rotulo: 'Publicado', proxima_acao: 'Nada.', terminal: true } };
    expect(tomSeguro(contraditorio)).toBe('atencao');
    expect(temTokenDeSucesso(classeDoTom(contraditorio))).toBe(false);
  });

  it('`incerto` ausente cai no piso ESTADOS_INCERTOS em vez de virar sucesso', () => {
    for (const estado of Array.from(ESTADOS_INCERTOS)) {
      const semCampo = { estado, leitura: { tom: 'sucesso' as TomDaLeitura } };
      expect(tomSeguro(semCampo), estado).toBe('atencao');
    }
  });
});

describe('CONTRAPROVA M — o que o contrato não conhece', () => {
  it('estado DESCONHECIDO com tom `sucesso` não vira verde', () => {
    const desconhecido = {
      estado: 'publicado_talvez',
      leitura: { tom: 'sucesso' as TomDaLeitura, incerto: false, terminal: true, rotulo: 'Tudo certo', proxima_acao: 'Nada.' },
    };
    expect(estadoConhecido('publicado_talvez')).toBe(false);
    expect(tomSeguro(desconhecido)).toBe('atencao');
    expect(temTokenDeSucesso(classeDoTom(desconhecido))).toBe(false);
  });

  it('estado DESCONHECIDO com a leitura honesta do backend também não vira verde', () => {
    // É assim que `dominio.leitura_do_estado` responde de verdade a um estado
    // fora da tabela: `atencao`, nunca `sucesso`. A tela concorda.
    const comoOBackendResponde = {
      estado: 'estado_do_futuro',
      leitura: {
        rotulo: 'Estado nao reconhecido (estado_do_futuro)',
        tom: 'atencao' as TomDaLeitura,
        proxima_acao: 'Nao trate como publicado.',
        incerto: false,
        terminal: false,
      },
    };
    expect(temTokenDeSucesso(classeDoTom(comoOBackendResponde))).toBe(false);
  });

  it('tom fora do vocabulário nunca herda o benefício da dúvida', () => {
    for (const tom of ['ok', 'green', 'verde', 'SUCESSO', '', 'success']) {
      const entrada = { estado: 'reconciliado', leitura: { tom: tom as unknown as TomDaLeitura } };
      expect(tomSeguro(entrada), tom).toBe('atencao');
      expect(temTokenDeSucesso(classeDoTom(entrada)), tom).toBe(false);
    }
  });

  it('leitura ausente ou nula é atenção, com rótulo e instrução honestos', () => {
    for (const entrada of [
      { estado: 'reconciliado' },
      { estado: 'reconciliado', leitura: null },
      { estado: undefined, leitura: undefined },
      null,
    ]) {
      expect(tomSeguro(entrada)).toBe('atencao');
      expect(temTokenDeSucesso(classeDoTom(entrada))).toBe(false);
    }
    expect(rotuloDe({ estado: 'reconciliado' })).toMatch(/não reconhecido/i);
    expect(proximaAcaoDe({ estado: 'reconciliado' })).toMatch(/não trate como publicado/i);
  });

  it('rótulo e próxima ação vêm do servidor quando existem', () => {
    const entrada = { estado: 'agendado', leitura: LEITURA_DO_BACKEND.agendado };
    expect(rotuloDe(entrada)).toBe('Agendado no destino');
    expect(proximaAcaoDe(entrada)).toBe('Aguardando o horário.');
  });
});

describe('terminal — nada mais acontece sem um job novo', () => {
  it('usa o campo do servidor quando ele existe', () => {
    for (const estado of ESTADOS) {
      expect(ehTerminal({ estado, leitura: LEITURA_DO_BACKEND[estado] }), estado)
        .toBe(ESTADOS_TERMINAIS.has(estado));
    }
  });

  it('sem o campo, cai no espelho do contrato', () => {
    expect(ehTerminal({ estado: 'cancelado' })).toBe(true);
    expect(ehTerminal({ estado: 'em_voo' })).toBe(false);
  });

  /**
   * ⚠️ "Nada a fazer neste job" é o VERDE EM TEXTO: quem lê isso para de
   * conferir tanto quanto quem vê a bolinha verde. `ehTerminal` tinha o campo do
   * servidor como palavra final e nenhuma escada de veto — o oposto de
   * `tomSeguro`, na mesma tela e sobre o mesmo dado.
   */
  it('estado DESCONHECIDO com terminal:true não vira terminal', () => {
    const doFuturo = {
      estado: 'publicado_e_promovido',
      leitura: {
        rotulo: 'Tudo certo', tom: 'sucesso' as TomDaLeitura,
        proxima_acao: 'Nada a fazer.', incerto: false, terminal: true,
      },
    };
    expect(estadoConhecido(doFuturo.estado)).toBe(false);
    expect(ehTerminal(doFuturo)).toBe(false);
  });

  it('estado INCERTO com terminal:true não vira terminal', () => {
    // Um backend que diz "em trânsito" e "acabou" na mesma leitura está se
    // contradizendo. A contradição não ganha o benefício da dúvida — é a mesma
    // regra que impede `incerto + sucesso` de virar verde.
    for (const estado of Array.from(ESTADOS_INCERTOS)) {
      const contraditorio = {
        estado,
        leitura: {
          rotulo: 'Publicado', tom: 'sucesso' as TomDaLeitura,
          proxima_acao: 'Nada.', incerto: true, terminal: true,
        },
      };
      expect(ehTerminal(contraditorio), estado).toBe(false);
    }
    // E também quando `incerto` não chegou: o piso responde no lugar.
    expect(ehTerminal({
      estado: 'em_voo',
      leitura: { tom: 'aguardando' as TomDaLeitura, terminal: true },
    })).toBe(false);
  });

  it('terminal:false nunca é promovido a terminal pelo espelho', () => {
    // Veto só anda numa direção. O servidor pode TIRAR o terminal de um estado
    // que o espelho considera terminal; nunca o contrário.
    expect(ehTerminal({
      estado: 'reconciliado',
      leitura: { ...LEITURA_DO_BACKEND.reconciliado, terminal: false },
    })).toBe(false);
  });
});

describe('incerteza efetiva — o que a tela conclui, não o que o backend afirmou', () => {
  it('o campo do servidor manda quando ele admite a incerteza', () => {
    expect(incertoSeguro({ estado: 'publicado', leitura: { incerto: true } })).toBe(true);
  });

  it('sem o campo, o piso ESTADOS_INCERTOS responde', () => {
    // ⚠️ É esta linha que o atributo `data-incerto` do selo publicava errado:
    // um `em_voo` sem `leitura.incerto` saía marcado como certo, e a varredura
    // do DOM pulava justamente a linha que o piso protege.
    for (const estado of Array.from(ESTADOS_INCERTOS)) {
      expect(incertoSeguro({ estado, leitura: { tom: 'aguardando' as TomDaLeitura } }), estado)
        .toBe(true);
    }
  });

  it('estado fora do contrato é incerto — não conhecer é não saber', () => {
    expect(incertoSeguro({ estado: 'estado_do_futuro', leitura: { incerto: false } })).toBe(true);
    expect(incertoSeguro(null)).toBe(true);
  });

  it('o que é certo continua certo', () => {
    for (const estado of ['rascunho', 'pronto', 'agendado', 'reconciliado', 'falha', 'cancelado']) {
      expect(incertoSeguro({ estado, leitura: LEITURA_DO_BACKEND[estado] }), estado).toBe(false);
    }
  });

  it('"espere o destino" só vale para estado CONHECIDO e incerto', () => {
    // Um estado que este contrato não conhece é incerto, mas ninguém sabe se há
    // pedido em trânsito: mandar esperar seria inventar um fato.
    expect(aguardaODestino({ estado: 'em_voo', leitura: LEITURA_DO_BACKEND.em_voo })).toBe(true);
    expect(aguardaODestino({ estado: 'estado_do_futuro', leitura: { incerto: true } })).toBe(false);
    expect(aguardaODestino({ estado: 'falha', leitura: LEITURA_DO_BACKEND.falha })).toBe(false);
  });
});

describe('versão da peça — a revisão exata, ou nada', () => {
  /**
   * ⚠️ O defeito medido: `Math.max(1, parseInt(texto, 10) || 1)` respondia `1`
   * para vazio, para `abc` e para `0`. O diálogo mostrava "versão " (vazio) e o
   * corpo levava a v1 — a revisão errada, carimbada com a aprovação de outra.
   */
  it('recusa tudo que não é um inteiro a partir de 1', () => {
    for (const texto of ['', '   ', '0', '-1', 'abc', '3.7', '1e3', '+2', null, undefined]) {
      expect(versaoDaPeca(texto as string), JSON.stringify(texto)).toBeNull();
    }
  });

  it('aceita o inteiro, com espaço em volta, e não o normaliza para outra coisa', () => {
    expect(versaoDaPeca('1')).toBe(1);
    expect(versaoDaPeca(' 12 ')).toBe(12);
    expect(versaoDaPeca(7)).toBe(7);
    expect(versaoDaPeca(0)).toBeNull();
    expect(versaoDaPeca(2.5)).toBeNull();
  });
});

describe('horário local — a forma que o domínio aceita, conferida antes do sim', () => {
  it('aceita exatamente AAAA-MM-DD HH:MM[:SS], sem fuso no texto', () => {
    expect(horarioLocalValido('2026-09-10 09:30')).toBe(true);
    expect(horarioLocalValido('2026-09-10T09:30:00')).toBe(true);
    expect(horarioLocalValido(' 2026-12-31 23:59 ')).toBe(true);
  });

  it('recusa o que abriria o diálogo com um horário que não existe', () => {
    for (const texto of [
      'amanhã cedo',            // o caso que passava e virava consentimento
      '10/09/2026 09:30',       // forma brasileira
      '2026-09-10 09:30-03:00', // fuso no texto: o fuso é o outro campo
      '2026-02-30 10:00',       // não existe no calendário
      '2026-13-01 10:00',
      '2026-09-10 24:00',
      '2026-09-10 09:60',
      '2026-09-10 09:30:99',
      '',
      null,
    ]) {
      expect(horarioLocalValido(texto as string), JSON.stringify(texto)).toBe(false);
    }
  });

  it('ano de dois dígitos não é remapeado para 19xx às escondidas', () => {
    // `new Date(Date.UTC(50, …))` viraria 1950. A recusa da tela não pode
    // divergir do que `dominio.validar_horario_local` aceitaria.
    expect(horarioLocalValido('0050-09-10 09:30')).toBe(true);
  });
});

describe('horário declarado — a armadilha do fuso do navegador', () => {
  /**
   * ⚠️ `new Date('2026-09-10 09:30:00')` seria interpretado no fuso de QUEM
   * ESTÁ LENDO. Um operador em Lisboa veria 13:30 para um job declarado às 09:30
   * em São Paulo. Este teste falha se alguém trocar a formatação por `Date`,
   * porque o resultado deixaria de ser igual à string declarada.
   */
  it('imprime o horário exatamente como foi declarado, com o fuso ao lado', () => {
    expect(horarioLocalLegivel('2026-09-10 09:30:00', 'America/Sao_Paulo'))
      .toBe('10/09/2026 09:30 (America/Sao_Paulo)');
    expect(horarioLocalLegivel('2026-12-31T23:59', 'Europe/Lisbon'))
      .toBe('31/12/2026 23:59 (Europe/Lisbon)');
  });

  it('não esconde a ausência: sem horário e sem fuso ele diz isso', () => {
    expect(horarioLocalLegivel(null, 'America/Sao_Paulo')).toBe('sem horário declarado');
    expect(horarioLocalLegivel('2026-09-10 09:30:00', null)).toContain('fuso não declarado');
  });

  it('forma inesperada não é reformatada às cegas — sai como veio, com o fuso', () => {
    expect(horarioLocalLegivel('amanhã cedo', 'America/Sao_Paulo'))
      .toBe('amanhã cedo (America/Sao_Paulo)');
  });
});

describe('identificadores — abreviar sem apagar a prova', () => {
  it('o hash da revisão perde o prefixo do algoritmo e mantém doze dígitos', () => {
    expect(hashAbreviado('sha256:a1b2c3d4e5f60718293a4b5c6d7e8f90')).toBe('a1b2c3d4e5f6…');
    expect(hashAbreviado('curto')).toBe('curto');
    expect(hashAbreviado(null)).toBe('sem hash');
  });

  it('a revisão legível junta versão e conteúdo — é ela que diz QUAL peça saiu', () => {
    expect(revisaoLegivel({ id: 'x', versao: 3, content_hash: 'sha256:a1b2c3d4e5f60718' }))
      .toBe('v3 · a1b2c3d4e5f6…');
  });

  it('um uuid vira algo que um humano consegue conferir de olho', () => {
    expect(idAbreviado('7f3c2b10-4a5d-4e2f-9a11-8c7b6d5e4f30')).toBe('7f3c2b10…4f30');
    expect(idAbreviado(null)).toBe('—');
  });
});

// ---------------------------------------------------------------------------
// O eixo estado × tom — a lacuna que DUAS verificações independentes acharam
// ---------------------------------------------------------------------------

describe('um backend que se contradiz no eixo estado × tom', () => {
  // ⚠️ A escada de veto olhava tom-desconhecido, `incerto` e estado-desconhecido,
  // e NENHUM degrau acoplava estado a tom. `falha` é um estado conhecido e não
  // está em ESTADOS_INCERTOS, então o `sucesso` do servidor passava inteiro:
  // o selo ficava VERDE e o rodapé dizia que tinha acabado, num job que manda
  // criar outro. Não era alcançável com o backend entregue — era defesa em
  // profundidade faltando exatamente no eixo da CONTRAPROVA M.
  const mentirosos = ESTADOS.filter((e) => e !== 'reconciliado');

  it.each(mentirosos)('estado %s com tom "sucesso" declarado NÃO fica verde', (estado) => {
    expect(
      tomSeguro({ estado, leitura: { tom: 'sucesso', incerto: false, terminal: true } }),
    ).not.toBe('sucesso');
  });

  it('só `reconciliado` sobrevive ao piso de estado', () => {
    const verdes = ESTADOS.filter(
      (estado) =>
        tomSeguro({ estado, leitura: { tom: 'sucesso', incerto: false, terminal: true } }) ===
        'sucesso',
    );
    expect(verdes).toEqual(['reconciliado']);
  });

  it.each(mentirosos.filter((e) => e !== 'cancelado'))(
    'estado %s com terminal:true declarado NÃO vira terminal',
    (estado) => {
      expect(
        ehTerminal({ estado, leitura: { tom: 'falha', incerto: false, terminal: true } }),
      ).toBe(false);
    },
  );

  it('o piso não engessa o caminho feliz: reconciliado continua verde e terminal', () => {
    // ⚠️ O CONTROLE. Sem ele, um piso que recusasse TUDO passaria nos testes
    // acima e a tela nunca mais mostraria sucesso nenhum.
    const bom = {
      estado: 'reconciliado',
      leitura: { tom: 'sucesso' as const, incerto: false, terminal: true },
    };
    expect(tomSeguro(bom)).toBe('sucesso');
    expect(ehTerminal(bom)).toBe(true);
    expect(
      ehTerminal({
        estado: 'cancelado',
        leitura: { tom: 'neutro' as const, incerto: false, terminal: true },
      }),
    ).toBe(true);
  });
});
