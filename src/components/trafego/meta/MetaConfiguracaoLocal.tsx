import React from 'react';
import { CheckCircle2, KeyRound, Loader2, Settings2, ShieldCheck, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import {
  pautadorApi,
  PautadorApiError,
  type EstadoDaConfiguracaoMetaLocal,
  type ResultadoDoTesteMetaLocal,
} from '@/lib/pautadorApi';

type Status = EstadoDaConfiguracaoMetaLocal | null;

function mensagemDoErro(erro: unknown): string {
  return erro instanceof PautadorApiError || erro instanceof Error
    ? erro.message
    : 'Não foi possível concluir a operação.';
}

export const MetaConfiguracaoLocal: React.FC<{
  aoMudar?: (status: EstadoDaConfiguracaoMetaLocal) => void;
}> = ({ aoMudar }) => {
  const [aberto, setAberto] = React.useState(false);
  const [token, setToken] = React.useState('');
  const [status, setStatus] = React.useState<Status>(null);
  const [resultado, setResultado] = React.useState<ResultadoDoTesteMetaLocal | null>(null);
  const [ocupado, setOcupado] = React.useState<'carregar' | 'salvar' | 'testar' | 'remover' | null>(null);
  const [erro, setErro] = React.useState<string | null>(null);

  const carregar = React.useCallback(async () => {
    setOcupado('carregar');
    setErro(null);
    try {
      const proximo = await pautadorApi.estadoMetaLocal();
      setStatus(proximo);
      aoMudar?.(proximo);
    } catch (causa) {
      setErro(mensagemDoErro(causa));
    } finally {
      setOcupado(null);
    }
  }, [aoMudar]);

  React.useEffect(() => {
    if (aberto) void carregar();
  }, [aberto, carregar]);

  const salvar = async () => {
    setOcupado('salvar');
    setErro(null);
    setResultado(null);
    try {
      const teste = await pautadorApi.salvarETestarMetaLocal(token);
      const proximo: EstadoDaConfiguracaoMetaLocal = {
        configurado: true,
        armazenamento: 'macOS Keychain',
        api_version: 'v26.0',
        salvo_em: teste.salvo_em,
      };
      setResultado(teste);
      setStatus(proximo);
      aoMudar?.(proximo);
      setToken('');
      toast.success('Integração Meta validada e protegida neste Mac.');
    } catch (causa) {
      setErro(mensagemDoErro(causa));
    } finally {
      setOcupado(null);
    }
  };

  const testar = async () => {
    setOcupado('testar');
    setErro(null);
    try {
      const teste = await pautadorApi.testarMetaLocal();
      setResultado(teste);
      toast.success('Leitura Meta validada sem alterar a conta.');
    } catch (causa) {
      setErro(mensagemDoErro(causa));
    } finally {
      setOcupado(null);
    }
  };

  const remover = async () => {
    setOcupado('remover');
    setErro(null);
    try {
      await pautadorApi.removerMetaLocal();
      const proximo: EstadoDaConfiguracaoMetaLocal = {
        configurado: false,
        armazenamento: 'macOS Keychain',
        api_version: 'v26.0',
      };
      setStatus(proximo);
      setResultado(null);
      aoMudar?.(proximo);
      toast.success('Token Meta removido deste Mac.');
    } catch (causa) {
      setErro(mensagemDoErro(causa));
    } finally {
      setOcupado(null);
    }
  };

  return (
    <Sheet open={aberto} onOpenChange={(valor) => { setAberto(valor); if (!valor) setToken(''); }}>
      <SheetTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="h-10 w-10 shrink-0 bg-card text-foreground hover:text-foreground"
          aria-label="Configurar integração Meta neste Mac"
          title="Configurar integração Meta"
        >
          <Settings2 className="h-4 w-4" aria-hidden />
        </Button>
      </SheetTrigger>
      <SheetContent className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader className="pr-8">
          <div className="mb-1 flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
            <KeyRound className="h-4 w-4" aria-hidden />
          </div>
          <SheetTitle>Integração Meta neste Mac</SheetTitle>
          <SheetDescription>
            Atalho provisório para provar a leitura. Não usa o Cofre e não autoriza criação,
            edição ou gasto.
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-5">
          <div className="rounded-md border border-border bg-muted/40 p-3 text-xs leading-relaxed text-muted-foreground">
            <div className="flex items-start gap-2">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden />
              <p>
                O token atravessa somente o loopback durante este clique e fica cifrado pelo
                Chaveiro do macOS. Não vai para Supabase, browser storage, URL, log ou Git.
              </p>
            </div>
          </div>

          {ocupado === 'carregar' && !status ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
              <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />
              Conferindo este Mac…
            </div>
          ) : (
            <div className="flex items-start justify-between gap-4 border-b border-border pb-4">
              <div>
                <p className="text-sm font-medium text-foreground">
                  {status?.configurado ? 'Token protegido' : 'Nenhum token salvo'}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Graph API v26.0 · {status?.armazenamento ?? 'macOS Keychain'}
                </p>
              </div>
              {status?.configurado && (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-success/25 bg-success/10 px-2.5 py-1 text-xs font-medium text-success">
                  <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> protegido
                </span>
              )}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="meta-system-user-token">Token do usuário de sistema</Label>
            <Input
              id="meta-system-user-token"
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={token}
              onChange={(evento) => setToken(evento.target.value)}
              placeholder={status?.configurado ? 'Digite apenas para substituir' : 'Cole o token para validar'}
            />
            <p className="text-xs leading-relaxed text-muted-foreground">
              O botão primeiro faz duas leituras seguras: identidade e contas acessíveis. Só
              depois de uma resposta válida o token é salvo.
            </p>
          </div>

          {erro && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive" role="alert">
              {erro}
            </div>
          )}

          {resultado && (
            <section aria-label="Resultado da validação Meta" className="border-t border-border pt-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-foreground">Leitura confirmada</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {resultado.ator.nome} · {resultado.ator.id_mascarado ?? 'ID não informado'}
                  </p>
                </div>
                <span className="text-sm font-semibold tabular-nums text-foreground">
                  {resultado.contas_acessiveis} conta{resultado.contas_acessiveis === 1 ? '' : 's'}
                </span>
              </div>
              <div className="mt-3 divide-y divide-border rounded-md border border-border bg-card">
                {resultado.contas.length ? resultado.contas.map((conta, indice) => (
                  <div key={`${conta.id_mascarado}-${indice}`} className="flex items-center justify-between gap-3 px-3 py-2.5 text-xs">
                    <span className="min-w-0 truncate font-medium text-foreground">{conta.nome}</span>
                    <span className="shrink-0 text-muted-foreground">{conta.id_mascarado} · {conta.moeda ?? 'moeda não lida'}</span>
                  </div>
                )) : (
                  <p className="px-3 py-3 text-xs text-muted-foreground">
                    Token válido, mas nenhuma conta de anúncios foi devolvida.
                  </p>
                )}
              </div>
            </section>
          )}
        </div>

        <SheetFooter className="mt-7 gap-2 sm:flex-col sm:space-x-0">
          <Button type="button" className="w-full" disabled={token.trim().length < 20 || ocupado != null} onClick={salvar}>
            {ocupado === 'salvar' && <Loader2 className="mr-2 h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />}
            Salvar e testar leitura
          </Button>
          {status?.configurado && (
            <div className="grid w-full grid-cols-2 gap-2">
              <Button type="button" variant="outline" disabled={ocupado != null} onClick={testar}>
                {ocupado === 'testar' && <Loader2 className="mr-2 h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />}
                Testar novamente
              </Button>
              <Button type="button" variant="outline" className="text-destructive hover:text-destructive" disabled={ocupado != null} onClick={remover}>
                <Trash2 className="mr-2 h-4 w-4" aria-hidden /> Remover
              </Button>
            </div>
          )}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
};

export default MetaConfiguracaoLocal;
