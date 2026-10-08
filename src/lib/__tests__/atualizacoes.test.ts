/**
 * `POST /api/atualizar` — o disparo da coleta no n8n deixa de ser público.
 *
 * Medido em 08/10/2026: `GeneralDashboard.tsx` chamava dois webhooks do n8n
 * direto do navegador (GET, sem credencial, URL no bundle). Estes testes provam
 * que (1) o front não carrega mais URL de webhook, (2) anônimo é recusado antes
 * de qualquer rede, (3) o repasse leva o segredo e respeita a janela mínima.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import {
  ALVOS,
  JANELA_MINIMA_MS,
  VARIAVEL_SEGREDO,
  criarDespacharAtualizacao,
} from '../../../api/_lib/atualizacoes.js';

const RAIZ = fileURLToPath(new URL('../../../', import.meta.url));

function arquivos(dir: string): string[] {
  return readdirSync(dir).flatMap((nome) => {
    const caminho = join(dir, nome);
    if (statSync(caminho).isDirectory()) return nome === '__tests__' ? [] : arquivos(caminho);
    return /\.(ts|tsx|js|jsx)$/.test(nome) ? [caminho] : [];
  });
}

const AMBIENTE = {
  [ALVOS['google-ads']]: 'https://n8n.invalido/webhook/gads',
  [ALVOS.gam]: 'https://n8n.invalido/webhook/gam',
  [VARIAVEL_SEGREDO]: 'segredo-de-teste',
};
const usuario = async () => ({ status: 200, usuario: { email: 'op@volc' } });

function montar(over: Record<string, unknown> = {}) {
  const chamadas: Array<{ url: string; init: RequestInit }> = [];
  let relogio = 1_000_000;
  const despachar = criarDespacharAtualizacao({
    exigir: usuario,
    buscar: async (url: string, init: RequestInit) => {
      chamadas.push({ url, init });
      return { ok: true, status: 200 } as Response;
    },
    ambiente: AMBIENTE,
    agora: () => relogio,
    ...over,
  });
  return { despachar, chamadas, avancar: (ms: number) => (relogio += ms) };
}

const pedido = (alvo: string) => ({ method: 'POST', query: { alvo }, authorization: 'Bearer x' });

describe('o front não carrega URL de webhook do n8n', () => {
  it('nenhum arquivo de src/ aponta para /webhook/ do n8n', () => {
    const achados = arquivos(join(RAIZ, 'src')).flatMap((arq) =>
      readFileSync(arq, 'utf8')
        .split('\n')
        .map((linha, i) => ({ linha, n: i + 1 }))
        .filter(({ linha }) => /fluxos\.agenciavolc\.com\.br\/webhook\//.test(linha))
        .map(({ n }) => `${relative(RAIZ, arq)}:${n}`),
    );
    expect(achados).toEqual([]);
  });
});

describe('POST /api/atualizar', () => {
  it('anônimo é recusado antes de qualquer rede', async () => {
    const { chamadas } = montar();
    const despachar = criarDespacharAtualizacao({
      buscar: async () => {
        chamadas.push({ url: 'x', init: {} });
        return { ok: true } as Response;
      },
      ambiente: AMBIENTE,
    });
    const r = await despachar({ method: 'POST', query: { alvo: 'gam' } });
    expect(r.status).toBe(401);
    expect(chamadas).toEqual([]);
  });

  it('só aceita POST', async () => {
    const { despachar } = montar();
    expect((await despachar({ method: 'GET', query: { alvo: 'gam' } })).status).toBe(405);
  });

  it('alvo fora da lista é 400 e não chama o n8n', async () => {
    const { despachar, chamadas } = montar();
    const r = await despachar(pedido('qualquer'));
    expect(r.status).toBe(400);
    expect(chamadas).toEqual([]);
  });

  it('sem a URL no ambiente é 503 (falha fechada)', async () => {
    const { despachar } = montar({ ambiente: {} });
    expect((await despachar(pedido('google-ads'))).status).toBe(503);
  });

  it('repassa para a URL do ambiente com o segredo no header', async () => {
    const { despachar, chamadas } = montar();
    const r = await despachar(pedido('google-ads'));
    expect(r.status).toBe(202);
    expect(chamadas).toHaveLength(1);
    expect(chamadas[0].url).toBe('https://n8n.invalido/webhook/gads');
    expect((chamadas[0].init.headers as Record<string, string>)['X-Volc-Webhook-Segredo']).toBe(
      'segredo-de-teste',
    );
  });

  it('a janela mínima segura clique repetido, por alvo', async () => {
    const { despachar, chamadas, avancar } = montar();
    expect((await despachar(pedido('gam'))).status).toBe(202);
    expect((await despachar(pedido('gam'))).status).toBe(429);
    expect((await despachar(pedido('google-ads'))).status).toBe(202);
    avancar(JANELA_MINIMA_MS);
    expect((await despachar(pedido('gam'))).status).toBe(202);
    expect(chamadas).toHaveLength(3);
  });

  it('n8n recusando vira 502 e não consome a janela', async () => {
    let tentativas = 0;
    const { despachar } = montar({
      buscar: async () => {
        tentativas += 1;
        return { ok: tentativas > 1, status: tentativas > 1 ? 200 : 500 } as Response;
      },
    });
    expect((await despachar(pedido('gam'))).status).toBe(502);
    expect((await despachar(pedido('gam'))).status).toBe(202);
  });
});
