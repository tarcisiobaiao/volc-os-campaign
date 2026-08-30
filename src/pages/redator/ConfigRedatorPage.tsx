/**
 * /redator/config — o que o motor diz, e com que ferramenta.
 *
 * ## Três coisas, três seções, e a diferença entre elas dita
 *
 * **A doutrina** é editorial: os termos que o funil nunca usa e os que ele sempre
 * usa. Uma edição aqui muda quatro prompts, dois validadores, o portão da LP e o
 * rodapé — POR CONSTRUÇÃO, porque todos leem da mesma fonte.
 *
 * **Os prompts** são a instrução de cada agente.
 *
 * **Os modelos** são com que ferramenta e a que preço.
 *
 * Numa tela só, isso cria a ilusão de que trocar o modelo do juiz e renomear um
 * termo proibido são a mesma classe de escolha. A primeira muda a conta; a
 * segunda muda o produto.
 *
 * ## Somente leitura, e isso é uma decisão
 *
 * Um prompt ruim salvo por aqui quebraria todo run seguinte, e o arquivo em
 * disco não tem histórico — não haveria como voltar atrás. Enquanto não existir
 * versionamento e um ensaio barato, ver é o que se faz com segurança. E ver já é
 * mais do que existia, que era nada: hoje esses valores só aparecem abrindo o
 * código do motor.
 */
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Lock, SlidersHorizontal } from 'lucide-react';

import { Layout } from '@/components/layout/Layout';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { pautadorApi } from '@/lib/pautadorApi';
import { cn } from '@/lib/utils';
import type { ConfiguracaoDoRedator, PromptDoAgente } from '@/types/redatorQuadro';

const ABA = cn(
  'rounded-md px-3 py-2 text-sm font-medium',
  'bg-transparent text-muted-foreground shadow-none',
  'data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-card',
);

const VisorDePrompt: React.FC<{ p: PromptDoAgente }> = ({ p }) => {
  const [aberto, setAberto] = useState(false);
  return (
    <div className="border-b border-border/60 last:border-b-0">
      <button type="button" onClick={() => setAberto((v) => !v)}
              className="flex w-full items-baseline justify-between gap-4 px-4 py-3 text-left transition-[color] duration-150 hover:text-foreground">
        <div className="min-w-0">
          <div className="tabular text-sm">{p.arquivo}</div>
          {p.usado_por && (
            <div className="text-[11px] text-muted-foreground">governa {p.usado_por}</div>
          )}
        </div>
        <span className="tabular shrink-0 text-[11px] text-muted-foreground">
          {p.linhas} linhas · {aberto ? 'fechar' : 'ver'}
        </span>
      </button>
      {aberto && (
        <pre className="mx-4 mb-3 max-h-[420px] overflow-auto rounded-lg border border-border bg-muted p-3 text-[11px] leading-relaxed">
          {p.conteudo}
        </pre>
      )}
    </div>
  );
};

const ConfigRedatorPage: React.FC = () => {
  const [cfg, setCfg] = useState<ConfiguracaoDoRedator | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let ativo = true;
    pautadorApi.configuracaoDoRedator()
      .then((c) => ativo && setCfg(c))
      .catch((e) => ativo && setErro(e instanceof Error ? e.message : 'Falhei ao ler a configuração.'));
    return () => { ativo = false; };
  }, []);

  return (
    <Layout>
      <div className="space-y-6 p-4 md:p-6">
        <Link to="/redator"
              className="kicker inline-flex items-center gap-1.5 text-muted-foreground transition-[color] duration-150 hover:text-foreground">
          <ArrowLeft className="h-3 w-3" aria-hidden /> quadro do redator
        </Link>
        <header className="reveal" style={{ ['--i' as never]: 0 }}>
          <div className="kicker mb-2 flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-md bg-primary/10 text-primary">
              <SlidersHorizontal className="h-3.5 w-3.5" aria-hidden />
            </span>
            configuração do motor
          </div>
          <h1 className="font-display text-3xl font-bold tracking-tight leading-[1.05] sm:text-4xl">
            O que o <span className="text-aurora">Redator</span> diz
          </h1>
          <div className="mt-3 aurora-rule w-16" />
        </header>

        {cfg?.somente_leitura && (
          <Card className="relative max-w-[76ch] overflow-hidden shadow-card">
            <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-warning" />
            <CardContent className="flex items-start gap-3 p-4">
              <Lock className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
              <div>
                <div className="kicker mb-1">somente leitura</div>
                <p className="text-xs leading-relaxed text-muted-foreground">{cfg.por_que}</p>
              </div>
            </CardContent>
          </Card>
        )}

        {erro && <p className="mt-8 max-w-[68ch] text-sm text-destructive">{erro}</p>}
        {!cfg && !erro && <p className="mt-8 text-sm text-muted-foreground">Lendo o motor…</p>}

        {cfg && (
          <Tabs defaultValue="doutrina" className="mt-2">
            <TabsList className="h-auto min-h-11 w-full justify-start gap-1 rounded-lg border border-border bg-muted p-1">
              <TabsTrigger value="doutrina" className={ABA}>
                doutrina
                <span className="tabular ml-2 text-muted-foreground">{cfg.doutrina.length}</span>
              </TabsTrigger>
              <TabsTrigger value="prompts" className={ABA}>
                prompts dos agentes
                <span className="tabular ml-2 text-muted-foreground">{cfg.prompts.length}</span>
              </TabsTrigger>
              <TabsTrigger value="modelos" className={ABA}>
                modelos e preço
                <span className="tabular ml-2 text-muted-foreground">{cfg.passos.length}</span>
              </TabsTrigger>
            </TabsList>

            <TabsContent value="doutrina" className="mt-8">
              <p className="mb-8 max-w-[70ch] text-sm leading-relaxed text-muted-foreground">
                O que o funil nunca escreve e o que ele sempre escreve. Cada lista
                é lida por vários pontos do motor ao mesmo tempo — por isso uma
                mudança aqui é consistente por construção, e não por disciplina.
              </p>
              <div className="space-y-10">
                {cfg.doutrina.map((d) => (
                  <section key={d.nome}>
                    <div className="flex flex-wrap items-baseline justify-between gap-3">
                      <h2 className="font-display text-base font-bold tracking-tight">{d.rotulo}</h2>
                      <span className="tabular text-[11px] text-muted-foreground">
                        {d.nome} · {d.total} {d.total === 1 ? 'item' : 'itens'}
                      </span>
                    </div>
                    <div className="hairline mt-2" />
                    {/* O EFEITO vem antes da lista. Sem ele, sete listas de
                        strings não dizem o que muda ao mexer em cada uma. */}
                    <p className="mt-3 max-w-[70ch] text-xs leading-relaxed text-muted-foreground">
                      {d.efeito}
                    </p>
                    <ul className="mt-4 flex flex-wrap gap-1.5">
                      {d.itens.map((i) => (
                        <li key={i} className="rounded-md border border-border bg-muted/50 px-2 py-1 text-xs text-foreground">{i}</li>
                      ))}
                    </ul>
                  </section>
                ))}
                {cfg.aviso_de_conformidade && (
                  <section>
                    <h2 className="font-display text-base font-bold tracking-tight">
                      aviso de conformidade
                    </h2>
                    <div className="hairline mt-2" />
                    <p className="mt-3 max-w-[70ch] text-xs leading-relaxed text-muted-foreground">
                      Vai no rodapé de toda página do funil.
                    </p>
                    <p className="mt-3 max-w-[70ch] rounded-lg border border-border bg-card p-3 text-sm leading-relaxed shadow-card">
                      {cfg.aviso_de_conformidade}
                    </p>
                  </section>
                )}
              </div>
            </TabsContent>

            <TabsContent value="prompts" className="mt-8">
              <p className="mb-6 max-w-[70ch] text-sm leading-relaxed text-muted-foreground">
                A instrução de cada agente. O rótulo abaixo de cada arquivo diz
                que parte do funil ele governa — é o que responde "se eu mexer
                aqui, o que muda?" antes de mexer.
              </p>
              <div className="overflow-hidden rounded-xl border border-border bg-card shadow-card">
                {cfg.prompts.map((p) => <VisorDePrompt key={p.arquivo} p={p} />)}
              </div>
            </TabsContent>

            <TabsContent value="modelos" className="mt-8">
              <p className="mb-6 max-w-[70ch] text-sm leading-relaxed text-muted-foreground">
                Com que ferramenta cada passo roda. A mesma instrução em modelos
                diferentes custa e rende diferente — e o juiz roda de propósito
                num provedor distinto do redator, para a avaliação não herdar os
                vícios de quem escreveu.
              </p>
              <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-card">
                <table className="w-full min-w-[680px] text-sm">
                  <thead>
                    <tr className="border-b border-border bg-secondary text-left">
                      <th className="kicker px-4 py-2 pr-4 font-normal">passo</th>
                      <th className="kicker py-2 pr-4 font-normal">modelo</th>
                      <th className="kicker py-2 pr-4 font-normal">reserva</th>
                      <th className="kicker py-2 pr-4 font-normal">temp.</th>
                      <th className="kicker py-2 pr-4 font-normal">validadores</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cfg.passos.map((p) => (
                      <tr key={p.passo} className="border-b border-border/50 last:border-b-0">
                        <td className="px-4 py-2.5 pr-4 tabular">{p.passo}</td>
                        <td className="tabular py-2.5 pr-4 text-xs">{p.modelo || '—'}</td>
                        <td className="tabular py-2.5 pr-4 text-xs text-muted-foreground">
                          {p.reservas.join(', ') || '—'}
                        </td>
                        <td className="tabular py-2.5 pr-4 text-xs">{p.temperatura ?? '—'}</td>
                        <td className="tabular py-2.5 text-xs text-muted-foreground">
                          {p.validadores.length || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <h2 className="mt-10 font-display text-base font-bold tracking-tight">
                o que este motor faz por padrão
              </h2>
              <div className="hairline mt-2" />
              <dl className="mt-4 grid gap-x-8 gap-y-2 sm:grid-cols-2">
                {Object.entries(cfg.corrida).map(([k, v]) => (
                  <div key={k} className="flex items-baseline justify-between gap-4 border-b border-border/40 py-1.5">
                    <dt className="tabular text-xs text-muted-foreground">{k}</dt>
                    <dd className="tabular text-xs">{String(v)}</dd>
                  </div>
                ))}
              </dl>
            </TabsContent>
          </Tabs>
        )}
      </div>
    </Layout>
  );
};

export default ConfigRedatorPage;
