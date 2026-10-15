/**
 * O navegador nunca fala com o Hermes, e nada do Hermes entra no bundle.
 *
 * Mesmo desenho de `src/__tests__/bundle-sem-codigo-de-servidor.test.ts` (W10):
 * a prova de FONTE roda sempre; a de BUNDLE roda `vite build` de verdade com
 * `VITE_BIA_ENABLED=true` e varre a saída, atrás de `VOLC_PROVA_DE_BUNDLE=1`.
 */
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const raiz = resolve(__dirname, '..', '..', '..', '..');
const pastaBia = resolve(raiz, 'src', 'features', 'bia');

const listar = (dir: string): string[] =>
  readdirSync(dir).flatMap((nome) => {
    const c = join(dir, nome);
    return statSync(c).isDirectory() ? (nome === '__tests__' ? [] : listar(c)) : [c];
  });

/** Formas que denunciariam o Hermes ou a chave dele no lado do navegador. */
export const MARCAS_DO_HERMES: Array<[string, RegExp]> = [
  ['rota de sessão do Hermes', /\/api\/sessions\b/],
  ['rota OpenAI do Hermes', /\/v1\/(chat\/completions|responses|runs|toolsets|capabilities)\b/],
  ['porta do API Server', /:(8642|8643|18643)\b/],
  ['variável da chave do Hermes', /API_SERVER_KEY|BIA_HERMES_API_KEY|HERMES_API_KEY/],
  ['base do Hermes', /BIA_HERMES_BASE_URL|HERMES_BASE_URL/],
  ['host da VPS do Hermes', /76\.13\.161\.49|srv1546019|hstgr\.cloud/],
  ['id de sessão interno', /volc_[0-9a-f]{32}/],
  ['cabeçalho de escopo de memória', /X-Hermes-Session-(Key|Id)/i],
];

const achados = (texto: string) => MARCAS_DO_HERMES.filter(([, re]) => re.test(texto)).map(([n]) => n);

describe('fonte da Bia no front', () => {
  it('nenhum arquivo da feature cita Hermes, porta, chave ou sessão interna', () => {
    for (const arquivo of listar(pastaBia)) {
      expect(achados(readFileSync(arquivo, 'utf-8')), arquivo).toEqual([]);
    }
  });

  it('o cliente só conhece /api/agent/* e reaproveita o secureApi', () => {
    const api = readFileSync(join(pastaBia, 'api.ts'), 'utf-8');
    const rotas = [...api.matchAll(/`(\/api\/[^`$]*)/g), ...api.matchAll(/'(\/api\/[^']*)'/g)].map((m) => m[1]);
    expect(rotas.length).toBeGreaterThan(0);
    for (const r of rotas) expect(r.startsWith('/api/agent/')).toBe(true);
    expect(api).toContain("from '@/lib/secureApi'");
    expect(api).not.toMatch(/\bfetch\(/);
    expect(api).not.toMatch(/createClient/);
  });

  it('nenhuma VITE_* nova carrega segredo ou endereço do Hermes', () => {
    const exemplo = readFileSync(resolve(raiz, '.env.example'), 'utf-8');
    const vites = exemplo.split('\n').filter((l) => /^\s*VITE_BIA/.test(l));
    expect(vites).toEqual(['VITE_BIA_ENABLED=false']);
  });

  it('o detector acha o que deve', () => {
    expect(achados('fetch("http://127.0.0.1:8643/api/sessions")')).toEqual(
      ['rota de sessão do Hermes', 'porta do API Server']);
    expect(achados('/api/agent/conversations')).toEqual([]);
  });
});

describe.runIf(process.env.VOLC_PROVA_DE_BUNDLE === '1')(
  'o build de produção com a Bia ligada não leva nada do Hermes',
  () => {
    it('nenhum arquivo do bundle contém marca do Hermes', () => {
      const saida = mkdtempSync(join(tmpdir(), 'volc-bundle-bia-'));
      try {
        execFileSync('npx', ['vite', 'build', '--outDir', saida, '--emptyOutDir', '--logLevel', 'error'], {
          cwd: raiz, stdio: 'pipe', timeout: 600_000,
          env: { ...process.env, VITE_BIA_ENABLED: 'true' },
        });
        const bundle = listar(saida);
        expect(bundle.length).toBeGreaterThan(0);
        const culpados: string[] = [];
        let temBia = false;
        for (const arquivo of bundle) {
          const conteudo = readFileSync(arquivo, 'utf-8');
          if (conteudo.includes('/api/agent/conversations')) temBia = true;
          for (const nome of achados(conteudo)) culpados.push(`${arquivo.slice(saida.length)}: ${nome}`);
        }
        expect(temBia, 'o bundle nem contém a Bia: a prova passaria por vazio').toBe(true);
        expect(culpados).toEqual([]);
      } finally {
        rmSync(saida, { recursive: true, force: true });
      }
    }, 600_000);
  },
);
