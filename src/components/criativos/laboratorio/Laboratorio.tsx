/**
 * O workspace do Laboratório de Templates.
 *
 * Três zonas no desktop, três abas abaixo de 1024px — mesmo padrão de
 * `LeituraDeVideo`. E três níveis de operação sobre O MESMO rascunho: trocar de
 * nível não perde nada, só muda quantos campos aparecem.
 *
 * ## O que esta tela NÃO faz, e diz que não faz
 *
 * Não salva. `criativo_template` não existe no banco — é a v11_03, planejada e
 * não aplicada. Uma receita vive na memória desta aba e morre com ela. Desenhar
 * um botão "Salvar" aqui seria a mentira mais barata desta fatia, então em vez
 * dele há uma frase dizendo onde a receita mora.
 *
 * Não renderiza. O motor de imagem produz peça a partir de briefing, e o de
 * vídeo é uma fábrica externa que o VOLC O.S. apenas observa. O preview desta
 * fatia é a receita compilada — o objeto que um motor executaria — e não um
 * quadro renderizado que não temos como produzir.
 */
import React from 'react';
import { CircleCheck, CircleOff, TriangleAlert } from 'lucide-react';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Ficha, Secao } from '@/components/criativos/comum/Painel';
import { Selo } from '@/components/criativos/comum/Selo';
import { Producao } from './Producao';
import { useIsMobile } from '@/hooks/useIsMobile';
import { cn } from '@/lib/utils';
import {
  CLASSE_DE_FINALIDADE,
  PROVA,
  type Parque,
} from '@/types/parqueCriativo';
import {
  RASCUNHO_VAZIO,
  canaisConhecidos,
  compilar,
  firmezaDoCanal,
  podeProduzirAgora,
  validar,
  type RascunhoDeReceita,
} from './receita';

type Nivel = 'guiado' | 'avancado' | 'especialista';

const NIVEIS: { chave: Nivel; palavra: string; explicacao: string }[] = [
  { chave: 'guiado', palavra: 'Guiado', explicacao: 'Poucas escolhas, com padrões seguros.' },
  { chave: 'avancado', palavra: 'Avançado', explicacao: 'Controles de direção criativa.' },
  {
    chave: 'especialista',
    palavra: 'Especialista',
    explicacao: 'O contrato inteiro, campo a campo, com diagnóstico.',
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Peças pequenas
// ─────────────────────────────────────────────────────────────────────────────

const Campo: React.FC<{
  rotulo: string;
  ajuda?: string;
  children: React.ReactNode;
  id: string;
}> = ({ rotulo, ajuda, children, id }) => (
  <div className="space-y-1">
    <label htmlFor={id} className="block text-[13px] font-medium text-foreground">
      {rotulo}
    </label>
    {ajuda && <p className="text-[12px] leading-relaxed text-muted-foreground">{ajuda}</p>}
    {children}
  </div>
);

const Escolha: React.FC<{
  id: string;
  valor: string;
  aoMudar: (v: string) => void;
  opcoes: { valor: string; palavra: string; desabilitado?: boolean; motivo?: string }[];
  vazio: string;
}> = ({ id, valor, aoMudar, opcoes, vazio }) => (
  <select
    id={id}
    value={valor}
    onChange={(e) => aoMudar(e.target.value)}
    className={cn(
      'min-h-9 w-full rounded-md border border-input bg-background px-2.5 text-[13px] text-foreground',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
    )}
  >
    <option value="">{vazio}</option>
    {opcoes.map((o) => (
      <option key={o.valor} value={o.valor} disabled={o.desabilitado}>
        {o.palavra}
        {o.desabilitado && o.motivo ? ` (${o.motivo})` : ''}
      </option>
    ))}
  </select>
);

/**
 * Uma coleção que não foi lida.
 *
 * ⚠️ Não é "vazio". É "esta tabela não respondeu", e a diferença importa: quem vê
 * vazio cadastra de novo o que já existe.
 */
const NaoLida: React.FC<{ o_que: string }> = ({ o_que }) => (
  <p className="rounded-md border border-warning/50 bg-warning/[0.08] px-3 py-2 text-[12px] leading-relaxed text-foreground">
    <strong className="font-semibold">{o_que} não foi lido.</strong> Isto não quer dizer que
    esteja vazio: a leitura desta parte do catálogo falhou.
  </p>
);

// ─────────────────────────────────────────────────────────────────────────────
// Workspace
// ─────────────────────────────────────────────────────────────────────────────

export const Laboratorio: React.FC<{ parque: Parque }> = ({ parque }) => {
  const estreito = useIsMobile(1024);
  const [nivel, setNivel] = React.useState<Nivel>('guiado');
  const [rascunho, setRascunho] = React.useState<RascunhoDeReceita>(RASCUNHO_VAZIO);

  const mexer = <K extends keyof RascunhoDeReceita>(campo: K, valor: RascunhoDeReceita[K]) =>
    setRascunho((r) => ({ ...r, [campo]: valor }));

  const receita = React.useMemo(() => compilar(rascunho, parque), [rascunho, parque]);
  const achados = React.useMemo(() => validar(receita, parque), [receita, parque]);
  const liberado = podeProduzirAgora(achados);

  const impedimentos = achados.filter((a) => a.gravidade === 'impede');
  const avisos = achados.filter((a) => a.gravidade === 'avisa');

  const canais = canaisConhecidos(parque);
  const finalidade = receita.finalidade;
  const firmeza = firmezaDoCanal(parque, rascunho.canal);

  // ── zona 1: direção ───────────────────────────────────────────────────────
  const direcao = (
    <Secao
      titulo="Direção"
      descricao="O que esta receita produz, para quem e com qual motor."
      className="min-w-0"
    >
      <div className="space-y-4">
        <Campo id="lab-nome" rotulo="Nome da receita">
          <input
            id="lab-nome"
            value={rascunho.nome}
            onChange={(e) => mexer('nome', e.target.value)}
            placeholder="Ex.: Depoimento vertical, linha institucional"
            className={cn(
              'min-h-9 w-full rounded-md border border-input bg-background px-2.5 text-[13px]',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
            )}
          />
        </Campo>

        {parque.finalidades === null ? (
          <NaoLida o_que="O catálogo de finalidades" />
        ) : (
          <Campo
            id="lab-finalidade"
            rotulo="Finalidade"
            ajuda="Mídia paga e orgânico têm obrigações diferentes de direito e de aviso. A peça pode ser a mesma; a entrega, não."
          >
            <Escolha
              id="lab-finalidade"
              valor={rascunho.finalidadeSlug ?? ''}
              aoMudar={(v) => mexer('finalidadeSlug', v || null)}
              vazio="Escolha a finalidade"
              opcoes={parque.finalidades
                .filter((f) => f.ativo)
                .map((f) => ({
                  valor: f.slug,
                  palavra: `${f.nome} · ${CLASSE_DE_FINALIDADE[f.classe]?.palavra ?? f.classe}`,
                }))}
            />
          </Campo>
        )}

        <Campo
          id="lab-canal"
          rotulo="Canal"
          ajuda={
            canais.length === 0
              ? 'Nenhum canal tem exigência registrada no catálogo.'
              : 'Só aparecem canais cujas exigências o catálogo declara.'
          }
        >
          <Escolha
            id="lab-canal"
            valor={rascunho.canal ?? ''}
            aoMudar={(v) => mexer('canal', v || null)}
            vazio="Sem canal: não confere exigência"
            opcoes={canais.map((c) => ({ valor: c, palavra: c }))}
          />
        </Campo>

        {parque.motores === null ? (
          <NaoLida o_que="O registro de motores" />
        ) : (
          <Campo id="lab-motor" rotulo="Motor">
            <Escolha
              id="lab-motor"
              valor={rascunho.motorSlug ?? ''}
              aoMudar={(v) => mexer('motorSlug', v || null)}
              vazio="Escolha o motor"
              opcoes={parque.motores
                .filter((m) => m.ativo)
                .map((m) => ({ valor: m.slug, palavra: `${m.nome} (${m.produz.join(', ')})` }))}
            />
          </Campo>
        )}

        {parque.modos === null ? (
          <NaoLida o_que="O catálogo de modos" />
        ) : (
          <Campo
            id="lab-modo"
            rotulo="Modo de produção"
            ajuda="Um modo que não produz aqui aparece na lista com o motivo; escondê-lo tiraria da vista uma capacidade que existe fora."
          >
            <Escolha
              id="lab-modo"
              valor={rascunho.modoSlug ?? ''}
              aoMudar={(v) => mexer('modoSlug', v || null)}
              vazio="Escolha o modo"
              opcoes={parque.modos.map((m) => {
                const p = PROVA[m.estadoDeProva];
                return {
                  valor: m.slug,
                  palavra: m.nome,
                  desabilitado: !p?.podeProduzir,
                  motivo: p?.podeProduzir ? undefined : p?.palavra,
                };
              })}
            />
          </Campo>
        )}

        {parque.formatos === null ? (
          <NaoLida o_que="O catálogo de formatos" />
        ) : (
          <fieldset className="space-y-2">
            <legend className="text-[13px] font-medium text-foreground">Formatos</legend>
            <div className="space-y-1.5">
              {parque.formatos
                .filter((f) => f.ativo)
                .map((f) => (
                  <label
                    key={f.slot}
                    className="flex min-h-[1.75rem] items-center gap-2 text-[13px] text-foreground"
                  >
                    <input
                      type="checkbox"
                      className="h-4 w-4 shrink-0 accent-primary"
                      checked={rascunho.slots.includes(f.slot)}
                      onChange={(e) =>
                        mexer(
                          'slots',
                          e.target.checked
                            ? [...rascunho.slots, f.slot]
                            : rascunho.slots.filter((s) => s !== f.slot),
                        )
                      }
                    />
                    <span className="min-w-0 truncate">
                      {f.rotulo}{' '}
                      <span className="text-muted-foreground">
                        {f.largura}×{f.altura} · {f.midia}
                      </span>
                    </span>
                  </label>
                ))}
            </div>
          </fieldset>
        )}

        {nivel !== 'guiado' && (
          <>
            {parque.skins && parque.skins.length > 0 && (
              <Campo id="lab-skin" rotulo="Estrutura da história">
                <Escolha
                  id="lab-skin"
                  valor={rascunho.skinSlug ?? ''}
                  aoMudar={(v) => mexer('skinSlug', v || null)}
                  vazio="Sem estrutura definida"
                  opcoes={parque.skins
                    .filter((s) => s.ativo)
                    .map((s) => ({ valor: s.slug, palavra: `${s.slug} · ${s.nicho}` }))}
                />
              </Campo>
            )}
            {parque.vozes && parque.vozes.length > 0 && (
              <Campo id="lab-voz" rotulo="Voz">
                <Escolha
                  id="lab-voz"
                  valor={rascunho.vozSlug ?? ''}
                  aoMudar={(v) => mexer('vozSlug', v || null)}
                  vazio="Sem voz definida"
                  opcoes={parque.vozes
                    .filter((v) => v.ativo)
                    .map((v) => ({
                      valor: v.slug,
                      palavra: `${v.slug} · ${v.idioma}${v.estilo ? ` · ${v.estilo}` : ''}`,
                    }))}
                />
              </Campo>
            )}
          </>
        )}

        {nivel === 'especialista' && (
          <Campo
            id="lab-seed"
            rotulo="Semente do render"
            ajuda="Fixa de propósito. A fábrica renderiza em paralelo; com semente livre, o mesmo traço sai diferente em cada pedaço do vídeo."
          >
            <input
              id="lab-seed"
              type="number"
              value={rascunho.seed}
              onChange={(e) => mexer('seed', Number(e.target.value) || 1)}
              className="min-h-9 w-full rounded-md border border-input bg-background px-2.5 text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            />
          </Campo>
        )}
      </div>
    </Secao>
  );

  // ── zona 2: a receita compilada ───────────────────────────────────────────
  const compilada = (
    <Secao
      titulo="Receita compilada"
      descricao="O objeto que um motor executaria. Derivado das escolhas, nunca digitado."
      className="min-w-0"
    >
      {receita.saidas.length === 0 ? (
        <p className="text-[13px] leading-relaxed text-muted-foreground">
          Escolha ao menos um formato para a receita tomar forma. Não há preview a mostrar:
          esta fatia compila a receita, e não renderiza peça.
        </p>
      ) : (
        <div className="space-y-4">
          <ul className="space-y-1.5">
            {receita.saidas.map((s) => (
              <li
                key={s.slot}
                className="flex flex-wrap items-baseline gap-x-2 rounded-md border border-border px-3 py-2 text-[13px]"
              >
                <span className="font-medium text-foreground">{s.rotulo}</span>
                <span className="text-muted-foreground">
                  {s.largura}×{s.altura} · {s.midia}
                </span>
              </li>
            ))}
          </ul>

          <Ficha
            itens={[
              {
                rotulo: 'Custo estimado',
                valor:
                  receita.custoEstimadoUsd === null ? (
                    <span className="text-muted-foreground">
                      Não estimado: este motor não declara custo. Não é o mesmo que ser de graça.
                    </span>
                  ) : (
                    <>
                      US$ {receita.custoEstimadoUsd.toFixed(4)}{' '}
                      <span className="text-muted-foreground">
                        · estimativa, não medição{receita.custoFonte ? ` · ${receita.custoFonte}` : ''}
                      </span>
                    </>
                  ),
              },
              {
                rotulo: 'Semente',
                valor: <span className="font-mono">{receita.seed}</span>,
              },
            ]}
          />

          {nivel === 'especialista' && receita.procedencia.length > 0 && (
            <div>
              <h3 className="mb-1.5 text-[13px] font-medium text-foreground">Procedência</h3>
              <ul className="space-y-1">
                {receita.procedencia.map((p, i) => (
                  <li key={`${p.campo}-${i}`} className="text-[12px] text-muted-foreground">
                    <span className="text-foreground">{p.campo}</span> · {p.fonte}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <p className="mt-4 border-t border-border pt-3 text-[12px] leading-relaxed text-muted-foreground">
        Esta receita vive apenas nesta aba. A tabela que a guardaria (`criativo_template`)
        está planejada e não foi aplicada, então não há botão de salvar, em vez de um botão
        que não salva.
      </p>
    </Secao>
  );

  // ── zona 3: compatibilidade ───────────────────────────────────────────────
  const compatibilidade = (
    <Secao
      titulo="Compatibilidade"
      descricao="O que impede, o que apenas avisa, e de onde veio cada número."
      className="min-w-0"
    >
      <div className="space-y-4">
        <div aria-live="polite" role="status">
          {liberado ? (
            <Selo
              glifo={CircleCheck}
              palavra="Nada impede"
              descricao="Nenhum impedimento encontrado para esta receita."
              tom="sucesso"
            />
          ) : (
            <Selo
              glifo={CircleOff}
              palavra={`${impedimentos.length} impedimento${impedimentos.length > 1 ? 's' : ''}`}
              descricao="Há regra que impede esta receita de produzir."
              tom="erro"
            />
          )}
        </div>

        {rascunho.canal && firmeza.provisorias > 0 && (
          <p className="rounded-md border border-warning/50 bg-warning/[0.08] px-3 py-2 text-[12px] leading-relaxed text-foreground">
            {firmeza.firmes === 0 ? (
              <>
                <strong className="font-semibold">
                  Nenhuma exigência de {rascunho.canal} pode barrar esta receita.
                </strong>{' '}
                As {firmeza.provisorias} regras registradas para este canal ainda não foram
                conferidas contra a fonte oficial, então elas avisam e não impedem. Ausência
                de bloqueio aqui não é aprovação.
              </>
            ) : (
              <>
                {firmeza.provisorias} de {firmeza.firmes + firmeza.provisorias} regras de{' '}
                {rascunho.canal} ainda não foram conferidas contra a fonte oficial. Elas
                avisam e não impedem.
              </>
            )}
          </p>
        )}

        {finalidade && (
          <p className="text-[12px] leading-relaxed text-muted-foreground">
            <span className="text-foreground">
              {CLASSE_DE_FINALIDADE[finalidade.classe]?.palavra ?? finalidade.classe}:
            </span>{' '}
            {CLASSE_DE_FINALIDADE[finalidade.classe]?.explicacao ?? finalidade.descricao}
          </p>
        )}

        {impedimentos.length > 0 && (
          <ul className="space-y-2">
            {impedimentos.map((a, i) => (
              <li
                key={i}
                className="rounded-md border border-destructive/50 bg-destructive/[0.06] px-3 py-2"
              >
                <p className="text-[13px] leading-relaxed text-foreground">{a.oQue}</p>
                {a.fonte && (
                  <p className="mt-1 text-[11px] text-muted-foreground">Fonte: {a.fonte}</p>
                )}
              </li>
            ))}
          </ul>
        )}

        {avisos.length > 0 && (
          <ul className="space-y-2">
            {avisos.map((a, i) => (
              <li key={i} className="rounded-md border border-warning/50 bg-warning/[0.08] px-3 py-2">
                <div className="flex items-start gap-2">
                  <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden />
                  <div className="min-w-0">
                    <p className="text-[13px] leading-relaxed text-foreground">{a.oQue}</p>
                    {a.fonte && (
                      <p className="mt-1 text-[11px] text-muted-foreground">Fonte: {a.fonte}</p>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}

        {parque.divergencias.length > 0 && (
          <div className="border-t border-border pt-3">
            <h3 className="text-[13px] font-medium text-foreground">
              Catálogo e executor discordam
            </h3>
            <p className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground">
              Medido nesta leitura. Não é configuração: some quando as duas pontas forem alinhadas.
            </p>
            <ul className="mt-2 space-y-1.5">
              {parque.divergencias.map((d, i) => (
                <li key={i} className="text-[12px] leading-relaxed text-foreground">
                  {d.oQue}
                  {(d.banco || d.runtime) && (
                    <span className="text-muted-foreground">
                      {' '}
                      (banco: {d.banco ?? 'não declara'} · executor: {d.runtime ?? 'não conhece'})
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Secao>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Nível de detalhe" className="flex flex-wrap gap-1">
          {NIVEIS.map((n) => (
            <button
              key={n.chave}
              type="button"
              onClick={() => setNivel(n.chave)}
              aria-pressed={nivel === n.chave}
              title={n.explicacao}
              className={cn(
                'min-h-9 rounded-md border px-3 text-[13px] font-medium',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                nivel === n.chave
                  ? 'border-primary/50 bg-primary/[0.10] text-foreground'
                  : 'border-border text-muted-foreground hover:text-foreground',
              )}
            >
              {n.palavra}
            </button>
          ))}
        </div>
        <p className="min-w-0 flex-1 text-[12px] leading-relaxed text-muted-foreground">
          {NIVEIS.find((n) => n.chave === nivel)?.explicacao} Trocar de nível não perde o que
          já foi escolhido.
        </p>
      </div>

      <Producao receita={receita} liberado={liberado} seed={rascunho.seed} />

      {estreito ? (
        <Tabs defaultValue="direcao">
          <TabsList className="w-full">
            <TabsTrigger value="direcao" className="flex-1">
              Direção
            </TabsTrigger>
            <TabsTrigger value="receita" className="flex-1">
              Receita
            </TabsTrigger>
            <TabsTrigger value="compat" className="flex-1">
              Compatibilidade
            </TabsTrigger>
          </TabsList>
          <TabsContent value="direcao" className="mt-4">
            {direcao}
          </TabsContent>
          <TabsContent value="receita" className="mt-4">
            {compilada}
          </TabsContent>
          <TabsContent value="compat" className="mt-4">
            {compatibilidade}
          </TabsContent>
        </Tabs>
      ) : (
        <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)_minmax(0,380px)]">
          {direcao}
          {compilada}
          {compatibilidade}
        </div>
      )}
    </div>
  );
};
