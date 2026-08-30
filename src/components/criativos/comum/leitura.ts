/**
 * Os quatro estados que uma lista pode ter, e que a tela não pode confundir.
 *
 * DESIGN.md: "An empty result after filtering is different from an empty
 * source. Loading preserves layout. A failed read does not erase the last good
 * data without explaining its age."
 *
 * São quatro fatos com quatro ações diferentes:
 *
 * - `carregando`  → espere; a estrutura já está na tela para não pular depois.
 * - `erro`        → a leitura falhou; o que está na tela pode estar velho.
 * - `vazio`       → perguntei e a fonte não tem nada. Nada a filtrar.
 * - `vazio_apos_filtro` → a fonte tem coisas; ESTE recorte é que não tem.
 *
 * Achatar os dois últimos em "nada encontrado" produz a ação errada metade das
 * vezes: quem vê um estoque vazio para de procurar, quem vê um filtro vazio
 * afrouxa o filtro.
 */
export type EstadoDaLeitura = 'carregando' | 'erro' | 'vazio' | 'vazio_apos_filtro' | 'com_dados';

export interface SituacaoDaLista {
  carregando: boolean;
  erro: unknown;
  /** Quantas linhas o recorte atual devolveu. */
  visiveis: number;
  /**
   * Quantas existem sem filtro nenhum. `null` quando o servidor não informou:
   * sem esse número não dá para separar "fonte vazia" de "filtro vazio", e a
   * tela declara o recorte em vez de chutar o estoque.
   */
  universo: number | null;
  temFiltro: boolean;
}

export function classificarLeitura(s: SituacaoDaLista): EstadoDaLeitura {
  // O erro vem antes do vazio: uma leitura que falhou não sabe se há zero ou mil.
  if (s.erro) return 'erro';
  if (s.carregando) return 'carregando';
  if (s.visiveis > 0) return 'com_dados';
  if (s.temFiltro) {
    // Universo desconhecido com filtro ativo continua sendo "este recorte não
    // trouxe nada" — é a única afirmação que a tela pode provar.
    return 'vazio_apos_filtro';
  }
  if (s.universo !== null && s.universo > 0) {
    // Sem filtro declarado, mas o universo não é zero: alguma restrição
    // implícita está agindo. Dizer "a fonte está vazia" seria falso.
    return 'vazio_apos_filtro';
  }
  return 'vazio';
}
