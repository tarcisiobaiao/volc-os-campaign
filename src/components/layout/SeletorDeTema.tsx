/**
 * O seletor de tema — e a razão de ele ter precisado nascer.
 *
 * ## O defeito que isto fecha
 *
 * ⚠️ Medido em 27/08/2026 no navegador autenticado: o tema escuro do produto
 * **não tinha como ser ligado**. `tailwind.config.ts` declara
 * `darkMode: ["class"]`, o `src/index.css` define um bloco `.dark` completo, e
 * `next-themes` está instalado desde sempre — mas nada no aplicativo aplicava a
 * classe, não havia controle na interface e não havia consulta a
 * `prefers-color-scheme`. `document.documentElement.className` voltava vazio nos
 * dois esquemas do sistema, e `background-color` do `body` era o MESMO
 * `rgb(243,244,246)` em ambos.
 *
 * Ou seja: existia um tema escuro inteiro, escrito e mantido, que nenhum
 * operador jamais viu. O `DESIGN.md` diz que o escuro é "complete and
 * equivalent, not a reduced alternate skin" — e um tema inalcançável não é nem
 * uma coisa nem outra.
 *
 * ## Por que três opções e não um interruptor
 *
 * `Sistema` é o que a maioria espera e o que respeita a configuração de
 * acessibilidade de quem já escolheu no sistema operacional. `Claro` e `Escuro`
 * existem porque a cena de referência do `DESIGN.md` — operador às 14h ao lado
 * de uma janela — não é a mesma do plantão noturno, e o produto não deve obrigar
 * ninguém a mudar a configuração do sistema inteiro para conferir uma conta.
 *
 * O padrão é CLARO, e não `sistema`, porque o `DESIGN.md` declara o claro como
 * o tema da cena de referência.
 */
import React from 'react';
import { Monitor, Moon, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';

import { cn } from '@/lib/utils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';

type Glifo = React.ComponentType<{ className?: string }>;

const OPCOES: ReadonlyArray<{ valor: string; rotulo: string; glifo: Glifo }> = [
  { valor: 'light', rotulo: 'Claro', glifo: Sun },
  { valor: 'dark', rotulo: 'Escuro', glifo: Moon },
  { valor: 'system', rotulo: 'Sistema', glifo: Monitor },
];

export const SeletorDeTema: React.FC<{ className?: string }> = ({ className }) => {
  const { theme, setTheme, resolvedTheme } = useTheme();
  // ⚠️ `next-themes` só sabe o tema depois da montagem no cliente. Renderizar o
  // glifo antes disso produz uma troca visível de ícone no primeiro quadro —
  // e num controle de tema isso parece o produto mudando de ideia sozinho.
  const [montado, setMontado] = React.useState(false);
  React.useEffect(() => setMontado(true), []);

  const atual = OPCOES.find((o) => o.valor === theme) ?? OPCOES[0];
  const Glifo = montado
    ? (theme === 'system' ? Monitor : resolvedTheme === 'dark' ? Moon : Sun)
    : Sun;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={cn('h-9 w-9 border border-border bg-card p-0', className)}
          // O nome acessível diz o estado ATUAL, não só a função: quem usa
          // leitor de tela precisa saber em que tema está antes de trocar.
          aria-label={montado ? `Tema: ${atual.rotulo}. Trocar tema` : 'Trocar tema'}
        >
          <Glifo className="h-4 w-4" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[9rem]">
        {OPCOES.map((o) => {
          const G = o.glifo;
          const ativo = montado && theme === o.valor;
          return (
            <DropdownMenuItem
              key={o.valor}
              onSelect={() => setTheme(o.valor)}
              className="gap-2 text-[13px]"
              // Estado não depende só de cor: o item ativo é anunciado.
              aria-current={ativo ? 'true' : undefined}
            >
              <G className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
              <span className="flex-1">{o.rotulo}</span>
              {ativo && <span className="text-[11px] text-muted-foreground">atual</span>}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default SeletorDeTema;
