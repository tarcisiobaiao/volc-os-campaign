/**
 * Bancada visual da Bia: `?cena=<cena>&tema=dark` monta o widget com a API
 * falsa. Ferramenta de QA — não entra no bundle do app (fora de `src/`).
 */
import { createRoot } from 'react-dom/client';

import { BiaWidget } from '@/features/bia/BiaWidget';
import '@/index.css';

import { apiFalsa, type Cena } from './apiFalsa';

const p = new URLSearchParams(location.search);
const cena = (p.get('cena') ?? 'conversa') as Cena;
if (p.get('tema') === 'dark') document.documentElement.classList.add('dark');
try {
  window.sessionStorage.clear();
} catch { /* sem armazenamento */ }

const api = apiFalsa(cena);

createRoot(document.getElementById('root')!).render(
  <div className="min-h-screen bg-background p-6 text-foreground">
    <p className="kicker">Bancada · Bia</p>
    <h1 className="font-display text-2xl font-semibold">Página de fundo</h1>
    <p className="mt-2 max-w-xl text-sm text-muted-foreground">
      Conteúdo da página para conferir que o painel não cobre ações importantes nem muda a rolagem.
    </p>
    <BiaWidget userId="harness" api={api} />
  </div>,
);
