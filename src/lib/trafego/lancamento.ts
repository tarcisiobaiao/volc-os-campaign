/**
 * As duas leituras que a tela de lançamento faz do que o SERVIDOR decidiu.
 *
 * ## Por que isto não mora no componente
 *
 * As duas perguntas abaixo são de governança, e a resposta pertence ao ledger:
 *
 *   · "esta tentativa está indeterminada, e portanto reenviar é proibido?"
 *   · "qual é o id desta campanha na conta?"
 *
 * Dentro de um `.tsx` elas viram condição de render — e condição de render é
 * reescrita sem cerimônia no próximo ajuste de layout. Aqui elas são função
 * pura, com teste, e a tela só pergunta.
 *
 * ## O defeito que a segunda função conserta
 *
 * A versão anterior lia `recibo.campaign_id` / `recibo.campanha_id` — duas
 * chaves que a projeção do recibo NUNCA produziu. O `onCriada` jamais disparava
 * e ninguém percebeu, porque o recibo chegava tipado como
 * `Record<string, unknown>`: um tipo que aceita qualquer chave também aceita
 * as que não existem.
 */
import type {
  ReciboDeLancamento, RecursoCriado, RecusaDeclarada, SubidaIndeterminada,
} from '@/types/trafego';

/** Um erro do cliente HTTP que possa carregar o corpo estruturado da recusa. */
export interface ErroComCorpo {
  status?: number;
  corpo?: unknown;
  message?: string;
}

/**
 * A indeterminação declarada PELO SERVIDOR, ou `null` quando ele não declarou.
 *
 * ⚠️ `null` aqui significa "o servidor não disse que está indeterminado" — não
 * significa "está tudo bem". Quem chama continua tendo de tratar os outros
 * desfechos; esta função responde uma pergunta só.
 *
 * O navegador não tem como decidir isto sozinho: ele sabe que uma requisição
 * demorou, e não sabe se um recibo ficou aberto do outro lado.
 */
export function indeterminacaoDeclarada(erro: unknown): SubidaIndeterminada | null {
  const corpo = (erro as ErroComCorpo | undefined)?.corpo as
    Partial<SubidaIndeterminada> | undefined;
  if (!corpo || typeof corpo !== 'object') return null;
  // ⚠️ UM CORPO QUE DECLARA OUTRO ESTADO NÃO É DESCONHECIDO.
  //
  // A regra frouxa abaixo existe para corpos que NÃO se nomeiam: aí, "proibiu
  // reenvio" é a melhor pista disponível e errar para o lado de "não reenvie" é
  // barato. Mas desde que `/subir` passou a recusar por falha de gravação do
  // plano, existe um corpo que se nomeia `plano_indisponivel`/`plano_recusado`
  // e que também traz `reenvio_permitido: false` — porque o recibo local não
  // fechou. Tratá-lo como indeterminação diria ao operador "pode haver uma
  // campanha criada na conta" sobre uma chamada que NUNCA saiu: é transformar
  // uma falha confirmada em ignorância, que é exatamente a confusão que estas
  // duas funções existem para não deixar acontecer.
  if (typeof corpo.estado === 'string' && corpo.estado !== 'indeterminado') {
    return null;
  }
  if (corpo.estado !== 'indeterminado' && corpo.reenvio_permitido !== false) return null;
  return {
    estado: 'indeterminado',
    mensagem: typeof corpo.mensagem === 'string' ? corpo.mensagem : '',
    recibo_id: corpo.recibo_id ?? null,
    item_id: corpo.item_id ?? null,
    reenvio_permitido: false,
  };
}

/**
 * A recusa RESPONDIDA declarada pelo servidor, ou `null` quando não houve uma.
 *
 * ⚠️ Esta função e `indeterminacaoDeclarada` respondem perguntas OPOSTAS, e
 * confundi-las é o defeito caro deste fluxo. Recusa é resposta: o Google
 * processou, disse não, e o mutate é atômico — nada foi criado, e corrigir o
 * plano e reenviar é seguro. Indeterminação é ignorância: ninguém disse nada,
 * pode haver campanha na conta, e reenviar cria a segunda.
 *
 * Por isso o reconhecimento aqui é ESTRITO — exige o rótulo `recusado`. O
 * inverso (`indeterminacaoDeclarada`) pode ser frouxo e aceitar qualquer corpo
 * que PROÍBA reenvio, porque errar para o lado de "não reenvie" é barato. Errar
 * para o lado de "pode reenviar" custa uma campanha duplicada, e é por isso que
 * esta função não deduz nada.
 */
export function recusaDeclarada(erro: unknown): RecusaDeclarada | null {
  const corpo = (erro as ErroComCorpo | undefined)?.corpo as
    Partial<RecusaDeclarada> | undefined;
  if (!corpo || typeof corpo !== 'object') return null;
  if (corpo.estado !== 'recusado') return null;
  return {
    estado: 'recusado',
    mensagem: typeof corpo.mensagem === 'string' ? corpo.mensagem : '',
    erro_codigo: corpo.erro_codigo ?? null,
    request_id: corpo.request_id ?? null,
    recibo_id: corpo.recibo_id ?? null,
    item_id: corpo.item_id ?? null,
    // Ausência não vira permissão: só `true` explícito do servidor libera.
    reenvio_permitido: corpo.reenvio_permitido === true,
  };
}

/** O id da campanha extraído do `resource_name`, quando o ledger não carimbou. */
export function idDoResourceName(criados: RecursoCriado[] | undefined): string {
  const campanha = (criados ?? []).find((c) => c.resource_name?.includes('/campaigns/'));
  if (!campanha) return '';
  return campanha.resource_name.split('/').pop() ?? '';
}

/**
 * O id da campanha na conta — ledger primeiro, recibo do executor depois.
 *
 * A ordem importa: o ledger é quem carimba o id COM a hora em que foi lido, e é
 * ele que a reconciliação consulta. O `resource_name` só entra quando o ledger
 * não estava disponível no processo que criou a campanha, e nesse caso a tela
 * já está avisando que não há recibo.
 *
 * Devolve `''` quando não há id — e `''` significa "não sei qual campanha é
 * esta", nunca "não criou".
 */
export function idExternoDaCampanha(recibo: ReciboDeLancamento | null): string {
  if (!recibo) return '';
  const doLedger = recibo.ledger?.id_externo;
  if (doLedger) return String(doLedger);
  return idDoResourceName(recibo.criados);
}

/**
 * O que o operador pode fazer em seguida, segundo o desfecho GRAVADO.
 *
 * Nenhuma opção aqui é "tentar de novo" a partir de ignorância: `sem_resposta` e
 * `em_voo` levam a verificar e reconciliar, porque uma chamada pode estar a
 * caminho e a segunda criaria a campanha duas vezes no mesmo leilão.
 */
export type ProximoAto =
  | 'conferir_politica'      // sucesso confirmado, com id carimbado
  | 'reconciliar_na_conta'   // ignorância: em voo, sem resposta, ou sem registro
  | 'corrigir_e_reenviar';   // falha CONFIRMADA pela plataforma

export function proximoAtoSeguro(recibo: ReciboDeLancamento | null): ProximoAto {
  const ledger = recibo?.ledger;
  if (!ledger?.registrado) return 'reconciliar_na_conta';
  if (ledger.desfecho === 'sucesso' && ledger.id_externo) return 'conferir_politica';
  if (ledger.desfecho === 'erro') return 'corrigir_e_reenviar';
  return 'reconciliar_na_conta';
}
