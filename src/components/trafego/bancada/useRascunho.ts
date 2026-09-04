/**
 * O rascunho da Bancada, preservado dentro da ABA.
 *
 * ## O que se perdia
 *
 * A tela anterior não persistia NADA: nem `sessionStorage`, nem `localStorage`,
 * nem autosave. Medido — um F5 devolvia orçamento a `'10'`, lance a `'0.12'`,
 * estratégia a `'MANUAL_CPC'`, graduação a `30`, e zerava certificações,
 * negativas e os match types escolhidos keyword a keyword. Pior: a seleção era
 * RE-SEMEADA do servidor marcando tudo que a mineração aprovou, então desmarcar
 * vinte termos e dar F5 devolvia os vinte marcados, silenciosamente.
 *
 * ## Por que `sessionStorage`, e por que só estes campos
 *
 * `sessionStorage` morre com a aba. É o alcance certo: o rascunho é do trabalho
 * em curso, não uma preferência do usuário, e um rascunho de campanha
 * sobrevivendo por semanas num `localStorage` é uma armadilha — o operador
 * voltaria a um pedido montado sobre um cluster que já mudou.
 *
 * ⚠️ NENHUM SEGREDO ENTRA AQUI. Não guardamos `customer_id`, token, id de
 * conversão nem qualquer coisa lida da conta: o estado remoto continua sendo a
 * autoridade e é sempre relido. O que se guarda é exclusivamente o que o
 * OPERADOR digitou — que é justamente o que o servidor não sabe repor.
 *
 * A chave inclui oportunidade e run porque dois funis abertos em abas diferentes
 * não podem trocar de rascunho entre si.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import type { CriterioDeKeyword } from '@/types/trafego';

/** Só o que o operador digitou. Nada lido da conta entra neste tipo. */
export interface RascunhoDaBancada {
  orcamento: string;
  lance: string;
  estrategia: string;
  graduacao: number;
  certificacoes: string[];
  /**
   * ⚠️ AS EXCLUSÕES INTEIRAS, e não os textos delas.
   *
   * A primeira versão deste rascunho guardava `string[]` e remontava o critério
   * com `match_type: 'PHRASE'` fixo. Isso PERDIA duas coisas que o operador
   * declarou: a correspondência — excluir `simulador` em EXACT bloqueia um
   * termo, em PHRASE bloqueia uma família inteira, e a diferença muda o que a
   * campanha compra — e o `motivo`, que é a frase que aparece na revisão e
   * responde "por que este termo está fora?" três meses depois.
   *
   * Guardar o objeto custa alguns bytes de `sessionStorage` e preserva a
   * decisão. `CriterioDeKeyword` é serializável por construção: só primitivos,
   * mais uma `evidencia` que também é.
   */
  negativas: CriterioDeKeyword[];
  matchPorKeyword: Record<string, string>;
  /** Os termos que o operador tirou do conjunto aprovado, por texto exato. */
  keywordsFora: string[];
  vertical: string | null;
  modeloDaCopy: string;
}

export const RASCUNHO_VAZIO: RascunhoDaBancada = {
  // ⚠️ Vazio, e não `'10'`/`'0.12'`. Um default numérico num campo de dinheiro é
  // um valor que ninguém declarou aparecendo como se alguém tivesse declarado —
  // e `Number('') || 0` mandava esse zero para o pedido em silêncio.
  orcamento: '',
  lance: '',
  estrategia: 'MANUAL_CPC',
  graduacao: 30,
  certificacoes: [],
  negativas: [],
  matchPorKeyword: {},
  keywordsFora: [],
  vertical: null,
  modeloDaCopy: '',
};

const PREFIXO = 'volc.bancada.rascunho';

export function chaveDoRascunho(opportunityId: number, runId?: number | null): string {
  return `${PREFIXO}.${opportunityId}.${runId ?? 'sem-run'}`;
}

function ler(chave: string): RascunhoDaBancada | null {
  try {
    const cru = window.sessionStorage.getItem(chave);
    if (!cru) return null;
    const o = JSON.parse(cru) as Partial<RascunhoDaBancada>;
    if (typeof o !== 'object' || o === null) return null;
    // Mescla sobre o vazio: um rascunho gravado por uma versão anterior do
    // formulário não pode derrubar a tela por falta de campo.
    return { ...RASCUNHO_VAZIO, ...o };
  } catch {
    // `sessionStorage` levanta em aba privada de alguns navegadores e quando o
    // usuário bloqueia dados de site. Perder o rascunho é aceitável; derrubar a
    // tela de lançamento por causa dele não é.
    return null;
  }
}

/**
 * O rascunho e o gravador. A leitura acontece UMA vez, no primeiro render, para
 * o valor inicial não piscar de vazio para preenchido.
 */
export function useRascunho(opportunityId: number, runId?: number | null) {
  const chave = chaveDoRascunho(opportunityId, runId);
  const [rascunho, setRascunho] = useState<RascunhoDaBancada>(
    () => (opportunityId ? ler(chave) : null) ?? RASCUNHO_VAZIO,
  );

  // A chave muda quando o operador navega para outro funil sem recarregar.
  const chaveAnterior = useRef(chave);
  useEffect(() => {
    if (chaveAnterior.current === chave) return;
    chaveAnterior.current = chave;
    setRascunho(ler(chave) ?? RASCUNHO_VAZIO);
  }, [chave]);

  useEffect(() => {
    if (!opportunityId) return;
    try {
      window.sessionStorage.setItem(chave, JSON.stringify(rascunho));
    } catch {
      // Ver o comentário de `ler`. Silencioso de propósito: um aviso de
      // armazenamento no meio de um lançamento é ruído sobre a decisão errada.
    }
  }, [chave, rascunho, opportunityId]);

  const alterar = useCallback(
    <K extends keyof RascunhoDaBancada>(campo: K, valor: RascunhoDaBancada[K]) =>
      setRascunho((r) => ({ ...r, [campo]: valor })),
    [],
  );

  const descartar = useCallback(() => {
    setRascunho(RASCUNHO_VAZIO);
    try { window.sessionStorage.removeItem(chave); } catch { /* ver `ler` */ }
  }, [chave]);

  return { rascunho, alterar, descartar };
}

/**
 * Um número digitado, ou `null`.
 *
 * ⚠️ NUNCA `Number(x) || 0`. Era isso que `NovaCampanhaPage.tsx:391-392` fazia
 * com orçamento e lance: texto inválido virava `0` no pedido, em silêncio — e
 * um orçamento zero é um pedido que o operador não fez. Vírgula é aceita porque
 * o teclado brasileiro a produz e a mesa de lance já a normalizava.
 */
export function numeroDigitado(bruto: string): number | null {
  const limpo = bruto.trim().replace(/\s/g, '').replace(',', '.');
  if (limpo === '') return null;
  const n = Number(limpo);
  return Number.isFinite(n) ? n : null;
}
