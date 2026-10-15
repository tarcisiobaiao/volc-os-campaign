/**
 * Estado da conversa da Bia para UM usuário montado.
 *
 * Regras que este hook defende (regra de negócio mora no servidor; aqui só a
 * disciplina do cliente):
 *
 * - **um request_id por clique**, gerado uma vez. Se a rede falhar, o mesmo
 *   envio NÃO é refeito: a tela relê o histórico (leitura pura) e mostra o que
 *   o servidor sabe.
 * - **incerta não se repete**: polling para em `uncertain`; a única ação
 *   oferecida é "verificar" (reconciliação por leitura) ou nova conversa.
 * - **isolamento por usuário**: a conversa salva fica em
 *   `volc.bia.conversa.<userId>`, e o componente que usa este hook é montado
 *   com `key={user.id}` — troca de usuário desmonta tudo. Nada do estado
 *   anterior sobrevive, e nenhum `setState` roda depois do desmonte.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { ErroDeApi } from '@/lib/secureApi';

import { biaApi, type BiaApi } from './api';
import {
  TERMINAIS,
  type ContextoPedido,
  type EstadoDaBia,
  type ExecucaoDaBia,
} from './tipos';

export const chaveDaConversa = (userId: string) => `volc.bia.conversa.${userId}`;

const INTERVALO_MS = 1500;
/** Usado só até `/estado` dizer o prazo do servidor (`limites.espera_maxima_s`). */
const ESPERA_PADRAO_MS = 300_000;

function lerSalva(userId: string): string | null {
  try {
    return window.localStorage.getItem(chaveDaConversa(userId));
  } catch {
    return null;
  }
}

function salvar(userId: string, conversaId: string | null): void {
  try {
    if (conversaId) window.localStorage.setItem(chaveDaConversa(userId), conversaId);
    else window.localStorage.removeItem(chaveDaConversa(userId));
  } catch {
    /* sem armazenamento: vale só para esta visita */
  }
}

function mensagemDe(erro: unknown): string {
  if (erro instanceof ErroDeApi) {
    if (erro.status === 0) {
      return 'A rede falhou. Não sabemos se o envio chegou: a conversa foi relida e nada foi reenviado.';
    }
    if (erro.status === 401) return 'Sua sessão expirou. Entre novamente.';
    if (erro.status === 403) return 'A Bia é restrita a administradores.';
    if (erro.status === 404 && erro.codigo === undefined) return 'A Bia não está habilitada neste servidor.';
    return erro.message;
  }
  return 'Falha inesperada. Nada foi reenviado.';
}

export interface EstadoDoHook {
  servico: EstadoDaBia | null;
  conversaId: string | null;
  execucoes: ExecucaoDaBia[];
  carregando: boolean;
  enviando: boolean;
  erro: string | null;
  bloqueada: boolean;
  emAndamento: boolean;
}

export function useBia(userId: string, api: BiaApi = biaApi) {
  const [servico, setServico] = useState<EstadoDaBia | null>(null);
  const [conversaId, setConversaId] = useState<string | null>(() => lerSalva(userId));
  const [execucoes, setExecucoes] = useState<ExecucaoDaBia[]>([]);
  const [carregando, setCarregando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const vivo = useRef(true);
  const esperaMs = useRef(ESPERA_PADRAO_MS);
  const acompanhando = useRef(new Set<string>());
  const retomarRef = useRef<(lista: ExecucaoDaBia[], id: string) => void>(() => {});

  useEffect(() => {
    vivo.current = true;
    return () => {
      vivo.current = false;
    };
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
        // Depois de um reload (ou de um 202 perdido na rede), o que estava em voo
        // volta a ser acompanhado. Só leitura: nada é reenviado.
        if (retomar) retomarRef.current(h.execucoes, id);
      } catch (e) {
        if (!vivo.current) return;
        if (e instanceof ErroDeApi && e.status === 404 && e.codigo === 'nao_encontrado') {
          // A conversa salva não existe (ou não é deste usuário): esquece.
          salvar(userId, null);
          setConversaId(null);
          setExecucoes([]);
          return;
        }
        setErro(mensagemDe(e));
      }
    },
    [api, userId],
  );

  // Recuperação depois de reload: estado do serviço + histórico salvo.
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
      if (ativo) await recarregar(lerSalva(userId), true);
      if (ativo && vivo.current) setCarregando(false);
    })();
    return () => {
      ativo = false;
    };
  }, [api, userId, recarregar]);

  const novaConversa = useCallback(async () => {
    setErro(null);
    try {
      const { conversa } = await api.novaConversa();
      if (!vivo.current) return;
      salvar(userId, conversa.id);
      setConversaId(conversa.id);
      setExecucoes([]);
    } catch (e) {
      if (vivo.current) setErro(mensagemDe(e));
    }
  }, [api, userId]);

  const acompanhar = useCallback(
    async (execucaoId: string, id: string) => {
      if (acompanhando.current.has(execucaoId)) return;
      acompanhando.current.add(execucaoId);
      const limite = Date.now() + esperaMs.current;
      while (vivo.current && Date.now() < limite) {
        await new Promise((r) => setTimeout(r, INTERVALO_MS));
        if (!vivo.current) return;
        try {
          const { execucao } = await api.execucao(execucaoId);
          if (!vivo.current) return;
          setExecucoes((atual) => atual.map((x) => (x.id === execucao.id ? execucao : x)));
          if (TERMINAIS.has(execucao.estado) || execucao.estado === 'uncertain') {
            await recarregar(id);
            return;
          }
        } catch {
          // Leitura falhou: só para de acompanhar. Nada é reenviado.
          break;
        }
      }
      acompanhando.current.delete(execucaoId);
      if (vivo.current) await recarregar(id);
    },
    [api, recarregar],
  );

  retomarRef.current = (lista, id) => {
    for (const x of lista) {
      if (x.estado === 'queued' || x.estado === 'running') void acompanhar(x.id, id);
    }
  };

  const enviar = useCallback(
    async (texto: string, contexto?: ContextoPedido): Promise<boolean> => {
      if (!conversaId || enviando || !texto.trim()) return false;
      setEnviando(true);
      setErro(null);
      // UM request_id por clique. Nunca regenerado para "tentar de novo".
      const pedido = {
        request_id: crypto.randomUUID(),
        texto,
        ...(contexto ? { contexto } : {}),
      };
      try {
        const { execucao } = await api.enviar(conversaId, pedido);
        if (!vivo.current) return true;
        setExecucoes((atual) => [...atual.filter((x) => x.id !== execucao.id), execucao]);
        if (!TERMINAIS.has(execucao.estado) && execucao.estado !== 'uncertain') {
          await acompanhar(execucao.id, conversaId);
        }
        return true;
      } catch (e) {
        if (!vivo.current) return false;
        setErro(mensagemDe(e));
        // Relê: se o envio chegou antes da falha de rede, ele aparece aqui — e,
        // se estiver em voo, volta a ser acompanhado (só leitura).
        await recarregar(conversaId, true);
        return false;
      } finally {
        if (vivo.current) setEnviando(false);
      }
    },
    [api, conversaId, enviando, acompanhar, recarregar],
  );

  const verificar = useCallback(
    async (execucaoId: string) => {
      setErro(null);
      try {
        const { execucao } = await api.reconciliar(execucaoId);
        if (!vivo.current) return;
        setExecucoes((atual) => atual.map((x) => (x.id === execucao.id ? execucao : x)));
        if (execucao.estado === 'uncertain') {
          setErro('Ainda incerto: o Hermes não mostra resposta para este envio. Abra uma nova conversa.');
        }
      } catch (e) {
        if (vivo.current) setErro(mensagemDe(e));
      }
    },
    [api],
  );

  const estado: EstadoDoHook = {
    servico,
    conversaId,
    execucoes,
    carregando,
    enviando,
    erro,
    bloqueada: execucoes.some((x) => x.estado === 'uncertain'),
    emAndamento: execucoes.some((x) => x.estado === 'queued' || x.estado === 'running'),
  };
  return { ...estado, novaConversa, enviar, verificar, recarregar: () => recarregar(conversaId, true) };
}
