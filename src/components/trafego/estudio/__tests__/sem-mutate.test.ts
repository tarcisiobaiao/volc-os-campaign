/**
 * Esta frente não fala com o Google Ads. A interseção de ação é apresentação;
 * mutate e validate_only continuam no cockpit, atrás da trava.
 */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const ARQUIVOS = [
  'src/components/trafego/canal/jornada.ts',
  'src/components/trafego/estudio/EstudioMulticanal.tsx',
  'src/components/trafego/estudio/EstudioLigado.tsx',
  'src/pages/trafego/HubDeTrafegoPage.tsx',
];

describe('a bancada não executa Google Ads', () => {
  const juntos = ARQUIVOS.map((p) => readFileSync(p, 'utf8')).join('\n');

  it('não embute segredo, mutate da API nem chamada a googleapis', () => {
    expect(juntos).not.toMatch(/service_role/i);
    expect(juntos).not.toMatch(/SUPABASE_SERVICE_ROLE/);
    expect(juntos).not.toMatch(/googleads\.googleapis\.com/);
    expect(juntos).not.toMatch(/mutateGoogle/i);
    expect(juntos).not.toMatch(/validate_only['"]\s*:/);
  });

  it('Vídeo não oferece criação pela API no texto da tela', () => {
    const estudio = readFileSync('src/components/trafego/estudio/EstudioMulticanal.tsx', 'utf8');
    expect(estudio).toMatch(/Não cria campanha Video pela API/);
    expect(estudio).not.toMatch(/Criar campanha Video pela API/);
  });
});
