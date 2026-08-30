/**
 * A preferência de densidade da grade, e a única coisa desta área que mora no
 * navegador.
 *
 * ⚠️ Preferência de visualização não é autoridade sobre nada. Se o valor sumir,
 * a tela abre em grade e ninguém perde ativo, aprovação ou job. Estado de
 * negócio continua inteiro no servidor: uma cópia local que discorde do
 * servidor é pior que não ter cópia.
 */
import { useCallback, useState } from 'react';

export type Densidade = 'grade' | 'lista';

const CHAVE_DENSIDADE = 'volc.criativos.densidade';

export function useDensidade(): [Densidade, (d: Densidade) => void] {
  const [densidade, setDensidade] = useState<Densidade>(() => {
    try {
      return localStorage.getItem(CHAVE_DENSIDADE) === 'lista' ? 'lista' : 'grade';
    } catch {
      return 'grade';
    }
  });
  const guardar = useCallback((d: Densidade) => {
    setDensidade(d);
    try {
      localStorage.setItem(CHAVE_DENSIDADE, d);
    } catch {
      /* modo privado ou storage cheio: a tela continua funcionando */
    }
  }, []);
  return [densidade, guardar];
}
