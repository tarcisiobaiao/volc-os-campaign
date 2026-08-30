/**
 * Acompanhar um trabalho da bancada, sem mentir enquanto espera.
 *
 * ## As sete regras que este hook implementa
 *
 * 1. **Uma consulta ativa por trabalho.** Um `setTimeout` guardado em ref, e o
 *    próximo só é agendado quando o anterior responde. Sem isso, uma aba lenta
 *    empilha consultas e cada resposta atrasada sobrescreve uma mais nova.
 * 2. **Backoff.** O intervalo cresce de 1s até 15s. Um job que demora não merece
 *    ser perguntado quatro vezes por segundo.
 * 3. **Pausa quando a aba some.** `visibilitychange`: aba escondida não pergunta,
 *    e volta a perguntar imediatamente quando reaparece.
 * 4. **Para em terminal.** `rendered`, `failed` e `cancelled` não mudam mais.
 *    Continuar perguntando é gastar rede para receber a mesma resposta.
 * 5. **Falha parcial preserva o último estado bom.** Uma consulta que falha NÃO
 *    apaga o que já se sabia; ela marca `leituraFalhou` e diz desde quando.
 * 6. **Limpeza no desmonte.** Timer cancelado, listener removido, resposta em
 *    voo ignorada — senão o React reclama de estado em componente morto, e pior,
 *    a resposta velha sobrescreve a tela nova.
 * 7. **Ausência não vira fila vazia.** `trabalho === null` com `carregando` é
 *    "ainda não sei"; `trabalho === null` sem carregando e sem erro é "não
 *    existe". Os dois têm telas diferentes.
 * 8. **Uma resposta só escreve na tela que a pediu.** Cada execução do efeito
 *    tem geração própria, e toda escrita confere geração + `trabalhoId` + ciclo
 *    de vida antes de tocar em estado.
 * 9. **Refresh pedido durante uma consulta não se perde.** Ele fica pendente e
 *    executa assim que a consulta em voo responde, sem esperar o backoff.
 *
 * ## Por que geração, e não apenas uma ref de "vivo" (achado #15)
 *
 * A versão anterior guardava `vivo`, `emVoo` e `terminou` em refs COMPARTILHADAS
 * entre execuções do efeito. Trocar de trabalho — o que a retomada faz, com
 * `setTrabalhoId(novo.id)` — produzia esta sequência:
 *
 * 1. a limpeza do efeito de A punha `vivo = false`;
 * 2. o efeito de B punha `vivo = true` de novo — ressuscitando a permissão de
 *    escrita da consulta de A, que continuava em voo;
 * 3. `emVoo` continuava `true`, então a primeira consulta de B voltava na hora
 *    sem perguntar nada: **B nunca era consultado**;
 * 4. a resposta de A chegava, passava pelo `vivo` ressuscitado e escrevia a peça
 *    de A na tela rotulada como B — e, se A fosse terminal, `terminou = true`
 *    parava o acompanhamento de B para sempre.
 *
 * O conserto é escopo: `ativo`, `emVoo`, `terminou`, `timer` e `intervalo` são
 * variáveis LOCAIS de cada execução do efeito. Uma execução não alcança o estado
 * da outra, então nenhuma limpeza pode ser desfeita pelo efeito seguinte. A
 * geração numérica é a segunda tranca, explícita e auditável.
 *
 * ## Semântica escolhida para o refresh (achado #16)
 *
 * Das duas opções seguras — abortar a leitura em voo e recomeçar, ou marcar um
 * pedido pendente e executá-lo ao final —, este hook usa a **segunda**:
 *
 * - `criativosApi.trabalhoDaBancada` não expõe `AbortSignal`, e a fronteira HTTP
 *   não pertence a este arquivo; "abortar" seria só ignorar a resposta, jogando
 *   fora uma leitura já paga e deixando a tela velha por mais um round-trip;
 * - o pedido pendente é coalescido: dez cliques viram uma releitura, não dez
 *   requisições — a tempestade que o modo "recomeçar" convidaria.
 *
 * Vale para as duas portas de entrada: `recarregar()` e a volta da aba.
 */
import React from 'react';

import { criativosApi, mensagemDaFalha } from '@/lib/criativosApi';
import type { EstadoDoTrabalho, TrabalhoDaBancada } from '@/types/parqueCriativo';

const TERMINAIS: ReadonlySet<EstadoDoTrabalho> = new Set([
  'rendered',
  'failed',
  'cancelled',
]);

export function ehTerminal(estado: EstadoDoTrabalho | undefined): boolean {
  return estado !== undefined && TERMINAIS.has(estado);
}

const PRIMEIRO_INTERVALO_MS = 1_000;
const MAIOR_INTERVALO_MS = 15_000;

export interface LeituraDoTrabalho {
  trabalho: TrabalhoDaBancada | null;
  /** Primeira leitura ainda não chegou. Diferente de "não existe". */
  carregando: boolean;
  /** A última tentativa falhou. O `trabalho` acima pode estar velho. */
  leituraFalhou: string | null;
  /** Quando a última leitura BEM-SUCEDIDA aconteceu. */
  lidoEm: Date | null;
  /** O acompanhamento está parado porque o trabalho terminou. */
  encerrado: boolean;
  /** Pausado porque a aba não está visível. */
  pausado: boolean;
  recarregar: () => void;
}

export function useTrabalhoDaBancada(
  trabalhoId: string | null,
  inicial?: TrabalhoDaBancada | null,
): LeituraDoTrabalho {
  const [trabalho, setTrabalho] = React.useState<TrabalhoDaBancada | null>(
    inicial ?? null,
  );
  const [carregando, setCarregando] = React.useState(Boolean(trabalhoId) && !inicial);
  const [leituraFalhou, setLeituraFalhou] = React.useState<string | null>(null);
  const [lidoEm, setLidoEm] = React.useState<Date | null>(inicial ? new Date() : null);
  const [pausado, setPausado] = React.useState(false);
  /**
   * De QUEM é o `trabalho` que está guardado agora.
   *
   * ⚠️ ACHADO ADVERSARIAL (revisão de 2026-08-29). Zerar a tela no efeito não
   * bastava: o efeito roda DEPOIS do commit, então o primeiro render com o id
   * novo ainda devolvia a peça do trabalho anterior — medido, a sequência de ids
   * renderizados após a troca era `["job-A", null]`. Um frame mostrando a peça de
   * A sob o rótulo de B é exatamente o sintoma que o achado #15 descreve, e
   * nenhuma proteção contra resposta atrasada o alcança, porque o dado já estava
   * em casa. A identidade viaja junto com o dado e a conferência acontece no
   * render, não num efeito.
   */
  const [trabalhoDe, setTrabalhoDe] = React.useState<string | null>(
    inicial ? trabalhoId : null,
  );

  /**
   * A geração corrente do acompanhamento. Cresce a cada execução do efeito e é a
   * identidade contra a qual TODA resposta se confere antes de escrever.
   *
   * ⚠️ O `finally` roda mesmo depois do `return` do `try`. Na versão anterior ele
   * lia `terminou` de uma ref compartilhada; hoje lê a variável local desta
   * execução, que é o valor do instante e não o de um fechamento antigo.
   */
  const geracao = React.useRef(0);
  /** Qual `trabalhoId` a tela acompanha AGORA. */
  const idCorrente = React.useRef<string | null>(trabalhoId);
  /** Porta única de "leia agora", reapontada a cada execução do efeito. */
  const pedirLeituraAgora = React.useRef<() => void>(() => undefined);
  /** Falso só na primeira execução: montar não é trocar de trabalho. */
  const jaMontou = React.useRef(false);

  // A peça só é da tela atual se o id de quem a trouxe for o id pedido agora.
  // Enquanto não for, a tela está "ainda não sei" — não "eis a peça de outro".
  const daTelaAtual = trabalhoDe === trabalhoId;
  const trabalhoVisivel = daTelaAtual ? trabalho : null;
  const encerrado = ehTerminal(trabalhoVisivel?.estado);

  React.useEffect(() => {
    // Trocar de trabalho zera a tela. Herdar a peça anterior sob o id novo é a
    // própria contaminação do achado #15, e ela apareceria antes mesmo de
    // qualquer resposta atrasada.
    if (jaMontou.current) {
      setTrabalho(null);
      setTrabalhoDe(null);
      setLeituraFalhou(null);
      setLidoEm(null);
      setCarregando(Boolean(trabalhoId));
      setPausado(false);
    }
    jaMontou.current = true;
    idCorrente.current = trabalhoId;

    if (!trabalhoId) {
      pedirLeituraAgora.current = () => undefined;
      return;
    }

    // ⚠️ Tudo daqui para baixo é LOCAL desta execução. Nenhuma execução seguinte
    // alcança estas variáveis, então nenhuma limpeza pode ser desfeita depois —
    // que era exatamente como `vivo = false` voltava a ser `true` e liberava a
    // resposta do trabalho antigo a escrever na tela do novo.
    const minhaGeracao = ++geracao.current;
    const meuId = trabalhoId;
    let ativo = true;
    let emVoo = false;
    let refreshPendente = false;
    let terminou = false;
    let intervalo = PRIMEIRO_INTERVALO_MS;
    let timer: ReturnType<typeof setTimeout> | null = null;

    /** Geração, trabalho e ciclo de vida — as três perguntas, sempre juntas. */
    const souAtual = () =>
      ativo && geracao.current === minhaGeracao && idCorrente.current === meuId;

    const limparTimer = () => {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
    };

    const consultar = async () => {
      if (!souAtual()) return;
      // Regra 1 + achado #16: uma consulta ativa por vez, mas o pedido de
      // releitura NÃO se perde — fica pendente e roda no `finally`.
      if (emVoo) {
        refreshPendente = true;
        return;
      }
      if (document.visibilityState === 'hidden') {
        setPausado(true);
        return;
      }
      setPausado(false);
      emVoo = true;
      limparTimer();
      try {
        const novo = await criativosApi.trabalhoDaBancada(meuId);
        if (!souAtual()) return; // Regra 8: a resposta chegou tarde demais.
        setTrabalho(novo);
        setTrabalhoDe(meuId);
        setLeituraFalhou(null);
        setLidoEm(new Date());
        setCarregando(false);
        if (ehTerminal(novo.estado)) {
          terminou = true;
          limparTimer();
          return; // Regra 4
        }
        intervalo = Math.min(intervalo * 1.6, MAIOR_INTERVALO_MS);
      } catch (erro) {
        if (!souAtual()) return;
        // Regra 5: NÃO apaga o que já se sabia.
        setLeituraFalhou(mensagemDaFalha(erro));
        setCarregando(false);
        intervalo = Math.min(intervalo * 2, MAIOR_INTERVALO_MS);
      } finally {
        emVoo = false;
        if (souAtual()) {
          if (refreshPendente) {
            // Regra 9: pediram leitura enquanto esta estava em voo. O pedido
            // vale agora, mesmo que o trabalho já tenha terminado — quem
            // cancelou quer ver a confirmação, não o backoff.
            refreshPendente = false;
            intervalo = PRIMEIRO_INTERVALO_MS;
            limparTimer();
            void consultar();
          } else if (!terminou) {
            limparTimer();
            timer = setTimeout(consultar, intervalo);
          }
        }
      }
    };

    pedirLeituraAgora.current = () => {
      if (!souAtual()) return;
      intervalo = PRIMEIRO_INTERVALO_MS;
      void consultar();
    };

    const aoTrocarVisibilidade = () => {
      if (!souAtual()) return;
      if (document.visibilityState !== 'visible') {
        setPausado(true);
        return;
      }
      setPausado(false);
      if (terminou) return;
      // Quem reabriu a aba quer saber agora. Com consulta em voo isto vira
      // pedido pendente em vez de sumir — era o segundo caminho do achado #16.
      intervalo = PRIMEIRO_INTERVALO_MS;
      void consultar();
    };

    document.addEventListener('visibilitychange', aoTrocarVisibilidade);
    void consultar();

    return () => {
      // Regra 6. `ativo` é local: o efeito seguinte não tem como ressuscitá-lo.
      ativo = false;
      limparTimer();
      document.removeEventListener('visibilitychange', aoTrocarVisibilidade);
    };
  }, [trabalhoId]);

  // Identidade estável: `Producao.tsx` chama isto dentro de `onSuccess`, e uma
  // função nova a cada render provocaria efeito em quem a receba por dependência.
  const recarregar = React.useCallback(() => {
    pedirLeituraAgora.current();
  }, []);

  return {
    trabalho: trabalhoVisivel,
    // Sem peça da tela atual e com id pedido, o estado honesto é "carregando" —
    // e não "não existe", que é a outra tela.
    carregando: carregando || (Boolean(trabalhoId) && !daTelaAtual),
    leituraFalhou: daTelaAtual ? leituraFalhou : null,
    lidoEm: daTelaAtual ? lidoEm : null,
    encerrado,
    pausado,
    recarregar,
  };
}
