/**
 * O substituto da bancada visual no build de produção.
 *
 * ## Por que um arquivo, e não um `if`
 *
 * Guardar a rota com `import.meta.env.DEV` elimina o RAMO, e guardar o
 * `React.lazy` junto elimina a chamada — mas nenhum dos dois elimina o CHUNK. O
 * Rollup monta o grafo de módulos a partir de cada `import()` antes de qualquer
 * eliminação de código morto, e por isso o build de produção emitia
 * `assets/BancadaVisual-*.js` com as fixtures dentro, mesmo com a rota
 * inalcançável. Foi a prova de bundle que mediu isso; a prova de fonte passava.
 *
 * `vite.config.ts` troca o módulo por este quando `mode === 'production'`. O
 * `import()` continua no lugar, o chunk continua existindo — e o que ele contém
 * é este arquivo.
 */
import React from 'react';

/** Mantido para a prova de bundle ter o que procurar — e não achar. */
export const MARCADOR_DA_BANCADA = 'bancada-ausente-em-producao';

export const CENAS_DA_BANCADA: ReadonlyArray<never> = [];

export const BancadaVisual: React.FC = () => null;

export default BancadaVisual;
