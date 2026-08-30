/**
 * A aba Google Ads das Integrações: em que conta cada projeto anuncia.
 *
 * ## O que esta tela existe para consertar
 *
 * O cockpit do Hub de Tráfego deriva a conta de `projects`, e quando não
 * encontra manda o operador para cá — mas até agora "cá" só conhecia Meta CAPI.
 * O vínculo só se fazia por API.
 *
 * ## Por que a lista é curta, e por que ela diz o que ficou de fora
 *
 * Medido em 18/08/2026: a credencial alcança 39 contas anunciáveis distintas
 * sob 9 MCCs, e três são da VOLC — o resto é de cliente. Oferecer as 39
 * transformaria "vincular na conta errada" num clique cuja consequência só
 * aparece depois, no `subir`, dentro da conta de outra empresa.
 *
 * A faixa de escopo diz o número que ficou de fora em vez de omiti-lo: uma
 * lista curta sem explicação faria o operador procurar a conta que "sumiu".
 *
 * ## Esta tela NÃO é a guarda
 *
 * Quem recusa é `app/trafego/escopo.py`, com 403, também em `/provar` e
 * `/subir` — onde `customer_id` viaja no corpo e nenhuma tela alcança.
 */
import React, { useState } from 'react';
import { AlertTriangle, Check, Link2, Loader2, Lock, RefreshCw, ShieldCheck, Unlink } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useContasGoogleAds } from '@/hooks/useContasGoogleAds';
import { cn } from '@/lib/utils';
import type { ContaDaCasa, ProjetoComConta } from '@/types/trafego';

/** `8017851692` → `801-785-1692`, que é como o painel do Google mostra.
 *  Só para LER: o que trafega e o que se grava são os dígitos. */
function comHifens(id: string | null): string {
  const d = (id || '').replace(/\D/g, '');
  if (d.length !== 10) return d || '—';
  return `${d.slice(0, 3)}-${d.slice(3, 6)}-${d.slice(6)}`;
}

export const PainelGoogleAds: React.FC = () => {
  const { escopo, projetos, trava, carregando, salvando, erro, carregar, vincular, desvincular } =
    useContasGoogleAds();

  // `null` = ninguém escolhendo; um id = o seletor aberto naquela linha.
  const [escolhendo, setEscolhendo] = useState<number | null>(null);

  const porConta = new Map<string, ProjetoComConta>();
  for (const p of projetos) {
    if (p.vinculada && p.google_ads_customer_id) porConta.set(p.google_ads_customer_id, p);
  }

  if (carregando) {
    return (
      <div className="py-16 flex justify-center">
        <LoadingSpinner text="Lendo as contas do Google Ads…" />
      </div>
    );
  }

  if (erro) {
    return (
      <Card className="border-destructive/40 shadow-card">
        <CardContent className="py-4 flex items-start gap-3">
          <span className="rounded-md p-1.5 shrink-0 bg-destructive/10 text-destructive">
            <AlertTriangle className="h-4 w-4" />
          </span>
          <div className="text-sm space-y-2">
            <p className="font-medium text-destructive">Não foi possível ler as contas</p>
            <p className="text-muted-foreground text-xs">{erro}</p>
            <Button size="sm" variant="outline" className="gap-2" onClick={() => void carregar()}>
              <RefreshCw className="h-3.5 w-3.5" /> Tentar de novo
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* ── o escopo ───────────────────────────────────────────────────── */}
      {escopo && (
        <Card className="shadow-card border-primary/30">
          <CardContent className="py-4 flex flex-wrap items-start gap-3">
            <span className="rounded-md p-1.5 shrink-0 bg-primary/10 text-primary">
              <ShieldCheck className="h-4 w-4" />
            </span>
            <div className="min-w-[16rem] flex-1 space-y-1">
              <p className="text-sm font-medium">
                Este sistema opera só sob o MCC{' '}
                <span className="tabular">{comHifens(escopo.mcc)}</span> · {escopo.nome}
              </p>
              <p className="text-xs text-muted-foreground">
                {escopo.contas.length}{' '}
                {escopo.contas.length === 1 ? 'conta anunciável' : 'contas anunciáveis'} · a
                credencial alcança {escopo.ids_acessiveis} ids, e {escopo.ids_fora_do_escopo} ficam
                de fora
              </p>
              {/* A frase vem do servidor: é lá que a recusa acontece, e as duas
                  não podem divergir com o tempo. */}
              <p className="text-[11px] leading-relaxed text-muted-foreground">{escopo.por_que}</p>
            </div>
            {/* ⚠️ `env_presente`, não `escrita_permitida` — este só é verdadeiro
                DENTRO do `with destravar()` no servidor, então em repouso ele
                diria "bloqueada" mesmo com a chave posta. Quem responde "há
                autorização neste processo?" é o ambiente. */}
            {trava && (
              <Badge variant={trava.env_presente ? 'danger' : 'success'} className="gap-1">
                <Lock className="h-3 w-3" />
                {trava.env_presente ? 'escrita LIBERADA' : 'escrita bloqueada'}
              </Badge>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── os projetos ────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {projetos.length} {projetos.length === 1 ? 'projeto' : 'projetos'} ·{' '}
          {projetos.filter((p) => p.vinculada).length} com conta vinculada
        </p>
        <Button size="sm" variant="outline" className="gap-2" onClick={() => void carregar()}>
          <RefreshCw className="h-3.5 w-3.5" /> Reler
        </Button>
      </div>

      <div className="space-y-3">
        {projetos.map((p) => {
          const conta = p.google_ads_customer_id
            ? escopo?.contas.find((c) => c.customer_id === p.google_ads_customer_id)
            : undefined;
          const aberto = escolhendo === p.id;
          return (
            <Card key={p.id} className="shadow-card">
              <CardContent className="py-4 space-y-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-[14rem] space-y-1">
                    <p className="font-medium text-sm">{p.dominio || p.nome}</p>
                    {p.vinculada ? (
                      <p className="text-xs text-muted-foreground">
                        {/* ⚠️ Conta vinculada que não está na árvore da casa
                            aparece assim: o vínculo é antigo ou o escopo mudou.
                            Inventar um nome esconderia a divergência. */}
                        {conta ? conta.nome : 'conta fora da árvore da casa'} ·{' '}
                        <span className="tabular">{comHifens(p.google_ads_customer_id)}</span>
                        {conta && ` · ${conta.moeda} · ${conta.fuso}`}
                      </p>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        Sem conta vinculada — o cockpit deste projeto para no estágio 4.
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    {p.vinculada ? (
                      <Badge variant="success" className="gap-1">
                        <Check className="h-3 w-3" /> vinculado
                      </Badge>
                    ) : (
                      <Badge variant="warning">sem conta</Badge>
                    )}
                    <Button
                      size="sm"
                      variant={p.vinculada ? 'outline' : 'default'}
                      className="gap-2"
                      disabled={salvando === p.id}
                      onClick={() => setEscolhendo(aberto ? null : p.id)}
                    >
                      {salvando === p.id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Link2 className="h-3.5 w-3.5" />
                      )}
                      {p.vinculada ? 'Trocar' : 'Vincular'}
                    </Button>
                    {p.vinculada && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="gap-2 text-muted-foreground"
                        disabled={salvando === p.id}
                        onClick={() => {
                          if (
                            window.confirm(
                              `Desvincular a conta de "${p.dominio || p.nome}"? O cockpit volta a ` +
                                `parar no estágio 4 para este projeto.`,
                            )
                          ) {
                            void desvincular(p.id);
                          }
                        }}
                      >
                        <Unlink className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                </div>

                {/* ⚠️ A divergência medida em 18/08/2026: o projeto 1 está
                    `google_ads_status='connected'` com os dois ids nulos. Essa
                    coluna é do webgo (ingestão de gasto) e o painel dele acende
                    por ela. Dizer isso aqui é o que impede alguém de concluir
                    que uma das duas telas está quebrada. */}
                {!p.vinculada && p.google_ads_status === 'connected' && (
                  <p className="text-[11px] leading-relaxed text-muted-foreground border-l-2 border-warning/50 pl-2">
                    O painel do projeto mostra "Google Ads conectado" por causa da coluna
                    <span className="font-mono"> google_ads_status</span>, que é do webgo e fala da
                    ingestão de gasto. Ela não diz nada sobre a conta em que se anuncia.
                  </p>
                )}

                {aberto && escopo && (
                  <div className="border-t border-border pt-3 space-y-2">
                    <p className="kicker">contas do MCC {comHifens(escopo.mcc)}</p>
                    {escopo.contas.map((c) => (
                      <LinhaDeConta
                        key={c.customer_id}
                        conta={c}
                        atual={c.customer_id === p.google_ads_customer_id}
                        usadaPor={porConta.get(c.customer_id)}
                        projetoAtual={p.id}
                        onEscolher={async () => {
                          const ok = await vincular(p.id, c.customer_id);
                          if (ok) setEscolhendo(null);
                        }}
                      />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
};

const LinhaDeConta: React.FC<{
  conta: ContaDaCasa;
  atual: boolean;
  usadaPor?: ProjetoComConta;
  projetoAtual: number;
  onEscolher: () => void;
}> = ({ conta, atual, usadaPor, projetoAtual, onEscolher }) => (
  <button
    type="button"
    onClick={onEscolher}
    disabled={atual}
    className={cn(
      'w-full text-left border border-border px-3 py-2 rounded-md transition-colors',
      atual ? 'bg-muted/60 cursor-default' : 'hover:border-primary/50 hover:bg-muted/30',
    )}
  >
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="text-sm">{conta.nome}</span>
      <span className="tabular text-[11px] text-muted-foreground">
        {comHifens(conta.customer_id)}
      </span>
    </div>
    <div className="flex flex-wrap items-center gap-2 mt-1">
      <span className="text-[11px] text-muted-foreground">
        {conta.moeda} · {conta.fuso}
      </span>
      {/* ⚠️ `teste` e `oculta` são MOSTRADOS, não filtrados: a conta de teste é
          justamente a que serve ao primeiro disparo, e esconder a oculta faria
          uma conta sumir da lista sem ninguém saber por quê. */}
      {conta.teste && <Badge variant="warning">conta de teste</Badge>}
      {conta.oculta && <Badge variant="warning">oculta no painel</Badge>}
      {atual && <Badge variant="success">vinculada aqui</Badge>}
      {!atual && usadaPor && usadaPor.id !== projetoAtual && (
        <span className="text-[11px] text-muted-foreground">
          já vinculada a {usadaPor.dominio || usadaPor.nome}
        </span>
      )}
    </div>
  </button>
);
