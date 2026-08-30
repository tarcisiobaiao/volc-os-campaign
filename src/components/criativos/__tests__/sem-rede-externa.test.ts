/**
 * O Estúdio fala com UM servidor: o backend da casa. Nada mais.
 *
 * ## O que este teste protege
 *
 * Uma tela de criativos é o lugar mais natural para alguém "só testar" um
 * provedor direto do navegador: a chave viraria `VITE_…`, e tudo que começa com
 * `VITE_` é substituído pelo VALOR LITERAL no build. Colocar no `.env` não
 * esconderia nada, publicaria. O mesmo vale para uma chamada ao Google Ads ou
 * ao Meta escondida num render.
 *
 * O teste lê os arquivos como TEXTO de propósito: importar os módulos provaria
 * só o caminho que o teste exercita, e o defeito costuma estar no caminho que
 * ninguém exercita.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const RAIZES = [
  'src/components/criativos',
  'src/pages/criativos',
  'src/lib/criativosApi.ts',
  'src/hooks/useCriativosResumo.ts',
  'src/hooks/useCriativosJob.ts',
  'src/hooks/useCriativosEventos.ts',
  'src/hooks/useCriativosBiblioteca.ts',
  'src/hooks/useCriativosCatalogo.ts',
  'src/hooks/useCriativosVideo.ts',
];

function arquivos(caminho: string): string[] {
  if (statSync(caminho).isFile()) return [caminho];
  return readdirSync(caminho).flatMap((nome) => arquivos(join(caminho, nome)));
}

const TODOS = RAIZES.flatMap(arquivos).filter((f) => /\.tsx?$/.test(f));
const FONTE = TODOS.filter((f) => !f.includes('__tests__'));
const JUNTOS = FONTE.map((f) => readFileSync(f, 'utf8')).join('\n');

/**
 * O CÓDIGO, sem as linhas que são comentário inteiro.
 *
 * ⚠️ Só linhas inteiramente de comentário são removidas. Um removedor de `//`
 * genérico apagaria `https://` de dentro de uma string e esconderia justamente
 * a chamada a terceiro que esta varredura existe para achar.
 *
 * Sem isto, um comentário que EXPLICA por que a aurora não pinta estado
 * operacional reprovaria a regra que ele documenta.
 */
function semComentarios(texto: string): string {
  return texto
    .split('\n')
    .filter((linha) => !/^\s*(\/\/|\*|\/\*)/.test(linha))
    .join('\n');
}

const CODIGO = FONTE.map((f) => semComentarios(readFileSync(f, 'utf8'))).join('\n');

describe('o Estúdio não fala com terceiros pelo navegador', () => {
  it('encontrou os arquivos que diz auditar', () => {
    expect(FONTE.length).toBeGreaterThan(15);
  });

  it('não chama provedor de imagem, vídeo ou anúncio direto do browser', () => {
    expect(JUNTOS).not.toMatch(/api\.openai\.com/);
    expect(JUNTOS).not.toMatch(/generativelanguage\.googleapis\.com/);
    expect(JUNTOS).not.toMatch(/googleads\.googleapis\.com/);
    expect(JUNTOS).not.toMatch(/graph\.facebook\.com/);
    expect(JUNTOS).not.toMatch(/api\.replicate\.com/);
    expect(JUNTOS).not.toMatch(/api\.elevenlabs\.io/);
    expect(JUNTOS).not.toMatch(/fal\.run/);
  });

  it('não embute segredo nem chave de provedor', () => {
    expect(JUNTOS).not.toMatch(/service_role/i);
    expect(JUNTOS).not.toMatch(/SUPABASE_SERVICE_ROLE/);
    expect(JUNTOS).not.toMatch(/VITE_[A-Z_]*API_KEY/);
    expect(JUNTOS).not.toMatch(/\bsk-[A-Za-z0-9]/);
    expect(JUNTOS).not.toMatch(/X-API-Key/i);
  });

  it('não monta caminho de storage: as URLs chegam assinadas do servidor', () => {
    expect(JUNTOS).not.toMatch(/storage\/v1\/object/);
    expect(JUNTOS).not.toMatch(/storageChave/);
    expect(JUNTOS).not.toMatch(/\.from\(\s*['"]criativos/);
  });

  it('só o cliente do Estúdio chama fetch, e só contra a base configurada', () => {
    const comFetch = FONTE.filter((f) => /\bfetch\(/.test(semComentarios(readFileSync(f, 'utf8'))));
    expect(comFetch).toEqual(['src/lib/criativosApi.ts']);

    const cliente = readFileSync('src/lib/criativosApi.ts', 'utf8');
    expect(cliente).toMatch(/VITE_PAUTADOR_API_URL/);
    // Toda URL sai de `endereco()`, que concatena API_BASE com o prefixo.
    expect(cliente).toMatch(/const PREFIXO = '\/api\/criativos'/);
    expect(semComentarios(cliente)).not.toMatch(/fetch\(\s*['"`]https?:/);
  });

  it('o token viaja em cabeçalho, nunca em query string', () => {
    const cliente = readFileSync('src/lib/criativosApi.ts', 'utf8');
    expect(cliente).toMatch(/Authorization: `Bearer \$\{token\}`/);
    expect(cliente).not.toMatch(/access_token=/);
    expect(cliente).not.toMatch(/token=\$\{/);
    // `EventSource` não manda cabeçalho: usá-lo obrigaria o token à URL.
    expect(CODIGO).not.toMatch(/new EventSource/);
  });

  it('nenhum estado de negócio vive no navegador, só a densidade da grade', () => {
    const comStorage = FONTE.filter((f) =>
      /localStorage|sessionStorage/.test(semComentarios(readFileSync(f, 'utf8'))),
    );
    expect(comStorage).toEqual(['src/components/criativos/biblioteca/densidade.ts']);
    const densidade = readFileSync('src/components/criativos/biblioteca/densidade.ts', 'utf8');
    expect(densidade).toMatch(/volc\.criativos\.densidade/);
  });

  it('a aurora VOLC não pinta estado operacional', () => {
    expect(CODIGO).not.toMatch(/aurora-blue|aurora-purple|aurora-orange|gradient-aurora|text-aurora/);
  });

  it('não usa os padrões visuais proibidos pelo DESIGN.md', () => {
    expect(CODIGO).not.toMatch(/transition:\s*all|transition-all/);
    expect(CODIGO).not.toMatch(/backdrop-blur|\bglass\b/);
    expect(CODIGO).not.toMatch(/background-clip:\s*text|bg-clip-text|gradient-text/);
    expect(CODIGO).not.toMatch(/shadow-glow|hover-glow|animate-pulse-glow/);
    // Cartão dentro de cartão: `Secao` é superfície de trabalho, não pilha.
    expect(CODIGO).not.toMatch(/<Card[\s>]/);
  });

  it('não há travessão em texto de interface', () => {
    // O travessão é estilo de comentário da casa; em texto renderizado ele vira
    // pausa que leitor de tela lê de formas diferentes e que quebra em telas
    // estreitas. A varredura ignora as linhas de comentário.
    const ofensas: string[] = [];
    for (const arquivo of FONTE) {
      readFileSync(arquivo, 'utf8')
        .split('\n')
        .forEach((linha, i) => {
          const semComentario = linha.replace(/^\s*(\/\/|\*|\/\*).*$/, '');
          if (semComentario.includes('—')) ofensas.push(`${arquivo}:${i + 1}`);
        });
    }
    expect(ofensas).toEqual([]);
  });
});
