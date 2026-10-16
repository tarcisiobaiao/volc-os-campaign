/**
 * Onde a Bia entra no shell autenticado.
 *
 * Três condições, todas no cliente só por VISIBILIDADE (o servidor confere de
 * novo, com papel lido do banco):
 *   1. `VITE_BIA_ENABLED=true`;
 *   2. há usuário com sessão (logout desmonta: `user` vira null);
 *   3. `userProfile.role === 'ADMIN'` (papel desconhecido = não mostra).
 *
 * `key={user.id}` desmonta o widget inteiro na troca de usuário: nenhum
 * estado, histórico ou conversa salva do anterior sobrevive no React.
 */
import React, { useEffect } from 'react';

import { useAuth } from '@/contexts/AuthContext';

import { BiaWidget } from './BiaWidget';
import { isBiaEnabled } from './featureFlag';

/** Logout apaga os rascunhos da Bia desta aba (máquina compartilhada). */
function apagarRascunhos() {
  try {
    const s = window.sessionStorage;
    for (let i = s.length - 1; i >= 0; i -= 1) {
      const k = s.key(i);
      if (k?.startsWith('volc.bia.rascunho.')) s.removeItem(k);
    }
  } catch {
    /* sem armazenamento: nada a apagar */
  }
}

const BiaComSessao: React.FC = () => {
  const { user, userProfile } = useAuth();
  const logado = !!user;
  useEffect(() => {
    if (!logado) apagarRascunhos();
  }, [logado]);
  if (!user || userProfile?.role !== 'ADMIN') return null;
  return <BiaWidget key={user.id} userId={user.id} />;
};

export const BiaNoLayout: React.FC = () => {
  // Segunda checagem da flag (o Layout já só importa este módulo com ela
  // ligada): constante de build, então a ordem dos hooks não muda.
  if (!isBiaEnabled()) return null;
  return <BiaComSessao />;
};

export default BiaNoLayout;
