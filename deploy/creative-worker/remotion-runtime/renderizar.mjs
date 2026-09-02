/**
 * O renderizador: um processo, um diretorio, um video.
 *
 * ## Contrato de entrada e saida
 *
 * Entrada: UM caminho para um arquivo JSON. O pedido nao viaja em `argv` de
 * proposito — `ps` e legivel por qualquer processo da maquina, e o titulo de uma
 * peca e material do cliente. O arquivo fica no diretorio exclusivo do trabalho,
 * que o chamador cria e apaga.
 *
 * Saida: UMA linha JSON em stdout, prefixada por `@@VOLC@@`. Todo o resto do
 * stdout/stderr e log do Remotion e do Chromium, e misturar log com contrato
 * faria o chamador parsear ruido.
 *
 * ## Hermetismo
 *
 * Nada aqui busca fonte na rede. A fonte e copiada para o `publicDir` do
 * trabalho pelo chamador, e `@remotion/fonts` a le por `staticFile`. O
 * `enableCaching: false` e deliberado: o ADR mediu que o cache de bundle do
 * webpack NAO invalida quando so `node_modules` muda, e um cache reaproveitado
 * mascararia exatamente a regressao que a prova de determinismo procura.
 */
import {bundle} from '@remotion/bundler';
import {renderMedia, selectComposition} from '@remotion/renderer';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import path from 'node:path';

const exigir = createRequire(import.meta.url);
const AQUI = path.dirname(new URL(import.meta.url).pathname);

function versoesCongeladas() {
  const nomes = ['remotion', '@remotion/bundler', '@remotion/renderer', '@remotion/fonts', 'react', 'react-dom'];
  const saida = {};
  for (const nome of nomes) {
    saida[nome] = exigir(`${nome}/package.json`).version;
  }
  saida['node'] = process.versions.node;
  return saida;
}

async function principal() {
  const caminhoDoPedido = process.argv[2];
  if (!caminhoDoPedido) {
    throw new Error('uso: node renderizar.mjs <caminho-do-pedido.json>');
  }
  const pedido = JSON.parse(readFileSync(caminhoDoPedido, 'utf8'));
  const {props, saida, publicDir, outDirDoBundle, codec, crf, x264Preset, audioCodec} = pedido;

  const iniciouBundle = process.hrtime.bigint();
  const serveUrl = await bundle({
    entryPoint: path.resolve(AQUI, 'src', 'entrada.ts'),
    publicDir,
    outDir: outDirDoBundle,
    // ver docstring: cache reaproveitado mascara regressao de determinismo
    enableCaching: false,
    onProgress: () => undefined,
  });
  const msBundle = Number(process.hrtime.bigint() - iniciouBundle) / 1e6;

  const composicao = await selectComposition({
    serveUrl,
    id: 'peca-volc',
    inputProps: props,
  });

  const iniciouRender = process.hrtime.bigint();
  await renderMedia({
    composition: composicao,
    serveUrl,
    codec: codec ?? 'h264',
    outputLocation: saida,
    inputProps: props,
    // Sem audio, `enforceAudioTrack` criaria uma faixa muda — e uma faixa muda
    // medida como "audio presente" e exatamente a ausencia virando valor.
    enforceAudioTrack: false,
    muted: props.audio === null,
    audioCodec: audioCodec ?? 'aac',
    crf: crf ?? 18,
    x264Preset: x264Preset ?? 'medium',
    overwrite: true,
    onProgress: () => undefined,
    logLevel: 'error',
  });
  const msRender = Number(process.hrtime.bigint() - iniciouRender) / 1e6;

  const relatorio = {
    ok: true,
    composicao: {
      id: composicao.id,
      largura: composicao.width,
      altura: composicao.height,
      fps: composicao.fps,
      duracaoEmQuadros: composicao.durationInFrames,
    },
    versoes: versoesCongeladas(),
    duracao_bundle_ms: Math.round(msBundle),
    duracao_render_ms: Math.round(msRender),
    saida,
  };
  process.stdout.write(`@@VOLC@@${JSON.stringify(relatorio)}\n`);
}

principal().catch((erro) => {
  process.stdout.write(
    `@@VOLC@@${JSON.stringify({ok: false, erro: String(erro && erro.message ? erro.message : erro)})}\n`,
  );
  process.exitCode = 1;
});
