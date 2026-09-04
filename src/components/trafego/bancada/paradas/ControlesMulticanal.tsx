import React from 'react';
import { Check, FileImage, FlaskConical, Loader2, Plus, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import type { AssetDemandGen } from '@/types/trafego';

export function itensDoTexto(texto: string): string[] {
  return texto.split('\n').map((item) => item.trim()).filter(Boolean);
}

export const CampoDeTexto: React.FC<{
  id: string;
  rotulo: string;
  valor: string;
  onChange: (valor: string) => void;
  limite?: number;
  placeholder?: string;
  ajuda?: string;
}> = ({ id, rotulo, valor, onChange, limite, placeholder, ajuda }) => (
  <label htmlFor={id} className="block space-y-2">
    <span className="flex items-end justify-between gap-3 text-sm font-semibold">
      {rotulo}
      {limite != null && (
        <span className={cn(
          'text-xs font-medium tabular-nums',
          valor.length > limite ? 'text-destructive' : 'text-muted-foreground',
        )}>{valor.length}/{limite}</span>
      )}
    </span>
    <Input
      id={id}
      value={valor}
      onChange={(e) => onChange(e.target.value)}
      maxLength={limite}
      placeholder={placeholder}
      className="h-11 bg-background"
    />
    {ajuda && <span className="block text-xs leading-relaxed text-muted-foreground">{ajuda}</span>}
  </label>
);

export const EditorDeLista: React.FC<{
  id: string;
  rotulo: string;
  valor: string;
  onChange: (valor: string) => void;
  minimo?: number;
  maximo?: number;
  limitePorItem?: number;
  placeholder?: string;
  ajuda?: string;
  linhas?: number;
}> = ({
  id, rotulo, valor, onChange, minimo = 0, maximo, limitePorItem,
  placeholder, ajuda, linhas = 5,
}) => {
  const itens = itensDoTexto(valor);
  const longos = limitePorItem == null ? 0 : itens.filter((item) => item.length > limitePorItem).length;
  const foraDaContagem = itens.length < minimo || (maximo != null && itens.length > maximo);
  return (
    <label htmlFor={id} className="block space-y-2">
      <span className="flex flex-wrap items-end justify-between gap-3 text-sm font-semibold">
        {rotulo}
        <span className={cn(
          'text-xs font-medium tabular-nums',
          foraDaContagem || longos > 0 ? 'text-destructive' : 'text-muted-foreground',
        )}>
          {itens.length}{maximo != null ? `/${maximo}` : ''} itens
          {longos > 0 ? ` · ${longos} acima do limite` : ''}
        </span>
      </span>
      <Textarea
        id={id}
        value={valor}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={linhas}
        className="resize-y bg-background leading-relaxed"
      />
      <span className="block text-xs leading-relaxed text-muted-foreground">
        Uma linha por item{limitePorItem ? ` · até ${limitePorItem} caracteres por linha` : ''}
        {ajuda ? ` · ${ajuda}` : ''}
      </span>
    </label>
  );
};

export const EscolhaExplicita: React.FC<{
  rotulo: string;
  valor: boolean | null;
  onChange: (valor: boolean) => void;
  positivo: string;
  negativo: string;
  ajuda: string;
}> = ({ rotulo, valor, onChange, positivo, negativo, ajuda }) => (
  <fieldset className="space-y-3">
    <legend className="text-sm font-semibold">{rotulo}</legend>
    <div className="grid gap-2 sm:grid-cols-2">
      {([[true, positivo], [false, negativo]] as const).map(([opcao, texto]) => (
        <button
          key={texto}
          type="button"
          aria-pressed={valor === opcao}
          onClick={() => onChange(opcao)}
          className={cn(
            'flex min-h-11 items-center gap-3 rounded-lg border px-4 py-3 text-left text-sm transition-colors',
            valor === opcao
              ? 'border-primary/45 bg-primary/[0.07] text-foreground'
              : 'border-border bg-background text-muted-foreground hover:border-primary/25 hover:text-foreground',
          )}
        >
          <span className={cn(
            'grid h-5 w-5 shrink-0 place-items-center rounded-full border',
            valor === opcao ? 'border-primary bg-primary text-primary-foreground' : 'border-border',
          )}>{valor === opcao && <Check className="h-3 w-3" />}</span>
          {texto}
        </button>
      ))}
    </div>
    <p className="text-xs leading-relaxed text-muted-foreground">{ajuda}</p>
  </fieldset>
);

async function base64DoArquivo(arquivo: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const leitor = new FileReader();
    leitor.onerror = () => reject(leitor.error ?? new Error('Não foi possível ler o arquivo.'));
    leitor.onload = () => resolve(String(leitor.result).split(',', 2)[1] ?? '');
    leitor.readAsDataURL(arquivo);
  });
}

async function hashDoArquivo(arquivo: File): Promise<`sha256:${string}`> {
  const digest = await crypto.subtle.digest('SHA-256', await arquivo.arrayBuffer());
  const hex = [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
  return `sha256:${hex}`;
}

export async function assetDoArquivo(
  arquivo: File,
  tipo: AssetDemandGen['tipo'],
): Promise<AssetDemandGen> {
  return {
    tipo,
    nome: arquivo.name,
    dados_base64: await base64DoArquivo(arquivo),
    conteudo_hash: await hashDoArquivo(arquivo),
    origem: 'humano',
    procedencia: {
      motor: 'humano:upload-volc-os',
      versao_do_motor: '1',
      insumo: arquivo.name,
      quando: new Date().toISOString(),
      pedido: 'bancada-multicanal',
      custo_usd: null,
    },
  };
}

export const SeletorDeAsset: React.FC<{
  id: string;
  rotulo: string;
  tipo: AssetDemandGen['tipo'];
  detalhe: string;
  assets: AssetDemandGen[];
  onChange: (assets: AssetDemandGen[]) => void;
  maximo?: number;
}> = ({ id, rotulo, tipo, detalhe, assets, onChange, maximo = 20 }) => {
  const doTipo = assets.filter((asset) => asset.tipo === tipo);
  const [lendo, setLendo] = React.useState(false);
  const [erro, setErro] = React.useState<string | null>(null);

  const receber = async (files: FileList | null) => {
    if (!files?.length) return;
    setLendo(true);
    setErro(null);
    try {
      const vagas = Math.max(0, maximo - doTipo.length);
      const novos = await Promise.all([...files].slice(0, vagas).map((file) => assetDoArquivo(file, tipo)));
      onChange([...assets, ...novos]);
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Não foi possível ler o arquivo.');
    } finally {
      setLendo(false);
    }
  };

  return (
    <div className="rounded-lg border border-border bg-background p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold">{rotulo}</p>
          <p className="mt-1 text-xs text-muted-foreground">{detalhe}</p>
        </div>
        <label htmlFor={id} className="inline-flex min-h-10 cursor-pointer items-center gap-2 rounded-md border border-border px-3 text-xs font-semibold transition-colors hover:border-primary/35 hover:bg-primary/[0.04]">
          {lendo ? <FileImage className="h-4 w-4 animate-pulse" /> : <Plus className="h-4 w-4" />}
          {lendo ? 'Lendo…' : 'Adicionar'}
        </label>
        <input
          id={id}
          className="sr-only"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          multiple
          disabled={lendo || doTipo.length >= maximo}
          onChange={(e) => { void receber(e.target.files); e.currentTarget.value = ''; }}
        />
      </div>
      {doTipo.length > 0 ? (
        <ul className="mt-3 space-y-2">
          {doTipo.map((asset) => (
            <li key={`${asset.conteudo_hash}:${asset.nome}`} className="flex min-h-10 items-center gap-3 rounded-md bg-muted/50 px-3 text-xs">
              <FileImage className="h-4 w-4 shrink-0 text-success" />
              <span className="min-w-0 flex-1 truncate font-medium">{asset.nome}</span>
              <span className="text-muted-foreground">medição no servidor</span>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                aria-label={`Remover ${asset.nome}`}
                onClick={() => onChange(assets.filter((item) => item !== asset))}
              ><X className="h-4 w-4" /></Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-xs font-medium text-muted-foreground">Nenhuma peça anexada · {doTipo.length}/{maximo}</p>
      )}
      {erro && <p role="alert" className="mt-2 text-xs text-destructive">{erro}</p>}
    </div>
  );
};

export const IrParaEstudio: React.FC<{ canal: string }> = ({ canal }) => (
  <Button asChild variant="outline" className="min-h-10">
    <a href={`/criativos/novo?destino=trafego&canal=${encodeURIComponent(canal)}`}>
      <FileImage className="h-4 w-4" /> Produzir no Estúdio
    </a>
  </Button>
);

export const AcaoDeProva: React.FC<{
  estado: 'ociosa' | 'provando' | 'aprovada' | 'recusada';
  mensagem: string | null;
  desabilitada: boolean;
  motivo: string | null;
  onProvar: () => void;
  somenteLocal?: boolean;
}> = ({ estado, mensagem, desabilitada, motivo, onProvar, somenteLocal = false }) => (
  <div className="rounded-xl border border-primary/20 bg-primary/[0.035] p-4 sm:p-5">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div>
        <p className="text-sm font-semibold">
          {somenteLocal ? 'Conferir o contrato antes do Google Ads' : 'Conferir o payload no Google Ads'}
        </p>
        <p className="mt-1 max-w-[62ch] text-xs leading-relaxed text-muted-foreground">
          {somenteLocal
            ? 'Monta e confere localmente todos os campos. O validate_only exige um ato externo separado e explícito.'
            : 'Executa validate_only: a API confere e descarta. Não cria campanha, asset ou orçamento.'}
        </p>
      </div>
      <Button type="button" disabled={desabilitada || estado === 'provando'} onClick={onProvar} className="min-h-11">
        {estado === 'provando' ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical className="h-4 w-4" />}
        {estado === 'provando' ? 'Conferindo…' : somenteLocal ? 'Conferir contrato' : 'Provar no Google'}
      </Button>
    </div>
    {motivo && <p className="mt-3 text-xs font-medium text-warning">Antes da prova: {motivo}</p>}
    {mensagem && (
      <p role="status" className={cn(
        'mt-3 rounded-md border px-3 py-2 text-sm',
        estado === 'aprovada' ? 'border-success/25 bg-success/[0.06] text-success' : 'border-destructive/25 bg-destructive/[0.04] text-destructive',
      )}>{mensagem}</p>
    )}
  </div>
);
