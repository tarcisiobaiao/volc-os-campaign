import React from 'react';
import { useSearchParams } from 'react-router-dom';

import CampaignDetailDashboard from './CampaignDetailDashboard';
import MetaCampaignInsightPage from './MetaCampaignInsightPage';

const CampaignDetailRouter: React.FC = () => {
  const [params] = useSearchParams();
  return params.get('rede') === 'meta' ? <MetaCampaignInsightPage /> : <CampaignDetailDashboard />;
};

export default CampaignDetailRouter;
