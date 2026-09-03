/**
 * Prontidão do ativo para receber peça, publicar e passar pelo QA visual.
 *
 * Lógica PURA: nenhum React, nenhum fetch. É aqui que mora a decisão de qual
 * dos dez estados a tela mostra, e é por isso que ela pode ser provada sem
 * montar componente.
 *
 * ## As três afirmações que este arquivo se recusa a colapsar
 *
 * **1. "Não conferimos" ≠ "está errado".** `nao_persistido`, `nao_executado`,
 * `indeterminado` e `corrigir` são fatos diferentes. Um booleano `qaOk` faria a
 * tela mostrar a mesma cara para "ninguém rodou o QA" e para "o QA reprovou" —
 * e as duas pedem ações opostas de quem está olhando.
 *
 * **2. "Pode receber peça" ≠ "pode publicar".** O primeiro é sobre o ativo
 * existir e não estar aposentado. O segundo exige referência de acesso
 * verificada e perfil de navegador relacionado. Um "pronto" único mandaria a
 * fábrica criativa produzir para uma página que ninguém consegue abrir.
 *
 * **3. Indeterminado NUNCA é verde.** `TOM_DA_PRONTIDAO` só devolve `sucesso`
 * para `aprovado`, e há teste que falha se alguém acrescentar outro. Pintar de
 * verde um QA que não conseguiu concluir é a maneira mais barata de ensinar a
 * operação a ignorar o portão visual.
 */

/** Os seis estados de QA que o backend publica em `qa_visual.estado`. */
export type EstadoDeQa =
  | 'nao_persistido'
  | 'nao_executado'
  | 'em_execucao'
  | 'indeterminado'
  | 'corrigir'
  | 'aprovado';

/**
 * Os dez estados da superfície. Nenhum é sinônimo de outro.
 *
 * `vazio` é "o Cofre não tem esta página"; `indisponivel` é "o Cofre não
 * respondeu". A distinção é a mesma que `AssetVaultContent` já preserva no
 * inventário, e ela some se as duas virarem "sem dados".
 */
export type EstadoDaProntidao =
  | 'carregando'
  | 'vazio'
  | 'indisponivel'
  | 'bloqueado'
  | 'pronto_para_peca'
  | 'pronto_para_qa'
  | 'qa_em_execucao'
  | 'corrigir'
  | 'indeterminado'
  | 'aprovado';

export type TomDaProntidao = 'neutro' | 'info' | 'atencao' | 'erro' | 'sucesso';

export interface BloqueioDeProntidao {
  codigo: string;
  mensagem: string;
  onde: string;
}

export interface ArtefatoVisual {
  /** Referência privada (`vpartifact://…`), nunca caminho de disco. */
  referencia: string;
  sha256: string;
  bytes: number;
  mime: string;
  criado_em: string;
}

export interface ProntidaoVisualPayload {
  ativo_id: string | null;
  destino: Record<string, unknown>;
  pagina: { presente: boolean; motivo: string };
  referencia_de_credencial: {
    presente: boolean;
    verificada: boolean;
    provider: string | null;
    nome_logico: string | null;
    verificacao_estado: string | null;
    verificado_em: string | null;
  };
  perfil_de_navegador: { presente: boolean; rotulo: string | null; ativo_id: string | null };
  broker: { estado: 'configurado' | 'nao_configurado'; motivo: string };
  qa_visual: {
    estado: EstadoDeQa;
    motivo: string;
    job: Record<string, unknown> | null;
    veredito: string | null;
    artefato: ArtefatoVisual | null;
  };
  pronto_para_receber_peca: boolean;
  pronto_para_publicar: boolean;
  pronto_para_qa: boolean;
  bloqueios: BloqueioDeProntidao[];
  bloqueios_do_cofre: string[];
  proxima_acao: string;
}

export interface EntradaDaProntidao {
  carregando: boolean;
  indisponivel: boolean;
  prontidao: ProntidaoVisualPayload | null;
}

/**
 * Decide o estado. A ORDEM é a regra, e ela não é arbitrária.
 *
 * O veredito do QA vem antes das prontidões porque ele é o fato mais recente
 * sobre a superfície: um ativo com QA reprovado não deve aparecer como "pronto
 * para QA" só porque a cadeia de acesso continua completa.
 */
export function estadoDaProntidao(entrada: EntradaDaProntidao): EstadoDaProntidao {
  if (entrada.carregando) return 'carregando';
  if (entrada.indisponivel || !entrada.prontidao) return 'indisponivel';

  const p = entrada.prontidao;
  if (!p.pagina.presente) return 'vazio';

  switch (p.qa_visual.estado) {
    case 'aprovado': return 'aprovado';
    case 'corrigir': return 'corrigir';
    case 'indeterminado': return 'indeterminado';
    case 'em_execucao': return 'qa_em_execucao';
    default: break;
  }

  if (!p.pronto_para_publicar) {
    return p.pronto_para_receber_peca ? 'pronto_para_peca' : 'bloqueado';
  }
  if (!p.pronto_para_qa) return 'bloqueado';
  return 'pronto_para_qa';
}

export const ROTULO_DA_PRONTIDAO: Record<EstadoDaProntidao, string> = {
  carregando: 'Apurando a prontidão',
  vazio: 'Página real não cadastrada',
  indisponivel: 'Prontidão indisponível',
  bloqueado: 'Bloqueado para QA visual',
  pronto_para_peca: 'Pronto para receber peça',
  pronto_para_qa: 'Pronto para QA visual',
  qa_em_execucao: 'QA visual em andamento',
  corrigir: 'QA visual pede correção',
  indeterminado: 'QA visual indeterminado',
  aprovado: 'Aprovado por revisão humana',
};

/**
 * ⚠️ `sucesso` aparece UMA vez, e é em `aprovado`.
 *
 * `indeterminado` é `atencao` de propósito: a captura não conseguiu concluir, e
 * isso não reprova a página nem a aprova. Pintá-lo de verde faria a operação
 * ler "deu certo" onde o sistema disse "não sei".
 */
export const TOM_DA_PRONTIDAO: Record<EstadoDaProntidao, TomDaProntidao> = {
  carregando: 'neutro',
  vazio: 'neutro',
  indisponivel: 'erro',
  bloqueado: 'atencao',
  pronto_para_peca: 'info',
  pronto_para_qa: 'info',
  qa_em_execucao: 'info',
  corrigir: 'erro',
  indeterminado: 'atencao',
  aprovado: 'sucesso',
};

/**
 * A frase que explica o estado sem depender da cor.
 *
 * Requisito de acessibilidade explícito: quem não distingue as cores precisa
 * chegar à mesma conclusão lendo. Por isso cada estado tem texto próprio, e o
 * componente rende rótulo + ícone + frase, nunca só um ponto colorido.
 */
export const EXPLICACAO_DA_PRONTIDAO: Record<EstadoDaProntidao, string> = {
  carregando: 'Consultando o Cofre, o broker e o último job de prova visual.',
  vazio:
    'O Cofre ainda não tem a página real deste ativo. Sem ela não há superfície para conferir — e inventar uma seria pior que o vazio.',
  indisponivel:
    'Não foi possível apurar a prontidão agora. Isso não significa que o ativo esteja irregular: significa que não sabemos.',
  bloqueado:
    'Falta algo na cadeia antes de o QA visual poder rodar. O primeiro bloqueio da lista é o que destrava os seguintes.',
  pronto_para_peca:
    'O ativo existe e pode receber peça. Ainda NÃO está pronto para publicar: falta completar a cadeia de acesso.',
  pronto_para_qa:
    'Cadeia completa e broker configurado. Nenhuma prova visual foi executada ainda.',
  qa_em_execucao:
    'A captura está em andamento ou já ocorreu e aguarda revisão humana. Capturado não é aprovado.',
  corrigir:
    'A prova visual encontrou divergência entre o que foi publicado e o esperado. Corrija a superfície e rode de novo.',
  indeterminado:
    'A prova visual não conseguiu concluir. Falha do executor NÃO reprova a página — investigue o AdsPower e repita.',
  aprovado:
    'Uma pessoa revisou a captura e aprovou. Nenhuma avaliação automática produz este estado.',
};

/** O bloqueio que a tela destaca. Uma lista de dez não diz o que fazer agora. */
export function primeiroBloqueio(p: ProntidaoVisualPayload | null): BloqueioDeProntidao | null {
  return p?.bloqueios?.[0] ?? null;
}

/**
 * Rótulo curto do artefato, para o operador reconhecer a captura sem abri-la.
 *
 * Mostra os 12 primeiros caracteres do SHA-256 — não a referência inteira, que
 * carrega o nome lógico do perfil, e nunca um caminho de disco.
 */
export function rotuloDoArtefato(artefato: ArtefatoVisual | null): string | null {
  if (!artefato?.sha256) return null;
  return `sha256 ${artefato.sha256.slice(0, 12)}…`;
}
