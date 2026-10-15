import React from 'react';

import { Layout } from '@/components/layout/Layout';
import { CarteiraEmSombra } from '@/components/trafego/sombra/CarteiraEmSombra';
import { useCarteiraShadow } from '@/hooks/useRecomendacaoShadow';

/** Carteira em sombra (W13): leitura das recomendações de todas as campanhas, sem ação. */
const SombraDaCarteiraPage: React.FC = () => (
  <Layout>
    <div className="overflow-x-clip p-4 pb-20 md:p-8 md:pb-20">
      <p className="kicker">tráfego · decisão não executada</p>
      <h1 className="mt-1 text-xl font-semibold">Carteira em sombra</h1>
      <div className="mt-6">
        <CarteiraEmSombra leitura={useCarteiraShadow()} />
      </div>
    </div>
  </Layout>
);

export default SombraDaCarteiraPage;
