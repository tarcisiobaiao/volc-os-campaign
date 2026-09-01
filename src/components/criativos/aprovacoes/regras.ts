/**
 * As regras da decisão de aprovação.
 *
 * `ajuste_solicitado` e `rejeitado` sem motivo são a mesma coisa na prática:
 * alguém recebe a peça de volta e não sabe o que corrigir. O campo obrigatório
 * não é burocracia, é o que faz a decisão ser acionável pela pessoa seguinte.
 */
import type { DecisaoDeAprovacao } from '@/types/criativos';

export const DECISOES: readonly DecisaoDeAprovacao[] = [
  'aprovado',
  'ajuste_solicitado',
  'rejeitado',
] as const;

export function motivoObrigatorio(decisao: DecisaoDeAprovacao): boolean {
  return decisao === 'ajuste_solicitado' || decisao === 'rejeitado';
}

/**
 * A descrição da fila, que só afirma número quando alguém contou.
 *
 * ⚠️ Conserto do defeito D5b da auditoria P17. A `AprovacoesPage` escrevia
 * `${consulta.data?.total ?? 0} peças aguardam decisão` ramificando só em
 * `isLoading`. Com a leitura falhada, `isLoading` era falso e `data` era
 * `undefined`: o cabeçalho da seção afirmava "0 peças aguardam decisão"
 * enquanto o corpo mostrava o alerta de erro. Fila vazia e fila não lida levam
 * a ações opostas — a primeira libera quem revisa, a segunda pede releitura.
 */
export interface SituacaoDaFila {
  carregando: boolean;
  erro: boolean;
  /** `null` = ninguém contou nesta leitura. Nunca substituir por `0`. */
  total: number | null;
}

export function fraseDaFila(s: SituacaoDaFila): string {
  if (s.carregando) return 'Lendo a fila.';
  if (s.erro || s.total === null) {
    return 'A contagem da fila não chegou nesta leitura. Nenhuma decisão foi perdida.';
  }
  if (s.total === 0) return 'Nenhuma peça aguarda decisão.';
  return `${s.total} ${s.total === 1 ? 'peça aguarda' : 'peças aguardam'} decisão.`;
}
