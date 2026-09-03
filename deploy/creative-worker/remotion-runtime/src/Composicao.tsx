/**
 * A composicao propria do VOLC O.S.
 *
 * ## Por que existe uma composicao aqui, e nao um import da fabrica
 *
 * A fabrica externa (`/Users/mac/volc-factory/remotion`) carrega 15 composicoes
 * no topo de `Root.tsx` e cada uma chama `loadFont()` do `@remotion/google-fonts`
 * no topo do seu modulo. O efeito medido no ADR: renderizar UMA composicao baixa
 * as fontes de TODAS — 34 chamadas em 11 familias, nenhuma com `weights`/`subsets`.
 * Nenhuma das 11 esta licenciada e versionada neste repositorio.
 *
 * Hermetismo, ali, custaria obter 11 familias e tocar 15 arquivos de um
 * repositorio de outra frente. Aqui custa uma familia — a Inter, que ja esta
 * versionada com OFL 1.1 em `backend/app/criativo/bancada/fontes/` — e um
 * arquivo. "Fontes locais, licenciadas e MINIMAS" e literalmente o pedido.
 *
 * ## Determinismo
 *
 * Nada aqui le relogio, aleatoriedade ou ambiente. Todo movimento deriva de
 * `useCurrentFrame()` e dos props. `seed` entra na aparencia por uma funcao
 * pura — o mesmo pedido produz o mesmo pixel, e um pedido diferente produz
 * outro, que e o que a `assinatura_determinista` do recibo afirma.
 */
import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

export type PropsDaPeca = {
  titulo: string;
  apoio: string;
  assinatura: string;
  seed: number;
  largura: number;
  altura: number;
  fps: number;
  duracaoEmQuadros: number;
  corDeFundo: string;
  corDeDestaque: string;
  /** Nome do arquivo de audio dentro do publicDir, ou null para peca muda. */
  audio: string | null;
};

/** Gerador determinista: mesma seed, mesma sequencia. Sem `Math.random`. */
function embaralhador(seed: number): () => number {
  let estado = (seed >>> 0) || 1;
  return () => {
    // xorshift32 — puro, sem estado global e sem dependencia de plataforma.
    estado ^= estado << 13;
    estado >>>= 0;
    estado ^= estado >> 17;
    estado ^= estado << 5;
    estado >>>= 0;
    return estado / 0xffffffff;
  };
}

const FAMILIA = 'InterVolc';

export const Peca: React.FC<PropsDaPeca> = ({
  titulo,
  apoio,
  assinatura,
  seed,
  corDeFundo,
  corDeDestaque,
  audio,
}) => {
  const quadro = useCurrentFrame();
  const {fps, durationInFrames, width, height} = useVideoConfig();
  const menorLado = Math.min(width, height);
  const proximo = embaralhador(seed);

  // Doze particulas com posicao derivada da seed. Nao e enfeite: e a prova de
  // que a seed atravessa ate o pixel — dois seeds diferentes dao dois hashes.
  //
  // ⚠️ ACHADO MEDIDO, e a razao de cada `Math.round` abaixo. A primeira versao
  // posicionava as particulas em porcentagem fracionaria com
  // `translate(-50%, -50%)`. Duas execucoes do MESMO pedido produziam quadros
  // diferentes: 17 dos 90 quadros divergiam, e o diff no quadro 80 era de
  // **8 pixels em 2.073.600** (0,0004%), todos na faixa `y` 1918–1920 — a borda
  // inferior. A causa e uma particula centrada perto de `y=1` que fica metade
  // fora do quadro: o Chromium rasteriza esse recorte sub-pixel de dois jeitos.
  //
  // Nao e ruido aceitavel. A `assinatura_determinista` do recibo existe para
  // responder "o motor repetiu?", e uma resposta que muda sozinha nao responde
  // nada. As particulas passam a ficar em pixel INTEIRO e dentro de uma faixa
  // que nao encosta na borda — as duas coisas, porque so arredondar ainda
  // deixaria a que nasce no limite recortada.
  const inteiro = (v: number) => Math.round(v);
  const particulas = Array.from({length: 12}, (_, i) => {
    const bruto = {x: proximo(), y: proximo(), r: 0.4 + proximo() * 0.6, fase: proximo()};
    // faixa de 8% a 92%: nenhuma particula alcanca a borda do quadro
    return {
      x: inteiro(width * (0.08 + bruto.x * 0.84)),
      y: inteiro(height * (0.08 + bruto.y * 0.84)),
      d: inteiro(menorLado * 0.06 * bruto.r),
      opacidade: 0.1 + 0.1 * bruto.r,
      fase: bruto.fase,
      chave: i,
    };
  });

  const entrada = spring({frame: quadro, fps, config: {damping: 200}});
  const saida = interpolate(
    quadro,
    [durationInFrames - Math.round(fps * 0.6), durationInFrames - 1],
    [1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );

  return (
    <AbsoluteFill style={{backgroundColor: corDeFundo, fontFamily: `${FAMILIA}, sans-serif`}}>
      {audio ? <Audio src={staticFile(audio)} /> : null}

      {particulas.map((p) => {
        // A oscilacao tambem vai a pixel inteiro: um deslocamento fracionario
        // recria a mesma ambiguidade de rasterizacao que o arredondamento acima
        // acabou de fechar.
        const oscilacao = Math.round(
          Math.sin((quadro / fps + p.fase) * Math.PI * 2 * 0.35) * menorLado * 0.02,
        );
        return (
          <div
            key={p.chave}
            style={{
              position: 'absolute',
              left: p.x - Math.round(p.d / 2),
              top: p.y - Math.round(p.d / 2) + oscilacao,
              width: p.d,
              height: p.d,
              borderRadius: '50%',
              backgroundColor: corDeDestaque,
              opacity: p.opacidade,
            }}
          />
        );
      })}

      <AbsoluteFill
        style={{
          justifyContent: 'center',
          alignItems: 'flex-start',
          // Safe zone: 10% de margem em cada lado. O gate de safe zone mede
          // contra este numero, e ele mora no codigo que desenha — nao num
          // documento que descreve o que alguem pretendia desenhar.
          padding: `${height * 0.1}px ${width * 0.1}px`,
          opacity: saida,
        }}
      >
        <div
          style={{
            width: menorLado * 0.14,
            height: menorLado * 0.012,
            backgroundColor: corDeDestaque,
            transform: `scaleX(${entrada})`,
            transformOrigin: 'left center',
            marginBottom: menorLado * 0.045,
          }}
        />
        <Sequence from={0}>
          <div
            style={{
              fontSize: menorLado * 0.095,
              fontWeight: 800,
              lineHeight: 1.05,
              color: '#FFFFFF',
              letterSpacing: -menorLado * 0.002,
              transform: `translateY(${(1 - entrada) * menorLado * 0.06}px)`,
              opacity: entrada,
              maxWidth: '92%',
            }}
          >
            {titulo}
          </div>
        </Sequence>
        <Sequence from={Math.round(fps * 0.35)}>
          <TextoDeApoio
            texto={apoio}
            tamanho={menorLado * 0.042}
            cor="rgba(255,255,255,0.78)"
            atraso={Math.round(fps * 0.35)}
            deslocamento={menorLado * 0.04}
          />
        </Sequence>
        <Sequence from={Math.round(fps * 0.75)}>
          <TextoDeApoio
            texto={assinatura}
            tamanho={menorLado * 0.032}
            cor={corDeDestaque}
            atraso={Math.round(fps * 0.75)}
            deslocamento={menorLado * 0.03}
            espacamento={menorLado * 0.004}
            peso={700}
            margemSuperior={menorLado * 0.05}
          />
        </Sequence>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const TextoDeApoio: React.FC<{
  texto: string;
  tamanho: number;
  cor: string;
  atraso: number;
  deslocamento: number;
  espacamento?: number;
  peso?: number;
  margemSuperior?: number;
}> = ({texto, tamanho, cor, atraso, deslocamento, espacamento, peso, margemSuperior}) => {
  const quadro = useCurrentFrame();
  const {fps} = useVideoConfig();
  const e = spring({frame: quadro - atraso, fps, config: {damping: 200}});
  return (
    <div
      style={{
        marginTop: margemSuperior ?? tamanho * 0.7,
        fontSize: tamanho,
        fontWeight: peso ?? 500,
        color: cor,
        letterSpacing: espacamento ?? 0,
        lineHeight: 1.3,
        maxWidth: '88%',
        opacity: e,
        transform: `translateY(${(1 - e) * deslocamento}px)`,
      }}
    >
      {texto}
    </div>
  );
};
