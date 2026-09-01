/**
 * A procedência de uma peça, e a regra que a tela não pode quebrar.
 *
 * > **Peça local ou de fixture nunca é apresentada como produção.**
 *
 * O motor declara a própria natureza e o servidor deriva `publicavel` dela,
 * nunca um booleano gravado que envelhece. A parte da tela é esta: onde
 * `publicavel` é falso, a peça é rotulada como ensaio, sem selo de "pronto para
 * subir" e sem botão de publicar habilitado.
 *
 * ## Por que a ausência tem rótulo próprio
 *
 * Um servidor mais antigo não manda `natureza`. Isso não vira "produção" nem
 * "ensaio": vira `nao_declarada`, que é o que ele de fato disse. Assumir
 * produção publicaria um ensaio; assumir ensaio esconderia uma peça boa. As
 * duas suposições custam, e nenhuma delas é necessária.
 *
 * ## O que este módulo NÃO faz
 *
 * Não formata medida nenhuma. Dimensão, bytes, MIME e custo já têm autoridade
 * em `criativos/comum/formato.ts`, com a mesma disciplina de ausência que este
 * arquivo defende para procedência. Reimplementá-los aqui criaria duas versões
 * de "não medido", e elas divergiriam.
 */

export type NaturezaDaPeca =
  | 'producao'
  | 'local'
  | 'fixture'
  | 'nao_declarada';

export interface RotuloDeProcedencia {
  natureza: NaturezaDaPeca;
  /** O que a tela escreve ao lado da peça. */
  palavra: string;
  /** O que aquela palavra AFIRMA: a frase que impede a leitura errada. */
  descricao: string;
  /**
   * ⚠️ Só `true` quando o servidor declarou `publicavel`. Ausência de
   * declaração não autoriza publicação; é o mesmo argumento que impede
   * `smart_bidding_eligible` de ser ligado por falta de bloqueio conhecido.
   */
  publicavel: boolean;
}

const ROTULOS: Record<NaturezaDaPeca, Omit<RotuloDeProcedencia, 'publicavel'>> = {
  producao: {
    natureza: 'producao',
    palavra: 'produção',
    descricao: 'Peça de produção: o motor que a fez é publicável.',
  },
  local: {
    natureza: 'local',
    palavra: 'ensaio (local)',
    descricao:
      'Produzida por um motor local, nesta máquina. Serve para conferir o ' +
      'formato e a régua do canal; não é peça para subir na conta.',
  },
  fixture: {
    natureza: 'fixture',
    palavra: 'ensaio (fixture)',
    descricao:
      'Peça de fixture, feita para exercitar o caminho. Ela não representa ' +
      'nada que alguém pediu, e nunca vai para uma conta.',
  },
  nao_declarada: {
    natureza: 'nao_declarada',
    palavra: 'procedência não declarada',
    descricao:
      'O servidor não disse de onde esta peça veio. Não saber não é o mesmo ' +
      'que ser de produção, e por isso ela não pode ser publicada.',
  },
};

/** O que o servidor mandou sobre o motor, sem promessa de completude. */
export interface MotorComNatureza {
  natureza?: string | null;
  publicavel?: boolean | null;
}

/**
 * O rótulo de procedência de uma peça produzida por este motor.
 *
 * ⚠️ `publicavel` não é derivado da natureza aqui. Ele vem do servidor, que já
 * o deriva de `natureza === 'producao'`. Recalcular no navegador criaria uma
 * segunda definição do que é publicável, e ela discordaria do servidor no dia
 * em que ele mudasse a dele, exatamente na direção perigosa.
 */
export function procedenciaDaPeca(
  motor: MotorComNatureza | null | undefined,
): RotuloDeProcedencia {
  const bruto = String(motor?.natureza ?? '').trim().toLowerCase();
  const natureza: NaturezaDaPeca =
    bruto === 'producao' || bruto === 'local' || bruto === 'fixture'
      ? bruto
      : 'nao_declarada';
  return {
    ...ROTULOS[natureza],
    // ⚠️ `=== true`, e não a coerção. `undefined` de um servidor antigo viraria
    // `false` de qualquer jeito, mas escrever a comparação deixa dito que a
    // ausência é tratada como não-autorização, e não como um acidente de
    // truthiness que o próximo refactor pode "simplificar".
    publicavel: motor?.publicavel === true,
  };
}
