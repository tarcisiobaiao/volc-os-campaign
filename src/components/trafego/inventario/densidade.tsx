/**
 * Qual das três formas do inventário está em cena.
 *
 * ## Por que isto é JavaScript e não só uma media query
 *
 * As três formas não são a mesma marcação com colunas escondidas: no desktop o
 * inventário é uma TABELA (cabeçalho de coluna de verdade, alinhamento para
 * comparar custo entre campanhas), e no telefone é uma LISTA de linhas altas.
 * Fazer isso com `hidden md:table` significaria emitir as duas marcações — o
 * leitor de tela leria a tela duas vezes e a prova não saberia qual das duas
 * está valendo.
 *
 * `useSyncExternalStore` lê a largura no PRIMEIRO render, não num efeito: se
 * fosse efeito, o telefone renderizaria a tabela por um quadro antes de
 * corrigir, e um piscar de layout numa lista longa é o tipo de coisa que faz o
 * operador perder o lugar onde estava lendo.
 */
import { useSyncExternalStore } from 'react';

export type Densidade = 'compacta' | 'media' | 'ampla';

/** `md` do Tailwind. Abaixo disso, tabela horizontal obriga a arrastar. */
export const LARGURA_MEDIA = 768;

/**
 * A partir daqui cabem as ONZE colunas da tabela comparativa.
 *
 * ⚠️ Era 1280 (`xl` do Tailwind) e subiu, porque o número de colunas mudou e a
 * janela NÃO é a largura da tabela: a navegação lateral do aplicativo ocupa
 * 320 px e o recuo da página come mais 64 px. Numa janela de 1280 sobram ~900 px
 * para onze colunas — o nome da campanha ficaria com menos de vinte caracteres
 * visíveis, e uma tabela onde o nome não cabe não serve para comparar nada. Em
 * 1440 sobram ~1050 px, que é onde a tabela começa a ser legível de verdade.
 *
 * Entre 768 e este limite as colunas se FUNDEM (compra num bloco, entrega
 * noutro); nenhuma delas some, e nada vira rolagem lateral.
 */
export const LARGURA_AMPLA = 1440;

export function densidadeDaLargura(largura: number): Densidade {
  if (largura < LARGURA_MEDIA) return 'compacta';
  if (largura < LARGURA_AMPLA) return 'media';
  return 'ampla';
}

function lerDensidade(): Densidade {
  if (typeof window === 'undefined') return 'ampla';
  return densidadeDaLargura(window.innerWidth);
}

function inscrever(avisar: () => void): () => void {
  if (typeof window === 'undefined') return () => undefined;
  window.addEventListener('resize', avisar);
  return () => window.removeEventListener('resize', avisar);
}

export function useDensidade(): Densidade {
  return useSyncExternalStore(inscrever, lerDensidade, () => 'ampla');
}
