/**
 * v6 RBAC — V6Header
 *
 * Header enxuto. Microcopy direta. Sem banners explicativos longos.
 */
import { ShieldCheck, Sparkles } from 'lucide-react';

export function V6Header() {
  return (
    <header className="reveal space-y-4 pb-5" style={{ ['--i' as any]: 0 }}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <div className="kicker flex items-center gap-2">
            <Sparkles className="h-3.5 w-3.5" />
            Administração v6
          </div>
          <h1 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">
            Comissões e <span className="text-foreground">acessos</span>
          </h1>
          <p className="max-w-xl text-sm text-muted-foreground">
            Membership define acesso. Role define função. Comissão é regra
            financeira separada.
          </p>
        </div>

        <div className="flex flex-wrap gap-1.5">
          <span className="inline-flex items-center gap-1 rounded-full bg-success/12 px-2.5 py-0.5 text-[10px] font-medium text-success">
            <span className="h-1.5 w-1.5 rounded-full bg-success" />
            Operacional
          </span>
          <span className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-0.5 text-[10px] font-medium text-muted-foreground">
            <ShieldCheck className="h-3 w-3" /> Admin only
          </span>
        </div>
      </div>
      <div className="hairline-aurora" />
    </header>
  );
}
