/**
 * O histórico do dono — e a porta de volta para uma operação.
 *
 * É uma TABELA, não um mural de cartões: são linhas comparáveis, e o design da
 * casa trata inventário comparável como tabela justamente para o olho varrer
 * uma coluna em vez de reler seis cartões idênticos.
 *
 * A lista não depende de blob URL nem de sessionStorage: ela vem do servidor,
 * por dono, e sobrevive a fechar o navegador.
 */
import { AlertCircle, Inbox } from 'lucide-react';

import { Button } from '@/components/ui/button';

import type { ResumoDaOperacao, StatusDaOperacao } from '../tipos';

const ROTULO: Record<StatusDaOperacao, { texto: string; classe: string }> = {
  RUNNING: { texto: 'Em andamento', classe: 'bg-muted/50 text-foreground' },
  READY_FOR_REVIEW: { texto: 'Pronta para revisão', classe: 'bg-success/10 text-success' },
  FAILED: { texto: 'Falhou', classe: 'bg-destructive/10 text-destructive' },
  ARCHIVED: { texto: 'Arquivada', classe: 'bg-muted/50 text-muted-foreground' },
};

function quando(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export interface HistoricoDeOperacoesProps {
  operacoes: ResumoDaOperacao[];
  carregando: boolean;
  erro?: string | null;
  onAbrir: (projectRef: string) => void;
  onNova: () => void;
}

export function HistoricoDeOperacoes({
  operacoes,
  carregando,
  erro,
  onAbrir,
  onNova,
}: HistoricoDeOperacoesProps) {
  if (erro) {
    return (
      <div
        role="alert"
        className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive"
      >
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <span>{erro}</span>
      </div>
    );
  }

  if (carregando) {
    // O esqueleto tem a MESMA altura de linha da tabela real: um carregamento
    // que muda a altura empurra o conteúdo quando chega, e o operador perde o
    // lugar onde estava olhando.
    return (
      <div className="rounded-lg border border-border bg-card shadow-card" aria-busy="true">
        <div className="sr-only" role="status">
          Carregando as operações
        </div>
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex items-center gap-4 border-b border-border p-4 last:border-0">
            <div className="h-4 w-1/3 animate-pulse rounded bg-muted motion-reduce:animate-none" />
            <div className="h-4 w-24 animate-pulse rounded bg-muted motion-reduce:animate-none" />
            <div className="h-4 w-32 animate-pulse rounded bg-muted motion-reduce:animate-none" />
          </div>
        ))}
      </div>
    );
  }

  if (operacoes.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center shadow-card">
        <Inbox className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden />
        <p className="mt-3 text-sm font-medium text-foreground">
          Você ainda não tem operações do Assistente.
        </p>
        <p className="mx-auto mt-1 max-w-[52ch] text-sm text-muted-foreground">
          Uma operação guarda o briefing, as estratégias propostas e o que você aprovou.
          Ela fica salva no servidor e pode ser retomada depois.
        </p>
        <Button type="button" className="mt-4" onClick={onNova}>
          Criar a primeira estratégia
        </Button>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card shadow-card">
      <table className="w-full min-w-[40rem] border-collapse text-sm">
        <caption className="sr-only">Operações do Assistente Criativo, mais recentes primeiro</caption>
        <thead>
          <tr className="border-b border-border text-left">
            <th scope="col" className="px-4 py-3 font-semibold text-foreground">
              Operação
            </th>
            <th scope="col" className="px-4 py-3 font-semibold text-foreground">
              Situação
            </th>
            <th scope="col" className="px-4 py-3 font-semibold text-foreground">
              Atualizada
            </th>
            <th scope="col" className="px-4 py-3 text-right font-semibold text-foreground">
              <span className="sr-only">Ações</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {operacoes.map((op) => {
            const rotulo = op.status ? ROTULO[op.status] : null;
            return (
              <tr
                key={op.project_ref}
                className="border-b border-border last:border-0 hover:bg-muted/30"
              >
                <td className="px-4 py-3">
                  <span className="block font-medium text-foreground">
                    {op.nome_da_operacao ?? 'Operação sem nome'}
                  </span>
                  <span className="block font-mono text-[11px] text-muted-foreground">
                    {op.project_ref}
                  </span>
                </td>
                <td className="px-4 py-3">
                  {rotulo ? (
                    <span
                      className={`inline-flex h-6 items-center rounded-full px-2.5 text-[11px] font-medium ${rotulo.classe}`}
                    >
                      {rotulo.texto}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
                <td className="px-4 py-3 tabular-nums text-muted-foreground">
                  {quando(op.updated_at)}
                </td>
                <td className="px-4 py-3 text-right">
                  {/* Botão de verdade, sempre visível: uma ação que só aparece
                      no hover não existe para teclado nem para toque. */}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => onAbrir(op.project_ref)}
                  >
                    Abrir
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
