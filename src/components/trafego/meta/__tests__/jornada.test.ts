import { describe, expect, it } from 'vitest';
import { perguntaDaUrl, perguntasMeta } from '../jornada';
import { lerSelecaoDoAssistente } from '../ponteAssistente';

describe('jornada Meta', () => {
  it('começa pela conta e preserva o caminho de recibos existentes', () => {
    expect(perguntaDaUrl(new URLSearchParams(), false).id).toBe('conta');
    expect(perguntaDaUrl(new URLSearchParams('etapa=revisao&operacao=abc'), false).id).toBe('revisao');
    expect(perguntaDaUrl(new URLSearchParams('pergunta=inexistente'), false).id).toBe('conta');
  });
  it('pede conversão antes do público somente quando necessária', () => {
    expect(perguntasMeta(false).some(p => p.id === 'conversao')).toBe(false);
    const ids = perguntasMeta(true).map(p => p.id);
    expect(ids.indexOf('conversao')).toBeLessThan(ids.indexOf('publico'));
    expect(ids.indexOf('criativos')).toBeLessThan(ids.indexOf('revisao'));
  });
  it('a ponte aceita apenas referências limitadas, sem transformar URLs ou payloads em assets', () => {
    expect(lerSelecaoDoAssistente({ type: 'volc:creative-selection', masterRefs: ['master_12345', 'master_12345'] }))
      .toEqual({ masterRefs: ['master_12345'] });
    for (const masterRefs of [[], ['https://evil.example/image.png'], Array(11).fill('master_12345'), [null], [123]]) {
      expect(lerSelecaoDoAssistente({ type: 'volc:creative-selection', masterRefs })).toBeNull();
    }
    expect(lerSelecaoDoAssistente({ type: 'upload', masterRefs: ['master_12345'] })).toBeNull();
  });
});
