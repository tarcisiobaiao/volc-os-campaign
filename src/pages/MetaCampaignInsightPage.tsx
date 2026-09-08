import React from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Layout } from '@/components/layout/Layout';
import { FaixaDeDemonstracao } from '@/components/campaign/MetaDemoStatus';
import { MetaCampaignReadView } from '@/components/trafego/meta/MetaCampaignReadView';
import { MetaCampaignDemoContext } from '@/components/trafego/meta/MetaCampaignData';
import { CONTA_DEMO_META, criarDadosDemoCampanha } from '@/components/trafego/meta/demoCampaignData';

/** Same view and interactions. Only explicit modo=demo selects the isolated data source. */
export const MetaCampaignInsightPage: React.FC = () => {
  const { campaignId = '' } = useParams<{ campaignId: string }>();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const demo = params.get('modo') === 'demo';
  const dadosDemo = React.useMemo(() => demo ? criarDadosDemoCampanha(campaignId) : null, [demo, campaignId]);
  const trocarConta = React.useCallback((contaRef: string) => {
    const proximos = new URLSearchParams(params);
    proximos.set('conta', contaRef);
    setParams(proximos, { replace: true });
  }, [params, setParams]);

  if (demo) return <Layout>
    <div className="px-4 pt-4 md:px-6 md:pt-6">
      <FaixaDeDemonstracao oQue="Mesma interface da operação real, com dados fictícios. Abra conjuntos, altere o período e simule propostas de gestão. Nenhuma ação consulta ou modifica contas Meta." />
      <p className="mt-2 text-sm text-muted-foreground">Dados de exemplo: 29/08 a 04/09/2026. As propostas são apenas conferidas, não aplicadas.</p>
    </div>
    {dadosDemo ? <MetaCampaignDemoContext.Provider value={dadosDemo} key={'demo:' + campaignId}>
      <MetaCampaignReadView referencia={campaignId} contaRef={CONTA_DEMO_META}
        aoVoltar={() => navigate('/settings/campaigns?rede=meta&modo=demo')} />
    </MetaCampaignDemoContext.Provider> : <div className="p-6" role="status">
      <h2 className="font-semibold">Este identificador não existe no cenário demonstrativo</h2>
      <p className="mt-2 text-sm text-muted-foreground">{campaignId}. Para consultar uma campanha real, abra a rota sem modo=demo. Nenhuma consulta real foi feita.</p>
    </div>}
  </Layout>;

  return <Layout><MetaCampaignReadView key={'real:' + campaignId} referencia={campaignId}
    contaRef={params.get('conta')} aoEscolherConta={trocarConta} aoVoltar={() => navigate(-1)} /></Layout>;
};
export default MetaCampaignInsightPage;
