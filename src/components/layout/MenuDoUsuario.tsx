import React from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { Icone } from "@/components/ui/icone";
import { ICONES } from "@/lib/icones";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { AvatarDeIniciais } from "@/components/sistema/AvatarDeIniciais";

export function nomeDoPapel(role?: string): string {
  if (role === "ADMIN") return "Administrador";
  if (role === "OPERATOR") return "Operador";
  return "Papel não informado";
}

export function useSair() {
  const { signOut } = useAuth();
  const { toast } = useToast();
  return async () => {
    try {
      await signOut();
      toast({ title: "Sessão encerrada", description: "Você saiu do VOLC O.S." });
    } catch {
      toast({
        title: "Não foi possível sair",
        description: "A sessão continua aberta. Tente de novo.",
        variant: "destructive",
      });
    }
  };
}

/**
 * Quem está logado, no canto em que todo produto põe isso.
 *
 * O rodapé do menu lateral gastava ~200px com e-mail, papel, "Sair" e um
 * rótulo de escopo. Aqui vira um botão de 36px: nome e papel no menu, e a
 * única ação destrutiva da sessão isolada no fim, em tinta de erro.
 */
export const MenuDoUsuario: React.FC<{ className?: string }> = ({ className }) => {
  const { user, userProfile } = useAuth();
  const sair = useSair();
  const nome = userProfile?.name || user?.email || "Conta";
  const papel = nomeDoPapel(userProfile?.role);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "flex h-9 items-center gap-2 rounded-md pl-1 pr-2 text-left transition-colors duration-150 hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          className,
        )}
        aria-label={`Conta: ${nome}, ${papel}`}
      >
        <AvatarDeIniciais nome={userProfile?.name} email={user?.email} className="h-7 w-7" />
        <span className="hidden min-w-0 flex-col leading-tight xl:flex">
          <span className="max-w-[160px] truncate text-xs font-semibold text-foreground">{nome}</span>
          <span className="text-[11px] text-muted-foreground">{papel}</span>
        </span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="font-normal">
          <span className="block truncate text-sm font-semibold text-foreground">{nome}</span>
          {user?.email && user.email !== nome ? (
            <span className="block truncate text-xs text-muted-foreground">{user.email}</span>
          ) : null}
          <span className="mt-1 block text-xs text-muted-foreground">{papel}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void sair()} className="gap-2 text-destructive focus:text-destructive">
          <Icone icon={ICONES.sair} tamanho="sm" />
          Sair
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
