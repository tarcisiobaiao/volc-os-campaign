/**
 * O fluxo de eventos do job, fora do React Query de propósito.
 *
 * ## Por que fora do React Query
 *
 * React Query modela pergunta e resposta com cache. Um fluxo é o contrário:
 * uma conexão longa que empurra incremento. Enfiá-lo num `queryFn` faria a
 * biblioteca acreditar que tem um dado fresco quando na verdade tem uma
 * conexão aberta, e o `refetch` reabriria o fluxo do zero, reenviando eventos
 * que a tela já mostrou.
 *
 * ## As duas regras da reconexão
 *
 * 1. **Retomar do último `seq` ACEITO**, nunca do último recebido. É por isso
 *    que o cursor mora no acumulador puro (`stream/fluxo.ts`) e não num `useState`
 *    solto: quem decide o que foi aceito é quem sabe deduplicar.
 * 2. **Desistir depois de um número finito de tentativas**, declarando que
 *    parou. Um cliente que reconecta para sempre em silêncio mostra uma tela
 *    parada que parece viva, e alguém decide gasto olhando para ela.
 *
 * ## Limpeza
 *
 * `AbortController` no desmonte. O laço de reconexão observa o mesmo sinal, e
 * a espera entre tentativas também: sem isso, sair da página deixaria um
 * `setTimeout` reabrindo uma conexão para um componente que não existe mais.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { abrirFluxoDeEventos, mensagemDaFalha } from '@/lib/criativosApi';
import { fluxoInicial, receberEvento, type EstadoDoFluxo } from '@/components/criativos/stream/fluxo';
import type { CreativeJob, EstadoDoJob, EventoDoJob } from '@/types/criativos';

export type EstadoDaConexao =
  | 'inativa'
  | 'abrindo'
  | 'aberta'
  | 'reconectando'
  | 'encerrada'
  | 'desistiu';

export const DESCRICAO_DA_CONEXAO: Record<EstadoDaConexao, string> = {
  inativa: 'Este trabalho já terminou. Não há atualização para acompanhar.',
  abrindo: 'Abrindo o acompanhamento ao vivo.',
  aberta: 'Acompanhando ao vivo.',
  reconectando: 'A conexão caiu. Retomando do último evento recebido.',
  encerrada: 'O servidor encerrou o acompanhamento deste trabalho.',
  desistiu: 'Não foi possível manter o acompanhamento ao vivo. Recarregue para ver o estado atual.',
};

const MAX_TENTATIVAS = 5;

/**
 * A escada de espera: 1s, 2s, 5s, 10s, teto de 15s.
 *
 * Fixa e curta de propósito. Um backoff exponencial longo faz a tela de um job
 * que está gastando dinheiro ficar minutos sem atualizar depois de uma queda
 * banal de rede.
 */
const ESCADA = [1_000, 2_000, 5_000, 10_000, 15_000] as const;

function atraso(tentativa: number): number {
  return ESCADA[Math.min(tentativa, ESCADA.length) - 1];
}

/**
 * Fechamento por ociosidade NÃO é falha.
 *
 * O servidor encerra o fluxo depois de cerca de dez minutos parado. Contar isso
 * como tentativa fracassada faria o cliente desistir de um job longo e saudável
 * depois de cinquenta minutos. Uma conexão que durou o bastante, ou que
 * entregou qualquer quadro, zera o contador.
 */
const DURACAO_SAUDAVEL_MS = 5_000;

function esperar(ms: number, sinal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (sinal.aborted) return resolve();
    const t = setTimeout(fim, ms);
    function fim() {
      clearTimeout(t);
      sinal.removeEventListener('abort', fim);
      resolve();
    }
    sinal.addEventListener('abort', fim);
  });
}

export interface LeituraDoFluxo {
  eventos: EventoDoJob[];
  cursor: number;
  conexao: EstadoDaConexao;
  /** Falha da última tentativa, já sanitizada. `null` quando não houve. */
  falha: string | null;
  /** Quantos eventos repetidos a retomada descartou. Diagnóstico honesto. */
  descartados: number;
}

export interface OpcoesDoFluxo {
  jobId: string | undefined;
  /** `job.cursorEventos`: o que a carga inicial por HTTP já conhecia. */
  cursorInicial: number;
  /** Só abre quando o job ainda pode mudar. Job terminado não abre conexão. */
  ativo: boolean;
  aoAtualizarJob: (job: CreativeJob) => void;
  aoTerminar?: (estado: EstadoDoJob) => void;
}

export function useCriativosEventos(opcoes: OpcoesDoFluxo): LeituraDoFluxo {
  const { jobId, cursorInicial, ativo } = opcoes;

  // Os callbacks vivem em ref para que trocar de identidade não reabra o fluxo.
  const aoAtualizarJob = useRef(opcoes.aoAtualizarJob);
  const aoTerminar = useRef(opcoes.aoTerminar);
  aoAtualizarJob.current = opcoes.aoAtualizarJob;
  aoTerminar.current = opcoes.aoTerminar;

  // `cursorInicial` chega em ref porque ele nasce 0 e vira `job.cursorEventos`
  // só depois da carga por HTTP. Lido direto na dependência do efeito, ele
  // reabriria o fluxo a cada leitura do job; lido em ref, o efeito de reinício
  // sempre enxerga o valor mais novo sem reabrir nada.
  const cursorInicialRef = useRef(cursorInicial);
  cursorInicialRef.current = cursorInicial;

  const fluxoRef = useRef<EstadoDoFluxo>(fluxoInicial(cursorInicial));
  const [fluxo, setFluxo] = useState<EstadoDoFluxo>(fluxoRef.current);
  const [conexao, setConexao] = useState<EstadoDaConexao>('inativa');
  const [falha, setFalha] = useState<string | null>(null);

  const empurrar = useCallback((evento: EventoDoJob) => {
    const proximo = receberEvento(fluxoRef.current, evento);
    fluxoRef.current = proximo;
    setFluxo(proximo);
  }, []);

  useEffect(() => {
    // Job novo é fluxo novo: o cursor do anterior não descreve este.
    //
    // ⚠️ Quem chama só deve informar `jobId` DEPOIS que o job foi carregado por
    // HTTP. É essa ordem que faz este reinício acontecer com o cursor certo, e
    // é a ordem que a página do job documenta: carregar, depois escutar.
    fluxoRef.current = fluxoInicial(cursorInicialRef.current);
    setFluxo(fluxoRef.current);
  }, [jobId]);

  useEffect(() => {
    if (!jobId || !ativo) {
      setConexao('inativa');
      return;
    }
    const controlador = new AbortController();
    let encerradoPeloServidor = false;

    const laco = async () => {
      let tentativa = 0;
      while (!controlador.signal.aborted) {
        setConexao(tentativa === 0 ? 'abrindo' : 'reconectando');
        let produziu = false;
        let houveErro = false;
        const inicio = Date.now();
        try {
          await abrirFluxoDeEventos(
            jobId,
            fluxoRef.current.cursor,
            {
              aoEvento: (evento) => {
                produziu = true;
                setConexao('aberta');
                setFalha(null);
                empurrar(evento);
              },
              aoJob: (job) => {
                produziu = true;
                setConexao('aberta');
                aoAtualizarJob.current(job);
              },
              aoFim: (estado) => {
                encerradoPeloServidor = true;
                aoTerminar.current?.(estado);
              },
            },
            controlador.signal,
          );
        } catch (err) {
          if (controlador.signal.aborted) return;
          houveErro = true;
          setFalha(mensagemDaFalha(err));
        }
        if (controlador.signal.aborted) return;
        if (encerradoPeloServidor) {
          setConexao('encerrada');
          return;
        }
        const saudavel = !houveErro && (produziu || Date.now() - inicio >= DURACAO_SAUDAVEL_MS);
        if (saudavel) {
          // Fechamento por ociosidade: retoma do cursor, sem contar tentativa.
          tentativa = 0;
          setConexao('reconectando');
          await esperar(ESCADA[0], controlador.signal);
          continue;
        }
        tentativa += 1;
        if (tentativa > MAX_TENTATIVAS) {
          setConexao('desistiu');
          return;
        }
        setConexao('reconectando');
        await esperar(atraso(tentativa), controlador.signal);
      }
    };

    void laco();
    return () => controlador.abort();
  }, [jobId, ativo, empurrar]);

  return {
    eventos: fluxo.eventos,
    cursor: fluxo.cursor,
    conexao,
    falha,
    descartados: fluxo.repetidos,
  };
}
