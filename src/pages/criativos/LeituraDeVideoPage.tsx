/**
 * `/criativos/videos/:buildSlug` — a leitura de um build observado, por slug.
 *
 * A rota existe porque `GET /video/{slug}` é indexado pelo identificador que a
 * fábrica externa deu ao build, e não pelo id do job. Sem uma rota por slug, o
 * catálogo de `GET /videos` não teria para onde apontar, e a leitura só seria
 * alcançável por um job observado que já estivesse na Home.
 */
import React from 'react';
import { useParams } from 'react-router-dom';

import { Layout } from '@/components/layout/Layout';
import { CabecalhoDoEstudio, Corpo } from '@/components/criativos/comum/Painel';
import { Carregando, ErroDeLeitura } from '@/components/criativos/comum/Estados';
import { LeituraDeVideo } from '@/components/criativos/video/LeituraDeVideo';
import { useCriativosVideo } from '@/hooks/useCriativosVideo';
import { codigoDaFalha, mensagemDaFalha } from '@/lib/criativosApi';

const LeituraDeVideoPage: React.FC = () => {
  const { buildSlug } = useParams<{ buildSlug: string }>();
  const consulta = useCriativosVideo(buildSlug);

  return (
    <Layout>
      <CabecalhoDoEstudio
        kicker="Build observado"
        titulo={consulta.data?.contrato.titulo ?? buildSlug ?? 'Build de vídeo'}
        proposito="Leitura de um build produzido pela fábrica externa. O VOLC O.S. não renderizou este vídeo, ele leu o arquivo e guardou a prova."
        voltar={{ para: '/criativos/videos/novo', rotulo: 'Builds observados' }}
      />
      <Corpo>
        {consulta.isLoading ? (
          <Carregando rotulo="Lendo o build" linhas={3} altura="h-24" />
        ) : consulta.isError || !consulta.data ? (
          <ErroDeLeitura
            mensagem={mensagemDaFalha(consulta.error)}
            codigo={codigoDaFalha(consulta.error)}
            aoTentarDeNovo={() => void consulta.refetch()}
          />
        ) : (
          <LeituraDeVideo leitura={consulta.data} />
        )}
      </Corpo>
    </Layout>
  );
};

export default LeituraDeVideoPage;
