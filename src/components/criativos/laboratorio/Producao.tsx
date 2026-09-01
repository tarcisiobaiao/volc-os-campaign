/**
 * Produzir uma peça de teste, localmente.
 *
 * ## A regra que governa este componente
 *
 * O botão de produzir só existe quando TRÊS coisas são verdade ao mesmo tempo:
 * a receita não tem impedimento, o motor escolhido está registrado no parque, e
 * ESTA máquina consegue rodar esse motor. As três são perguntas diferentes, e a
 * terceira é a que costuma ser esquecida — um motor que existe no catálogo e não
 * roda aqui produziria um botão que falha depois do clique.
 *
 * ## O que este componente não faz
 *
 * Não publica, não entrega a canal, não sobe arquivo para lugar nenhum. A peça
 * fica no disco desta máquina e é servida por uma rota que lê o caminho do
 * RECIBO, nunca da URL.
 */
import React from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { CircleCheck, CircleOff, Loader } from 'lucide-react';

import { Ficha, Secao } from '@/components/criativos/comum/Painel';
import { Selo } from '@/components/criativos/comum/Selo';
import { Button } from '@/components/ui/button';
import { criativosApi, codigoDaFalha, mensagemDaFalha } from '@/lib/criativosApi';
import { useTrabalhoDaBancada } from '@/hooks/useTrabalhoDaBancada';
import { cn } from '@/lib/utils';
import { procedenciaDaPeca } from '@/components/criativos/laboratorio/procedencia';
import {
  bytesLegiveis,
  custoLegivel,
  dimensoes,
  mimeLegivel,
} from '@/components/criativos/comum/formato';
import {
  ESTADO_DO_TRABALHO,
  type MotorDaBancada,
  type TrabalhoDaBancada,
  type ValidacaoDoRecibo,
} from '@/types/parqueCriativo';
import type { RenderRecipe } from './receita';

const GLIFO_DO_RESULTADO: Record<string, { g: typeof CircleCheck; tom: 'sucesso' | 'atencao' | 'erro' | 'neutro'; palavra: string }> = {
  PASS: { g: CircleCheck, tom: 'sucesso', palavra: 'Passou' },
  WARN: { g: CircleOff, tom: 'atencao', palavra: 'Ressalva' },
  FAIL: { g: CircleOff, tom: 'erro', palavra: 'Reprovou' },
  SKIPPED: { g: Loader, tom: 'neutro', palavra: 'Não executado' },
};

/** Traduz o gate para palavra de operação, mantendo o número visível. */
function descreverValidacao(v: ValidacaoDoRecibo): string {
  const d = (v.detalhe ?? {}) as Record<string, unknown>;
  if (v.gate === 'contraste' && typeof d.razao === 'number') {
    return `contraste medido ${d.razao}, piso ${String(d.piso_aa)}`;
  }
  if (v.gate === 'dimensao' && Array.isArray(d.produzido)) {
    return `${(d.produzido as number[]).join('×')} produzido`;
  }
  if (v.gate === 'arquivo_nao_vazio' && typeof d.bytes === 'number') {
    return `${d.bytes.toLocaleString('pt-BR')} bytes`;
  }
  if (v.resultado === 'SKIPPED' && typeof d.motivo === 'string') return d.motivo;
  return '';
}

const ROTULO_DO_GATE: Record<string, string> = {
  contraste: 'Contraste do texto',
  dimensao: 'Dimensão pedida',
  arquivo_nao_vazio: 'Arquivo produzido',
  cobertura_dos_slots: 'Todos os formatos',
  slot_pedido: 'Formato pedido',
};

/**
 * A peça, buscada com credencial.
 *
 * ⚠️ Não é `<img src="/api/...">`. Aquilo resolve contra a origem da PÁGINA (e o
 * FastAPI mora noutra) e não manda `Authorization` — `criativosApi.ts` documenta
 * esse defeito exato no topo, com a frase "toda miniatura dava 404 enquanto o
 * JSON dizia que o arquivo existia". A regressão chegou no commit seguinte ao
 * comentário. Aqui os bytes vêm pelo mesmo cliente autenticado das outras rotas.
 */
const PecaProduzida: React.FC<{
  trabalhoId: string;
  slot: string;
  largura: number | null;
  altura: number | null;
}> = ({ trabalhoId, slot, largura, altura }) => {
  const [url, setUrl] = React.useState<string | null>(null);
  const [erro, setErro] = React.useState(false);

  React.useEffect(() => {
    let vivo = true;
    let objeto: string | null = null;
    criativosApi
      .bytesDaBancada(trabalhoId, slot)
      .then((blob) => {
        if (!vivo) return;
        objeto = URL.createObjectURL(blob);
        setUrl(objeto);
      })
      .catch(() => vivo && setErro(true));
    return () => {
      vivo = false;
      // Sem isto, cada peça vista vaza um blob até a aba fechar.
      if (objeto) URL.revokeObjectURL(objeto);
    };
  }, [trabalhoId, slot]);

  if (erro) {
    return (
      <p className="py-8 text-center text-[12px] text-muted-foreground">
        A peça foi produzida e o arquivo não pôde ser lido agora.
      </p>
    );
  }
  if (!url) {
    return (
      <div
        className="mx-auto h-40 w-full animate-pulse rounded-sm bg-muted/60 motion-reduce:animate-none"
        aria-busy="true"
        aria-label={`Carregando a peça ${slot}`}
      />
    );
  }
  return (
    <img
      src={url}
      alt={`Peça produzida no formato ${slot}${largura && altura ? `, ${largura} por ${altura} pixels` : ''}`}
      className="mx-auto block h-auto max-h-64 w-auto max-w-full"
    />
  );
};

export const Producao: React.FC<{
  receita: RenderRecipe;
  liberado: boolean;
  seed: number;
}> = ({ receita, liberado, seed }) => {
  const maquina = useQuery({
    queryKey: ['criativos', 'bancada', 'motores'],
    queryFn: () => criativosApi.motoresDaBancada(),
    retry: false,
    staleTime: 60_000,
  });

  const [trabalhoId, setTrabalhoId] = React.useState<string | null>(null);
  const [motivoDoCancelamento, setMotivo] = React.useState('');
  const [pedindoCancelamento, setPedindoCancelamento] = React.useState(false);

  // Acompanhamento com backoff, pausa por visibilidade e parada em terminal.
  const acompanhamento = useTrabalhoDaBancada(trabalhoId);
  const trabalho = acompanhamento.trabalho;

  const produzir = useMutation({
    mutationFn: () =>
      criativosApi.produzirNaBancada({
        receitaId: receita.nome || 'receita-sem-nome',
        motorSlug: receita.motor?.slug ?? '',
        modoSlug: receita.modo?.slug ?? '',
        finalidadeSlug: receita.finalidade?.slug ?? '',
        seed,
        slots: receita.saidas.map((s) => s.slot),
        titulo: receita.nome,
        apoio: null,
      }),
    onSuccess: (t) => setTrabalhoId(t.id),
  });

  const cancelar = useMutation({
    mutationFn: (motivo: string) =>
      criativosApi.cancelarNaBancada(trabalho!.id, motivo),
    // ⚠️ O estado só muda quando o SERVIDOR confirma. Não há atualização
    // otimista aqui: dizer "cancelado" antes da confirmação é a forma mais
    // rápida de o operador achar que parou algo que continua rodando.
    onSuccess: () => {
      setPedindoCancelamento(false);
      setMotivo('');
      acompanhamento.recarregar();
    },
  });

  const retomar = useMutation({
    mutationFn: () => criativosApi.retomarNaBancada(trabalho!.id),
    // A retomada devolve um trabalho NOVO. Acompanhar o antigo depois disso
    // mostraria para sempre o `failed` que motivou a retomada.
    onSuccess: (novo) => setTrabalhoId(novo.id),
  });

  const daMaquina: MotorDaBancada[] = maquina.data?.motores ?? [];
  const motorRoda = Boolean(
    receita.motor && daMaquina.some((m) => m.slug === receita.motor?.slug),
  );
  const podeClicar = liberado && motorRoda && receita.saidas.length > 0;

  const estado = trabalho ? ESTADO_DO_TRABALHO[trabalho.estado] : null;

  // ⚠️ A procedência vem do MOTOR QUE PRODUZIU, casado pelo slug gravado no
  // recibo — não do motor selecionado agora no formulário. Ler o seletor diria
  // a natureza de um render que ainda não aconteceu, e uma peça antiga herdaria
  // o rótulo da escolha nova.
  //
  // Motor não encontrado na lista da máquina cai em `undefined`, e
  // `procedenciaDaPeca` responde `nao_declarada` — que é o que de fato se sabe.
  const procedencia = procedenciaDaPeca(
    trabalho?.recibo
      ? daMaquina.find((m) => m.slug === trabalho.recibo?.motorSlug)
      : undefined,
  );

  return (
    <Secao
      titulo="Produzir peça de teste"
      descricao="Roda nesta máquina, com recibo. Não publica e não entrega a canal nenhum."
      className="min-w-0"
    >
      <div className="space-y-4">
        {maquina.isLoading && (
          <p className="text-[13px] text-muted-foreground">
            Perguntando o que esta máquina consegue rodar…
          </p>
        )}

        {!maquina.isLoading && !motorRoda && (
          <p className="rounded-md border border-border px-3 py-2 text-[13px] leading-relaxed text-foreground">
            {receita.motor ? (
              <>
                <strong className="font-semibold">
                  Esta máquina não roda o motor “{receita.motor.nome}”.
                </strong>{' '}
                Ele existe no catálogo; o executor daqui não o tem.{' '}
                {daMaquina.length > 0 && (
                  <>Disponível agora: {daMaquina.map((m) => m.slug).join(', ')}.</>
                )}
              </>
            ) : (
              'Escolha um motor para saber se esta máquina consegue produzir.'
            )}
          </p>
        )}

        {/* ⚠️ O botão não aparece desabilitado quando falta capacidade: ele não
            aparece. Um botão desabilitado por falta de motor convida ao clique e
            depois não explica nada. O motivo está escrito acima, em texto. */}
        {motorRoda && (
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              onClick={() => produzir.mutate()}
              disabled={!podeClicar || produzir.isPending}
              className="min-h-10"
            >
              {produzir.isPending ? 'Produzindo…' : 'Produzir peça de teste'}
            </Button>
            {!liberado && (
              <span className="text-[12px] text-muted-foreground">
                Resolva os impedimentos antes de produzir.
              </span>
            )}
          </div>
        )}

        {produzir.isError && (
          <p role="alert" className="rounded-md border border-destructive/50 bg-destructive/[0.06] px-3 py-2 text-[13px] text-foreground">
            {mensagemDaFalha(produzir.error)}
            {codigoDaFalha(produzir.error) && (
              <span className="ml-2 font-mono text-[11px] text-muted-foreground">
                {codigoDaFalha(produzir.error)}
              </span>
            )}
          </p>
        )}

        {/* ⚠️ A região `aria-live` fica SEMPRE no DOM. Criá-la junto com o
            conteúdo faz o leitor de tela não anunciar nada: uma live region só
            anuncia mudança se já existia antes dela. */}
        <div aria-live="polite" role="status" className="sr-only">
          {trabalho && estado ? `${estado.palavra}. ${estado.descricao}` : ''}
        </div>

        {trabalho && estado && (
          <div className="space-y-3 border-t border-border pt-3">
            <div className="flex flex-wrap items-center gap-2">
              <Selo
                glifo={trabalho.estado === 'rendered' ? CircleCheck : trabalho.estado === 'failed' ? CircleOff : Loader}
                palavra={estado.palavra}
                descricao={estado.descricao}
                tom={estado.tom}
              />
              <span className="text-[12px] text-muted-foreground">
                tentativa {trabalho.tentativa} de {trabalho.maxTentativas}
                {trabalho.operario && ` · ${trabalho.operario}`}
              </span>
            </div>

            {trabalho.retomaDe && (
              <p className="text-[12px] text-muted-foreground">
                Esta é a {trabalho.retomadaN}ª retomada. O trabalho original continua
                guardado com o motivo da falha.
              </p>
            )}

            {acompanhamento.leituraFalhou && (
              <p className="rounded-md border border-warning/50 bg-warning/[0.08] px-3 py-2 text-[12px] leading-relaxed text-foreground">
                <strong className="font-semibold">A última leitura não chegou.</strong>{' '}
                O que está na tela é de{' '}
                {acompanhamento.lidoEm?.toLocaleTimeString('pt-BR') ?? 'antes'} e pode
                estar velho. {acompanhamento.leituraFalhou}
              </p>
            )}

            {acompanhamento.pausado && !acompanhamento.encerrado && (
              <p className="text-[12px] text-muted-foreground">
                Acompanhamento pausado enquanto esta aba está em segundo plano.
              </p>
            )}

            {/* ⚠️ `vivo` vem do lease, não do estado. Um trabalho em `running`
                cujo lease venceu NÃO está rodando. */}
            {!acompanhamento.encerrado && (
              <p className="text-[12px] text-muted-foreground">
                {trabalho.vivo
                  ? `Batimento em dia${trabalho.batimentoEm ? ` (último às ${new Date(trabalho.batimentoEm).toLocaleTimeString('pt-BR')})` : ''}.`
                  : 'Sem batimento no prazo. O trabalho volta para a fila; ninguém garante que ele esteja rodando.'}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-2">
              {/* O botão só existe quando o SERVIDOR diz que a operação cabe.
                  A tela não reimplementa a regra de transição. */}
              {trabalho.podeCancelar && !pedindoCancelamento && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="min-h-9"
                  onClick={() => setPedindoCancelamento(true)}
                >
                  Cancelar
                </Button>
              )}
              {trabalho.podeRetomar && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="min-h-9"
                  disabled={retomar.isPending}
                  onClick={() => retomar.mutate()}
                >
                  {retomar.isPending ? 'Retomando…' : 'Tentar de novo'}
                </Button>
              )}
            </div>

            {pedindoCancelamento && (
              <div className="space-y-2 rounded-md border border-border p-3">
                <label
                  htmlFor="motivo-do-cancelamento"
                  className="block text-[13px] font-medium text-foreground"
                >
                  Por que está cancelando?
                </label>
                <p className="text-[12px] text-muted-foreground">
                  O motivo fica no registro. Sem ele o servidor recusa.
                </p>
                <input
                  id="motivo-do-cancelamento"
                  value={motivoDoCancelamento}
                  onChange={(e) => setMotivo(e.target.value)}
                  className="min-h-9 w-full rounded-md border border-input bg-background px-2.5 text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    className="min-h-9"
                    disabled={motivoDoCancelamento.trim().length < 3 || cancelar.isPending}
                    onClick={() => cancelar.mutate(motivoDoCancelamento.trim())}
                  >
                    {cancelar.isPending ? 'Cancelando…' : 'Confirmar cancelamento'}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="min-h-9"
                    onClick={() => setPedindoCancelamento(false)}
                  >
                    Voltar
                  </Button>
                </div>
                {cancelar.isError && (
                  <p role="alert" className="text-[12px] text-destructive">
                    {mensagemDaFalha(cancelar.error)}
                  </p>
                )}
              </div>
            )}

            {trabalho.canceladoMotivo && (
              <p className="text-[12px] text-muted-foreground">
                Cancelado por {trabalho.canceladoPor}: “{trabalho.canceladoMotivo}”.
              </p>
            )}

            {trabalho.falha && (
              <p className="rounded-md border border-destructive/50 bg-destructive/[0.06] px-3 py-2 text-[13px] text-foreground">
                {trabalho.falha.mensagem}
                {trabalho.falha.permanente === false && ' Esta falha pode ser retentada.'}
              </p>
            )}

            {trabalho.recibo && (
              <div className="space-y-3">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {trabalho.recibo.artefatos.map((a) => (
                    <figure key={a.slot} className="min-w-0 rounded-md border border-border p-2">
                      <PecaProduzida
                        trabalhoId={trabalho.id}
                        slot={a.slot}
                        largura={a.largura}
                        altura={a.altura}
                      />
                      <figcaption className="mt-2 text-[12px] text-muted-foreground">
                        {/* ⚠️ `dimensoes()`, e não `{largura}x{altura}`. Uma
                            altura nula renderizada crua produzia `600x`, uma
                            peça com largura e sem altura, que não existe. A
                            autoridade de "não medido" já mora em
                            `comum/formato.ts`; uma segunda aqui divergiria. */}
                        {a.slot} · {dimensoes(a.largura, a.altura)} ·{' '}
                        {mimeLegivel(a.mime)} · {bytesLegiveis(a.bytes)} ·{' '}
                        <span className="font-mono" title={a.sha256}>
                          {a.sha256.slice(0, 12)}
                        </span>
                      </figcaption>
                      {/* A procedência viaja com a PEÇA, e não só na ficha lá
                          embaixo: quem olha a imagem precisa ler ali mesmo que
                          ela é um ensaio. */}
                      <p
                        className={cn(
                          'mt-1 text-[11px]',
                          procedencia.publicavel
                            ? 'text-muted-foreground'
                            : 'text-warning',
                        )}
                        title={procedencia.descricao}
                      >
                        {procedencia.palavra}
                      </p>
                    </figure>
                  ))}
                </div>

                <div>
                  <h3 className="text-[13px] font-medium text-foreground">Portões</h3>
                  <ul className="mt-1.5 space-y-1">
                    {trabalho.recibo.validacoes.map((v, i) => {
                      const visual = GLIFO_DO_RESULTADO[v.resultado] ?? GLIFO_DO_RESULTADO.SKIPPED;
                      const nota = descreverValidacao(v);
                      return (
                        <li key={`${v.gate}-${i}`} className="flex flex-wrap items-baseline gap-x-2 text-[12px]">
                          <span
                            className={cn(
                              'font-medium',
                              visual.tom === 'sucesso' && 'text-success',
                              visual.tom === 'erro' && 'text-destructive',
                              visual.tom === 'atencao' && 'text-warning',
                              visual.tom === 'neutro' && 'text-muted-foreground',
                            )}
                          >
                            {visual.palavra}
                          </span>
                          <span className="text-foreground">
                            {ROTULO_DO_GATE[v.gate] ?? v.gate}
                          </span>
                          {nota && <span className="text-muted-foreground">· {nota}</span>}
                        </li>
                      );
                    })}
                  </ul>
                </div>

                <Ficha
                  itens={[
                    { rotulo: 'Semente', valor: <span className="font-mono">{trabalho.recibo.seed}</span> },
                    {
                      rotulo: 'Motor',
                      valor: `${trabalho.recibo.motorSlug} v${trabalho.recibo.motorVersao}`,
                    },
                    {
                      rotulo: 'Procedência',
                      valor: (
                        <span
                          className={
                            procedencia.publicavel ? undefined : 'text-warning'
                          }
                        >
                          {procedencia.palavra}
                          <span className="ml-1 text-[12px] text-muted-foreground">
                            {procedencia.descricao}
                          </span>
                        </span>
                      ),
                    },
                    {
                      // ⚠️ `null` vira "custo não apurado", nunca "US$ 0,00". O
                      // motor local não custa dinheiro, mas zero é uma
                      // afirmação de custo APURADO, e um relatório de COGS que
                      // soma esses zeros fecha bonito e está errado.
                      rotulo: 'Custo apurado',
                      valor: custoLegivel(trabalho.recibo.custoRealUsd),
                    },
                    {
                      rotulo: 'Custo estimado',
                      valor: custoLegivel(trabalho.recibo.custoEstimadoUsd),
                    },
                    {
                      rotulo: 'Versões congeladas',
                      valor: (
                        <span className="text-[12px] text-muted-foreground">
                          {Object.entries(trabalho.recibo.versoes)
                            .map(([k, v]) => `${k}: ${k.endsWith('sha256') ? v.slice(0, 12) : v}`)
                            .join(' · ')}
                        </span>
                      ),
                    },
                    {
                      rotulo: 'Assinatura',
                      valor: (
                        <span className="font-mono text-[12px]" title={trabalho.recibo.assinaturaDeterminista}>
                          {trabalho.recibo.assinaturaDeterminista.slice(0, 20)}
                        </span>
                      ),
                    },
                    {
                      rotulo: 'Custo apurado',
                      valor:
                        trabalho.recibo.custoRealUsd === null ? (
                          <span className="text-muted-foreground">
                            Não apurado. Este motor roda nesta máquina e não cobra por peça.
                          </span>
                        ) : (
                          `US$ ${trabalho.recibo.custoRealUsd}`
                        ),
                    },
                  ]}
                />
                <p className="text-[12px] leading-relaxed text-muted-foreground">
                  Peça produzida e guardada nesta máquina. Nada foi publicado, entregue a
                  canal ou enviado para fora.
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </Secao>
  );
};
