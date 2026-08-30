import { ShieldAlert } from "lucide-react";
import { Layout } from "@/components/layout/Layout";
import { useAuth } from "@/contexts/AuthContext";
import { AssetVaultContent } from "@/features/asset-vault/AssetVaultContent";

export default function AssetVaultPage() {
  const { userProfile } = useAuth();

  if (userProfile?.role !== "ADMIN") {
    return (
      <Layout>
        <div className="mx-auto max-w-3xl p-4 sm:p-6">
          <section className="rounded-lg border border-destructive/35 bg-card px-5 py-10 text-center" aria-labelledby="asset-vault-denied">
            <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-destructive/10 text-destructive"><ShieldAlert aria-hidden="true" className="h-5 w-5" /></span>
            <h1 id="asset-vault-denied" className="mt-4 text-lg font-semibold">Acesso restrito</h1>
            <p className="mt-2 text-sm text-muted-foreground">O inventário de ativos e postura de acesso é exclusivo para administradores.</p>
          </section>
        </div>
      </Layout>
    );
  }

  return <Layout><AssetVaultContent /></Layout>;
}
