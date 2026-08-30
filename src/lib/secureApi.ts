/**
 * secureApi — o cliente das rotas nomeadas do backend.
 *
 * ---------------------------------------------------------------------------
 * O QUE ESTE ARQUIVO ERA, E POR QUE MUDOU
 * ---------------------------------------------------------------------------
 * Até 24/08/2026 esta classe expunha `query`, `insert`, `update`, `delete` e
 * `rpc` genéricos: o navegador mandava o NOME DA TABELA e o NOME DA FUNÇÃO, e
 * o servidor executava com `service_role` — sem autenticação nenhuma. O nome
 * "secureApi" descrevia a intenção (não expor a credencial no browser), não o
 * resultado: a credencial ficava no servidor, mas o PODER dela estava aberto
 * na internet para qualquer um com `curl`.
 *
 * Agora cada operação tem uma rota nomeada, e nenhum identificador de banco
 * sai daqui. O que o cliente escolhe é qual chave da lista permitida ler, não
 * o que executar.
 *
 * ---------------------------------------------------------------------------
 * TODA REQUISIÇÃO LEVA `Authorization: Bearer`
 * ---------------------------------------------------------------------------
 * O token é o access token da sessão Supabase do usuário logado — o mesmo que
 * o `@supabase/supabase-js` já gerencia e renova. NÃO é uma API key: não há
 * segredo de backend neste arquivo, nem em nenhuma `VITE_*`, porque tudo que
 * entra no bundle é público por definição.
 *
 * Sem sessão, o método falha ANTES do fetch. Não existe caminho anônimo: um
 * fallback "tenta sem token" transformaria cada 401 do servidor num convite a
 * reabrir a rota, que é exatamente como a superfície anterior nasceu.
 */

import { supabase } from '@/lib/supabase';

// Local dev: http://localhost:3001 (endpoints são /api/...)
// Produção (Vercel): string vazia (endpoints são /api/...)
const envUrl = import.meta.env.VITE_API_URL || '';
const API_BASE_URL = envUrl === '/api' ? '' : envUrl;

/** Chaves de `system_settings` que o servidor aceita ler. */
export type ChaveConfiguracao =
  | 'dollar_exchange_rate'
  | 'last_currency_update'
  | 'currency_display'
  | 'auto_convert_values'
  | 'gam_last_update'
  | 'google_ads_last_update';

export interface Configuracao {
  key: ChaveConfiguracao;
  value: string;
  updated_at?: string;
}

export interface PerfilDoUsuario {
  id: string;
  name: string | null;
  email: string;
  role: 'ADMIN' | 'OPERATOR';
  needs_password_change?: boolean;
  first_login?: boolean;
  commission_percentage?: number | null;
  created_at?: string;
  updated_at?: string;
}

/**
 * Erro de API que preserva o status e o código.
 *
 * Sem isso, quem chama só recebe uma string e não consegue distinguir "você
 * não tem permissão" de "a rede caiu" — e tratar as duas igual é como o
 * sistema decide sozinho que o usuário não existe.
 */
export class ErroDeApi extends Error {
  readonly status: number;
  readonly codigo?: string;

  constructor(mensagem: string, status: number, codigo?: string) {
    super(mensagem);
    this.name = 'ErroDeApi';
    this.status = status;
    this.codigo = codigo;
  }

  /** O servidor decidiu que não pode: identidade ausente, inválida ou insuficiente. */
  get ehNegado(): boolean {
    return this.status === 401 || this.status === 403;
  }
}

class SecureApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  /** Access token da sessão atual, ou null se não há sessão. */
  private async token(): Promise<string | null> {
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit & { anonimo?: boolean; token?: string } = {},
  ): Promise<T> {
    const { anonimo, token: tokenExplicito, ...init } = options;
    const cabecalhos: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((init.headers as Record<string, string>) || {}),
    };

    if (!anonimo) {
      // Token explícito tem precedência e NUNCA chama `getSession()`.
      //
      // Isso não é otimização: `supabase.auth.getSession()` chamado de dentro
      // de um callback de `onAuthStateChange` NÃO RESOLVE. O `auth-js` aguarda
      // cada subscriber dentro do lock (`_notifyAllSubscribers` faz
      // `await Promise.all(callbacks)`), e `getSession()` pede o mesmo lock;
      // o reentrante espera a promise que está esperando por ele. Espera
      // circular, provada com a biblioteca real em 24/08/2026.
      //
      // Quem já tem a sessão em mãos — o callback de auth, o retorno de
      // `signInWithPassword` — passa `token` e não toca no lock.
      const token = tokenExplicito ?? (await this.token());
      if (!token) {
        // Falha fechada, antes da rede. Mandar a requisição sem credencial só
        // produziria um 401 mais tarde e um log confuso no servidor.
        throw new ErroDeApi('Sessão expirada. Faça login novamente.', 401, 'SEM_SESSAO');
      }
      cabecalhos.Authorization = `Bearer ${token}`;
    }

    const url = `${this.baseUrl}${endpoint}`;
    let resposta: Response;

    try {
      resposta = await fetch(url, { ...init, headers: cabecalhos });
    } catch (erro) {
      // Rede caiu, DNS falhou, CORS barrou. Não é negação de acesso — e
      // confundir os dois faria a UI deslogar o usuário por causa do wi-fi.
      throw new ErroDeApi(
        erro instanceof Error ? erro.message : 'Falha de rede',
        0,
        'REDE',
      );
    }

    const texto = await resposta.text();

    if (!resposta.ok) {
      let mensagem = `Requisição falhou (${resposta.status})`;
      let codigo: string | undefined;
      try {
        const json = JSON.parse(texto);
        mensagem = json.error || mensagem;
        codigo = json.codigo;
      } catch {
        if (texto) mensagem = texto;
      }
      throw new ErroDeApi(mensagem, resposta.status, codigo);
    }

    if (!texto) return undefined as unknown as T;
    return JSON.parse(texto) as T;
  }

  // -------------------------------------------------------------------------
  // Identidade
  // -------------------------------------------------------------------------

  /**
   * `GET /api/me` — o perfil de quem está logado.
   *
   * Não recebe e-mail: quem a requisição descreve vem do JWT. A rota antiga
   * (`POST /api/users/query {email}`) permitia perguntar por qualquer pessoa,
   * o que a tornava um oráculo de enumeração de contas.
   *
   * @param accessToken passe SEMPRE que já tiver a sessão em mãos. Ver a nota
   *        sobre o lock do `auth-js` em `request()`.
   */
  async me(accessToken?: string): Promise<PerfilDoUsuario> {
    return this.request<PerfilDoUsuario>('/api/me', { token: accessToken });
  }

  /**
   * `POST /api/users` — cria um usuário. Exige ADMIN, conferido no servidor.
   *
   * Importante: este endpoint NÃO toca em nenhuma sessão de browser — ao
   * contrário do `supabase.auth.signUp()` do client, que substituiria a sessão
   * do admin logado pela do novo usuário. Use sempre este método quando um
   * admin criar outro usuário.
   */
  async createUser(input: {
    name: string;
    email: string;
    password: string;
    role: 'ADMIN' | 'OPERATOR';
  }): Promise<PerfilDoUsuario> {
    return this.request<PerfilDoUsuario>('/api/users', {
      method: 'POST',
      body: JSON.stringify(input),
    });
  }

  // -------------------------------------------------------------------------
  // Configurações
  // -------------------------------------------------------------------------

  /** `GET /api/settings` — lê chaves da lista permitida. */
  async getSettings(chaves: ChaveConfiguracao[]): Promise<Configuracao[]> {
    const busca = chaves.length > 0 ? `?keys=${encodeURIComponent(chaves.join(','))}` : '';
    const corpo = await this.request<{ settings: Configuracao[] }>(`/api/settings${busca}`);
    return corpo?.settings ?? [];
  }

  /** `PUT /api/settings` — grava chaves da lista permitida. Exige ADMIN. */
  async setSettings(itens: Array<{ key: ChaveConfiguracao; value: string }>): Promise<string[]> {
    const corpo = await this.request<{ updated: string[] }>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify({ settings: itens }),
    });
    return corpo?.updated ?? [];
  }

  /**
   * `PUT /api/settings/exchange-rate` — grava a cotação E recalcula o mês.
   *
   * Rota própria porque é uma transação, não uma escrita de chave: a RPC
   * `rpc_set_dollar_exchange_rate` atualiza a taxa e reconverte as receitas do
   * mês junto. Por isso `dollar_exchange_rate` é recusada em `setSettings`.
   */
  async setExchangeRate(taxa: number): Promise<{ rate: number; last_currency_update: string | null }> {
    return this.request('/api/settings/exchange-rate', {
      method: 'PUT',
      body: JSON.stringify({ rate: taxa }),
    });
  }

  // -------------------------------------------------------------------------
  // Saúde
  // -------------------------------------------------------------------------

  /** `GET /api/health` — a única rota anônima. Não toca no banco. */
  async healthCheck(): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>('/api/health', { anonimo: true });
  }
}

export const secureApi = new SecureApiClient();
