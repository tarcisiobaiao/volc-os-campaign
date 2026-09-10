// @vitest-environment jsdom
import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { PainelDeMensuracao } from '../PainelDeMensuracao';
import { conjuntoInicial, type Draft } from '../rascunho';
afterEach(cleanup);
function Bancada() {
  const [conjunto, setConjunto] = useState(() => ({ ...conjuntoInicial('adset-1', 'Conjunto', '2026-10-01T10:00', '10,00'),
    mensuracao: { proposito: 'OPTIMIZE' as const, fonteTipo: 'PIXEL' as const, fonteRef: 'pixel', conversaoRef: 'rewarded', eventoPadrao: '' } }));
  return <><PainelDeMensuracao draft={{ accountRef: 'conta', destinationUrl: 'https://example.com' } as Draft}
    conjunto={conjunto} propositosDaReceita={['OPTIMIZE']} motivoDaReceita={null}
    catalogoDeFontes={null} catalogoDeConversoes={null} lendoConversoes={false} erroDasConversoes={null}
    resumoDoConjunto={null} onDestino={() => {}} onLerConversoes={() => {}}
    onConjunto={(_, patch) => setConjunto(c => ({ ...c, ...patch }) as typeof c)} />
    <output data-testid="measurement">{JSON.stringify(conjunto.mensuracao)}</output></>;
}
it('ViewContent é selecionável sem catálogo de conversões personalizadas e limpa o caminho concorrente', () => {
  render(<Bancada />);
  fireEvent.change(screen.getByLabelText('Evento padrão do site'), { target: { value: 'CONTENT_VIEW' } });
  const medida = JSON.parse(screen.getByTestId('measurement').textContent!);
  expect(medida.eventoPadrao).toBe('CONTENT_VIEW');
  expect(medida.conversaoRef).toBe('');
  expect(medida.fonteRef).toBe('pixel');
});
