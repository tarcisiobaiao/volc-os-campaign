/**
 * A raiz registra UMA composicao, de proposito.
 *
 * O custo estrutural medido no ADR — "carregar as 15 composicoes e custo
 * estrutural atual" — nasce de uma raiz que importa 15 modulos, cada um
 * chamando `loadFont` no topo. Uma raiz de uma composicao nao tem esse custo,
 * e o hermetismo deixa de depender de tocar 15 arquivos de outra frente.
 *
 * A fonte e carregada por `@remotion/fonts` a partir do `publicDir` que o
 * renderizador monta — nunca por `@remotion/google-fonts`, que e exatamente a
 * dependencia de rede que o hermetismo remove.
 */
import React from 'react';
import {Composition, continueRender, delayRender, staticFile} from 'remotion';
import {loadFont} from '@remotion/fonts';
import {Peca, type PropsDaPeca} from './Composicao';

const ESPERA = delayRender('carregando a fonte local Inter');

loadFont({
  family: 'InterVolc',
  url: staticFile('Inter-Variable.ttf'),
  format: 'truetype',
  weight: '100 900',
})
  .then(() => continueRender(ESPERA))
  .catch((erro) => {
    // Falha de fonte permanece VISIVEL e sem artefato (decisao 5 do ADR).
    // Nao ha fallback para fonte de sistema: ela mudaria o pixel sem mudar o
    // pedido, e a assinatura determinista nao acusaria.
    throw new Error(`fonte local nao carregou: ${(erro as Error).message}`);
  });

const PADRAO: PropsDaPeca = {
  titulo: 'placeholder',
  apoio: 'placeholder',
  assinatura: 'placeholder',
  seed: 1,
  largura: 1080,
  altura: 1920,
  fps: 30,
  duracaoEmQuadros: 90,
  corDeFundo: '#0B0B0F',
  corDeDestaque: '#FF4D2E',
  audio: null,
};

export const Raiz: React.FC = () => (
  <Composition
    id="peca-volc"
    component={Peca}
    // Estes valores sao substituidos por `calculateMetadata` a partir dos props
    // reais. Registrar 1080x1920/90 aqui e so o que o tipo exige.
    durationInFrames={PADRAO.duracaoEmQuadros}
    fps={PADRAO.fps}
    width={PADRAO.largura}
    height={PADRAO.altura}
    defaultProps={PADRAO}
    calculateMetadata={({props}) => ({
      width: props.largura,
      height: props.altura,
      fps: props.fps,
      durationInFrames: props.duracaoEmQuadros,
    })}
  />
);
