// @vitest-environment jsdom
/**
 * As regras que não dependem de pixel nenhum.
 *
 * Formatar é onde as três regras do módulo vivem ou morrem: é aqui que um
 * `null` viraria `0` sem ninguém notar, que um número perderia a data, e que
 * uma conta velha ficaria nova por estar ao lado de uma recente.
 */
import { describe, expect, it } from 'vitest';

import { mesclarPaginas, piorFrescor } from '@/hooks/useInventario';
import type { Inventario } from '@/types/trafego';

import {
  AUSENTE,
  contagem,
  dinheiro,
  horaExata,
  idade,
  lidoHa,
  presencaLegivel,
} from '@/components/trafego/inventario/formato';
import {
  creditoUp,
  inventarioDeProva,
  portalMundoMais,
} from '@/components/trafego/inventario/fixtureDeProvas';

describe('ausência é null, zero é fato', () => {
  it('travessão para ausência, número para zero', () => {
    expect(dinheiro(null, 'BRL')).toBe(AUSENTE);
    expect(dinheiro(0, 'BRL')).toBe('R$ 0,00');
    expect(contagem(null)).toBe(AUSENTE);
    expect(contagem(0)).toBe('0');
  });

  it('micros viram moeda sem perder centavo', () => {
    expect(dinheiro(120_000, 'BRL')).toBe('R$ 0,12');
    expect(dinheiro(10_000_000, 'BRL')).toBe('R$ 10,00');
    expect(dinheiro(47_310_000, 'BRL')).toBe('R$ 47,31');
  });

  it('moeda não declarada não vira real, e também não vira número solto', () => {
    // O número puro era o defeito: `0,12` numa coluna onde a linha de cima diz
    // `R$ 10,00` lê-se como reais, e a falta da unidade não aparece em lugar
    // nenhum. O valor é fato; a moeda é que não foi declarada, e é isso que a
    // célula passa a dizer.
    const semMoeda = dinheiro(120_000, null);
    expect(semMoeda).toContain('0,12');
    expect(semMoeda).toContain('sem moeda declarada');
    expect(semMoeda).not.toContain('R$');
  });

  it('código de moeda desconhecido não derruba a linha', () => {
    expect(dinheiro(1_000_000, 'ZZZ')).toContain('ZZZ');
  });

  it('⚠️ código de moeda MALFORMADO não muda o número de casas da coluna', () => {
    // `ZZZ` não cai aqui: o `Intl` aceita qualquer código bem formado de três
    // letras e só usa a sigla como símbolo. O ramo de emergência é para o que
    // NÃO é código — `R$` gravado no lugar de `BRL`, uma sigla de cinco letras
    // — e ele formatava como número decimal comum, cujo padrão é TRÊS casas.
    // A mesma coluna passava a ter linhas com duas e linhas com três casas, e
    // `1,235` lido na altura de `R$ 12,35` é erro de ordem de grandeza no meio
    // de uma decisão de gasto.
    expect(dinheiro(1_234_500, 'MOEDA')).toBe('1,23 MOEDA');
    expect(dinheiro(1_234_500, 'R$')).toBe('1,23 R$');
    expect(dinheiro(1_234_500, null)).toContain('1,23');
    expect(dinheiro(1_234_500, null)).not.toContain('1,234');
  });
});

describe('nenhum número sem frescor', () => {
  it('a idade é dita em linguagem de operação', () => {
    expect(idade(30)).toBe('agora');
    expect(idade(372)).toBe('há 6 min');
    expect(idade(26_400)).toBe('há 7 h');
    expect(idade(400_000)).toBe('há 5 dias');
  });

  it('sem data, a tela diz que não tem data — não inventa uma', () => {
    expect(idade(null)).toBe('sem data de leitura');
    expect(lidoHa(null)).toBe('sem data de leitura');
    expect(lidoHa(372)).toBe('lido há 6 min');
  });

  it('⚠️ leitura carimbada no FUTURO não é "agora"', () => {
    // Idade negativa é relógio fora de sincronia. Caindo no ramo do `agora`,
    // ela dava a resposta mais tranquilizadora possível justamente para o caso
    // em que a data não vale nada — a degradação exata que o módulo proíbe:
    // desconhecido nunca vira recente.
    expect(idade(-7200)).toBe('em data futura — relógio fora de sincronia');
    expect(lidoHa(-7200)).toContain('relógio fora de sincronia');
    // Diferença pequena entre o relógio do servidor e o desta máquina é normal
    // e não muda decisão nenhuma.
    expect(idade(-30)).toBe('agora');
  });
});

describe('o instante que sai da tela', () => {
  it('a hora exata leva ano e segundos — a hora de leitura não', () => {
    // Ano e segundos não ajudam a decidir gasto e por isso não aparecem na
    // tela; ajudam a achar a linha no log e por isso existem no texto copiado.
    const exata = horaExata('2026-08-25T10:11:12.000Z') as string;
    expect(exata).toContain('2026');
    expect(exata).toMatch(/\d{2}:\d{2}:\d{2}/);
  });

  it('data que não é data devolve nada — nunca "Invalid Date" na tela', () => {
    expect(horaExata('nem data nem coisa nenhuma')).toBeNull();
    expect(horaExata(null)).toBeNull();
    expect(horaExata(undefined)).toBeNull();
  });
});

describe('o vocabulário de presença', () => {
  it('nomeia os seis estados sem concluir nada além do observado', () => {
    expect(presencaLegivel('nao_encontrada').palavra).toBe('não encontrada');
    expect(presencaLegivel('nao_encontrada').descricao).toContain('lida com sucesso');
    expect(presencaLegivel('sincronizacao_falhou').descricao)
      .toContain('não dá para afirmar presença nem ausência');
  });

  it('aceita o sétimo estado que o servidor já emite', () => {
    // `presente` ainda não está na união de tipos. Um mapa devolveria
    // `undefined` e derrubaria a linha; a função devolve a frase verdadeira.
    expect(presencaLegivel('presente').palavra).toBe('presente');
  });

  it('palavra desconhecida vira "não reconhecida", nunca um dos seis', () => {
    const r = presencaLegivel('sumiu_da_conta');
    expect(r.palavra).toBe('presença não reconhecida');
    expect(r.descricao).toContain('sumiu_da_conta');
  });
});

describe('mescla de páginas', () => {
  it('o pior frescor manda: leitura velha não rejuvenesce ao lado de recente', () => {
    expect(piorFrescor('recente', 'falhou')).toBe('falhou');
    expect(piorFrescor('velho', 'recente')).toBe('velho');
    expect(piorFrescor('vazio_confirmado', 'nunca_lido')).toBe('nunca_lido');
  });

  it('sem página nenhuma, não há envelope inventado', () => {
    expect(mesclarPaginas([])).toBeNull();
  });

  it('concatena campanhas da mesma conta sem substituir nem duplicar', () => {
    const pagina1: Inventario = inventarioDeProva({
      contas: [{ ...creditoUp, campanhas: [creditoUp.campanhas[0]] }],
      parcial: false,
      faltou: [],
      proximo_cursor: 'x',
    });
    const pagina2: Inventario = inventarioDeProva({
      contas: [
        { ...creditoUp, campanhas: [creditoUp.campanhas[0], creditoUp.campanhas[1]] },
        portalMundoMais,
      ],
      parcial: false,
      faltou: [],
      proximo_cursor: null,
    });

    const junto = mesclarPaginas([pagina1, pagina2]);
    expect(junto).not.toBeNull();
    expect(junto?.contas.length).toBe(2);
    expect(junto?.contas[0].campanhas.length).toBe(2);
    expect(junto?.proximo_cursor).toBeNull();
  });

  it('parcial de qualquer página contamina o envelope, e o que faltou não se perde', () => {
    const boa = inventarioDeProva({ parcial: false, faltou: [], frescor: 'recente' });
    const ruim = inventarioDeProva();
    const junto = mesclarPaginas([boa, ruim]);
    expect(junto?.parcial).toBe(true);
    expect(junto?.faltou.length).toBe(1);
    expect(junto?.frescor).toBe('falhou');
  });
});
