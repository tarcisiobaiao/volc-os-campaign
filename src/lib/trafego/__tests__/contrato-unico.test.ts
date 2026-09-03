/**
 * Um objeto do servidor, um tipo. Contraprovas de fonte, não de forma.
 *
 * ## Por que estas provas leem o ARQUIVO e não o tipo
 *
 * Tipo não existe em tempo de execução: uma prova que apenas atribuísse um
 * objeto a `ManifestoDeCanal` passaria mesmo com duas declarações divergentes —
 * ela provaria que UMA delas aceita o objeto, que é justamente a pergunta
 * errada. O defeito que estas provas fecham é a EXISTÊNCIA de uma segunda
 * declaração, e isso só se vê no texto do módulo.
 *
 * O repositório já usa esta forma em `seguranca-hub.test.ts` e
 * `seguranca-bundle.test.ts`, pelo mesmo motivo.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const raiz = resolve(__dirname, '..', '..', '..', '..');
const ler = (rel: string) => readFileSync(resolve(raiz, rel), 'utf-8');

const TIPOS = 'src/types/trafego.ts';
const CANAIS = 'src/lib/trafego/canais.ts';

describe('o manifesto de canal tem uma declaração só', () => {
  it('canais.ts não declara uma segunda interface do manifesto', () => {
    // ⚠️ Havia duas, e elas já discordavam: `sabe_provar` obrigatório aqui e
    // opcional lá, `plataforma: string` aqui e `Plataforma` lá. Uma resposta é
    // uma só; dois tipos para ela fazem metade das telas validar outra forma.
    const fonte = ler(CANAIS);
    expect(fonte).not.toMatch(/export\s+interface\s+ManifestoDoCanal\b/);
    expect(fonte).toMatch(/export\s+type\s+ManifestoDoCanal\s*=\s*ManifestoDeCanal\s*;/);
  });

  it('canais.ts importa o tipo canônico em vez de redeclarar', () => {
    expect(ler(CANAIS)).toMatch(
      /import\s+type\s*\{[^}]*\bManifestoDeCanal\b[^}]*\}\s*from\s*'@\/types\/trafego'/,
    );
  });

  it('sabe_provar é obrigatório — o servidor sempre o emite', () => {
    // `plataforma.ManifestoDeCanal.para_json()` escreve `sabe_provar` em toda
    // resposta (backend/app/trafego/plataforma.py). O marcador `?` obrigava
    // cada leitor a inventar um padrão para um campo que sempre chega — e
    // `capacidadesDoCanal` inventava `sabe_criar`, que responde outra pergunta.
    const bloco = ler(TIPOS).match(
      /export interface ManifestoDeCanal \{[\s\S]*?\n\}/,
    )?.[0];
    expect(bloco, 'interface ManifestoDeCanal sumiu de types/trafego.ts').toBeTruthy();
    expect(bloco!).toMatch(/\n\s*sabe_provar:\s*boolean;/);
    expect(bloco!).not.toMatch(/sabe_provar\?/);
  });
});

describe('os dois vocabulários de portão continuam separados e nomeados', () => {
  // `canais.ts` responde "o que ESTE CANAL pode fazer" com quatro estados.
  // `portoes.ts` responde "esta CAMPANHA pode medir/nascer/ativar" com cinco.
  // São perguntas diferentes e o repositório mantém as duas — o risco não é
  // colidir num arquivo (o TypeScript proíbe identificador duplicado), é
  // importar a errada. Estas provas fixam que cada módulo continua dono do seu
  // conjunto, para que uma fusão silenciosa não passe despercebida.
  it('canais.ts tem os quatro estados do canal', () => {
    const fonte = ler(CANAIS);
    const bloco = fonte.match(/export type EstadoDePortao =[\s\S]*?;/)?.[0] ?? '';
    for (const estado of ['PERMITIDO', 'BLOQUEADO', 'INDETERMINADO', 'NAO_APLICAVEL']) {
      expect(bloco, `estado ${estado} sumiu do contrato de canal`).toContain(estado);
    }
    expect(bloco).not.toContain('PRONTO');
  });

  it('portoes.ts tem os cinco estados da mensuração, e PRONTO não é PERMITIDO', () => {
    const bloco = ler('src/lib/trafego/portoes.ts')
      .match(/export type EstadoDePortao =[\s\S]*?;/)?.[0] ?? '';
    for (const estado of ['PRONTO', 'PARCIAL', 'NAO_PRONTO', 'INDETERMINADO', 'NAO_APLICAVEL']) {
      expect(bloco, `estado ${estado} sumiu do contrato de mensuração`).toContain(estado);
    }
    expect(bloco).not.toContain('PERMITIDO');
  });
});
