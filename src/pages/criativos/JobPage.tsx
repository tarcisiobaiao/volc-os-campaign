/**
 * `/criativos/jobs/:creativeJobId` — o trabalho durável.
 *
 * ## A ordem que faz a tela sobreviver a um F5
 *
 * 1. `GET /jobs/{id}` traz o estado completo, inclusive `cursorEventos`.
 * 2. Só então o fluxo de eventos abre, a partir desse cursor.
 *
 * Invertendo a ordem, uma reconexão que perdesse o começo deixaria a tela sem
 * saber quantas peças foram pedidas. O job é a autoridade; o fluxo é o
 * incremento. É por isso que `jobId` só é entregue ao hook do fluxo DEPOIS que
 * a leitura por HTTP chegou.
 *
 * ## Vídeo observado entra por aqui e sai por outra tela
 *
 * `procedenciaExecucao === 'observado'` não é uma variação do job de imagem: é
 * outra coisa, produzida por outra fábrica, e a leitura editorial de vídeo é
 * quem sabe apresentá-la. A chave da leitura é o slug do build, que vem em
 * `origemExterna.identificadorDoBuild`.
 */
import React from 'react';
import { useLocation, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { RefreshCw, XCircle } from 'lucide-react';

import { Layout } from '@/components/layout/Layout';
import { Button } from '@/components/ui/button';
import { CabecalhoDoEstudio, Corpo, Secao } from '@/components/criativos/comum/Painel';
import { Carregando, ErroDeLeitura, Indisponivel } from '@/components/criativos/comum/Estados';
import { SeloDoJob, SeloDeProcedencia } from '@/components/criativos/comum/Selo';
import { PainelDeFase, PecaDoJob } from '@/components/criativos/job/Acompanhamento';
import { frasePecas, ofertaDeCancelamento, ofertaDeRetry, resumirPecas } from '@/components/criativos/job/pecas';
import { LeituraDeVideo } from '@/components/criativos/video/LeituraDeVideo';
import { custoLegivel, instante } from '@/components/criativos/comum/formato';
import { chaveDoJob, useAcoesDoJob, useCriativosJob } from '@/hooks/useCriativosJob';
import { useCriativosEventos } from '@/hooks/useCriativosEventos';
import { useCriativosVideo } from '@/hooks/useCriativosVideo';
import { codigoDaFalha, mensagemDaFalha } from '@/lib/criativosApi';
import { jobTerminou, type CreativeJob } from '@/types/criativos';

const JobPage: React.FC = () => {
  const { creativeJobId } = useParams<{ creativeJobId: string }>();
  const local = useLocation();
  const replay = Boolean((local.state as { replay?: boolean } | null)?.replay);

  const cliente = useQueryClient();
  const consulta = useCriativosJob(creativeJobId);
  const job = consulta.data;

  const observado = job?.procedenciaExecucao === 'observado';
  const buildSlug = job?.origemExterna?.identificadorDoBuild;
  const video = useCriativosVideo(buildSlug, Boolean(observado));

  const acoes = useAcoesDoJob(creativeJobId);

  const aoAtualizarJob = React.useCallback(
    (novo: CreativeJob) => cliente.setQueryData(chaveDoJob(novo.id), novo),
    [cliente],
  );
  const aoTerminar = React.useCallback(() => void consulta.refetch(), [consulta]);

  const fluxo = useCriativosEventos({
    // ⚠️ `undefined` enquanto o job não chegou: é o que garante que o fluxo
    // abra com o cursor certo em vez de abrir em zero e reprocessar tudo.
    jobId: job ? creativeJobId : undefined,
    // ⚠️ `0`, e não `job.cursorEventos`.
    //
    // `cursorEventos` é onde a HISTÓRIA está, não onde a leitura deve começar.
    // Abrindo o stream nele, o servidor respondia "nada de novo depois do 9" e a
    // tela dizia "Ainda não houve nenhum evento deste trabalho" para um job com
    // nove eventos gravados. A frase era falsa, e falsa justamente na tela que
    // existe para contar o que aconteceu.
    //
    // Numa carga nova o cliente não viu nada, então o cursor honesto é 0. O
    // `cursorEventos` continua servindo para o que foi feito: RECONECTAR de onde
    // parou, e isso o próprio hook guarda a partir do último `seq` recebido.
    cursorInicial: 0,
    ativo: Boolean(job) && !observado && !jobTerminou(job.estado),
    aoAtualizarJob,
    aoTerminar,
  });

  const renovarPrevias = React.useCallback(() => void consulta.refetch(), [consulta]);

  if (consulta.isLoading) {
    return (
      <Layout>
        <CabecalhoDoEstudio
          kicker="Trabalho"
          titulo="Carregando o trabalho"
          proposito="Lendo o estado guardado no servidor antes de abrir o acompanhamento ao vivo."
          voltar={{ para: '/criativos', rotulo: 'Estúdio Criativo' }}
        />
        <Corpo>
          <Carregando rotulo="Lendo o trabalho" linhas={3} altura="h-24" />
        </Corpo>
      </Layout>
    );
  }

  if (consulta.isError || !job) {
    return (
      <Layout>
        <CabecalhoDoEstudio
          kicker="Trabalho"
          titulo="Trabalho não lido"
          proposito="A leitura deste trabalho não chegou. Nada abaixo foi confirmado pelo servidor."
          voltar={{ para: '/criativos', rotulo: 'Estúdio Criativo' }}
        />
        <Corpo>
          <ErroDeLeitura
            mensagem={mensagemDaFalha(consulta.error)}
            codigo={codigoDaFalha(consulta.error)}
            aoTentarDeNovo={() => void consulta.refetch()}
          />
        </Corpo>
      </Layout>
    );
  }

  const resumo = resumirPecas(job.renditions);
  const retry = ofertaDeRetry(job);
  const cancelamento = ofertaDeCancelamento(job);

  return (
    <Layout>
      <CabecalhoDoEstudio
        kicker={observado ? 'Build observado' : 'Trabalho'}
        titulo={job.projetoTitulo}
        proposito={
          observado
            ? 'Leitura de um build produzido por uma fábrica externa. O VOLC O.S. não renderizou este vídeo.'
            : 'Uma peça por formato, cada uma com estado próprio. Você pode sair desta tela sem interromper nada.'
        }
        voltar={{ para: '/criativos', rotulo: 'Estúdio Criativo' }}
        situacao={
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <SeloDoJob estado={job.estado} />
            <SeloDeProcedencia procedencia={job.procedenciaExecucao} />
            <span className="text-[12px] text-muted-foreground">
              Motor {job.motor} {job.motorVersao}. Tentativa {job.tentativa}.{' '}
              {custoLegivel(job.custoRealUsd ?? job.custoEstimadoUsd)}. Criado em{' '}
              {instante(job.criadoEm)}.
            </span>
          </div>
        }
      />

      <Corpo className="space-y-6">
        {replay && (
          <div
            role="status"
            className="rounded-md border border-border bg-muted/50 px-4 py-3 text-[13px] leading-relaxed text-foreground"
          >
            Este pedido já existia. O servidor reconheceu o reenvio do mesmo formulário e devolveu o
            trabalho que já estava registrado: nenhuma peça nova foi produzida e nada foi cobrado de
            novo.
          </div>
        )}

        {observado ? (
          video.isLoading ? (
            <Carregando rotulo="Lendo o build observado" linhas={3} altura="h-24" />
          ) : !buildSlug ? (
            <Indisponivel
              titulo="Build sem identificador"
              motivo="Este trabalho está marcado como observado, mas não guardou o identificador do build externo. Sem ele, a leitura editorial não pode ser montada."
            />
          ) : video.isError || !video.data ? (
            <ErroDeLeitura
              mensagem={mensagemDaFalha(video.error)}
              codigo={codigoDaFalha(video.error)}
              ressalva="O trabalho existe e o estado acima é real. O que não chegou foi a leitura do build."
              aoTentarDeNovo={() => void video.refetch()}
            />
          ) : (
            <LeituraDeVideo leitura={video.data} />
          )
        ) : (
          <>
            <Secao
              titulo="Acompanhamento"
              descricao="A etapa que o servidor relatou. Sem estimativa e sem barra inventada."
            >
              <PainelDeFase
                job={job}
                eventos={fluxo.eventos}
                conexao={fluxo.conexao}
                falhaDoFluxo={fluxo.falha}
              />
            </Secao>

            {job.falha && (
              <Indisponivel titulo="O trabalho falhou por inteiro" motivo={job.falha.mensagem} />
            )}

            <Secao
              titulo="Peças"
              descricao={frasePecas(resumo)}
              acao={
                <div className="flex flex-wrap items-center gap-2">
                  {cancelamento.disponivel && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => acoes.cancelar.mutate()}
                      disabled={acoes.cancelar.isPending}
                      title={cancelamento.motivo}
                    >
                      <XCircle className="h-4 w-4" aria-hidden />
                      {acoes.cancelar.isPending ? 'Interrompendo' : 'Interromper'}
                    </Button>
                  )}
                  {retry.disponivel && (
                    <Button
                      size="sm"
                      onClick={() => acoes.retentar.mutate()}
                      disabled={acoes.retentar.isPending}
                    >
                      <RefreshCw className="h-4 w-4" aria-hidden />
                      {acoes.retentar.isPending ? 'Pedindo' : 'Preencher as peças que faltaram'}
                    </Button>
                  )}
                </div>
              }
            >
              <p className="mb-3 text-pretty text-[12px] leading-relaxed text-muted-foreground">
                {retry.disponivel ? retry.motivo : `Repetir não está disponível. ${retry.motivo}`}
              </p>

              {(acoes.retentar.isError || acoes.cancelar.isError) && (
                <ErroDeLeitura
                  className="mb-3"
                  mensagem={mensagemDaFalha(acoes.retentar.error ?? acoes.cancelar.error)}
                  codigo={codigoDaFalha(acoes.retentar.error ?? acoes.cancelar.error)}
                  ressalva="Nada foi alterado. As peças já prontas continuam prontas."
                />
              )}

              {job.renditions.length ? (
                <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                  {job.renditions.map((peca) => (
                    <PecaDoJob key={peca.id} peca={peca} aoRenovar={renovarPrevias} />
                  ))}
                </ul>
              ) : (
                <p className="text-[13px] leading-relaxed text-muted-foreground">
                  Nenhuma peça foi registrada neste trabalho ainda. Assim que o motor aceitar o
                  pedido, cada formato aparece aqui com estado próprio.
                </p>
              )}
            </Secao>
          </>
        )}
      </Corpo>
    </Layout>
  );
};

export default JobPage;
