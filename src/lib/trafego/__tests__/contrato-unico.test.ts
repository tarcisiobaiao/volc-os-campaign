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

describe('navegação interna não recarrega o documento', () => {
  // ⚠️ Defeito medido: o ÚNICO caminho de entrada da página canônica da campanha
  // era `<a href="/trafego/campanhas/:id">` dentro de uma linha do inventário.
  // Âncora crua faz recarga de documento inteiro — perde o estado da SPA e refaz
  // TODAS as leituras do Hub para abrir uma campanha. O mesmo valia para
  // `cockpit_href`, que o servidor monta como `/dashboard/campaign/:id`
  // (backend/app/trafego/inventario.py) e que também é rota deste aplicativo.
  const ROTAS_INTERNAS = [
    '/trafego/campanhas/',
    '/dashboard/campaign/',
    '/trafego/nova/',
    '/trafego?aba=',
  ];

  it('nenhum <a href> aponta para rota interna nos componentes de tráfego', () => {
    const { readdirSync, statSync } = require('node:fs') as typeof import('node:fs');
    const culpados: string[] = [];
    const varrer = (dir: string) => {
      for (const nome of readdirSync(dir)) {
        const caminho = resolve(dir, nome);
        if (statSync(caminho).isDirectory()) {
          if (nome === '__tests__') continue;
          varrer(caminho);
          continue;
        }
        if (!nome.endsWith('.tsx')) continue;
        const fonte = readFileSync(caminho, 'utf-8');
        // `<a ... href={...}` ou `href="..."` cujo destino começa com rota interna.
        for (const rota of ROTAS_INTERNAS) {
          const padrao = new RegExp(
            `<a[^>]*href=\\{?[\`'"][^\`'"]*${rota.replace(/[?/]/g, '\\$&')}`,
            's',
          );
          if (padrao.test(fonte)) {
            culpados.push(`${caminho.replace(raiz + '/', '')} → ${rota}`);
          }
        }
      }
    };
    varrer(resolve(raiz, 'src/components/trafego'));
    varrer(resolve(raiz, 'src/pages/trafego'));
    expect(
      culpados,
      'rota interna atrás de <a href> recarrega o documento inteiro; use <Link>',
    ).toEqual([]);
  });

  it('a linha do inventário navega com Link para as duas rotas internas', () => {
    const fonte = ler('src/components/trafego/inventario/LinhaDeCampanha.tsx');
    expect(fonte).toMatch(/<Link\s+to=\{`\/trafego\/campanhas\/\$\{c\.volc_campaign_id\}`\}/);
    expect(fonte).toMatch(/<Link\s+to=\{c\.cockpit_href\}/);
    expect(fonte).toMatch(/import \{ Link \} from 'react-router-dom';/);
  });
});
