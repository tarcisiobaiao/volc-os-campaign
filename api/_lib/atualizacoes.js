/**
 * atualizacoes — `POST /api/atualizar?alvo=google-ads|gam`.
 *
 * ---------------------------------------------------------------------------
 * O QUE HAVIA ANTES (medido em 08/10/2026)
 * ---------------------------------------------------------------------------
 * `GeneralDashboard.tsx` chamava DOIS webhooks do n8n direto do navegador, por
 * GET e sem credencial — as URLs viajavam no bundle. Quem abrisse o DevTools
 * levava um botão que dispara a coleta de custo do Google Ads e a de receita GAM
 * quantas vezes quisesse: cota da API consumida por anônimo, sem registro de
 * quem pediu.
 *
 * Agora o navegador pede ao NOSSO servidor, autenticado. As URLs e o segredo
 * moram em variável de ambiente e saem daqui com o header
 * `X-Volc-Webhook-Segredo`, que o n8n deve exigir (Header Auth no nó Webhook).
 * Uma janela mínima entre disparos protege a cota de clique repetido.
 */

import { exigirUsuario, lerTokenBearer, falha, ok } from './identidade.js';

export const ALVOS = Object.freeze({
  'google-ads': 'N8N_WEBHOOK_ATUALIZAR_GOOGLE_ADS',
  gam: 'N8N_WEBHOOK_ATUALIZAR_GAM',
});
export const VARIAVEL_SEGREDO = 'N8N_WEBHOOK_SEGREDO';
export const JANELA_MINIMA_MS = 60_000;
const TEMPO_LIMITE_MS = 15_000;

/**
 * @param {{exigir?: Function, buscar?: Function, ambiente?: Record<string,string|undefined>, agora?: () => number}} deps
 */
export function criarDespacharAtualizacao({
  exigir = exigirUsuario,
  buscar = (...a) => fetch(...a),
  ambiente = process.env,
  agora = () => Date.now(),
} = {}) {
  const ultimoDisparo = new Map();

  return async function despacharAtualizacao(entrada) {
    const metodo = String(entrada?.method || '').toUpperCase();
    if (metodo !== 'POST') {
      return falha(405, `Método ${metodo || '(vazio)'} não permitido em /api/atualizar.`);
    }

    // Identidade ANTES de qualquer outra coisa: anônimo não descobre nem quais
    // alvos existem.
    const identidade = await exigir(lerTokenBearer(entrada?.authorization));
    if (identidade.status !== 200) {
      return falha(identidade.status, identidade.error, { codigo: identidade.codigo });
    }

    const alvo = String(entrada?.query?.alvo || entrada?.body?.alvo || '');
    const variavel = ALVOS[alvo];
    if (!variavel) {
      return falha(400, `Alvo desconhecido: use ${Object.keys(ALVOS).join(' ou ')}.`, {
        codigo: 'ALVO_INVALIDO',
      });
    }

    const url = ambiente[variavel];
    if (!url) {
      return falha(503, `Atualização indisponível: ${variavel} não configurada no servidor.`, {
        codigo: 'CONFIG_AUSENTE',
      });
    }

    const ultimo = ultimoDisparo.get(alvo);
    if (ultimo !== undefined && agora() - ultimo < JANELA_MINIMA_MS) {
      const faltam = Math.ceil((JANELA_MINIMA_MS - (agora() - ultimo)) / 1000);
      return falha(429, `Atualização de ${alvo} já pedida há pouco; tente em ${faltam}s.`, {
        codigo: 'JANELA_MINIMA',
      });
    }

    const cabecalhos = {};
    if (ambiente[VARIAVEL_SEGREDO]) cabecalhos['X-Volc-Webhook-Segredo'] = ambiente[VARIAVEL_SEGREDO];

    const controle = new AbortController();
    const relogio = setTimeout(() => controle.abort(), TEMPO_LIMITE_MS);
    let resposta;
    try {
      resposta = await buscar(url, { method: 'GET', headers: cabecalhos, signal: controle.signal });
    } catch (erro) {
      return falha(502, 'O n8n não respondeu ao disparo da atualização.', { codigo: 'N8N_INDISPONIVEL' });
    } finally {
      clearTimeout(relogio);
    }

    if (!resposta.ok) {
      return falha(502, `O n8n recusou o disparo (${resposta.status}).`, { codigo: 'N8N_RECUSOU' });
    }

    ultimoDisparo.set(alvo, agora());
    return ok(202, { disparado: true, alvo, pedido_por: identidade.usuario?.email ?? null });
  };
}

export const despacharAtualizacao = criarDespacharAtualizacao();
