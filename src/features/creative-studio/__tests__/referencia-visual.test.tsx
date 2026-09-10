// @vitest-environment jsdom
import React from 'react';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { FotografiaReal } from '../componentes/FotografiaReal';
import type { Anexo } from '../tipos';

afterEach(cleanup);
it('oferece inspiração separada de colagem e exige escolha explícita', () => {
  const escolher = vi.fn();
  render(<FotografiaReal
    anexo={{ anexo_ref: 'crimg_' + 'a'.repeat(24), largura: 1080, altura: 1080,
      bytes_totais: 2048, exif_removido: true, content_sha256: 'b'.repeat(64) } as Anexo}
    modo="" enviando={false} onEnviar={vi.fn()} onRemover={vi.fn()} onModo={escolher}
    modos={[
      { id: 'referencia_visual', rotulo: 'Usar como inspiração visual', descricao: 'Novas versões, sem colagem.', preserva_pixels_da_foto: false },
      { id: 'hibrido', rotulo: 'Compor com a fotografia', descricao: 'Preservar pixels.', preserva_pixels_da_foto: true },
    ]} />);
  expect(screen.getAllByRole('radio').every(r => !(r as HTMLInputElement).checked)).toBe(true);
  fireEvent.click(screen.getByRole('radio', { name: /Usar como inspiração visual/ }));
  expect(escolher).toHaveBeenCalledWith('referencia_visual');
  expect(screen.queryByText('A pessoa e os detalhes da foto podem mudar.')).toBeNull();
});
