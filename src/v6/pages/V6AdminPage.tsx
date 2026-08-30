/**
 * v6 RBAC — V6AdminPage
 *
 * Página `/admin/v6`. Lazy-loaded a partir de App.tsx (entra no
 * bundle só quando a feature flag está ativa e a rota é visitada).
 *
 * Etapa 3.C operacional: agora com 4 abas (Resumo, Usuários,
 * Memberships, Comissões), CRUD completo via dialogs e
 * confirmações para ações destrutivas.
 *
 * NÃO toca em triggers, RLS, comportamento legado ou cálculo
 * legado. Memberships são dual-write para `user_campaigns` (legado)
 * e `campaign_members` (v6). Comissões só vivem em
 * `campaign_commissions`.
 */
import { useCallback } from 'react';
import { Layout } from '@/components/layout/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  ShieldAlert,
  LayoutDashboard,
  Users as UsersIcon,
  Network,
  Receipt,
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { isV6Enabled } from '@/v6/featureFlag';
import { useCampaignMembers } from '@/v6/hooks/useCampaignMembers';
import { useCampaignCommissions } from '@/v6/hooks/useCampaignCommissions';
import { useMemberPayouts } from '@/v6/hooks/useMemberPayouts';
import { V6Header } from '@/v6/components/V6Header';
import { SummaryCards } from '@/v6/components/SummaryCards';
import { PayoutsMonthly } from '@/v6/components/PayoutsMonthly';
import { TopCampaigns } from '@/v6/components/TopCampaigns';
import { SystemStatusCard } from '@/v6/components/SystemStatusCard';
import { UsersTab } from '@/v6/components/UsersTab';
import { MembershipsTab } from '@/v6/components/MembershipsTab';
import { CommissionsTab } from '@/v6/components/CommissionsTab';

function ForbiddenView({ reason }: { reason: string }) {
  return (
    <Layout>
      <div className="container mx-auto p-4">
        <Card className="border-destructive/40">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <ShieldAlert className="h-5 w-5" /> Acesso restrito
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{reason}</p>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
}

export default function V6AdminPage() {
  const { userProfile } = useAuth();
  const flagEnabled = isV6Enabled();

  if (!flagEnabled) {
    return (
      <ForbiddenView reason="A área v6 está desativada. Defina VITE_USE_V6_ADMIN=true e reinicie o dev server." />
    );
  }

  if (userProfile?.role !== 'ADMIN') {
    return (
      <ForbiddenView reason="Esta área é exclusiva para administradores." />
    );
  }

  return <V6AdminPageContent />;
}

function V6AdminPageContent() {
  const { userProfile } = useAuth();

  // Hooks de leitura compartilhados pelas abas Resumo + tabs.
  // Refetch é exposto para que mutações de outras abas possam
  // sincronizar os números do bloco de Resumo.
  const membersHook = useCampaignMembers();
  const commissionsHook = useCampaignCommissions();
  const payoutsHook = useMemberPayouts();

  const refetchAll = useCallback(() => {
    membersHook.refetch();
    commissionsHook.refetch();
    payoutsHook.refetch();
  }, [membersHook, commissionsHook, payoutsHook]);

  return (
    <Layout>
      <div className="container mx-auto space-y-6 p-4">
        <V6Header />

        <Tabs defaultValue="resumo" className="space-y-4">
          <TabsList className="h-10 w-full justify-start gap-1 rounded-lg bg-muted/40 p-1">
            <TabsTrigger
              value="resumo"
              className="gap-1.5 text-xs data-[state=active]:bg-card"
            >
              <LayoutDashboard className="h-3.5 w-3.5" /> Resumo
            </TabsTrigger>
            <TabsTrigger
              value="usuarios"
              className="gap-1.5 text-xs data-[state=active]:bg-card"
            >
              <UsersIcon className="h-3.5 w-3.5" /> Usuários
            </TabsTrigger>
            <TabsTrigger
              value="memberships"
              className="gap-1.5 text-xs data-[state=active]:bg-card"
            >
              <Network className="h-3.5 w-3.5" /> Memberships
            </TabsTrigger>
            <TabsTrigger
              value="comissoes"
              className="gap-1.5 text-xs data-[state=active]:bg-card"
            >
              <Receipt className="h-3.5 w-3.5" /> Comissões
            </TabsTrigger>
          </TabsList>

          <TabsContent value="resumo" className="space-y-4">
            <SummaryCards
              summary={payoutsHook.summary}
              membersCount={membersHook.members.length}
              activeCommissionsCount={commissionsHook.active.length}
              countByRole={membersHook.countByRole}
              isLoading={
                membersHook.isLoading ||
                commissionsHook.isLoading ||
                payoutsHook.isLoading
              }
            />
            <PayoutsMonthly
              data={payoutsHook.byMonth}
              isLoading={payoutsHook.isLoading}
              error={payoutsHook.error}
            />
            <TopCampaigns
              data={payoutsHook.topCampaigns}
              isLoading={payoutsHook.isLoading}
              error={payoutsHook.error}
            />
          </TabsContent>

          <TabsContent value="usuarios">
            <UsersTab onMutated={refetchAll} />
          </TabsContent>

          <TabsContent value="memberships">
            <MembershipsTab onMutated={refetchAll} />
          </TabsContent>

          <TabsContent value="comissoes">
            <CommissionsTab onMutated={refetchAll} />
          </TabsContent>
        </Tabs>

        <SystemStatusCard
          flagEnabled={true}
          userEmail={userProfile?.email}
          userRole={userProfile?.role}
          userName={userProfile?.name}
        />
      </div>
    </Layout>
  );
}
