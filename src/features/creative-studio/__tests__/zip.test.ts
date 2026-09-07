// @vitest-environment node
import { execFileSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';
import { zipDeImagens } from '../zip';

describe('ZIP interoperável', () => {
  it('abre em leitor independente, com CRC e dois conteúdos intactos', async () => {
    const zip = zipDeImagens([
      { name: 'retrato.png', data: new TextEncoder().encode('fixture-image-one') },
      { name: 'vertical.webp', data: new Uint8Array([0, 255, 30, 10]) },
    ]);
    const result = execFileSync('python3', ['-c', 'import sys,io,zipfile,json; z=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read())); assert z.testzip() is None; print(json.dumps({n:list(z.read(n)) for n in z.namelist()}))'], { input: Buffer.from(await zip.arrayBuffer()), encoding: 'utf8' });
    const decoded = JSON.parse(result);
    expect(decoded['vertical.webp']).toEqual([0, 255, 30, 10]);
    expect(Buffer.from(decoded['retrato.png']).toString()).toBe('fixture-image-one');
  });
  it('recusa vazio, path traversal e nomes repetidos', () => {
    expect(() => zipDeImagens([])).toThrow();
    expect(() => zipDeImagens([{ name: '../x.png', data: new Uint8Array() }])).toThrow();
    const f = { name: 'x.png', data: new Uint8Array() };
    expect(() => zipDeImagens([f, f])).toThrow();
  });
});
