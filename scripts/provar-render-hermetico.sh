#!/usr/bin/env bash
# Prova que o render Remotion do VOLC O.S. e hermetico, determinista e medido.
#
# ## Por que a prova NAO e por variavel de ambiente
#
# O ADR mediu que `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` sao INERTES contra o
# Remotion: `@remotion/renderer/dist/open-browser.js:103-105` lanca o Chromium com
# `--no-proxy-server`, `--proxy-server='direct://'` e `--proxy-bypass-list=*`
# embutidos, e nao existe `--offline` em ponto nenhum do renderer. Uma prova
# baseada em proxy morto passaria sem provar coisa alguma.
#
# ## Por que a prova NAO e por amostragem de `lsof`
#
# Porque amostragem prova PRESENCA e nunca AUSENCIA: entre duas amostras cabe uma
# conexao inteira. O adendo do ADR usou `lsof` porque nao tinha instrumento melhor
# a mao, e a leitura honesta daquele resultado era "nao observei rede", nao "nao
# houve rede".
#
# ## O instrumento que esta aqui
#
# `sandbox-exec` com `(deny network-outbound)` e uma excecao para loopback. O
# kernel recusa o `connect()` para qualquer destino externo — o processo recebe
# EPERM. Nao e observacao: e impossibilidade. Loopback fica liberado porque o
# bundler do Remotion sobe um servidor estatico em 127.0.0.1 e o Chromium precisa
# alcanca-lo; bloquear isso nao provaria hermetismo, so impediria o render.
#
# O DEGRAU 4 calibra o proprio instrumento: um processo de controle tenta uma
# conexao externa DENTRO do mesmo sandbox e a prova exige que ela seja RECUSADA.
# Sem essa calibracao, um sandbox que silenciosamente nao se aplicasse produziria
# um verde que nao significa nada.
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="$RAIZ/deploy/creative-worker/remotion-runtime"
FONTE="$RAIZ/backend/app/criativo/bancada/fontes/Inter-Variable.ttf"
PERFIL="$RAIZ/deploy/creative-worker/sem-rede.sb"
REPETICOES="${CRIATIVO_REPETICOES_DETERMINISMO:-4}"
TRABALHO="$(mktemp -d "${TMPDIR:-/private/tmp}/volc-hermetico-XXXXXX")"
trap 'rm -rf "$TRABALHO"' EXIT

passaram=0; falharam=0
ok()  { echo "  ok   $1"; passaram=$((passaram+1)); }
nok() { echo "  NAO  $1"; falharam=$((falharam+1)); }
nota(){ echo "  --   $1"; }
secao(){ echo; echo "DEGRAU $1"; }

exigir() { command -v "$1" >/dev/null 2>&1 || { echo "FALTA a ferramenta '$1'"; exit 2; }; }
exigir ffmpeg; exigir ffprobe; exigir node
[ -x /usr/bin/sandbox-exec ] || { echo "FALTA /usr/bin/sandbox-exec (esta prova e de macOS)"; exit 2; }
[ -d "$RUNTIME/node_modules" ] || { echo "FALTA $RUNTIME/node_modules — rode 'npm ci' la dentro"; exit 2; }
[ -f "$PERFIL" ] || { echo "FALTA o perfil de sandbox $PERFIL"; exit 2; }
[ -f "$FONTE" ] || { echo "FALTA a fonte licenciada $FONTE"; exit 2; }

gerar_leito() {
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "sine=frequency=110:sample_rate=48000:duration=3" \
    -f lavfi -i "sine=frequency=164.81:sample_rate=48000:duration=3" \
    -filter_complex "[0:a]volume=0.28[a];[1:a]volume=0.16[b];[a][b]amix=inputs=2:normalize=0,afade=t=in:st=0:d=0.4,afade=t=out:st=2.5:d=0.5,alimiter=limit=0.89" \
    -c:a pcm_s16le -ar 48000 -ac 2 -fflags +bitexact -flags +bitexact -map_metadata -1 "$1"
}

montar() { # $1=dir $2=seed $3=audio(json)
  mkdir -p "$1/public" "$1/bundle"
  cp "$FONTE" "$1/public/"
  [ -f "$TRABALHO/leito.wav" ] && cp "$TRABALHO/leito.wav" "$1/public/"
  cat > "$1/pedido.json" <<JSON
{
  "props": {
    "titulo": "Sua matricula 2027 comeca aqui",
    "apoio": "Turmas com vagas limitadas e bolsa por merito.",
    "assinatura": "COLEGIO POSITIVO",
    "seed": $2,
    "largura": 1080, "altura": 1920, "fps": 30, "duracaoEmQuadros": 90,
    "corDeFundo": "#0B0B0F", "corDeDestaque": "#FF4D2E",
    "audio": $3
  },
  "saida": "$1/peca.mp4",
  "publicDir": "$1/public",
  "outDirDoBundle": "$1/bundle"
}
JSON
}

render_sem_rede() {
  ( cd "$RUNTIME" && /usr/bin/sandbox-exec -f "$PERFIL" \
      node renderizar.mjs "$1/pedido.json" > "$1/stdout.txt" 2> "$1/stderr.txt" )
}

px() { ffmpeg -hide_banner -loglevel error -i "$1" -map 0:v -f rawvideo -pix_fmt yuv420p - 2>/dev/null | shasum -a 256 | cut -d' ' -f1; }
au() { ffmpeg -hide_banner -loglevel error -i "$1" -map 0:a -f s16le -ar 48000 -ac 2 - 2>/dev/null | shasum -a 256 | cut -d' ' -f1; }

echo "════════════════════════════════════════════════════════"
echo "  RENDER REMOTION HERMETICO — prova por execucao"
echo "  runtime : $RUNTIME"
echo "  perfil  : $PERFIL"

secao "0 — o leito sonoro e determinista"
gerar_leito "$TRABALHO/leito.wav"; gerar_leito "$TRABALHO/leito-b.wav"
h1="$(shasum -a 256 < "$TRABALHO/leito.wav"   | cut -d' ' -f1)"
h2="$(shasum -a 256 < "$TRABALHO/leito-b.wav" | cut -d' ' -f1)"
[ "$h1" = "$h2" ] && ok "duas geracoes do leito dao o mesmo byte (sha256 ${h1:0:16}…)" \
                  || nok "o leito variou entre geracoes"
rm -f "$TRABALHO/leito-b.wav"

secao "1 — render integral, com audio, SEM REDE EXTERNA"
montar "$TRABALHO/r1" 20260902 '"leito.wav"'
if render_sem_rede "$TRABALHO/r1"; then
  ok "o render terminou com codigo 0 dentro do sandbox sem rede"
else
  nok "o render falhou: $(tail -3 "$TRABALHO/r1/stderr.txt" 2>/dev/null | tr '\n' ' ')"
fi
grep -q '"ok":true' "$TRABALHO/r1/stdout.txt" 2>/dev/null \
  && ok "o renderizador reportou sucesso no contrato @@VOLC@@" \
  || nok "o renderizador nao reportou sucesso"
[ -s "$TRABALHO/r1/peca.mp4" ] \
  && ok "o arquivo existe e nao esta vazio ($(stat -f%z "$TRABALHO/r1/peca.mp4" 2>/dev/null) bytes)" \
  || nok "nao ha arquivo de saida"

secao "2 — o arquivo e um video integral de verdade"
V="$TRABALHO/r1/peca.mp4"
codec_v="$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$V" 2>/dev/null)"
codec_a="$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$V" 2>/dev/null)"
larg="$(ffprobe -v error -select_streams v:0 -show_entries stream=width  -of default=nw=1:nk=1 "$V" 2>/dev/null)"
alt="$(ffprobe  -v error -select_streams v:0 -show_entries stream=height -of default=nw=1:nk=1 "$V" 2>/dev/null)"
fps="$(ffprobe  -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=nw=1:nk=1 "$V" 2>/dev/null)"
nq="$(ffprobe   -v error -select_streams v:0 -count_frames -show_entries stream=nb_read_frames -of default=nw=1:nk=1 "$V" 2>/dev/null)"
dur="$(ffprobe  -v error -show_entries format=duration -of default=nw=1:nk=1 "$V" 2>/dev/null)"
echo "       codec=$codec_v/$codec_a  ${larg}x${alt}  fps=$fps  quadros=$nq  duracao=${dur}s"
[ "$codec_v" = "h264" ] && ok "video em h264" || nok "codec de video inesperado: $codec_v"
[ "$codec_a" = "aac" ]  && ok "audio em aac (a faixa existe — nao e peca muda)" || nok "codec de audio inesperado: $codec_a"
{ [ "$larg" = "1080" ] && [ "$alt" = "1920" ]; } \
  && ok "1080x1920 conferido NOS BYTES, nao declarado" || nok "dimensao inesperada ${larg}x${alt}"
[ "$fps" = "30/1" ] && ok "30 fps" || nok "fps inesperado: $fps"
[ "$nq" = "90" ] && ok "90 quadros CONTADOS (render integral, nao um still)" || nok "quadros contados: $nq"

secao "3 — determinismo: $REPETICOES execucoes do mesmo pedido"
# ⚠️ ACHADO ADVERSARIAL. A versao anterior fazia DOIS renders e a mensagem de
# entrega falava em seis — o numero maior existia so num comentario. Duas
# execucoes tambem sao um n pequeno demais para o defeito que este degrau existe
# para pegar: a divergencia medida (8 pixels na borda inferior) aparecia em
# ALGUMAS execucoes, nao em todas, e um par podia sair identico por sorte.
#
# `CRIATIVO_REPETICOES_DETERMINISMO` permite subir o n numa investigacao.
pxa="$(px "$TRABALHO/r1/peca.mp4")"
aua="$(au "$TRABALHO/r1/peca.mp4")"
mpa="$(shasum -a 256 < "$TRABALHO/r1/peca.mp4" | cut -d' ' -f1)"
px_distintos=1; au_distintos=1; mp_distintos=1
for n in $(seq 2 "$REPETICOES"); do
  montar "$TRABALHO/r$n" 20260902 '"leito.wav"'
  render_sem_rede "$TRABALHO/r$n" || true
  [ "$(px "$TRABALHO/r$n/peca.mp4")" = "$pxa" ] || px_distintos=$((px_distintos+1))
  [ "$(au "$TRABALHO/r$n/peca.mp4")" = "$aua" ] || au_distintos=$((au_distintos+1))
  [ "$(shasum -a 256 < "$TRABALHO/r$n/peca.mp4" | cut -d' ' -f1)" = "$mpa" ] \
    || mp_distintos=$((mp_distintos+1))
done
echo "       $REPETICOES execucoes · hashes de pixel distintos: $px_distintos"
{ [ -n "$pxa" ] && [ "$px_distintos" -eq 1 ]; } \
  && ok "as $REPETICOES execucoes dao os MESMOS quadros (sha256 ${pxa:0:16}…)" \
  || nok "os quadros divergiram: $px_distintos hashes distintos em $REPETICOES execucoes"
{ [ -n "$aua" ] && [ "$au_distintos" -eq 1 ]; } \
  && ok "as $REPETICOES execucoes dao o MESMO audio (sha256 ${aua:0:16}…)" \
  || nok "o audio divergiu: $au_distintos hashes distintos"
if [ "$mp_distintos" -eq 1 ]; then
  ok "o CONTAINER tambem e byte-identico nas $REPETICOES (sha256 ${mpa:0:16}…)"
else
  nota "o container difere entre execucoes ($mp_distintos hashes) — o muxer carimba"
  nota "metadado. O que decide determinismo e o PIXEL e o AUDIO acima."
fi

secao "4 — calibracao: o proprio sandbox recusa saida externa"
cat > "$TRABALHO/controle.mjs" <<'JS'
import net from 'node:net';
const s = net.connect(443, '1.1.1.1');
s.on('connect', () => { console.log('CONECTOU'); s.destroy(); process.exit(0); });
s.on('error', (e) => { console.log('RECUSADO:' + (e.code || 'erro')); process.exit(0); });
setTimeout(() => { console.log('SEM-RESPOSTA'); process.exit(0); }, 4000);
JS
fora="$(node "$TRABALHO/controle.mjs" 2>/dev/null | tail -1)"
dentro="$(/usr/bin/sandbox-exec -f "$PERFIL" node "$TRABALHO/controle.mjs" 2>/dev/null | tail -1)"
echo "       fora do sandbox: $fora · dentro do sandbox: $dentro"
if [ "$fora" = "CONECTOU" ]; then
  ok "fora do sandbox a MESMA tentativa conecta — o teste nao e vacuo"
else
  # ⚠️ Isto era `nota`, isto e, nao contava. Mas sem esta metade a prova inteira
  # perde o sentido: numa maquina sem rede, o DEGRAU 1 fica verde por ausencia de
  # rede e nao por hermetismo, e o relatorio afirmaria a segunda coisa.
  nok "fora do sandbox a mesma tentativa TAMBEM nao conectou ($fora): esta maquina nao"
  echo "       tem rede alcancavel, entao este script nao consegue distinguir"
  echo "       hermetismo de ausencia de rede. Rode com rede para provar."
fi
# ⚠️ ACHADO ADVERSARIAL. A versao anterior aceitava QUALQUER erro prefixado
# `RECUSADO` — inclusive `ENETUNREACH` e `ECONNREFUSED`, que uma maquina sem rede
# produz sozinha. Provar hermetismo com ausencia de rede prova outra coisa.
# `EPERM`/`EACCES` sao o kernel dizendo "voce nao tem permissao", que e o que o
# sandbox faz e o que so ele faz.
codigo_dentro="${dentro#*:}"
case "$codigo_dentro" in
  EPERM|EACCES)
    ok "dentro do sandbox o kernel RECUSA a saida ($codigo_dentro) — o bloqueio e real" ;;
  *)
    nok "dentro do sandbox a resposta foi '$dentro', e nao EPERM/EACCES — nao ha prova de bloqueio" ;;
esac

secao "5 — a seed atravessa ate o pixel"
montar "$TRABALHO/seed" 777 '"leito.wav"'
render_sem_rede "$TRABALHO/seed" || true
pxc="$(px "$TRABALHO/seed/peca.mp4")"
{ [ -n "$pxc" ] && [ "$pxc" != "$pxa" ]; } \
  && ok "outra seed produz outros quadros — a seed nao e enfeite de recibo" \
  || nok "duas seeds diferentes deram o mesmo pixel"

secao "6 — sem a fonte local, o render FALHA e nao deixa artefato"
# ⚠️ Diretorio de nome PROPRIO. Ele era `r4`, e o laco de determinismo do
# DEGRAU 3 passou a ocupar r2..rN: o degrau reusava um diretorio que ja
# tinha bundle e peca.mp4, e a prova ficava verde-falso nos dois sentidos.
# Defeito do arranjo, pego pelo proprio gate.
montar "$TRABALHO/sem-fonte" 20260902 '"leito.wav"'
rm -f "$TRABALHO/sem-fonte/public/Inter-Variable.ttf"
if render_sem_rede "$TRABALHO/sem-fonte"; then
  nok "o render SAIU sem a fonte local — houve fallback silencioso e o pixel mentiria"
else
  ok "o render falhou sem a fonte local (falha dura, decisao 5 do ADR)"
fi
[ -s "$TRABALHO/sem-fonte/peca.mp4" ] \
  && nok "sobrou artefato de um render que falhou" \
  || ok "nenhum artefato foi deixado para tras"

echo
echo "════════════════════════════════════════════════════════"
echo "  passaram $passaram · falharam $falharam"
if [ "$falharam" -eq 0 ]; then
  echo "  RENDER HERMETICO, DETERMINISTICO, INTEGRAL E MEDIDO"; exit 0
else
  echo "  HA FALHA ACIMA"; exit 1
fi
