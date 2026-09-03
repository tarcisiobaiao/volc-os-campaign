/**
 * As regras da decisão de aprovação.
 *
 * `ajuste_solicitado` e `rejeitado` sem motivo são a mesma coisa na prática:
 * alguém recebe a peça de volta e não sabe o que corrigir. O campo obrigatório
 * não é burocracia, é o que faz a decisão ser acionável pela pessoa seguinte.
 */
import type { AssetMaster, DecisaoDeAprovacao } from '@/types/criativos';

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

/**
 * Esta peça pode ser decidida?
 *
 * ⚠️ DEFEITO FECHADO. `FormularioDeDecisao` documenta a regra desde o começo —
 * "Peça pronta? Uma peça que não ficou pronta não é aprovável" — e o ramo
 * `if (!aprovavel)` está escrito e testado. Só que os DOIS chamadores passavam
 * `aprovavel` sem valor, ou seja, `true` literal: a guarda existia, tinha
 * mensagem pronta e nunca podia disparar. Uma guarda que o chamador desliga é
 * documentação, não guarda.
 *
 * O critério é o que o cliente REALMENTE sabe: um master sem `contentHash` ou
 * sem `bytesTotais` é uma peça cujos bytes ninguém mediu. Aprovar isso é
 * autorizar um arquivo sobre o qual não se sabe nem o tamanho — e a autorização
 * vale para uma finalidade escrita, contra um arquivo que talvez não esteja lá.
 *
 * ⚠️ NÃO se usa `previewUrl` aqui. Link assinado ausente é falha de LEITURA
 * ("a peça existe, o arquivo não veio nesta leitura"), e `Preview` já trata isso
 * como quinto estado. Confundir os dois faria uma peça íntegra virar
 * inaprovável por causa de um link expirado.
 */
export function pecaEDecidivel(asset: Pick<AssetMaster, 'contentHash' | 'bytesTotais'>): boolean {
  return Boolean(asset.contentHash) && asset.bytesTotais !== null;
}
