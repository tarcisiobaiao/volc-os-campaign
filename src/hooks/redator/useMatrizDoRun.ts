// ============================================
// O run ao vivo — polling de 3s, ETag, e a célula corrente
//
// ## O motor NÃO emite "em andamento"
//
// Não existe status RUNNING em lugar nenhum do código do motor: uma chave só
// aparece no `step_status` quando o passo TERMINA. "Rodando" é, portanto,
// inferência da tela — e ela precisa ser determinística, senão duas abas do
// mesmo run mostrariam coisas diferentes:
//
//   a célula corrente é a PRIMEIRA coluna aplicável sem chave,
//   na página não bloqueada de MENOR número.
//
// ## Por que o cronômetro é obrigatório e não enfeite
//
// Medido: `research_p1` levou 3min07s num run real, e o `state.json` só é
// reescrito nos pontos de checkpoint do pipeline. Sem cronômetro, esses três
// minutos são indistinguíveis de uma tela travada — e o operador cancela um run
// saudável, jogando fora o que já foi pago.
// ============================================
import { useCallback, useEffect, useRef, useState } from 'react';

import { pautadorApi } from '@/lib/pautadorApi';
import type { MatrizDoRun } from '@/types/redator';

/** Cadência do polling. Uma etapa do motor leva de 7s a 3min — 3s é folga de
 *  sobra, e com o 304 a consulta que não traz nada custa ~0 bytes. */
const CADENCIA_MS = 3000;

/** Estados em que ainda há o que observar. Fora deles o polling PARA — um run
 *  encerrado que continua sendo consultado é bateria e banda queimadas à toa. */
const VIVO = new Set(['queued', 'running']);

export interface CelulaCorrente {
  chave: string;
  page_number: number;
  etapa: string;
  /** Segundos desde que ESTA tela viu a célula virar corrente. Não desde o
   *  início do run: o backend não guarda quando cada etapa começou, e inventar
   *  um instante seria mentir sobre a única coisa que o cronômetro promete. */
  segundos: number;
}

export interface EstadoDaMatriz {
  matriz: MatrizDoRun | null;
  carregando: boolean;
  erro: string | null;
  /** Pisca no instante exato em que o polling traz mudança. */
  pulsou: boolean;
  corrente: CelulaCorrente | null;
  /** Há quanto tempo o custo total não muda. Passando de 3 min, a tela precisa
   *  DIZER isso — senão parece travada. */
  segundosSemCobranca: number;
  recarregar: () => void;
}

/** A célula corrente, pela regra determinística acima. */
export function acharCorrente(m: MatrizDoRun | null): { chave: string; page_number: number; etapa: string } | null {
  if (!m || !VIVO.has(m.run.status)) return null;
  const ordem = m.colunas.map((c) => c.chave);
  const paginas = [...m.paginas].sort((a, b) => a.page_number - b.page_number);
  for (const pg of paginas) {
    if (pg.bloqueada) continue;
    for (const etapa of ordem) {
      if (!pg.aplicaveis.includes(etapa)) continue;
      const chave = `${etapa}_p${pg.page_number}`;
      if (!(chave in m.celulas)) {
        return { chave, page_number: pg.page_number, etapa };
      }
    }
  }
  return null;
}

export function useMatrizDoRun(runRowId: number | null): EstadoDaMatriz {
  const [matriz, setMatriz] = useState<MatrizDoRun | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [pulsou, setPulsou] = useState(false);

  const etag = useRef<string | null>(null);
  // Instante em que ESTA tela viu a célula corrente / o custo mudarem. Refs e
  // não state: mudam a cada tick e não devem, sozinhos, disparar re-render.
  const desdeCorrente = useRef<number>(Date.now());
  const chaveCorrente = useRef<string | null>(null);
  const desdeCobranca = useRef<number>(Date.now());
  const ultimoCusto = useRef<number>(-1);
  // Um relógio de 1s move os dois cronômetros SEM depender do polling: entre
  // duas consultas de 3s o número precisa continuar andando, senão ele pula de
  // 3 em 3 e parece um contador quebrado.
  const [, tique] = useState(0);

  const buscar = useCallback(async (limpar = false) => {
    if (runRowId == null) return;
    if (limpar) { etag.current = null; setCarregando(true); }
    try {
      const r = await pautadorApi.matrizDoRun(runRowId, etag.current);
      setErro(null);
      if (!r.mudou || !r.matriz) return;   // 304: o caminho mais comum
      etag.current = r.etag;
      setMatriz(r.matriz);
      setPulsou(true);
      window.setTimeout(() => setPulsou(false), 900);
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falhei ao ler a matriz.');
    } finally {
      setCarregando(false);
    }
  }, [runRowId]);

  // Polling. Para quando o run fecha.
  useEffect(() => {
    if (runRowId == null) { setMatriz(null); return; }
    etag.current = null;
    setCarregando(true);
    void buscar();
    const id = window.setInterval(() => {
      // Lê o status pelo state mais recente via callback do setter: um
      // `matriz` capturado na closure ficaria congelado no primeiro render e o
      // polling nunca pararia.
      setMatriz((atual) => {
        if (atual && !VIVO.has(atual.run.status)) return atual;
        void buscar();
        return atual;
      });
    }, CADENCIA_MS);
    return () => window.clearInterval(id);
  }, [runRowId, buscar]);

  // O relógio de 1s dos cronômetros.
  useEffect(() => {
    if (!matriz || !VIVO.has(matriz.run.status)) return;
    const id = window.setInterval(() => tique((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [matriz]);

  // Zera o cronômetro da célula quando a corrente MUDA de identidade.
  const bruta = acharCorrente(matriz);
  if (bruta?.chave !== chaveCorrente.current) {
    chaveCorrente.current = bruta?.chave ?? null;
    desdeCorrente.current = Date.now();
  }
  const custoAgora = matriz?.custo_total ?? -1;
  if (custoAgora !== ultimoCusto.current) {
    ultimoCusto.current = custoAgora;
    desdeCobranca.current = Date.now();
  }

  const vivo = !!matriz && VIVO.has(matriz.run.status);
  return {
    matriz,
    carregando,
    erro,
    pulsou,
    corrente: bruta
      ? { ...bruta, segundos: Math.floor((Date.now() - desdeCorrente.current) / 1000) }
      : null,
    segundosSemCobranca: vivo
      ? Math.floor((Date.now() - desdeCobranca.current) / 1000)
      : 0,
    recarregar: () => void buscar(true),
  };
}
