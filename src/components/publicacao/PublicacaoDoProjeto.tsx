/**
 * Onde o redator publica — o WordPress deste projeto.
 *
 * ## Por que engrenagem, e não bloco na página
 *
 * Isto se configura uma vez por site e depois some. Ocupar espaço permanente
 * numa página que existe para acompanhar receita diária seria trocar leitura
 * frequente por escrita rara. A engrenagem fica no cabeçalho, com um ponto
 * quando o site ainda não está pronto — o único momento em que a configuração
 * precisa chamar atenção.
 *
 * ## A decisão que organiza o formulário
 *
 * O Application Password **nunca chega aqui**. O backend responde com
 * `senha_mascarada` e nada mais, então esta tela não tem como exibir a senha
 * nem sem querer. O campo é de ESCRITA: vazio significa "não mexi", e só um
 * valor digitado troca a credencial.
 *
 * ## O que deliberadamente NÃO está aqui
 *
 * CNPJ e autor: saem do tema do site, que já os renderiza. Lista de
 * cross-funnel: o engine lê o sitemap real e escolhe sozinho
 * (`adapters/sitemap_http.py`); a lista manual era só fallback. Cadastrar
 * qualquer um dos três aqui seria manter à mão o que o site já publica.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { pautadorApi, PautadorApiError } from '@/lib/pautadorApi';
import {
  PERFIL_VAZIO, paraFormulario,
  type PerfilEntrada, type PerfilPublicacao, type ResultadoTesteConexao,
} from '@/types/publicacao';
import {
  AlertTriangle, Check, KeyRound, Loader2, Plug, Save, Settings2,
} from 'lucide-react';

interface Props {
  projectId: number;
  /** Só para pré-preencher a URL na primeira vez. Nunca sobrescreve o salvo. */
  dominioSugerido?: string | null;
}

export const PublicacaoDoProjeto: React.FC<Props> = ({ projectId, dominioSugerido }) => {
  const { toast } = useToast();
  const [aberto, setAberto] = useState(false);
  const [perfil, setPerfil] = useState<PerfilPublicacao | null>(null);
  const [form, setForm] = useState<PerfilEntrada>(PERFIL_VAZIO);
  const [senha, setSenha] = useState('');
  const [carregando, setCarregando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [testando, setTestando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [ultimoTeste, setUltimoTeste] = useState<ResultadoTesteConexao | null>(null);

  const carregar = useCallback(async (silencioso = false) => {
    if (!silencioso) setCarregando(true);
    setErro(null);
    try {
      const p = await pautadorApi.perfilPublicacao(projectId);
      setPerfil(p);
      const f = paraFormulario(p);
      // A sugestão de domínio só entra em campo VAZIO. Um projeto que já tem
      // WordPress cadastrado noutro domínio (staging, subdomínio) não pode ter
      // a URL trocada por baixo do operador.
      if (!f.wp_url && dominioSugerido) {
        f.wp_url = dominioSugerido.startsWith('http') ? dominioSugerido : `https://${dominioSugerido}`;
      }
      setForm(f);
    } catch (e) {
      setErro(e instanceof PautadorApiError ? e.message : 'Não consegui ler o perfil de publicação.');
    } finally {
      setCarregando(false);
    }
  }, [projectId, dominioSugerido]);

  // Lê uma vez em silêncio, só para saber se a engrenagem merece o ponto de
  // atenção. Sem isso o operador teria que abrir o diálogo para descobrir que
  // ainda não configurou nada.
  useEffect(() => { void carregar(true); }, [carregar]);
  useEffect(() => { if (aberto) void carregar(); }, [aberto, carregar]);

  const pronto = perfil?.configurado === true && perfil?.conexao?.ok === true;

  const estado = useMemo(() => {
    if (!perfil) return { texto: '—', ok: false };
    if (!perfil.configurado) return { texto: 'sem credencial', ok: false };
    if (perfil.conexao?.ok === false) return { texto: 'o último teste falhou', ok: false };
    if (perfil.conexao?.ok == null) return { texto: 'conexão não testada', ok: false };
    const q = perfil.conexao.em
      ? new Date(perfil.conexao.em).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })
      : '';
    return { texto: `pronto · testado em ${q}`, ok: true };
  }, [perfil]);

  const salvar = async () => {
    if (!form.wp_url.trim() || !form.wp_username.trim()) {
      toast({ title: 'Faltam a URL e o usuário', description: 'Os dois são obrigatórios.', variant: 'destructive' });
      return;
    }
    setSalvando(true);
    try {
      const corpo: PerfilEntrada = { ...form };
      if (senha.trim()) corpo.wp_app_password = senha.trim();
      const p = await pautadorApi.salvarPerfilPublicacao(projectId, corpo);
      setPerfil(p);
      setForm(paraFormulario(p));
      setSenha('');
      setUltimoTeste(null);
      toast({ title: 'Publicação salva' });
    } catch (e) {
      toast({
        title: 'Não consegui salvar',
        description: e instanceof PautadorApiError ? e.message : 'Erro inesperado.',
        variant: 'destructive',
      });
    } finally {
      setSalvando(false);
    }
  };

  const testar = async () => {
    setTestando(true);
    setUltimoTeste(null);
    try {
      const r = await pautadorApi.testarPublicacao(projectId);
      setUltimoTeste(r);
      await carregar(true);
      toast({
        title: r.ok ? 'Conexão OK' : 'A conexão falhou',
        description: r.detalhe,
        variant: r.ok ? undefined : 'destructive',
      });
    } catch (e) {
      toast({
        title: 'Não consegui testar',
        description: e instanceof PautadorApiError ? e.message : 'Erro inesperado.',
        variant: 'destructive',
      });
    } finally {
      setTestando(false);
    }
  };

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setAberto(true)}
        className="flex-shrink-0 touch-target relative"
        title="Publicação · o WordPress deste site"
      >
        <Settings2 className="h-4 w-4" />
        {/* Ponto só quando falta resolver algo. Configurado e testado, some. */}
        {perfil && !pronto && (
          <span className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-warning" />
        )}
      </Button>

      <Dialog open={aberto} onOpenChange={setAberto}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Settings2 className="h-4 w-4 text-primary" />
              Publicação
            </DialogTitle>
            <DialogDescription>
              O WordPress onde o redator publica o funil deste site. A senha fica cifrada no
              servidor e nunca volta para esta tela.
            </DialogDescription>
          </DialogHeader>

          {carregando ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
              <Loader2 className="h-4 w-4 animate-spin" /> lendo…
            </div>
          ) : erro ? (
            <div className="flex items-start gap-2 text-sm text-destructive border border-destructive/30 bg-destructive/5 p-3">
              <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
              <div>{erro}</div>
            </div>
          ) : (
            <div className="space-y-4">
              {perfil && !perfil.cofre_pronto && (
                <div className="flex items-start gap-2 text-xs border border-destructive/30 bg-destructive/5 p-2.5">
                  <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-destructive" />
                  <div>
                    <b>O cofre do servidor não tem chave.</b> Sem <code>VOLC_SEGREDO_KEY</code> no{' '}
                    <code>backend/.env</code> não há como cifrar a senha, e gravar em texto puro não
                    é uma opção. Cadastrar vai falhar até isso ser resolvido.
                  </div>
                </div>
              )}

              {/* Estado, numa linha. Vale mais que uma trilha de marcos num
                  diálogo pequeno — aqui o operador já veio resolver. */}
              <div className="flex items-center gap-1.5 text-xs">
                {estado.ok
                  ? <Check className="h-3.5 w-3.5 text-success shrink-0" />
                  : <span className="h-3.5 w-3.5 shrink-0 rounded-full border border-warning" />}
                <span className={estado.ok ? 'text-success' : 'text-muted-foreground'}>{estado.texto}</span>
                {perfil?.configurado && (
                  <span className="ml-auto text-muted-foreground font-mono text-[11px]">
                    {perfil.senha_mascarada}
                  </span>
                )}
              </div>

              <div className="space-y-3">
                <div>
                  <Label htmlFor="wp_url" className="text-xs">URL do site</Label>
                  <Input
                    id="wp_url" value={form.wp_url} placeholder="https://seusite.com.br"
                    onChange={(e) => setForm((f) => ({ ...f, wp_url: e.target.value }))}
                  />
                  {form.wp_url.startsWith('http://') && (
                    <p className="text-xs text-destructive mt-1">
                      Sem TLS a senha viaja em texto claro. Use <code>https://</code>.
                    </p>
                  )}
                </div>

                <div>
                  <Label htmlFor="wp_user" className="text-xs">Usuário do WordPress</Label>
                  <Input
                    id="wp_user" value={form.wp_username} placeholder="redator-volc"
                    onChange={(e) => setForm((f) => ({ ...f, wp_username: e.target.value }))}
                  />
                </div>

                <div>
                  <Label htmlFor="wp_pass" className="text-xs flex items-center gap-1.5">
                    <KeyRound className="h-3 w-3" /> Application Password
                  </Label>
                  <Input
                    id="wp_pass" type="password" value={senha} autoComplete="new-password"
                    placeholder={perfil?.configurado ? 'preencha só para trocar' : 'cole a Application Password'}
                    onChange={(e) => setSenha(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    Gerada em <i>Usuários → Perfil → Application Passwords</i>. Não é a senha de login.
                  </p>
                </div>

                <div className="grid gap-3 grid-cols-2">
                  <div>
                    <Label htmlFor="pt" className="text-xs">Post type · soluções</Label>
                    <Input id="pt" value={form.post_type}
                           onChange={(e) => setForm((f) => ({ ...f, post_type: e.target.value }))} />
                    <p className="text-xs text-muted-foreground mt-1">Gutenberg · <code>/rec/</code></p>
                  </div>
                  <div>
                    <Label htmlFor="lpt" className="text-xs">Post type · landing</Label>
                    <Input id="lpt" value={form.lp_post_type}
                           onChange={(e) => setForm((f) => ({ ...f, lp_post_type: e.target.value }))} />
                    <p className="text-xs text-muted-foreground mt-1">Elementor · <code>/r/</code></p>
                  </div>
                </div>
              </div>

              {ultimoTeste && (
                <div className={`text-sm border p-2.5 ${ultimoTeste.ok
                  ? 'border-success/30 bg-success/5' : 'border-destructive/30 bg-destructive/5'}`}>
                  <div className="flex items-start gap-2">
                    {ultimoTeste.ok
                      ? <Check className="h-4 w-4 mt-0.5 shrink-0 text-success" />
                      : <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0 text-destructive" />}
                    <div className="min-w-0 text-xs">{ultimoTeste.detalhe}</div>
                  </div>
                </div>
              )}
            </div>
          )}

          <DialogFooter className="gap-2 sm:gap-2">
            <Button variant="outline" onClick={testar} disabled={testando || !perfil?.configurado}
                    title={perfil?.configurado ? 'Faz um GET autenticado no site' : 'Cadastre a credencial primeiro'}>
              {testando ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Plug className="h-4 w-4 mr-1.5" />}
              Testar
            </Button>
            <Button onClick={salvar} disabled={salvando || carregando}>
              {salvando ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Save className="h-4 w-4 mr-1.5" />}
              Salvar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};
