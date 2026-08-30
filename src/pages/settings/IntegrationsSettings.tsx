import { useState } from "react";
import { Layout } from "@/components/layout/Layout";
import { Card, CardContent } from "@/components/ui/card";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AlertTriangle, ShieldAlert } from "lucide-react";
import { useIsMobile } from "@/hooks/useIsMobile";
import { useAuth } from "@/contexts/AuthContext";
import { useMetaCapiSites, type MetaCapiSite } from "@/hooks/useMetaCapiSites";
import { SiteList } from "@/components/settings/meta-capi/SiteList";
import { MetaCapiWizard } from "@/components/settings/meta-capi/MetaCapiWizard";
import { PainelGoogleAds } from "@/components/settings/google-ads/PainelGoogleAds";

export default function IntegrationsSettings() {
  const isMobile = useIsMobile();
  const { userProfile } = useAuth();
  const { sites, loading, saving, error, saveSite, removeSite, recordCheck } = useMetaCapiSites();

  // `null` = lista; objeto = editando aquele site; 'new' = wizard em branco.
  const [editing, setEditing] = useState<MetaCapiSite | "new" | null>(null);

  // Primeiro uso: sem a migração, o PostgREST devolve "relation does not exist".
  // Traduzir isso evita que o operador leia erro de banco e ache que quebrou.
  const missingTable =
    !!error && /meta_capi_sites|does not exist|PGRST205|42P01|schema cache/i.test(error);

  // Mesmo padrão de UsersSettings: a rota já redireciona OPERATOR, mas a página
  // se defende sozinha — aqui trafega token de conversão.
  if (userProfile?.role !== "ADMIN") {
    return (
      <Layout>
        <div className={`${isMobile ? "p-4" : "p-6"} max-w-3xl mx-auto`}>
          <Card className="border-destructive/40 shadow-card reveal" style={{ ["--i" as any]: 0 }}>
            <CardContent className="py-10 text-center space-y-3">
              <div className="mx-auto h-12 w-12 rounded-full bg-destructive/10 flex items-center justify-center">
                <ShieldAlert className="h-6 w-6 text-destructive" />
              </div>
              <div className="space-y-1">
                <h2 className="font-display text-lg font-semibold">Acesso restrito</h2>
                <p className="text-sm text-muted-foreground">
                  Esta área é exclusiva de administradores.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className={`${isMobile ? "p-4" : "p-6"} space-y-6 max-w-5xl mx-auto`}>
        <div className="reveal" style={{ ["--i" as any]: 0 }}>
          <div className="kicker mb-2 flex items-center gap-2">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-success animate-pulse" />
            Integrações
          </div>
          <h1
            className={`font-display font-bold tracking-tight leading-[1.05] ${isMobile ? "text-[1.7rem]" : "text-4xl"}`}
          >
            Contas e <span className="text-foreground">conversões</span>
          </h1>
          <div className="mt-3 aurora-rule w-16" />
          <p className={`text-muted-foreground ${isMobile ? "text-sm mt-3" : "mt-3"}`}>
            Onde cada projeto compra o clique, e para onde as conversões são enviadas.
          </p>
        </div>

        {/* Google Ads é a aba padrão porque é para cá que o cockpit do Hub de
            Tráfego manda quem tem projeto sem conta vinculada — e ele é a única
            tela que aponta para esta URL. */}
        <Tabs defaultValue="google-ads" className="space-y-4">
          <TabsList className="h-10 w-full justify-start gap-1 rounded-lg bg-muted/40 p-1">
            <TabsTrigger value="google-ads">Google Ads</TabsTrigger>
            <TabsTrigger value="meta-capi">Meta CAPI</TabsTrigger>
          </TabsList>

          <TabsContent value="google-ads">
            <PainelGoogleAds />
          </TabsContent>

          <TabsContent value="meta-capi" className="space-y-6">
            <p className="text-sm text-muted-foreground">
              Envie as visualizações de anúncio dos seus sites direto para a Meta, pelo servidor.
            </p>

            {error && (
          <Card
            className={`shadow-card reveal ${missingTable ? "border-warning/40 bg-warning/10" : "border-destructive/40"}`}
            style={{ ["--i" as any]: 1 }}
          >
            <CardContent className="py-4 flex items-start gap-3">
              <span
                className={`rounded-md p-1.5 shrink-0 ${missingTable ? "bg-warning/10 text-warning" : "bg-destructive/10 text-destructive"}`}
              >
                <AlertTriangle className="h-4 w-4" />
              </span>
              <div className="text-sm space-y-1">
                {missingTable ? (
                  <>
                    <p className="font-medium text-warning">
                      Falta rodar a migração
                    </p>
                    <p className="text-muted-foreground text-xs">
                      Execute{" "}
                      <code className="font-mono">src/sql/v7_13_meta_capi_sites.sql</code> no SQL
                      Editor do Supabase e recarregue esta página. Ela cria a tabela que guarda os
                      sites — nenhum dado existente é alterado.
                    </p>
                  </>
                ) : (
                  <>
                    <p className="font-medium text-destructive">Não foi possível carregar</p>
                    <p className="text-muted-foreground text-xs">{error}</p>
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* O wizard vem ANTES do estado de carregamento de propósito: qualquer
            recarga da lista (ex.: logo após salvar) trocaria o wizard pelo
            spinner, desmontando o componente e zerando passo e formulário. */}
        {editing ? (
          <MetaCapiWizard
            site={editing === "new" ? null : editing}
            saving={saving}
            onSave={async (payload) => {
              const salvo = await saveSite(payload);
              // Adota o site salvo: sair e voltar passa a encontrar o cadastro,
              // sem depender de refresh da página.
              if (salvo) setEditing(salvo);
              return salvo;
            }}
            onRecordCheck={recordCheck}
            onExit={() => setEditing(null)}
          />
        ) : loading ? (
          <div className="py-16 flex justify-center">
            <LoadingSpinner text="Carregando sites…" />
          </div>
        ) : (
          <SiteList
            sites={sites}
            onCreate={() => setEditing("new")}
            onOpen={(site) => setEditing(site)}
            onRemove={(site) => {
              if (
                window.confirm(
                  `Remover "${site.site_name}"? Os eventos deste site param de chegar na Meta.`,
                )
              ) {
                void removeSite(site.id);
              }
            }}
          />
            )}
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
}
