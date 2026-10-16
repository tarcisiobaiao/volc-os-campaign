/**
 * Estado da conversa da Bia para UM usuário montado.
 *
 * Regras que este hook defende (a regra de negócio mora no servidor; aqui a
 * disciplina do cliente):
 *
 * - **um request_id por clique**, gerado uma vez. Se a rede falhar, o mesmo
 *   envio NÃO é refeito: a tela relê o histórico (leitura pura) e mostra o que
 *   o servidor sabe. O rascunho só é limpo depois do 202/200.
 * - **progresso honesto**: o texto parcial só existe quando o servidor mandou
 *   `parcial` (deltas reais do Hermes). Sem isso, a tela diz "preparando a
 *   resposta", nunca "digitando".
 * - **incerta não se repete**: o acompanhamento para em `uncertain`; a única
 *   ação é "verificar" (reconciliação por leitura) ou nova conversa.
 * - **isolamento por usuário**: tudo vive sob `key={user.id}`; a conversa salva
 *   fica em `volc.bia.conversa.<userId>`. Nenhum `setState` após o desmonte.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { ErroDeApi } from '@/lib/secureApi';

import { biaApi, type BiaApi } from './api';
import {
  TERMINAIS,
  type ContextoPedido,
  type ConversaDaBia,
  type EstadoDaBia,
  type ExecucaoDaBia,
  type IntencaoDeEnvio,
  type ResultadoDoStatus,
  type StatusDoCerebro,
} from './tipos';

export const chaveDaConversa = (userId: string) => `volc.bia.conversa.${userId}`;

const INTERVALO_MS = 1500;
const ESPERA_PADRAO_MS = 300_000;

/** Nota local: resultado de comando, ajuda ou recusa. Nunca vai ao servidor. */
export type NotaLocal =
  | { id: string; tipo: 'ajuda'; criada_em: string }
  | { id: string; tipo: 'status'; criada_em: string; resultado: ResultadoDoStatus; duracao_ms?: number }
  | { id: string; tipo: 'cerebro'; criada_em: string; resultado: StatusDoCerebro }
  | { id: string; tipo: 'recusa'; criada_em: string; titulo: string; texto: string }
  | { id: string; tipo: 'info'; criada_em: string; texto: string };

type SemIdentidade<T> = T extends unknown ? Omit<T, 'id' | 'criada_em'> : never;
export type NovaNota = SemIdentidade<NotaLocal>;

function ler(chave: string): string | null {
  try {
    return window.localStorage.getItem(chave);
  } catch {
    return null;
  }
}

function gravar(chave: string, valor: string | null): void {
  try {
    if (valor) window.localStorage.setItem(chave, valor);
    else window.localStorage.removeItem(chave);
  } catch {
    /* sem armazenamento: vale só para esta visita */
  }
}

export function mensagemDe(erro: unknown): string {
  if (erro instanceof ErroDeApi) {
    if (erro.status === 0) {
      return 'A rede falhou. Não sabemos se o envio chegou: a conversa foi relida e nada foi reenviado.';
    }
    if (erro.status === 401) return 'Sua sessão expirou. Entre novamente.';
    if (erro.status === 403) return erro.codigo ? erro.message : 'A Bia é restrita a administradores.';
    if (erro.status === 404 && erro.codigo === undefined) return 'A Bia não está habilitada neste servidor.';
    if (erro.status === 503) return erro.message || 'A Bia está indisponível no momento.';
    return erro.message;
  }
  return 'Falha inesperada. Nada foi reenviado.';
}

const novoId = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

export function useBia(userId: string, api: BiaApi = biaApi) {
  const [servico, setServico] = useState<EstadoDaBia | null>(null);
  const [conversaId, setConversaId] = useState<string | null>(() => ler(chaveDaConversa(userId)));
  const [execucoes, setExecucoes] = useState<ExecucaoDaBia[]>([]);
  const [parciais, setParciais] = useState<Record<string, string>>({});
  const [notas, setNotas] = useState<NotaLocal[]>([]);
  const [conversas, setConversas] = useState<ConversaDaBia[] | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [online, setOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine));
  const vivo = useRef(true);
  // Trava síncrona: dois Enter no mesmo quadro não podem virar dois envios.
  const enviandoRef = useRef(false);
  const esperaMs = useRef(ESPERA_PADRAO_MS);
  const acompanhando = useRef(new Map<string, AbortController>());
  const retomarRef = useRef<(lista: ExecucaoDaBia[], id: string) => void>(() => {});

  useEffect(() => {
    vivo.current = true;
    const mapa = acompanhando.current;
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      vivo.current = false;
      mapa.forEach((c) => c.abort());
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  }, []);

  const atualizar = useCallback((e: ExecucaoDaBia) => {
    setExecucoes((atual) =>
      atual.some((x) => x.id === e.id) ? atual.map((x) => (x.id === e.id ? e : x)) : [...atual, e]);
  }, []);

  const recarregar = useCallback(
    async (id: string | null, retomar = false) => {
      if (!id) {
        setExecucoes([]);
        return;
      }
      try {
        const h = await api.historico(id);
        if (!vivo.current) return;
        setExecucoes(h.execucoes);
        if (retomar) retomarRef.current(h.execucoes, id);
      } catch (e) {
        if (!vivo.current) return;
        if (e instanceof ErroDeApi && e.status === 404 && e.codigo === 'nao_encontrado') {
          gravar(chaveDaConversa(userId), null);
          setConversaId(null);
          setExecucoes([]);
          return;
        }
        setErro(mensagemDe(e));
      }
    },
    [api, userId],
  );

  useEffect(() => {
    let ativo = true;
    setCarregando(true);
    (async () => {
      try {
        const s = await api.estado();
        if (ativo && vivo.current) {
          setServico(s);
          if (s.limites?.espera_maxima_s) esperaMs.current = s.limites.espera_maxima_s * 1000;
        }
      } catch (e) {
        if (ativo && vivo.current) setErro(mensagemDe(e));
      }
      if (ativo) await recarregar(ler(chaveDaConversa(userId)), true);
      if (ativo && vivo.current) setCarregando(false);
    })();
    return () => {
      ativo = false;
    };
  }, [api, userId, recarregar]);

  /** Por polling: o caminho de reserva quando o fluxo SSE não está disponível. */
  const sondar = useCallback(
    async (execucaoId: string, id: string, sinal: AbortSignal) => {
      const limite = Date.now() + esperaMs.current;
      while (vivo.current && !sinal.aborted && Date.now() < limite) {
        await new Promise((r) => setTimeout(r, INTERVALO_MS));
        if (!vivo.current || sinal.aborted) return;
        try {
          const { execucao } = await api.execucao(execucaoId);
          if (!vivo.current) return;
          atualizar(execucao);
          if (TERMINAIS.has(execucao.estado) || execucao.estado === 'uncertain') return;
        } catch {
          return; // leitura falhou: só para. Nada é reenviado.
        }
      }
      if (vivo.current) await recarregar(id);
    },
    [api, atualizar, recarregar],
  );

  const acompanhar = useCallback(
    async (execucaoId: string, id: string) => {
      if (acompanhando.current.has(execucaoId)) return;
      const controle = new AbortController();
      acompanhando.current.set(execucaoId, controle);
      try {
        await api.acompanhar(
          execucaoId,
          (evento) => {
            if (!vivo.current) return;
            if (evento.tipo === 'estado') atualizar(evento.execucao);
            else if (evento.tipo === 'parcial') setParciais((p) => ({ ...p, [execucaoId]: evento.texto }));
          },
          controle.signal,
        );
      } catch {
        if (!controle.signal.aborted) await sondar(execucaoId, id, controle.signal);
      } finally {
        acompanhando.current.delete(execucaoId);
        if (vivo.current && !controle.signal.aborted) {
          setParciais((p) => {
            const { [execucaoId]: _descartado, ...resto } = p;
            return resto;
          });
          await recarregar(id);
        }
      }
    },
    [api, atualizar, recarregar, sondar],
  );

  retomarRef.current = (lista, id) => {
    for (const x of lista) {
      if (x.estado === 'queued' || x.estado === 'running') void acompanhar(x.id, id);
    }
  };

  const trocarConversa = useCallback(
    async (id: string | null) => {
      acompanhando.current.forEach((c) => c.abort());
      acompanhando.current.clear();
      gravar(chaveDaConversa(userId), id);
      setConversaId(id);
      setExecucoes([]);
      setParciais({});
      setNotas([]);
      setErro(null);
      if (id) {
        setCarregando(true);
        await recarregar(id, true);
        if (vivo.current) setCarregando(false);
      }
    },
    [recarregar, userId],
  );

  const novaConversa = useCallback(async (): Promise<string | null> => {
    setErro(null);
    try {
      const { conversa } = await api.novaConversa();
      if (!vivo.current) return null;
      await trocarConversa(conversa.id);
      setConversas(null);
      return conversa.id;
    } catch (e) {
      if (vivo.current) setErro(mensagemDe(e));
      return null;
    }
  }, [api, trocarConversa]);

  const carregarConversas = useCallback(async () => {
    try {
      const { conversas: lista } = await api.conversas();
      if (vivo.current) setConversas(lista);
    } catch (e) {
      if (vivo.current) setErro(mensagemDe(e));
    }
  }, [api]);

  const enviar = useCallback(
    async (
      texto: string,
      opcoes: { anexos?: string[]; contexto?: ContextoPedido; intencao?: IntencaoDeEnvio } = {},
    ): Promise<boolean> => {
      if (enviandoRef.current) return false;
      enviandoRef.current = true;
      let id = conversaId;
      setEnviando(true);
      setErro(null);
      try {
        if (!id) id = await novaConversa();
        if (!id) return false;
        // UM request_id por clique. Nunca regenerado para "tentar de novo".
        const pedido = {
          request_id: novoId(),
          texto,
          ...(opcoes.anexos?.length ? { anexos: opcoes.anexos } : {}),
          ...(opcoes.contexto ? { contexto: opcoes.contexto } : {}),
          ...(opcoes.intencao ? { intencao: opcoes.intencao } : {}),
        };
        const { execucao } = await api.enviar(id, pedido);
        if (!vivo.current) return true;
        atualizar(execucao);
        if (!TERMINAIS.has(execucao.estado) && execucao.estado !== 'uncertain') void acompanhar(execucao.id, id);
        return true;
      } catch (e) {
        if (!vivo.current) return false;
        setErro(mensagemDe(e));
        if (id) await recarregar(id, true);
        return false;
      } finally {
        enviandoRef.current = false;
        if (vivo.current) setEnviando(false);
      }
    },
    [api, conversaId, novaConversa, atualizar, acompanhar, recarregar],
  );

  const verificar = useCallback(
    async (execucaoId: string) => {
      setErro(null);
      try {
        const { execucao } = await api.reconciliar(execucaoId);
        if (!vivo.current) return;
        atualizar(execucao);
        if (execucao.estado === 'uncertain') {
          setErro('Ainda incerto: o Hermes não mostra resposta para este envio. Abra uma nova conversa.');
        }
      } catch (e) {
        if (vivo.current) setErro(mensagemDe(e));
      }
    },
    [api, atualizar],
  );

  const adicionarNota = useCallback((nota: NovaNota) => {
    setNotas((n) => [...n, { ...nota, id: novoId(), criada_em: new Date().toISOString() } as NotaLocal]);
  }, []);

  const executarStatus = useCallback(async () => {
    try {
      const r = await api.executarComando('status', conversaId);
      if (!vivo.current) return;
      adicionarNota({ tipo: 'status', resultado: r.resultado, duracao_ms: r.recibo?.duracao_ms as number | undefined });
    } catch (e) {
      if (vivo.current) adicionarNota({ tipo: 'recusa', titulo: '/status', texto: mensagemDe(e) });
    }
  }, [api, conversaId, adicionarNota]);

  /** Status dos três cérebros (só leitura). Indisponível vira nota com o motivo do servidor. */
  const statusDoCerebro = useCallback(async () => {
    try {
      const r = await api.cerebroStatus();
      if (vivo.current) adicionarNota({ tipo: 'cerebro', resultado: r });
    } catch (e) {
      if (vivo.current) adicionarNota({ tipo: 'recusa', titulo: '/cerebro', texto: mensagemDe(e) });
    }
  }, [api, adicionarNota]);

  /** Pede à Bia (sem ferramenta) um rascunho de captura. Nada é gravado aqui. */
  const pedirRascunho = useCallback(
    (observacao = '') => enviar(observacao, { intencao: 'rascunho_cerebro' }),
    [enviar],
  );

  const ultimaResposta = execucoes.slice().reverse().find((x) => x.estado === 'succeeded' && x.resposta)?.resposta ?? null;

  return {
    servico,
    conversaId,
    execucoes,
    parciais,
    notas,
    conversas,
    carregando,
    enviando,
    erro,
    online,
    ultimaResposta,
    bloqueada: execucoes.some((x) => x.estado === 'uncertain'),
    emAndamento: execucoes.some((x) => x.estado === 'queued' || x.estado === 'running'),
    limparErro: () => setErro(null),
    novaConversa,
    trocarConversa,
    carregarConversas,
    enviar,
    verificar,
    adicionarNota,
    executarStatus,
    statusDoCerebro,
    pedirRascunho,
  };
}

export type EstadoDoChat = ReturnType<typeof useBia>;
