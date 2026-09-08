import { Layout } from "@/components/layout/Layout";
import { useAuth } from "@/contexts/AuthContext";
import { AssetVaultContent } from "@/features/asset-vault/AssetVaultContent";
import { EstadoOperacional } from "@/components/sistema/EstadoOperacional";

export default function AssetVaultPage() {
  const { userProfile } = useAuth();

  if (userProfile?.role !== "ADMIN") {
    return (
      <Layout>
        <div className="page-workspace">
          <EstadoOperacional
            tom="bloqueado"
            titulo="Acesso restrito"
            explicacao="O inventário de ativos e a postura de acesso são exclusivos para administradores. Isto é autorização negada no VOLC, não cofre externo bloqueado."
          />
        </div>
      </Layout>
    );
  }

  return <Layout><AssetVaultContent /></Layout>;
}
