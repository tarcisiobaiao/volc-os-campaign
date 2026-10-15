/**
 * Recusa da gestão → frase de operação.
 *
 * Decide pela `codigo` do contrato (§2), nunca pela `mensagem`: a mensagem é
 * do servidor, muda sem aviso e às vezes cita tabela e gatilho. A mensagem
 * crua continua disponível (`tecnica`) para quem precisa copiar num chamado.
 *
 * Módulo puro: sem React, sem HTTP.
 */
import type { CodigoDeErroDaGestao } from '@/types/gestao';

export interface ErroLegivel {
  /** Frase para o operador. */
  titulo: string;
  /** O que fazer agora, quando há o que fazer. */
  proximoPasso: string | null;
  codigo: string | null;
  status: number | null;
  /** Mensagem crua do servidor (para chamado), quando veio. */
  tecnica: string | null;
  /** `true` = não é recusa: o sistema não respondeu e pode ter feito algo. */
  incerto: boolean;
  /** Ação sugerida pela própria recusa. */
  sugere: 'importar' | 'verificar' | 'recarregar' | null;
}

const FRASES: Record<
  CodigoDeErroDaGestao,
  { titulo: string; proximo?: string; incerto?: boolean; sugere?: ErroLegivel['sugere'] }
> = {
  nao_encontrado: {
    titulo: 'A proposta, aplicação ou campanha não existe mais.',
    proximo: 'Recarregue a fila.',
    sugere: 'recarregar',
  },
  acao_invalida: {
    titulo: 'O pedido não monta uma ação válida.',
    proximo: 'Confira os campos do formulário.',
  },
  estado_nao_permite: {
    titulo: 'A conta, lida agora, não permite esta mudança.',
    proximo:
      'Pode ser orçamento compartilhado sem ciência, valor que já está na conta, estratégia que mudou ou recomendação expirada.',
  },
  sem_motivo: { titulo: 'Falta o motivo.', proximo: 'Escreva por que mudar.' },
  recusa_sem_motivo: { titulo: 'Recusa exige motivo.', proximo: 'Diga por que recusou.' },
  sem_diff_apresentado: {
    titulo: 'A aprovação precisa levar o diff que a tela mostrou.',
    proximo: 'Recarregue a proposta e aprove de novo.',
    sugere: 'recarregar',
  },
  google_recusou: {
    titulo: 'O Google recusou a mudança. A tentativa ficou registrada como erro.',
    proximo: 'Leia o motivo abaixo; nada foi alterado na conta.',
  },
  regra_ausente: {
    titulo: 'Não há regra de gestão publicada para esta conta.',
    proximo:
      'Toda proposta cita a regra que a limita. Publicar a regra (teto, limite, responsável) é decisão do dono da conta.',
  },
  campanha_nao_importada: {
    titulo: 'Esta campanha ainda não tem identidade na gestão.',
    proximo: 'Importe a campanha e proponha de novo.',
    sugere: 'importar',
  },
  evidencia_insuficiente: {
    titulo: 'A janela da regra não tem dados suficientes para sustentar a proposta.',
    proximo: 'Espere a campanha acumular dados ou proponha sob outra regra.',
  },
  regra_exige_delta: {
    titulo: 'Este tipo de ação ainda não é aceito pelo ledger.',
    proximo:
      'A regra vigente não lista esta operação entre as que dispensam tamanho numérico. Incluí-la é decisão de quem publica a regra (nova versão).',
  },
  repropostas_demais: {
    titulo: 'Este mesmo pedido já foi proposto e encerrado vezes demais.',
    proximo: 'Revise o motivo das recusas anteriores na fila antes de propor de novo; o limite existe para impedir laço automático.',
  },
  teto_sem_delta: {
    titulo: 'A proposta passa do teto que a regra fixa para esta operação.',
    proximo: 'Reduza o pedido (itens, escopo, status, estratégia ou ajuste) para caber no teto.',
  },
  limite_pct: {
    titulo: 'A alteração passa do limite percentual da regra.',
    proximo: 'Proponha um passo menor.',
  },
  limite_absoluto: {
    titulo: 'A alteração passa do limite em valor da regra.',
    proximo: 'Proponha um passo menor.',
  },
  teto_orcamento: {
    titulo: 'A verba proposta passa do teto de orçamento da regra.',
    proximo: 'Proponha um valor abaixo do teto.',
  },
  moeda_do_teto: {
    titulo: 'A moeda da conta não é a moeda do teto da regra.',
    proximo: 'A regra precisa declarar teto na moeda desta conta.',
  },
  antes_velho: {
    titulo: 'A leitura da conta ficou velha demais para a regra.',
    proximo: 'Proponha de novo para reler a conta.',
  },
  diff_divergente: {
    titulo: 'O diff que você viu não é o gravado.',
    proximo: 'Recarregue a fila antes de decidir.',
    sugere: 'recarregar',
  },
  ja_decidida: {
    titulo: 'Esta proposta já tem decisão — ela é única e não se reescreve.',
    sugere: 'recarregar',
  },
  proposta_expirada: {
    titulo: 'A proposta venceu.',
    proximo: 'Proponha de novo: o "antes" que ela viu pode não ser mais o da conta.',
  },
  exige_aprovacao_humana: {
    titulo: 'Sem aprovação humana, nada é aplicado.',
    proximo: 'Peça a um administrador que aprove antes.',
  },
  em_carencia: {
    titulo: 'A regra está em carência sobre este alvo.',
    proximo: 'Espere o fim da carência para aplicar.',
  },
  antes_divergiu: {
    titulo: 'A conta mudou desde a proposta. Nada foi enviado.',
    proximo: 'Recuse esta e proponha de novo sobre o estado atual.',
  },
  verificar_antes: {
    titulo: 'Há uma tentativa anterior sem desfecho conhecido.',
    proximo: 'Verifique a aplicação antes de qualquer nova tentativa.',
    sugere: 'verificar',
  },
  aplicacao_em_andamento: {
    titulo: 'Outra pessoa acabou de abrir a aplicação desta proposta.',
    proximo: 'Aguarde e recarregue.',
    sugere: 'recarregar',
  },
  escrita_bloqueada: {
    titulo: 'A trava de escrita do servidor está fechada. Nada foi enviado ao Google.',
    proximo: 'A trava é aberta fora desta tela, por quem administra o servidor.',
  },
  nada_a_reverter: {
    titulo: 'Esta aplicação não tem o que reverter.',
    proximo: 'Se o desfecho é incerto, verifique antes.',
  },
  irreversivel: {
    titulo: 'Esta mudança não tem reverso automático.',
    proximo: 'Para desfazer, proponha a ação inversa.',
  },
  estado_mudou_depois: {
    titulo: 'A conta mudou depois da aplicação; reverter apagaria a mudança de outra pessoa.',
    proximo: 'Proponha a ação inversa sobre o estado atual.',
  },
  reversao_ja_existe: {
    titulo: 'Esta aplicação já tem uma reversão.',
    proximo: 'Para desfazer de novo, proponha a ação inversa como proposta nova.',
  },
  banco_recusou: {
    titulo: 'O ledger recusou o registro.',
    proximo: 'Uma regra do banco barrou a operação; o código técnico vai abaixo.',
  },
  estado_invalido: {
    titulo: 'O estado desta proposta não permite o pedido.',
    sugere: 'recarregar',
  },
  campanha_removida: {
    titulo: 'A campanha está removida no Google; não há o que gerir.',
  },
  regra_invalida: {
    titulo: 'A regra publicada não passa na validação do motor.',
    proximo: 'Quem publicou a regra precisa corrigi-la.',
  },
  plataforma: {
    titulo: 'A regra citada não vale para Google Ads.',
  },
  fora_do_escopo: {
    titulo: 'Esta conta não está na árvore de contas da casa.',
  },
  valor_sem_origem: {
    titulo: 'Falta dizer de onde veio o valor de verba ou lance.',
    proximo:
      'Digite o valor no formulário: o número que você digita entra como valor do operador. Se o pedido veio de uma automação, ela precisa mandar a origem.',
  },
  valor_sem_autoridade: {
    titulo: 'A origem deste valor não autoriza gastar verba nem mudar lance.',
    proximo:
      'Só vale número digitado por uma pessoa logada (com motivo de ao menos 10 caracteres) ou lido pelo VOLC na própria conta. CPC de SERP, Semrush, Keyword Planner ou estimativa não liberam verba. Se a proposta é antiga e não tem origem gravada, recuse-a e proponha de novo.',
  },
  proposta_ilegivel: {
    titulo: 'A proposta gravada não reconstrói uma ação.',
    proximo: 'Recuse-a e proponha de novo.',
  },
  indisponivel: {
    titulo: 'O banco ou o Google não respondeu. Não é recusa.',
    proximo: 'Tente de novo em instantes.',
  },
  escopo_indisponivel: {
    titulo: 'Não deu para conferir se a conta é da casa. Não é recusa.',
    proximo: 'Tente de novo em instantes.',
  },
  sdk_ausente: {
    titulo: 'O servidor está sem a biblioteca do Google Ads.',
    proximo: 'Avise quem administra o backend.',
  },
  motor_ausente: {
    titulo: 'O servidor está sem o motor de gestão.',
    proximo: 'Avise quem administra o backend.',
  },
  sem_resposta: {
    titulo: 'A escrita saiu e a resposta não voltou: a conta PODE ter mudado.',
    proximo: 'Verifique a aplicação antes de qualquer outra coisa.',
    incerto: true,
    sugere: 'verificar',
  },
  desfecho_nao_gravado: {
    titulo: 'O Google respondeu e o ledger não gravou o desfecho.',
    proximo: 'Verifique a aplicação.',
    incerto: true,
    sugere: 'verificar',
  },
};

function campo(erro: unknown, nome: string): unknown {
  if (typeof erro !== 'object' || erro === null) return undefined;
  return (erro as Record<string, unknown>)[nome];
}

/** A `codigo` do contrato, venha de `ErroDaGestao` ou de um `corpo` cru. */
export function codigoDoErro(erro: unknown): string | null {
  const direto = campo(erro, 'codigo');
  if (typeof direto === 'string') return direto;
  const corpo = campo(erro, 'corpo');
  const c = campo(corpo, 'codigo');
  return typeof c === 'string' ? c : null;
}

export function detalheDoErro(erro: unknown): unknown {
  const d = campo(erro, 'detalhe');
  if (d !== undefined) return d;
  return campo(campo(erro, 'corpo'), 'detalhe');
}

/** Complementa a frase com o que `detalhe` traz e serve à tela. */
function complemento(codigo: string | null, detalhe: unknown): string | null {
  if (!detalhe || typeof detalhe !== 'object') return null;
  const d = detalhe as Record<string, unknown>;
  if (codigo === 'evidencia_insuficiente' && Array.isArray(d.faltantes) && d.faltantes.length) {
    return `Faltam: ${d.faltantes.join(', ')}.`;
  }
  if (codigo === 'antes_divergiu' && Array.isArray(d.campos) && d.campos.length) {
    return `Mudou: ${d.campos.join(', ')}.`;
  }
  if (codigo === 'em_carencia' && typeof d.ate === 'string') {
    return `Carência até ${d.ate}.`;
  }
  if (codigo === 'limite_pct' && d.limite != null) {
    return `Pedido: ${d.delta_pct ?? '?'}% · limite: ${d.limite}%.`;
  }
  if (codigo === 'regra_exige_delta' && Array.isArray(d.operacoes_sem_delta_da_regra)) {
    return d.operacoes_sem_delta_da_regra.length
      ? `A regra aceita sem delta: ${d.operacoes_sem_delta_da_regra.join(', ')}.`
      : 'A regra não aceita nenhuma operação sem delta.';
  }
  if (codigo === 'teto_sem_delta') {
    const partes = [typeof d.motivo === 'string' ? d.motivo : null, d.teto != null ? `Teto: ${JSON.stringify(d.teto)}.` : null];
    return partes.filter(Boolean).join(' ') || null;
  }
  if (codigo === 'banco_recusou' && typeof d.sqlstate === 'string') {
    return `sqlstate ${d.sqlstate}.`;
  }
  return null;
}

export function erroLegivel(erro: unknown): ErroLegivel {
  const codigo = codigoDoErro(erro);
  const statusBruto = campo(erro, 'status');
  const status = typeof statusBruto === 'number' ? statusBruto : null;
  const mensagem = campo(erro, 'message');
  const tecnica = typeof mensagem === 'string' && mensagem ? mensagem : null;
  const frase = codigo ? FRASES[codigo as CodigoDeErroDaGestao] : undefined;

  if (frase) {
    const extra = complemento(codigo, detalheDoErro(erro));
    return {
      titulo: frase.titulo,
      proximoPasso: [frase.proximo, extra].filter(Boolean).join(' ') || null,
      codigo,
      status,
      tecnica,
      incerto: Boolean(frase.incerto),
      sugere: frase.sugere ?? null,
    };
  }
  if (status === 401) {
    return {
      titulo: 'Sua sessão expirou.',
      proximoPasso: 'Entre de novo.',
      codigo,
      status,
      tecnica,
      incerto: false,
      sugere: null,
    };
  }
  if (status === 403) {
    return {
      titulo: 'Esta operação exige papel administrativo.',
      proximoPasso: 'Peça a um administrador.',
      codigo,
      status,
      tecnica,
      incerto: false,
      sugere: null,
    };
  }
  if (status != null && status >= 500) {
    return {
      titulo: 'O servidor não respondeu. Não é recusa.',
      proximoPasso: 'Tente de novo em instantes.',
      codigo,
      status,
      tecnica,
      incerto: false,
      sugere: null,
    };
  }
  return {
    titulo: tecnica ?? 'A operação falhou.',
    proximoPasso: null,
    codigo,
    status,
    tecnica,
    incerto: false,
    sugere: null,
  };
}
