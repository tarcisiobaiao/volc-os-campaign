import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const ARQUIVOS = [
  'src/components/trafego/hub/adaptacao.ts',
  'src/components/trafego/hub/contrato.ts',
  'src/components/trafego/hub/PropostaDeAcao.tsx',
  'src/pages/trafego/CampanhaCanonPage.tsx',
  'src/pages/trafego/HubDeTrafegoPage.tsx',
  'src/components/trafego/canal/jornada.ts',
  'src/components/trafego/estudio/EstudioMulticanal.tsx',
  'src/components/trafego/estudio/EstudioLigado.tsx',
  'src/hooks/useEstadoDoHub.ts',
  'src/hooks/useCampanhaCanonica.ts',
];

describe('nenhuma ação privilegiada sai do Hub', () => {
  it('os arquivos da frente não embutem segredo nem mutate', () => {
    const juntos = ARQUIVOS.map((p) => readFileSync(p, 'utf8')).join('\n');
    expect(juntos).not.toMatch(/service_role/i);
    expect(juntos).not.toMatch(/SUPABASE_SERVICE_ROLE/);
    expect(juntos).not.toMatch(/googleads\.googleapis\.com/);
    expect(juntos).not.toMatch(/n8n\.[a-z]+\/webhook/i);
    expect(juntos).not.toMatch(/mutateGoogle/i);
  });
});
