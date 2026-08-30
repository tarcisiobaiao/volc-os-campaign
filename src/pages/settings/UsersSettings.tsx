/**
 * UsersSettings — Rota oficial `/settings/users`
 *
 * A partir desta versão, a rota oficial consolida a experiência
 * construída e validada em `src/v6/` (Etapas 3.A → 3.C operacional).
 * Não há mais "experimentação paralela" em `/admin/v6` — esta é a
 * única tela que o admin precisa usar no dia-a-dia para:
 *
 *   - cadastrar / editar usuários
 *   - vincular usuários a campanhas (membership + role funcional)
 *   - configurar comissões versionadas
 *
 * Usa `UsersTab`, `MembershipsTab` e `CommissionsTab` (reusados da
 * pasta `src/v6/components/`) em uma estrutura de 3 abas simples,
 * sem dashboards nem resumos — esses ficam no fallback técnico
 * `/admin/v6` (acessível via URL direta, atrás de feature flag).
 *
 * Regra central herdada da v6:
 *   - membership = acesso
 *   - role funcional = função por campanha
 *   - comissão = regra financeira separada
 *   - múltiplos membros por campanha é permitido por design
 *
 * EXCEÇÃO de isolamento: este arquivo LEGADO importa de
 * `@/v6/components/*`. É o ponto oficial de cutover entre o modelo
 * antigo e o novo. Antes deste cutover, só `App.tsx` e
 * `Navigation.tsx` podiam importar de `src/v6/`.
 */
import { useState } from "react";
import { Layout } from "@/components/layout/Layout";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  Network,
  Receipt,
  ShieldAlert,
  Users as UsersIcon,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { UsersTab } from "@/v6/components/UsersTab";
import { MembershipsTab } from "@/v6/components/MembershipsTab";
import { CommissionsTab } from "@/v6/components/CommissionsTab";

export default function UsersSettings() {
  const { userProfile } = useAuth();

  // Defesa em camada de componente (o ProtectedRoute já bloqueia
  // OPERATOR para todas as rotas fora da allowlist; isto é um
  // cinto-e-suspensórios para o caso de alguém entrar com ADMIN e
  // depois perder o role em runtime).
  if (userProfile?.role !== "ADMIN") {
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
              <p className="text-sm text-muted-foreground">
                Esta área é exclusiva para administradores.
              </p>
            </CardContent>
          </Card>
        </div>
      </Layout>
    );
  }

  return <UsersSettingsContent />;
}

function UsersSettingsContent() {
  // Cross-tab sync: incrementar `version` força re-mount dos tabs,
  // fazendo todos os hooks de leitura re-fetcharem dados frescos.
  // Isso garante que criar um usuário em "Usuários" já apareça no
  // select de "Memberships" sem reload manual.
  const [version, setVersion] = useState(0);
  const bumpVersion = () => setVersion((v) => v + 1);

  return (
    <Layout>
      <div className="container mx-auto space-y-5 p-4">
        <header className="space-y-1 border-b pb-5">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">
            Configurações
          </div>
          <h1 className="text-xl font-semibold tracking-tight">
            Usuários e acessos
          </h1>
          <p className="text-sm text-muted-foreground">
            Cadastre operadores, defina acessos por campanha e configure
            vigências de comissão.
          </p>
        </header>

        <Tabs defaultValue="usuarios" className="space-y-4">
          <TabsList className="h-10 w-full justify-start gap-1 rounded-lg bg-muted/40 p-1">
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
              <Network className="h-3.5 w-3.5" /> Agrupamentos
            </TabsTrigger>
            <TabsTrigger
              value="comissoes"
              className="gap-1.5 text-xs data-[state=active]:bg-card"
            >
              <Receipt className="h-3.5 w-3.5" /> Comissões
            </TabsTrigger>
          </TabsList>

          <TabsContent value="usuarios">
            <UsersTab key={`u-${version}`} onMutated={bumpVersion} />
          </TabsContent>
          <TabsContent value="memberships">
            <MembershipsTab key={`m-${version}`} onMutated={bumpVersion} />
          </TabsContent>
          <TabsContent value="comissoes">
            <CommissionsTab key={`c-${version}`} onMutated={bumpVersion} />
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
}
