import React from "react";
import { cn } from "@/lib/utils";

/** "Ana Exemplo" → "AE"; um nome só → duas letras; sem nome, a 1ª do e-mail; sem nada, "?". */
export function iniciais(nome?: string | null, email?: string | null): string {
  const partes = (nome ?? "").trim().split(/\s+/).filter(Boolean);
  if (partes.length >= 2) return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
  if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
  const local = (email ?? "").trim();
  return local ? local[0].toUpperCase() : "?";
}

/**
 * Avatar de iniciais. Usado no menu do usuário, na gaveta do telefone e na
 * tabela de usuários. Sem glow: é identidade, não controle operacional.
 * Decorativo: o nome sempre aparece em texto ao lado.
 */
export const AvatarDeIniciais: React.FC<{ nome?: string | null; email?: string | null; className?: string }> = ({
  nome,
  email,
  className,
}) => (
  <span
    aria-hidden
    className={cn(
      "flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-aurora text-[11px] font-semibold tracking-wide text-white",
      className,
    )}
  >
    {iniciais(nome, email)}
  </span>
);
