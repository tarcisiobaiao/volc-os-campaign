/**
 * A REAUDITORIA AO VIVO, do lado da tela.
 *
 * ## O que este arquivo existe para impedir
 *
 * A ação que emite o recibo de escopo `live` tem DUAS etapas, e a separação é o
 * assunto: um portão que se autoaprova em silêncio não é portão. Se a tela
 * pudesse chamar `confirmar` direto — ou reaproveitar um hash de uma prova que
 * o operador nunca viu —, a confirmação humana viraria decoração.
 *
 * Então o vocabulário aqui é fechado em torno de uma máquina de estados de
 * quatro posições, e `confirmar` só existe como ação possível numa delas.
 *
 * ## A regra que organiza tudo aqui
 *
 * **Nada é derivado desta camada.** Quem lê a página e avalia é
 * `app.redator.reauditoria`, que tem o HTML e as três leituras. O que este
 * arquivo faz é TRADUZIR a prova — preservando as distinções que o backend
 * paga para manter, e reusando o vocabulário de `prontidao.ts` para que o
 * operador leia a mesma língua nas duas telas.
 *
 * ⚠️ E nunca verde por ausência. Prova que não foi feita é `INDETERMINADO`;
 * prova com bloqueio é `BLOQUEADO`; prova com desconhecido também é
 * `INDETERMINADO`, nunca `APTO` — um desconhecido é uma verificação exigida que
 * não pôde ser concluída, e ele reprova igual a um bloqueio.
 *
 * ## Por que as chamadas são INJETADAS
 *
 * `requisitar` entra por parâmetro em vez de este módulo importar o cliente de
 * API. Duas razões: o cliente vive noutro módulo, cuja base do backend só ele
 * conhece; e uma função que recebe o transporte é testável sem `fetch` de
 * mentira e sem `jsdom`.
 */

import type { EstadoDaProntidao } from '@/lib/landing-policy/prontidao';

/** Espelha `app.redator.reauditoria.ESQUEMA_DA_PROVA`. */
export const ESQUEMA_DA_PROVA = 'landing_policy_reaudit_proof.v1';

/** Espelha `app.redator.reauditoria.CHAVE_DO_RECIBO_ANTERIOR`. */
export const CHAVE_DO_RECIBO_ANTERIOR = 'landing_policy_receipt_anterior';

/**
 * Os donos possíveis de um bloqueio, e por que a distinção é acionável.
 *
 * ⚠️ `LINK_EXTERNO_NO_CHROME` e `LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO`
 * descrevem o mesmo fato físico — um hyperlink externo clicável num destino
 * pago — e mesmo assim têm donos diferentes, porque o CONSERTO é feito em
 * lugares diferentes. Mandar o operador ao repositório errado é como um
 * bloqueio fica seis semanas aberto.
 */
export const ROTULO_DO_DONO: Record<string, string> = {
  'tema/WordPress': 'tema / WordPress',
  funil: 'conteúdo do funil',
};

export function textoDoDono(dono: string | null | undefined): string {
  const chave = (dono ?? '').trim();
  if (!chave) return 'dono não atribuído';
  return ROTULO_DO_DONO[chave] ?? chave;
}

/**
 * O próximo ato, por dono. É a frase que o operador executa.
 *
 * ⚠️ Ela é curta de propósito e não promete resultado: "remover do template" é
 * o que dá para afirmar; "isto libera a campanha" não é, porque a aprovação do
 * Google continua desconhecida deste lado.
 */
export const ACAO_DO_DONO: Record<string, string> = {
  'tema/WordPress':
    'Sai do template do site (cabeçalho, rodapé, navegação ou widget) — ou o '
    + 'host é declarado no chrome do site, com procedência. Allowlist de '
    + 'cliente não limpa este.',
  funil:
    'Sai do texto que o motor escreveu. A fonte fica no dossiê de evidência e '
    + 'é citada em prosa; ela não vira âncora no corpo de um destino pago.',
};

export function acaoDoDono(dono: string | null | undefined): string | null {
  return ACAO_DO_DONO[(dono ?? '').trim()] ?? null;
}

// ═══════════════════════════════════════════════════════════════════════════
// O CONTRATO QUE VEM DO BACKEND
// ═══════════════════════════════════════════════════════════════════════════

/** Um achado da prova. `owner` é o que o recibo de política não carrega. */
export interface AchadoDaReauditoria {
  code: string;
  severity: string;
  message: string;
  owner: string;
  evidence?: unknown;
}

export interface DesconhecidoDaReauditoria {
  verificacao: string;
  status?: string;
  motivo: string;
}

/** Um link do inventário. ⚠️ Sem texto de âncora: o backend o remove. */
export interface LinkDaReauditoria {
  host: string;
  regiao: string;
  classe: string;
  em_botao: boolean;
  oculto: boolean;
}

export interface DiffDaReauditoria {
  tinha_recibo: boolean;
  escopo_anterior: string | null;
  impressao_anterior_12: string | null;
  impressao_agora_12: string;
  mudou: boolean;
  comparavel: boolean;
}

export interface ProvaDaReauditoria {
  schema: string;
  url_canonica: string;
  impressao_da_prova: string;
  elegivel: boolean;
  veredito: string;
  motivos: string[];
  bloqueios: AchadoDaReauditoria[];
  riscos: AchadoDaReauditoria[];
  desconhecidos: DesconhecidoDaReauditoria[];
  recibo_candidato: Record<string, unknown>;
  inventario_de_links: LinkDaReauditoria[];
  diff_com_o_recibo_anterior: DiffDaReauditoria;
  lido_em_epoch: number;
  lido_em: string;
}

export interface RespostaDaProva {
  run_row_id: number;
  page_number: number;
  prova: ProvaDaReauditoria;
}

export interface RespostaDaConfirmacao {
  run_row_id: number;
  page_number: number;
  recibo: Record<string, unknown>;
  gravado: boolean;
  prova: ProvaDaReauditoria;
}

// ═══════════════════════════════════════════════════════════════════════════
// A MÁQUINA DE ESTADOS DAS DUAS ETAPAS
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Onde o operador está no fluxo. `confirmar` só é possível em `PROVADO`.
 *
 * ⚠️ `PROVADO` significa "existe uma prova ELEGÍVEL na tela, e o hash dela está
 * na mão". Uma prova que reprovou fica em `REPROVADO` e não habilita nada — a
 * tela não é o lugar de contornar o portão.
 */
export type EtapaDaReauditoria =
  | 'SEM_PROVA'
  | 'LENDO'
  | 'PROVADO'
  | 'REPROVADO'
  | 'CONFIRMADO'
  | 'CONFLITO'
  | 'ERRO';

export const ROTULO_DA_ETAPA: Record<EtapaDaReauditoria, string> = {
  SEM_PROVA: 'nenhuma leitura ao vivo nesta sessão',
  LENDO: 'lendo a página no ar…',
  PROVADO: 'prova pronta — falta a sua confirmação',
  REPROVADO: 'a página no ar não passou',
  CONFIRMADO: 'recibo ao vivo gravado',
  CONFLITO: 'a página mudou entre a prova e a confirmação',
  ERRO: 'a leitura ao vivo não concluiu',
};

/**
 * O que fazer agora, em uma frase. É o texto que fica sob o botão.
 *
 * ⚠️ `CONFLITO` manda PROVAR DE NOVO, e não "tentar de novo": confirmar de novo
 * com o mesmo hash daria o mesmo conflito, e repetir a mesma ação esperando
 * outro resultado é o que ensina o operador a ignorar o aviso.
 */
export const PROXIMA_ACAO: Record<EtapaDaReauditoria, string> = {
  SEM_PROVA:
    'Ler a página no ar. A leitura não altera nada — nem a página, nem o '
    + 'registro, nem campanha alguma.',
  LENDO: 'Três leituras públicas: desktop, celular e AdsBot.',
  PROVADO:
    'Confira o veredito e os bloqueios acima. Confirmar re-lê a página e grava '
    + 'o recibo ao vivo — nada além do recibo.',
  REPROVADO:
    'Consertar o que está listado, no dono indicado, e provar de novo. A tela '
    + 'não tem caminho para contornar o portão.',
  CONFIRMADO:
    'O recibo ao vivo está no registro desta página. A aprovação do Google '
    + 'continua desconhecida: este portão lê HTML.',
  CONFLITO: 'Provar de novo. A prova antiga descreve uma página que já não está no ar.',
  ERRO: 'Provar de novo quando o destino voltar a responder. Sem leitura não há prova.',
};

/**
 * O estado de prontidão desta prova, no vocabulário fechado de `prontidao.ts`.
 *
 * ⚠️ Desconhecido NUNCA pinta verde, e não vira `BLOQUEADO` também: são coisas
 * diferentes. `BLOQUEADO` é "olhei e achei o defeito"; `INDETERMINADO` é
 * "faltou olhar" — e só o segundo é resolvido lendo de novo.
 */
export function estadoDaProva(prova: ProvaDaReauditoria | null): EstadoDaProntidao {
  if (!prova) return 'INDETERMINADO';
  if (prova.elegivel) return 'APTO';
  if (prova.bloqueios.length > 0) return 'BLOQUEADO';
  return 'INDETERMINADO';
}

/**
 * A etapa, apurada do que a tela tem em mãos.
 *
 * `confirmadaCom` é o hash que a última confirmação bem-sucedida carregou. Ele
 * é comparado com o da prova atual porque uma prova NOVA depois de uma
 * confirmação volta a pedir confirmação — senão o botão ficaria desabilitado
 * mostrando "confirmado" sobre uma leitura que ninguém aprovou.
 */
export function etapaDaReauditoria(entrada: {
  prova: ProvaDaReauditoria | null;
  lendo: boolean;
  conflito: boolean;
  erro: string | null;
  confirmadaCom: string | null;
}): EtapaDaReauditoria {
  if (entrada.lendo) return 'LENDO';
  if (entrada.conflito) return 'CONFLITO';
  if (entrada.erro) return 'ERRO';
  if (!entrada.prova) return 'SEM_PROVA';
  if (entrada.confirmadaCom && entrada.confirmadaCom === entrada.prova.impressao_da_prova) {
    return 'CONFIRMADO';
  }
  return entrada.prova.elegivel ? 'PROVADO' : 'REPROVADO';
}

/**
 * O botão de confirmar habilita?
 *
 * ⚠️ Três condições, e nenhuma delas é "o operador quer". Sem prova não há o
 * que confirmar; prova reprovada não vira aprovação por clique; e sem hash não
 * há vínculo com a leitura que o operador viu — que é o que a segunda etapa
 * existe para provar.
 */
export function podeConfirmar(
  prova: ProvaDaReauditoria | null,
  etapa: EtapaDaReauditoria,
): boolean {
  return etapa === 'PROVADO' && !!prova?.elegivel && !!prova?.impressao_da_prova;
}

/** Doze caracteres: bastam para reconciliar com o backend, e não convidam a copiar identidade. */
export function curto(hash: string | null | undefined): string {
  const bruto = (hash ?? '').trim();
  return bruto ? bruto.slice(0, 12) : '—';
}

/**
 * O diff contra o recibo anterior, em uma frase que não colapsa estados.
 *
 * ⚠️ "não havia com o que comparar" NÃO é "nada mudou". O recibo do portão 2
 * impressiona o ARTEFATO — o corpo que o motor escreveu — e a leitura é a
 * página dentro do tema do WordPress. Comparar os dois emitia deriva em 100%
 * das páginas reais; é por isso que o escopo aparece na frase.
 */
export function textoDoDiff(diff: DiffDaReauditoria | null | undefined): string {
  if (!diff) return 'sem diff nesta resposta.';
  if (!diff.tinha_recibo) {
    return 'Primeira avaliação desta página: não havia recibo anterior para comparar.';
  }
  if (!diff.comparavel) {
    return (
      `O recibo anterior é de escopo "${diff.escopo_anterior ?? 'desconhecido'}", `
      + 'que impressiona o corpo escrito pelo motor — não a página dentro do tema. '
      + 'Não havia com o que comparar, e isso não é o mesmo que "nada mudou".'
    );
  }
  return diff.mudou
    ? `A página no ar mudou desde o último recibo ao vivo `
      + `(${diff.impressao_anterior_12} → ${diff.impressao_agora_12}).`
    : `A página no ar é a mesma do último recibo ao vivo (${diff.impressao_agora_12}).`;
}

/** Os bloqueios agrupados por dono — é assim que viram duas listas de tarefas. */
export function bloqueiosPorDono(
  bloqueios: AchadoDaReauditoria[],
): { dono: string; itens: AchadoDaReauditoria[] }[] {
  const mapa = new Map<string, AchadoDaReauditoria[]>();
  for (const b of bloqueios) {
    const dono = (b.owner ?? '').trim() || 'dono não atribuído';
    const atual = mapa.get(dono);
    if (atual) atual.push(b);
    else mapa.set(dono, [b]);
  }
  return [...mapa.entries()]
    .map(([dono, itens]) => ({ dono, itens }))
    .sort((a, b) => a.dono.localeCompare(b.dono));
}

// ═══════════════════════════════════════════════════════════════════════════
// O TRANSPORTE
// ═══════════════════════════════════════════════════════════════════════════

/** A assinatura do cliente de API. Injetada — ver o cabeçalho deste arquivo. */
export type RequisitarApi = <T>(caminho: string, init?: RequestInit) => Promise<T>;

export function caminhoDaProva(runRowId: number, pageNumber: number): string {
  return `/api/publicacao/redator/runs/${runRowId}/reauditar/${pageNumber}/provar`;
}

export function caminhoDaConfirmacao(runRowId: number, pageNumber: number): string {
  return `/api/publicacao/redator/runs/${runRowId}/reauditar/${pageNumber}/confirmar`;
}

export interface ClienteDeReauditoria {
  provar(runRowId: number, pageNumber: number): Promise<RespostaDaProva>;
  confirmar(
    runRowId: number,
    pageNumber: number,
    impressaoDaProva: string,
  ): Promise<RespostaDaConfirmacao>;
}

/**
 * O cliente das duas rotas, sobre o transporte que o chamador entrega.
 *
 * ⚠️ `confirmar` manda APENAS a impressão. Se o corpo carregasse o recibo
 * candidato, o cliente escolheria o que vai ser gravado e o hash viraria
 * crachá — quem tem o texto entra. O recibo gravado é o que o backend emite
 * relendo a página.
 */
export function criarClienteDeReauditoria(requisitar: RequisitarApi): ClienteDeReauditoria {
  return {
    provar: (runRowId, pageNumber) =>
      requisitar<RespostaDaProva>(caminhoDaProva(runRowId, pageNumber), { method: 'POST' }),
    confirmar: (runRowId, pageNumber, impressaoDaProva) =>
      requisitar<RespostaDaConfirmacao>(caminhoDaConfirmacao(runRowId, pageNumber), {
        method: 'POST',
        body: JSON.stringify({ impressao_da_prova: impressaoDaProva }),
      }),
  };
}

/**
 * O 409 de conflito, reconhecido pela FORMA e não pela mensagem.
 *
 * ⚠️ Casar por texto de mensagem é como um erro traduzido deixa de ser
 * reconhecido. O backend manda `proxima_acao: "provar de novo"` dentro do
 * `detail` justamente para que a tela ramifique por estrutura.
 */
export function ehConflitoDeProva(erro: unknown): boolean {
  const detalhe = (erro as { detail?: unknown })?.detail
    ?? (erro as { corpo?: { detail?: unknown } })?.corpo?.detail;
  if (!detalhe || typeof detalhe !== 'object') return false;
  return (detalhe as { proxima_acao?: unknown }).proxima_acao === 'provar de novo';
}

/** A mensagem legível de um erro de qualquer uma das duas rotas. */
export function mensagemDoErro(erro: unknown): string {
  const detalhe = (erro as { detail?: unknown })?.detail
    ?? (erro as { corpo?: { detail?: unknown } })?.corpo?.detail;
  if (typeof detalhe === 'string') return detalhe;
  if (detalhe && typeof detalhe === 'object') {
    const dito = (detalhe as { erro?: unknown }).erro;
    if (typeof dito === 'string') return dito;
  }
  if (erro instanceof Error && erro.message) return erro.message;
  return 'A reauditoria não concluiu, e o motivo não veio na resposta.';
}
