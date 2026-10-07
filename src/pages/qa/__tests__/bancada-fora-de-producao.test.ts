/**
 * A bancada visual não pode chegar em produção — provado em dois níveis.
 *
 * ## Por que dois
 *
 * A prova de FONTE mostra que o mecanismo está escrito: guarda
 * `import.meta.env.DEV` na rota e import preguiçoso. Ela é rápida e roda em toda
 * suíte. Mas ela prova o mecanismo, não o resultado: um `React.lazy` fora do
 * ramo guardado, uma reexportação por outro módulo, ou uma mudança de `define`
 * no Vite continuariam passando por ela e levariam a página junto.
 *
 * A prova de BUNDLE roda `vite build` de verdade e procura o marcador no que
 * saiu. É a que responde a pergunta real, e por isso é ela que decide. Fica
 * atrás de `VOLC_PROVA_DE_BUNDLE=1` porque leva dezenas de segundos e a suíte
 * é rodada dezenas de vezes por hora — o gate de fechamento a liga.
 */
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { MARCADOR_DA_BANCADA } from '@/pages/qa/BancadaVisual';

const raiz = resolve(__dirname, '..', '..', '..', '..');
const ler = (rel: string) => readFileSync(resolve(raiz, rel), 'utf-8');

describe('a fonte declara o guarda', () => {
  const app = ler('src/App.tsx');

  it('a rota da bancada só é registrada sob import.meta.env.DEV', () => {
    // Toda menção a `/qa/trafego` precisa estar dentro de um ramo guardado.
    const linhas = app.split('\n');
    const rotas = linhas
      .map((linha, i) => ({ linha, i }))
      .filter(({ linha }) => linha.includes('path="/qa/'));
    expect(rotas.length, 'a bancada sumiu de App.tsx').toBeGreaterThan(0);
    for (const { i } of rotas) {
      // O guarda abre até 3 linhas antes da rota.
      const vizinhanca = linhas.slice(Math.max(0, i - 3), i + 1).join('\n');
      expect(vizinhanca, `rota /qa na linha ${i + 1} sem guarda de DEV`).toContain(
        'import.meta.env.DEV',
      );
    }
  });

  it('a bancada entra por import preguiçoso, nunca no topo', () => {
    expect(app).toMatch(/React\.lazy\(\(\)\s*=>\s*import\(["'][^"']*pages\/qa\/BancadaVisual["']\)\)/);
    expect(app).not.toMatch(/^import\s+BancadaVisual\s+from/m);
  });

  it('nada fora de src/pages/qa importa a bancada', () => {
    // Uma segunda porta de entrada anularia o guarda da rota.
    const encontrados: string[] = [];
    const varrer = (dir: string) => {
      for (const nome of readdirSync(dir)) {
        const caminho = join(dir, nome);
        if (statSync(caminho).isDirectory()) {
          if (nome === 'node_modules') continue;
          varrer(caminho);
          continue;
        }
        if (!/\.(ts|tsx)$/.test(nome)) continue;
        if (caminho.includes(join('src', 'pages', 'qa'))) continue;
        if (caminho.endsWith(join('src', 'App.tsx'))) continue;
        if (readFileSync(caminho, 'utf-8').includes('pages/qa/BancadaVisual')) {
          encontrados.push(caminho.replace(raiz + '/', ''));
        }
      }
    };
    varrer(resolve(raiz, 'src'));
    expect(encontrados).toEqual([]);
  });
});

describe.runIf(process.env.VOLC_PROVA_DE_BUNDLE === '1')(
  'o build de produção não leva a bancada',
  () => {
    it('o marcador não aparece em nenhum arquivo do bundle', () => {
      const saida = mkdtempSync(join(tmpdir(), 'volc-bundle-'));
      try {
        execFileSync(
          'npx',
          ['vite', 'build', '--outDir', saida, '--emptyOutDir', '--logLevel', 'error'],
          { cwd: raiz, stdio: 'pipe', timeout: 600_000 },
        );
        expect(existsSync(saida), 'o build não produziu saída').toBe(true);

        const culpados: string[] = [];
        const varrer = (dir: string) => {
          for (const nome of readdirSync(dir)) {
            const caminho = join(dir, nome);
            if (statSync(caminho).isDirectory()) { varrer(caminho); continue; }
            let conteudo = '';
            try { conteudo = readFileSync(caminho, 'utf-8'); } catch { continue; }
            if (conteudo.includes(MARCADOR_DA_BANCADA)) {
              culpados.push(caminho.replace(saida + '/', ''));
            }
          }
        };
        varrer(saida);
        expect(culpados, 'a bancada visual foi para o bundle de produção').toEqual([]);
      } finally {
        rmSync(saida, { recursive: true, force: true });
      }
    }, 600_000);
  },
);
