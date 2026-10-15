import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

// A v8_06 (pacote do incidente anon, W4) troca o SELECT de tabela em
// public.users por SELECT nas colunas não sensíveis. Depois dela, um
// `.from('users').select('*')` do browser devolve 42501. Este teste garante que
// o frontend já não pede '*' em users antes de a v8_06 ir para produção.
function arquivos(dir: string): string[] {
  return readdirSync(dir).flatMap((nome) => {
    const caminho = join(dir, nome);
    if (statSync(caminho).isDirectory()) return nome === '__tests__' ? [] : arquivos(caminho);
    return /\.(ts|tsx)$/.test(nome) ? [caminho] : [];
  });
}

describe('public.users sem select(*) no frontend', () => {
  it('nenhuma consulta a users pede todas as colunas', () => {
    const raiz = join(__dirname, '..', '..');
    const ofensores = arquivos(raiz).filter((f) =>
      // '*', `*`, '*, rel(*)' ou select() vazio — todos pedem todas as colunas.
      /\.from\(\s*['"`]users['"`]\s*\)\s*\.select\(\s*(['"`]\s*\*[^'"`]*['"`])?\s*[,)]/.test(
        readFileSync(f, 'utf8').replace(/\s+/g, ' '),
      ),
    );
    expect(ofensores).toEqual([]);
  });
});
