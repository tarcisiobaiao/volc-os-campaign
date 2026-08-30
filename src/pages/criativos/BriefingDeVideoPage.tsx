/**
 * `/criativos/videos/novo` — o briefing de vídeo, com a limitação declarada.
 *
 * ## Por que não há formulário e não há botão de gerar
 *
 * Porque o VOLC O.S. ainda não inicia render de vídeo. Um formulário completo
 * terminando em "ainda não dá" gasta o tempo de quem o preencheu, e um botão
 * que parece funcionar e falha é pior que a ausência do botão. O DESIGN.md pede
 * o contrário: "Explain why an action is unavailable and what prerequisite is
 * missing."
 *
 * ⚠️ O MOTIVO vem do servidor (`limitacaoDeclarada`), não daqui. Escrever a
 * limitação no bundle congelaria uma versão da verdade que muda no dia em que a
 * isolação avançar, e a tela continuaria dizendo a versão antiga.
 */
import React from 'react';
import { FileVideo } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Layout } from '@/components/layout/Layout';
import { CabecalhoDoEstudio, Corpo, Secao } from '@/components/criativos/comum/Painel';
import { Carregando, ErroDeLeitura, Indisponivel, Vazio } from '@/components/criativos/comum/Estados';
import { useCriativosVideo, useCriativosVideos } from '@/hooks/useCriativosVideo';
import { codigoDaFalha, mensagemDaFalha } from '@/lib/criativosApi';

const BriefingDeVideoPage: React.FC = () => {
  const catalogo = useCriativosVideos();
  const builds = catalogo.data?.builds ?? [];
  const disponivel = catalogo.data?.disponivel ?? false;

  // A frase da limitação mora dentro da leitura de um build. Lemos o primeiro
  // para ter o texto do servidor em vez de inventar o motivo técnico; a mesma
  // leitura fica no cache para quando alguém abrir esse build.
  const primeiro = useCriativosVideo(builds[0], builds.length > 0);
  const limitacao = primeiro.data?.limitacaoDeclarada ?? null;

  return (
    <Layout>
      <CabecalhoDoEstudio
        kicker="Vídeo"
        titulo="Briefing de vídeo"
        proposito="Hoje o Estúdio LÊ builds de vídeo produzidos pela fábrica externa. Iniciar um render novo por aqui ainda não é possível, e o motivo abaixo vem do servidor."
        voltar={{ para: '/criativos', rotulo: 'Estúdio Criativo' }}
      />

      <Corpo className="space-y-6">
        <Secao
          titulo="Iniciar um render novo"
          descricao="O que falta para esta ação existir, dito pelo servidor."
        >
          {catalogo.isLoading || primeiro.isLoading ? (
            <Carregando rotulo="Lendo a situação do vídeo" linhas={1} altura="h-20" />
          ) : limitacao ? (
            <Indisponivel titulo="Ainda não é possível iniciar um render por aqui" motivo={limitacao} />
          ) : (
            <Indisponivel
              titulo="Ainda não é possível iniciar um render por aqui"
              motivo="O servidor não declarou o motivo nesta leitura. Esta tela não inventa a explicação técnica: enquanto a declaração não chegar, o que se sabe é que a ação não está disponível."
            />
          )}
          <p className="mt-3 text-pretty text-[13px] leading-relaxed text-muted-foreground">
            Não há formulário nesta tela de propósito. Preencher tema, hook, voz e beats para
            descobrir no fim que nada pode ser enviado seria trabalho jogado fora.
          </p>
        </Secao>

        <Secao
          titulo="Builds observados"
          descricao="O que a fábrica externa já produziu e o Estúdio consegue ler, inspecionar e aprovar."
        >
          {catalogo.isLoading ? (
            <Carregando rotulo="Lendo os builds disponíveis" linhas={3} altura="h-11" />
          ) : catalogo.isError ? (
            <ErroDeLeitura
              mensagem={mensagemDaFalha(catalogo.error)}
              codigo={codigoDaFalha(catalogo.error)}
              aoTentarDeNovo={() => void catalogo.refetch()}
            />
          ) : !disponivel ? (
            <Indisponivel
              titulo="Leitura de vídeo indisponível neste ambiente"
              motivo="O servidor declarou que não há leitura de build de vídeo aqui. Isto não é erro e não é falta de permissão: é a fábrica externa não estar acessível a este ambiente."
            />
          ) : builds.length ? (
            <ul className="space-y-2">
              {builds.map((slug) => (
                <li key={slug}>
                  <Link
                    to={`/criativos/videos/${encodeURIComponent(slug)}`}
                    className="flex min-h-11 items-center gap-3 rounded-md border border-border px-3 py-2 transition-colors duration-150 ease-out hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  >
                    <FileVideo className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium text-foreground">
                        {slug}
                      </span>
                      <span className="block text-[12px] text-muted-foreground">
                        Abrir a leitura do contrato, das cenas e dos gates de QA.
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <Vazio
              titulo="Nenhum build observado neste ambiente"
              explicacao="Quando a fábrica externa publicar um build, ele aparece aqui com contrato, cenas, ledger de assets e gates de QA prontos para leitura."
            />
          )}
        </Secao>
      </Corpo>
    </Layout>
  );
};

export default BriefingDeVideoPage;
