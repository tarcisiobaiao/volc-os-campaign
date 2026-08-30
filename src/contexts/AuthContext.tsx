/**
 * AuthContext — quem está logado, e se essa pessoa tem cadastro.
 *
 * ---------------------------------------------------------------------------
 * OS TRÊS DEFEITOS QUE ESTE ARQUIVO CARREGAVA (corrigidos em 24/08/2026)
 * ---------------------------------------------------------------------------
 *
 * 1. `getSession()` DENTRO do callback de `onAuthStateChange`.
 *
 *    O `auth-js` aguarda cada subscriber dentro do lock de sessão
 *    (`_notifyAllSubscribers` faz `await Promise.all(callbacks)`), e
 *    `getSession()` pede esse mesmo lock. O caminho reentrante do
 *    `_acquireLock` faz `await last`, onde `last` é justamente a promise que
 *    está esperando o callback terminar. Espera circular — a chamada nunca
 *    resolve. Provado com a biblioteca real.
 *
 *    Agora o callback é SÍNCRONO e o trabalho assíncrono é agendado para
 *    fora do lock. E o token vai explícito para o `secureApi`, porque a
 *    sessão já chega no argumento do callback: não havia motivo para
 *    perguntar de novo.
 *
 * 2. Um `catch` que transformava todo motivo na mesma frase.
 *
 *    Rede caída, 500, 503, 401 e 403 terminavam todos em
 *    "o email não está cadastrado" seguido de `signOut()`. Um usuário ADMIN,
 *    cadastrado, existente, era informado de que não existia — porque o
 *    sistema não sabia distinguir "não consegui perguntar" de "perguntei e a
 *    resposta é não".
 *
 *    Agora só `403 SEM_CADASTRO` diz isso. As demais falhas têm significado
 *    próprio, e as transitórias PRESERVAM a sessão para permitir nova
 *    tentativa.
 *
 * 3. Dois caminhos concorrentes pedindo o mesmo perfil.
 *
 *    `getSession().then(...)` e `onAuthStateChange` chamavam ambos
 *    `fetchUserProfile`, e `INITIAL_SESSION`/`SIGNED_IN`/`TOKEN_REFRESHED`
 *    disparavam mais. Como o `catch` chamava `signOut()`, bastava UMA dessas
 *    corridas falhar para derrubar a sessão de todas as outras.
 *
 *    Agora existe um caminho só, com voo único por usuário.
 *
 * ---------------------------------------------------------------------------
 * A REGRA QUE NÃO PODE SER RELAXADA
 * ---------------------------------------------------------------------------
 * `user` só é instalado quando o perfil foi confirmado. `ProtectedRoute` libera
 * a aplicação com base em `user`, e aplica as restrições de OPERATOR com base
 * em `userProfile.role`. Instalar `user` sem perfil daria acesso a alguém sem
 * papel conhecido — que o roteador trataria como "não é OPERATOR", ou seja,
 * como se fosse admin. Preservar a sessão para nova tentativa NÃO é o mesmo
 * que conceder acesso.
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Session, User } from "@supabase/supabase-js";

import { supabase } from "@/lib/supabase";
import { ErroDeApi, secureApi, type PerfilDoUsuario } from "@/lib/secureApi";

export interface UserProfile {
  id?: string; // UUID
  name?: string;
  email?: string;
  role?: 'ADMIN' | 'OPERATOR';
  needs_password_change?: boolean;
  created_at?: string;
  updated_at?: string;
}

/**
 * Por que a autorização falhou.
 *
 * `podeTentarNovamente` separa o que é definitivo do que é circunstancial. É a
 * diferença entre "essa pessoa não tem acesso" e "não deu para verificar
 * agora" — e tratar as duas igual foi exatamente o defeito.
 */
export type TipoDeFalha =
  | 'sem_cadastro'      // 403 SEM_CADASTRO — autenticou, mas não há perfil
  | 'sem_permissao'     // 403 NAO_ADMIN / ORIGEM_NAO_AUTORIZADA
  | 'sessao_invalida'   // 401 — token ausente, inválido ou expirado
  | 'indisponivel';     // rede, 500, 503 — não foi possível verificar

export interface FalhaDeAutorizacao {
  tipo: TipoDeFalha;
  mensagem: string;
  status: number;
  codigo?: string;
  podeTentarNovamente: boolean;
}

interface AuthContextType {
  user: User | null;
  session: Session | null;
  userProfile: UserProfile | null;
  loading: boolean;
  /** Só preenchido em `sem_cadastro`. Mantido pelo nome antigo para a UI. */
  unauthorizedUser: string | null;
  falha: FalhaDeAutorizacao | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  clearUnauthorizedUser: () => void;
  /** Refaz a verificação com a sessão que ainda está guardada. */
  tentarNovamente: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};

/** Traduz o erro do `secureApi` para um motivo com significado próprio. */
export function classificarFalha(erro: unknown): FalhaDeAutorizacao {
  if (erro instanceof ErroDeApi) {
    if (erro.status === 403 && erro.codigo === 'SEM_CADASTRO') {
      return {
        tipo: 'sem_cadastro',
        mensagem: erro.message,
        status: erro.status,
        codigo: erro.codigo,
        podeTentarNovamente: false,
      };
    }
    if (erro.status === 403) {
      return {
        tipo: 'sem_permissao',
        mensagem: erro.message,
        status: erro.status,
        codigo: erro.codigo,
        podeTentarNovamente: false,
      };
    }
    if (erro.status === 401) {
      return {
        tipo: 'sessao_invalida',
        mensagem: erro.message,
        status: erro.status,
        codigo: erro.codigo,
        podeTentarNovamente: false,
      };
    }
    // 0 (rede), 500, 502, 503… — não sabemos, e não saber não é "não existe".
    return {
      tipo: 'indisponivel',
      mensagem: erro.status === 0
        ? 'Não foi possível falar com o servidor. Verifique a conexão e tente novamente.'
        : 'O servidor não conseguiu confirmar seu acesso agora. Tente novamente em instantes.',
      status: erro.status,
      codigo: erro.codigo,
      podeTentarNovamente: true,
    };
  }

  return {
    tipo: 'indisponivel',
    mensagem: 'Falha inesperada ao verificar o acesso. Tente novamente.',
    status: -1,
    podeTentarNovamente: true,
  };
}

/** Erro lançado por `signIn` quando a senha estava certa mas o acesso não. */
export class ErroDeAutorizacao extends Error {
  readonly falha: FalhaDeAutorizacao;
  constructor(falha: FalhaDeAutorizacao) {
    super(falha.mensagem);
    this.name = 'ErroDeAutorizacao';
    this.falha = falha;
  }
}

interface AuthProviderProps {
  children: React.ReactNode;
}

export const AuthProvider = ({ children }: AuthProviderProps) => {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [unauthorizedUser, setUnauthorizedUser] = useState<string | null>(null);
  const [falha, setFalha] = useState<FalhaDeAutorizacao | null>(null);

  /** Sessão bruta mais recente, mesmo quando o acesso ainda não foi concedido. */
  const sessaoBruta = useRef<Session | null>(null);
  /** Voo único: id do usuário cujo perfil está sendo (ou já foi) resolvido. */
  const emVoo = useRef<{ userId: string; promessa: Promise<PerfilDoUsuario> } | null>(null);
  /** Usuário cujo perfil JÁ está instalado — evita refazer em TOKEN_REFRESHED. */
  const perfilInstaladoPara = useRef<string | null>(null);
  const montado = useRef(true);

  const limparAcesso = useCallback(() => {
    setUser(null);
    setSession(null);
    setUserProfile(null);
    perfilInstaladoPara.current = null;
    emVoo.current = null;
  }, []);

  /**
   * Confirma o cadastro e instala (ou não) o acesso.
   *
   * O token vai EXPLÍCITO: esta função é chamada de dentro do fluxo de auth, e
   * pedir a sessão de novo ali trava o lock do `auth-js`.
   */
  const aplicarSessao = useCallback(async (sessaoAtual: Session): Promise<void> => {
    const userId = sessaoAtual.user.id;

    // Já instalado para este usuário: TOKEN_REFRESHED não precisa refazer nada.
    if (perfilInstaladoPara.current === userId) {
      sessaoBruta.current = sessaoAtual;
      setSession(sessaoAtual);
      setUser(sessaoAtual.user);
      return;
    }

    sessaoBruta.current = sessaoAtual;

    // Voo único: se já há uma verificação em curso para o mesmo usuário,
    // aguarda ELA em vez de abrir outra. Sem isso, `INITIAL_SESSION`,
    // `SIGNED_IN` e o retorno do login abrem três requisições concorrentes —
    // e uma falha qualquer entre elas derrubava a sessão de todas.
    if (!emVoo.current || emVoo.current.userId !== userId) {
      emVoo.current = { userId, promessa: secureApi.me(sessaoAtual.access_token) };
    }

    try {
      const perfil = await emVoo.current.promessa;
      if (!montado.current) return;

      perfilInstaladoPara.current = userId;
      emVoo.current = null;
      setUserProfile(perfil);
      setSession(sessaoAtual);
      setUser(sessaoAtual.user);
      setUnauthorizedUser(null);
      setFalha(null);
    } catch (erro) {
      emVoo.current = null;
      const motivo = classificarFalha(erro);
      if (!montado.current) throw new ErroDeAutorizacao(motivo);

      setFalha(motivo);
      setUserProfile(null);
      perfilInstaladoPara.current = null;

      // O acesso NUNCA é concedido sem perfil — nem no caso transitório.
      // `ProtectedRoute` libera com base em `user`, e um `user` sem
      // `userProfile.role` passaria pelas restrições de OPERATOR.
      setUser(null);

      if (motivo.tipo === 'sem_cadastro') {
        setUnauthorizedUser(sessaoAtual.user.email || 'Email não disponível');
        setSession(null);
        await supabase.auth.signOut();
      } else if (motivo.tipo === 'sessao_invalida' || motivo.tipo === 'sem_permissao') {
        setSession(null);
        await supabase.auth.signOut();
      } else {
        // Transitório: a sessão do Supabase FICA. Recarregar ou tentar
        // novamente pode resolver, e destruí-la aqui obrigaria a digitar a
        // senha por causa de uma oscilação de rede.
        setSession(sessaoAtual);
      }

      throw new ErroDeAutorizacao(motivo);
    }
  }, []);

  useEffect(() => {
    montado.current = true;

    // O callback é SÍNCRONO de propósito. O `auth-js` aguarda cada subscriber
    // dentro do lock de sessão; qualquer `await` aqui dentro que toque no
    // próprio cliente trava. O trabalho vai para fora do lock via setTimeout.
    //
    // Também não há `getSession()` separado: `onAuthStateChange` emite
    // `INITIAL_SESSION` na inscrição, então perguntar de novo só criaria a
    // segunda corrida.
    const { data: { subscription } } = supabase.auth.onAuthStateChange((evento, sessaoNova) => {
      if (!sessaoNova?.user) {
        sessaoBruta.current = null;
        limparAcesso();
        setFalha(null);
        if (evento !== 'SIGNED_OUT') setUnauthorizedUser(null);
        setLoading(false);
        return;
      }

      sessaoBruta.current = sessaoNova;

      setTimeout(() => {
        void aplicarSessao(sessaoNova)
          .catch(() => { /* o estado já foi definido por aplicarSessao */ })
          .finally(() => { if (montado.current) setLoading(false); });
      }, 0);
    });

    return () => {
      montado.current = false;
      subscription.unsubscribe();
    };
  }, [aplicarSessao, limparAcesso]);

  const signIn = async (email: string, password: string) => {
    const normalizedEmail = email.trim().toLowerCase();

    const { data, error } = await supabase.auth.signInWithPassword({
      email: normalizedEmail,
      password,
    });
    if (error) throw error;
    if (!data.session) {
      throw new ErroDeAutorizacao({
        tipo: 'sessao_invalida',
        mensagem: 'O login não devolveu uma sessão. Tente novamente.',
        status: -1,
        podeTentarNovamente: true,
      });
    }

    // A senha estava certa. Isso ainda NÃO é acesso concedido: quem decide é
    // `GET /api/me`. Esta chamada acontece fora de qualquer callback de auth,
    // então pode aguardar sem travar o lock — e é ela que faz `signIn` só
    // resolver quando o perfil estiver instalado. É o que impede a tela de
    // comemorar antes da autorização.
    await aplicarSessao(data.session);
  };

  const signInWithGoogle = async () => {
    const isLocalhost = window.location.hostname === 'localhost';
    const redirectUrl = isLocalhost
      ? window.location.origin + '/'
      : (import.meta.env.VITE_SITE_URL || window.location.origin) + '/';

    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: redirectUrl },
    });
    if (error) throw error;
  };

  const signOut = async () => {
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
  };

  const clearUnauthorizedUser = () => {
    setUnauthorizedUser(null);
    setFalha(null);
  };

  const tentarNovamente = async () => {
    const sessaoAtual = sessaoBruta.current;
    if (!sessaoAtual) {
      setFalha({
        tipo: 'sessao_invalida',
        mensagem: 'Não há sessão para revalidar. Faça login novamente.',
        status: 401,
        podeTentarNovamente: false,
      });
      return;
    }
    setFalha(null);
    emVoo.current = null;
    try {
      await aplicarSessao(sessaoAtual);
    } catch {
      /* aplicarSessao já registrou o motivo */
    }
  };

  const value: AuthContextType = {
    user,
    session,
    userProfile,
    loading,
    unauthorizedUser,
    falha,
    signIn,
    signInWithGoogle,
    signOut,
    clearUnauthorizedUser,
    tentarNovamente,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
