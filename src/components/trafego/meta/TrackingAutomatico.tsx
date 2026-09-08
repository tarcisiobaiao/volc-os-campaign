import React from 'react';
import { Link2, Copy, Check } from 'lucide-react';
import { pautadorApi } from '@/lib/pautadorApi';
import type { TrackingAutomaticoMeta } from '@/types/metaOperacao';
import { Button } from '@/components/ui/button';

const SIGNIFICADOS: Record<string, string> = {
  utm_source: 'Plataforma de origem do clique',
  utm_medium: 'Mídia paga social',
  utm_campaign: 'ID do conjunto: chave da receita no GAM',
  utm_term: 'ID do conjunto',
  utm_content: 'ID do anúncio',
  placement: 'Posicionamento do anúncio',
  campaign_id: 'ID da campanha: contexto para o site',
};

/** Preview comes from the compiler's server contract, never a second template. */
export function TrackingAutomatico({ destino }: { destino: string }) {
  const [resposta, setResposta] = React.useState<TrackingAutomaticoMeta | null>(null);
  const [erro, setErro] = React.useState(false);
  const [copia, setCopia] = React.useState('');
  React.useEffect(() => {
    let vivo = true;
    setResposta(null);
    setErro(false);
    setCopia('');
    const timer = setTimeout(() => {
      pautadorApi.trackingAutomaticoMeta(destino)
        .then((r) => { if (vivo) setResposta(r); })
        .catch(() => { if (vivo) setErro(true); });
    }, 250);
    return () => { vivo = false; clearTimeout(timer); };
  }, [destino]);

  async function copiar() {
    try {
      await navigator.clipboard.writeText(resposta!.template);
      setCopia('Copiado');
    } catch { setCopia('Não foi possível copiar. Selecione o texto abaixo.'); }
  }

  return <section aria-label="Tracking automático" className="space-y-3 rounded-lg border border-border bg-muted/20 p-4">
    <div className="flex items-center gap-2">
      <Link2 className="h-4 w-4 text-primary" aria-hidden />
      <h3 className="font-semibold">UTMs automáticas por conjunto</h3>
    </div>
    <p className="max-w-[72ch] text-sm text-muted-foreground">
      Informe a URL da página sem UTMs. O sistema adiciona os parâmetros em cada anúncio.
      O GAM atribui a receita ao conjunto e a campanha soma seus conjuntos.
    </p>
    {erro ? <p role="status" className="text-sm text-warning">Não foi possível carregar a prévia do tracking. Confira novamente na revisão do plano.</p>
      : !resposta ? <p role="status" className="text-sm text-muted-foreground">Conferindo o tracking no servidor…</p>
      : <>
        {resposta.erro && <p role="alert" className="text-sm text-destructive">{resposta.erro.mensagem}</p>}
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div><dt className="text-muted-foreground">Receita por conjunto</dt><dd><code>utm_campaign = {resposta.parametros.find(p => p.nome === 'utm_campaign')?.valor ?? 'Não informado pelo servidor'}</code></dd></div>
          <div><dt className="text-muted-foreground">Receita da campanha</dt><dd>Soma dos conjuntos vinculados, no mesmo período</dd></div>
        </dl>
        <details className="text-sm">
          <summary className="cursor-pointer py-2 font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Ver parâmetros e prévia da URL</summary>
          <dl className="divide-y divide-border">
            {resposta.parametros.map((p) => <div key={p.nome} className="grid gap-1 py-2 sm:grid-cols-[9rem_1fr]">
              <dt className="font-mono text-xs">{p.nome}</dt>
              <dd className="min-w-0"><code className="break-all">{p.valor}</code><span className="block text-xs text-muted-foreground">{SIGNIFICADOS[p.nome] ?? p.nome}</span></dd>
            </div>)}
          </dl>
          {resposta.previa_url && <div className="mt-3 space-y-1"><p className="font-medium">URL ilustrativa após adicionar os parâmetros</p><code className="block select-all break-all rounded bg-muted p-3 text-xs">{resposta.previa_url}</code></div>}
          <code className="mt-3 block select-all break-all text-xs">{resposta.template}</code>
          <Button type="button" variant="ghost" size="sm" onClick={copiar} className="mt-2 gap-2">
            {copia === 'Copiado' ? <Check className="h-4 w-4" aria-hidden /> : <Copy className="h-4 w-4" aria-hidden />}Copiar parâmetros
          </Button><span role="status" className="ml-2 text-xs">{copia}</span>
        </details>
        <p className="text-xs text-muted-foreground">As expressões entre chaves serão substituídas pela Meta. Esta prévia não comprova clique, redirecionamento nem receita recebida. Os anúncios não recebem receita individual por este mapeamento.</p>
      </>}
  </section>;
}
