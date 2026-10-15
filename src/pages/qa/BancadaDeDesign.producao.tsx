/**
 * O substituto da bancada de design no build de produção.
 *
 * Mesmo motivo de `BancadaVisual.producao.tsx`: o guarda de DEV elimina a rota
 * e a chamada, mas não o chunk do `import()`. `vite.config.ts` troca o módulo
 * por este quando `mode === 'production'`, e a prova de bundle confere.
 */
import React from 'react';

/** Mantido para a prova de bundle ter o que procurar — e não achar. */
export const MARCADOR_DA_BANCADA_DE_DESIGN = 'bancada-de-design-ausente-em-producao';

const BancadaDeDesign: React.FC = () => null;

export default BancadaDeDesign;
