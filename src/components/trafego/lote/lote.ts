/**
 * O resumo de um lote de criação — e as regras que ele existe para obedecer.
 *
 * ## 1 · Falha de um item não mascara os demais
 *
 * A forma comum de quebrar essa regra não é esconder itens: é resumir. "3 de 6
 * criadas" está certo e não diz nada útil, porque as outras três podem ser três
 * falhas (investigar cada uma), três indeterminadas (verificar na conta, jamais
 * reenviar) ou três que ainda nem chegaram a vez. São três ações diferentes.
 *
 * ## 2 · `indeterminado` é o balde que não pode ser somado com nenhum outro
 *
 * Ele diz "a chamada saiu e não sabemos se criou". Junto com `falhou` — que
 * AFIRMA que não criou — ele vira um número que autoriza reenviar, e reenviar
 * um item indeterminado cria a segunda campanha real disputando o mesmo leilão
 * contra a primeira. É o defeito mais caro que esta tela pode cometer.
 *
 * ## 3 · A ordem da frase é a ordem da atenção
 *
 * Um resumo que começa por "12 criadas" faz o "1 indeterminada" desaparecer no
 * meio da linha. O que exige alguém vem primeiro; o que correu bem vem no fim.
 *
 * ⚠️ **A próxima ação de cada item vem do servidor.** Ela é decidida em
 * `trafego_item_situacao.proxima_acao` (SQL) e em `lote.proxima_acao()`
 * (Python), que já são duas definições comparadas contra um Postgres real. Uma
 * terceira aqui seria a que ninguém compara.
 *
 * Módulo puro: sem React, sem HTTP, sem Google Ads.
 */
import {
  ESTADOS_CRIADOS,
  type AcaoDoItem,
  type ItemDoLote,
  type Lote,
} from '@/types/diagnostico';

export interface ResumoDoLote {
  total: number;
  /** Itens que existem na conta de anúncio, em qualquer degrau pós-criação. */
  criados: number;
  falharam: number;
  /** ⚠️ Nunca somado a `falharam`. */
  indeterminados: number;
  /** Enviados agora, resposta ainda não voltou. Não é "na fila" nem "indeterminado". */
  emVoo: number;
  duplicados: number;
  cancelados: number;
  aguardando: number;
  /** Uma frase que nomeia todos os buckets não vazios, atenção primeiro. */
  frase: string;
  /** `true` quando ainda há item fora de estado final. */
  emAndamento: boolean;
}

const TERMINAIS = new Set<ItemDoLote['estado']>(['cancelada', 'revertida', 'ativa']);

/** `true` quando este item exige uma pessoa antes de qualquer coisa acontecer. */
export function exigeAlguem(item: ItemDoLote): boolean {
  return (
    item.proxima_acao === 'parar_duplicidade' ||
    item.proxima_acao === 'decidir_retomada' ||
    item.proxima_acao === 'verificar'
  );
}

export function resumoDoLote(lote: Lote): ResumoDoLote {
  const itens = lote.itens;
  const porAcao = (a: AcaoDoItem) => itens.filter((i) => i.proxima_acao === a).length;

  const criados = itens.filter((i) => ESTADOS_CRIADOS.includes(i.estado)).length;
  const falharam = itens.filter((i) => i.estado === 'falhou').length;
  const indeterminados = itens.filter(
    (i) => i.estado === 'indeterminado' || i.recibo_em_voo,
  ).length;
  const duplicados = porAcao('parar_duplicidade');
  const cancelados = itens.filter((i) => i.estado === 'cancelada').length;
  // ⚠️ "Aguardando a vez" é o balde do que NUNCA FOI TENTADO, e essa é
  // exatamente a crença que autoriza reenviar.
  //
  // O filtro por exclusão deixava passar `indeterminado` e `criando`: os dois
  // significam "o pedido saiu e a resposta não voltou". Um lote com um único
  // item indeterminado dizia, na mesma frase, "1 sem resposta da conta" E "1
  // aguardando a vez" — dois baldes para um item, e o segundo desmentindo o
  // primeiro. Com três itens os baldes somavam quatro.
  //
  // A exclusão agora é explícita: quem já foi enviado sai daqui, e continua
  // contado no seu balde próprio.
  const aguardando = itens.filter(
    (i) =>
      !TERMINAIS.has(i.estado) &&
      !ESTADOS_CRIADOS.includes(i.estado) &&
      i.estado !== 'falhou' &&
      i.estado !== 'indeterminado' &&
      i.estado !== 'criando' &&
      !i.recibo_em_voo,
  ).length;

  // `criando` tem balde próprio: o pedido está em voo agora, e isso é
  // diferente tanto de "na fila" quanto de "não sabemos se criou".
  const emVoo = itens.filter((i) => i.estado === 'criando' && !i.recibo_em_voo).length;

  const partes: string[] = [];
  if (duplicados) {
    partes.push(
      `${duplicados} com mais de uma campanha na conta — o lote fica travado até alguém decidir qual fica`,
    );
  }
  if (indeterminados) {
    partes.push(
      `${indeterminados} sem resposta da conta — não sabemos se criaram, e nenhuma será reenviada`,
    );
  }
  if (falharam) partes.push(`${falharam} ${falharam === 1 ? 'falhou' : 'falharam'}`);
  if (emVoo) partes.push(`${emVoo} ${emVoo === 1 ? 'enviada' : 'enviadas'} agora, esperando resposta`);
  if (aguardando) {
    partes.push(`${aguardando} ${aguardando === 1 ? 'aguardando' : 'aguardando'} a vez`);
  }
  if (cancelados) partes.push(`${cancelados} ${cancelados === 1 ? 'cancelada' : 'canceladas'}`);
  if (criados) {
    partes.push(`${criados} ${criados === 1 ? 'criada' : 'criadas'}, ${criados === 1 ? 'pausada' : 'todas pausadas'}`);
  }

  return {
    total: itens.length,
    criados,
    falharam,
    indeterminados,
    duplicados,
    cancelados,
    aguardando,
    frase: partes.length ? partes.join('; ') : 'nenhum item neste lote',
    emVoo,
    emAndamento: aguardando + indeterminados + emVoo > 0,
  };
}

/**
 * `true` quando o lote pode ser retomado.
 *
 * Três recusas, e as três são deliberadas:
 *
 *  - **lote cancelado** — retomar sem decisão nova apagaria um gesto declarado
 *    com motivo por uma pessoa;
 *  - **sem aprovação humana** — nada é executado antes dela;
 *  - **item indeterminado ou duplicado presente** — retomar aqui é reenviar
 *    exatamente o que não pode ser reenviado. Primeiro verificar, depois retomar.
 */
export function podeRetomar(lote: Lote): { pode: boolean; motivo: string | null } {
  if (lote.estado === 'concluido' || lote.estado === 'revertido') {
    return { pode: false, motivo: 'este lote já terminou.' };
  }
  if (lote.cancelado_em != null) {
    return {
      pode: false,
      motivo: 'este lote foi cancelado; retomar exige uma decisão nova, não este botão.',
    };
  }
  if (lote.aprovado_em == null) {
    return {
      pode: false,
      motivo: 'este lote ainda não tem aprovação humana. Nada é executado antes dela.',
    };
  }
  const travado = lote.itens.some(
    (i) => i.proxima_acao === 'parar_duplicidade' || i.estado === 'indeterminado' || i.recibo_em_voo,
  );
  if (travado) {
    return {
      pode: false,
      motivo:
        'há item sem resposta da conta ou com mais de uma campanha encontrada. ' +
        'Verificar na conta vem antes de retomar — reenviar aqui criaria campanha duplicada.',
    };
  }
  if (!lote.itens.some((i) => i.proxima_acao === 'decidir_retomada' || i.proxima_acao === 'criar')) {
    return { pode: false, motivo: 'não há item esperando execução.' };
  }
  return { pode: true, motivo: null };
}
