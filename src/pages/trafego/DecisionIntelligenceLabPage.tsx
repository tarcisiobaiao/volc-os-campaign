import React from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { Layout } from '@/components/layout/Layout';
import { DecisionIntelligenceLab } from '@/components/trafego/laboratorio/DecisionIntelligenceLab';
import { useDecisionIntelligenceLab } from '@/hooks/useDecisionIntelligenceLab';

const CENARIO_PADRAO = 'new-no-delivery';

const DecisionIntelligenceLabPage: React.FC = () => {
  const { scenarioId = CENARIO_PADRAO } = useParams<{ scenarioId: string }>();
  const navegar = useNavigate();
  const leitura = useDecisionIntelligenceLab(scenarioId);

  return (
    <Layout>
      <div className="overflow-x-clip p-4 pb-20 md:p-8 md:pb-20">
        <DecisionIntelligenceLab
          scenarioId={scenarioId}
          resposta={leitura.resposta}
          carregando={leitura.carregando}
          atualizando={leitura.atualizando}
          erro={leitura.erro}
          aoEscolher={(proximo) => navegar(`/trafego/laboratorio/inteligencia/${proximo}`)}
        />
      </div>
    </Layout>
  );
};

export default DecisionIntelligenceLabPage;
