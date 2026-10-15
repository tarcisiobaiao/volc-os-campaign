/**
 * O bundle de produção não leva código de Edge Function nem segredo.
 *
 * ## O que aconteceu
 *
 * `WizardSteps.tsx` importava `supabase/functions/capi-router/index.ts?raw`
 * para exibir o código no wizard do Meta CAPI. O `?raw` vira string dentro do
 * JS, então as ~500 linhas de servidor (desenho da cifra dos tokens, nomes de
 * secret, chamadas com service_role) iam para qualquer navegador que abrisse o
 * painel. Agora o import passa por `capiRouterSource.ts`, que o `vite.config.ts`
 * troca por um substituto vazio em produção.
 *
 * ## Por que dois níveis
 *
 * Como na bancada visual (`src/pages/qa/__tests__/bancada-fora-de-producao.test.ts`):
 * a prova de FONTE é rápida e roda sempre; a de BUNDLE roda `vite build` de
 * verdade e varre a saída, e é a que decide. Ela fica atrás de
 * `VOLC_PROVA_DE_BUNDLE=1` porque leva dezenas de segundos.
 *
 * A varredura não lê `.env`: procura FORMAS de segredo (JWT com papel
 * service_role, chave privada PEM, prefixos de chave conhecidos) e nunca
 * imprime o valor achado, só o arquivo e o tipo.
 */
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const raiz = resolve(__dirname, '..', '..');

const arquivos = (dir: string, filtro: (nome: string) => boolean): string[] => {
  const saida: string[] = [];
  for (const nome of readdirSync(dir)) {
    const caminho = join(dir, nome);
    if (statSync(caminho).isDirectory()) {
      if (nome === 'node_modules') continue;
      saida.push(...arquivos(caminho, filtro));
    } else if (filtro(nome)) {
      saida.push(caminho);
    }
  }
  return saida;
};

/**
 * Impressões digitais do código de cada Edge Function: as linhas de código mais
 * longas, sem aspas nem barra invertida (que o `?raw` escaparia ao virar
 * string JS e deixariam de casar byte a byte).
 */
export function impressoesDasFunctions(): Map<string, string[]> {
  const mapa = new Map<string, string[]>();
  for (const arquivo of arquivos(resolve(raiz, 'supabase', 'functions'), (n) => /\.(ts|js)$/.test(n))) {
    const linhas = readFileSync(arquivo, 'utf-8')
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l.length >= 40 && !/["'`\\]/.test(l))
      .filter((l) => !l.startsWith('//') && !l.startsWith('*') && !l.startsWith('/*'));
    mapa.set(relative(raiz, arquivo), [...new Set(linhas)].sort((a, b) => b.length - a.length).slice(0, 5));
  }
  return mapa;
}

/** APIs que só existem no runtime Deno da Edge Function. */
const MARCAS_DE_DENO = ['Deno.env.get(', 'Deno.serve('];

type Achado = { tipo: string };

/** Formas de segredo. Devolve só o TIPO — o valor nunca sai daqui. */
export function segredosEm(conteudo: string): Achado[] {
  const achados: Achado[] = [];
  if (/-----BEGIN [A-Z ]*PRIVATE KEY-----/.test(conteudo)) achados.push({ tipo: 'chave privada PEM' });
  if (/\bsk_live_[0-9A-Za-z]{16,}/.test(conteudo)) achados.push({ tipo: 'chave live Stripe' });
  if (/\bsk-ant-[0-9A-Za-z_-]{20,}/.test(conteudo)) achados.push({ tipo: 'chave Anthropic' });
  if (/\bAKIA[0-9A-Z]{16}\b/.test(conteudo)) achados.push({ tipo: 'chave AWS' });
  if (/\bghp_[0-9A-Za-z]{36}\b/.test(conteudo)) achados.push({ tipo: 'token GitHub' });
  // JWT: a anon key É pública e vai para o bundle de propósito; service_role não.
  for (const m of conteudo.matchAll(/eyJ[A-Za-z0-9_-]{8,}\.(eyJ[A-Za-z0-9_-]{8,})\.[A-Za-z0-9_-]{8,}/g)) {
    try {
      const corpo = JSON.parse(Buffer.from(m[1], 'base64url').toString('utf-8'));
      if (corpo?.role === 'service_role') achados.push({ tipo: 'JWT service_role' });
    } catch {
      /* não é JWT de verdade */
    }
  }
  return achados;
}

describe('a fonte declara a troca', () => {
  it('só capiRouterSource.ts importa de supabase/functions, e o vite o troca em produção', () => {
    const importadores = arquivos(resolve(raiz, 'src'), (n) => /\.(ts|tsx)$/.test(n) && !n.includes('.test.'))
      .filter((f) => /from\s+['"][^'"]*supabase\/functions\//.test(readFileSync(f, 'utf-8')))
      .map((f) => relative(raiz, f));
    expect(importadores).toEqual(['src/components/settings/meta-capi/capiRouterSource.ts']);

    const vite = readFileSync(resolve(raiz, 'vite.config.ts'), 'utf-8');
    expect(vite).toContain('"./capiRouterSource"');
    expect(vite).toContain('capiRouterSource.producao.ts');
    const substituto = readFileSync(
      resolve(raiz, 'src/components/settings/meta-capi/capiRouterSource.producao.ts'), 'utf-8');
    expect(substituto).not.toMatch(/supabase\/functions\/[^'"\s]*\?raw/);
  });

  it('as impressões digitais existem (senão a prova de bundle passaria por vazio)', () => {
    const mapa = impressoesDasFunctions();
    expect(mapa.size).toBeGreaterThan(0);
    for (const [arquivo, linhas] of mapa) {
      expect(linhas.length, `${arquivo} sem linha característica`).toBeGreaterThan(0);
    }
  });

  it('o detector de segredo acha o que deve e ignora a anon key', () => {
    const jwt = (role: string) =>
      ['eyJhbGciOiJIUzI1NiJ9', Buffer.from(JSON.stringify({ role, iss: 'x' })).toString('base64url'), 'assinaturaqualquer']
        .join('.');
    const marcadorPem = ['-----BEGIN ', 'PRIVATE KEY-----'].join('');
    expect(segredosEm(`a="${jwt('anon')}"`)).toEqual([]);
    expect(segredosEm(`a="${jwt('service_role')}"`)).toEqual([{ tipo: 'JWT service_role' }]);
    expect(segredosEm(marcadorPem).map((a) => a.tipo)).toEqual(['chave privada PEM']);
  });
});

describe.runIf(process.env.VOLC_PROVA_DE_BUNDLE === '1')(
  'o build de produção não leva código de servidor nem segredo',
  () => {
    it('nenhum arquivo do bundle contém Edge Function ou segredo', () => {
      const saida = mkdtempSync(join(tmpdir(), 'volc-bundle-'));
      try {
        execFileSync(
          'npx',
          ['vite', 'build', '--outDir', saida, '--emptyOutDir', '--logLevel', 'error'],
          { cwd: raiz, stdio: 'pipe', timeout: 600_000 },
        );
        const bundle = arquivos(saida, () => true);
        expect(bundle.length, 'o build não produziu saída').toBeGreaterThan(0);

        const impressoes = impressoesDasFunctions();
        const culpados: string[] = [];
        for (const arquivo of bundle) {
          let conteudo = '';
          try { conteudo = readFileSync(arquivo, 'utf-8'); } catch { continue; }
          const nome = relative(saida, arquivo);
          for (const marca of MARCAS_DE_DENO) {
            if (conteudo.includes(marca)) culpados.push(`${nome}: API Deno ${marca}`);
          }
          for (const [funcao, linhas] of impressoes) {
            if (linhas.some((l) => conteudo.includes(l))) culpados.push(`${nome}: código de ${funcao}`);
          }
          for (const { tipo } of segredosEm(conteudo)) culpados.push(`${nome}: ${tipo}`);
        }
        expect(culpados, 'código de servidor ou segredo no bundle de produção').toEqual([]);
      } finally {
        rmSync(saida, { recursive: true, force: true });
      }
    }, 600_000);
  },
);
