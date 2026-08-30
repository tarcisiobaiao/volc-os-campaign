/**
 * `/criativos/imagens/novo` — o briefing guiado de imagem.
 *
 * ## As três proibições que governam esta tela
 *
 * 1. **O formulário não é destruído ao gerar.** SPEC §8.2 lista isso como
 *    padrão rejeitado. O rascunho vive num estado local que sobrevive ao envio;
 *    se a criação falhar, ou se a pessoa voltar, tudo continua preenchido.
 * 2. **Nada de wizard modal.** A trilha fica visível, dá para saltar de etapa e
 *    dá para reler o que já foi respondido.
 * 3. **A revisão do contrato vem antes de gerar.** DESIGN.md, regra 5: uma ação
 *    que gasta dinheiro explica escopo e consequência ANTES de ficar disponível.
 *
 * ## Sobre os modos
 *
 * Só `full_llm` está implementado. Os outros cinco aparecem desabilitados, com
 * o motivo escrito. Escondê-los faria a tela prometer que só existe um caminho;
 * oferecê-los sem marca faria a tela prometer capacidade inexistente.
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles } from 'lucide-react';

import { Layout } from '@/components/layout/Layout';
import { Button } from '@/components/ui/button';
import { CabecalhoDoEstudio, Corpo, Secao } from '@/components/criativos/comum/Painel';
import { ErroDeLeitura, Indisponivel } from '@/components/criativos/comum/Estados';
import { CampoDeArea, CampoDeTexto, GrupoDeEscolha } from '@/components/criativos/briefing/Campos';
import { Trilha } from '@/components/criativos/briefing/Trilha';
import {
  DESTINOS,
  ETAPAS,
  MODOS,
  RASCUNHO_VAZIO,
  RESUMO_DA_ETAPA,
  TITULO_DA_ETAPA,
  etapaAnterior,
  fraseDeConsequencia,
  linhasDaRevisao,
  paraPedido,
  podeGerar,
  proximaEtapa,
  validarEtapa,
  validarTudo,
  type EtapaDoBriefing,
  type RascunhoDeImagem,
} from '@/components/criativos/briefing/contrato';
import { useCriarJobDeImagem } from '@/hooks/useCriativosJob';
import { useCriativosBrandPacks, useCriativosFormatos } from '@/hooks/useCriativosCatalogo';
import { CODIGO, codigoDaFalha, ehCodigo, mensagemDaFalha } from '@/lib/criativosApi';
import type { ModoDeProducao } from '@/types/criativos';

function alternar(lista: string[], valor: string): string[] {
  return lista.includes(valor) ? lista.filter((v) => v !== valor) : [...lista, valor];
}

const BriefingDeImagemPage: React.FC = () => {
  const navegar = useNavigate();
  const [rascunho, setRascunho] = React.useState<RascunhoDeImagem>(RASCUNHO_VAZIO);
  const [etapa, setEtapa] = React.useState<EtapaDoBriefing>('intencao');
  const [tentouGerar, setTentouGerar] = React.useState(false);

  const { formatos, doContrato, motorConfigurado } = useCriativosFormatos();
  const { brandPacks, nomeDoPack } = useCriativosBrandPacks();
  const criar = useCriarJobDeImagem();

  const mudar = <K extends keyof RascunhoDeImagem>(chave: K, valor: RascunhoDeImagem[K]) =>
    setRascunho((r) => ({ ...r, [chave]: valor }));

  // Erros da etapa aparecem depois da primeira tentativa de avançar, e todos os
  // erros aparecem depois da primeira tentativa de gerar: marcar campo vazio
  // como errado antes de a pessoa chegar nele é ruído, não ajuda.
  const [tentouAvancar, setTentouAvancar] = React.useState<Record<string, boolean>>({});
  const errosDaEtapa = validarEtapa(etapa, rascunho);
  const mostrarErros = tentouAvancar[etapa] || tentouGerar;
  const erro = (campo: keyof RascunhoDeImagem) =>
    mostrarErros ? (validarTudo(rascunho)[campo] ?? undefined) : undefined;

  const gerar = async () => {
    setTentouGerar(true);
    if (!podeGerar(rascunho)) {
      setEtapa(ETAPAS.find((e) => Object.keys(validarEtapa(e, rascunho)).length > 0) ?? 'intencao');
      return;
    }
    // Sem `idempotencyKey`: o backend descarta campo extra, e a chave montada
    // aqui era enviada e ignorada. Quem resolve a idempotencia e o servidor,
    // derivando do mesmo conteudo; o reenvio reconhecido volta como HTTP 200
    // com o cabecalho `X-Criativo-Idempotente: replay`.
    const pedido = paraPedido(rascunho);
    try {
      const { job, replay } = await criar.mutateAsync(pedido);
      // ⚠️ O rascunho NÃO é limpo aqui. Voltar a esta tela reencontra tudo.
      //
      // `replay` viaja junto para a tela do trabalho dizer que o pedido já
      // existia. Sem isso, o operador que clicou duas vezes vê um job
      // aparecendo e conclui que produziu duas vezes, e paga duas vezes na
      // cabeça dele.
      navegar(`/criativos/jobs/${job.id}`, { state: { replay } });
    } catch {
      /* a falha é renderizada abaixo; o formulário permanece intacto */
    }
  };

  const avancar = () => {
    setTentouAvancar((t) => ({ ...t, [etapa]: true }));
    if (Object.keys(errosDaEtapa).length === 0) setEtapa(proximaEtapa(etapa));
  };

  return (
    <Layout>
      <CabecalhoDoEstudio
        kicker="Nova imagem"
        titulo="Briefing de imagem"
        proposito="Responda o que a peça precisa fazer. A última etapa mostra o contrato do pedido e o que ele custa antes de qualquer chamada ao motor."
        voltar={{ para: '/criativos', rotulo: 'Estúdio Criativo' }}
      />

      <Corpo>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,260px)_minmax(0,1fr)]">
          <div className="min-w-0">
            <Trilha atual={etapa} rascunho={rascunho} aoIr={setEtapa} />
          </div>

          <div className="min-w-0 space-y-4">
            <Secao titulo={TITULO_DA_ETAPA[etapa]} descricao={RESUMO_DA_ETAPA[etapa]}>
              {etapa === 'intencao' && (
                <div className="space-y-5">
                  <CampoDeTexto
                    id="briefing-titulo"
                    rotulo="Nome do trabalho"
                    ajuda="É por este nome que você reencontra o trabalho na Home e na biblioteca."
                    valor={rascunho.projetoTitulo}
                    aoMudar={(v) => mudar('projetoTitulo', v)}
                    erro={erro('projetoTitulo')}
                    obrigatorio
                    maximo={120}
                  />
                  <CampoDeArea
                    id="briefing-objetivo"
                    rotulo="Objetivo da peça"
                    ajuda="O que esta peça precisa fazer acontecer. Não descreva a arte, descreva o resultado."
                    valor={rascunho.objetivo}
                    aoMudar={(v) => mudar('objetivo', v)}
                    erro={erro('objetivo')}
                    obrigatorio
                    linhas={3}
                  />
                  <GrupoDeEscolha
                    nome="briefing-destinos"
                    legenda="Destinos pretendidos"
                    ajuda="Pretender não valida e não autoriza. A peça só é declarada compatível com um destino depois da validação de formato e contrato."
                    multipla
                    colunas={2}
                    opcoes={DESTINOS.map((d) => ({
                      valor: d.destino,
                      rotulo: d.rotulo,
                      descricao: d.descricao,
                    }))}
                    selecionados={rascunho.destinosPretendidos}
                    aoAlternar={(v) =>
                      mudar('destinosPretendidos', alternar(rascunho.destinosPretendidos, v))
                    }
                    erro={erro('destinosPretendidos')}
                  />
                </div>
              )}

              {etapa === 'formatos' && (
                <div className="space-y-4">
                  {doContrato && (
                    <p className="rounded-md border border-border bg-muted/50 px-3 py-2 text-[12px] leading-relaxed text-muted-foreground">
                      A lista de formatos do servidor não foi lida nesta sessão. Estes são os
                      formatos que o contrato local declara, e são os mesmos que o motor valida.
                    </p>
                  )}
                  <GrupoDeEscolha
                    nome="briefing-formatos"
                    legenda="Formatos a gerar"
                    ajuda="Cada formato é uma peça com estado próprio. Uma peça que falha não derruba as outras."
                    multipla
                    colunas={2}
                    opcoes={formatos.map((f) => ({
                      valor: f.slot,
                      rotulo: `${f.rotulo}, ${f.proporcao}`,
                      descricao: `${f.largura} x ${f.altura} px. ${f.descricao}`,
                    }))}
                    selecionados={rascunho.slots}
                    aoAlternar={(v) => mudar('slots', alternar(rascunho.slots, v))}
                    erro={erro('slots')}
                  />
                </div>
              )}

              {etapa === 'mensagem' && (
                <div className="space-y-5">
                  <CampoDeArea
                    id="briefing-mensagem"
                    rotulo="Mensagem da peça"
                    ajuda="O que a peça precisa comunicar. Este texto vai para o motor; ele não é gravado como prompt visível na biblioteca."
                    valor={rascunho.mensagem}
                    aoMudar={(v) => mudar('mensagem', v)}
                    erro={erro('mensagem')}
                    obrigatorio
                    linhas={5}
                  />
                  <CampoDeTexto
                    id="briefing-audiencia"
                    rotulo="Público"
                    ajuda="Opcional. Deixe em branco se ainda não souber: em branco fica registrado como ausência, não como público genérico."
                    valor={rascunho.audiencia}
                    aoMudar={(v) => mudar('audiencia', v)}
                    maximo={200}
                  />
                </div>
              )}

              {etapa === 'marca' && (
                <div className="space-y-6">
                  <GrupoDeEscolha
                    nome="briefing-brandpack"
                    legenda="Brand pack"
                    ajuda="A identidade que governa paleta, tipografia e regra de logo. Sem pack, o motor compõe sem identidade declarada."
                    multipla={false}
                    opcoes={[
                      {
                        valor: '',
                        rotulo: 'Nenhum brand pack',
                        descricao: 'A peça sai sem identidade declarada e sem regra de logo.',
                      },
                      ...brandPacks.map((p) => ({
                        valor: p.id,
                        rotulo: `${p.nome}, versão ${p.versao}`,
                        descricao: p.ativo
                          ? 'Pack ativo.'
                          : 'Pack inativo. Ele ainda pode ser usado, mas não é o padrão da casa.',
                      })),
                    ]}
                    selecionados={[rascunho.brandPackId]}
                    aoAlternar={(v) => mudar('brandPackId', v)}
                  />
                  <GrupoDeEscolha
                    nome="briefing-modo"
                    legenda="Modo de produção"
                    ajuda="Você escolhe a finalidade, não a implementação. Cinco modos existem no desenho e ainda não estão ligados neste ambiente."
                    multipla={false}
                    opcoes={MODOS.map((m) => ({
                      valor: m.modo,
                      rotulo: m.rotulo,
                      descricao: m.descricao,
                      disponivel: m.disponivel,
                      motivo: m.motivo,
                    }))}
                    selecionados={[rascunho.modo]}
                    aoAlternar={(v) => mudar('modo', v as ModoDeProducao)}
                    erro={erro('modo')}
                  />
                </div>
              )}

              {etapa === 'revisao' && (
                <div className="space-y-5">
                  <dl className="divide-y divide-border/70">
                    {linhasDaRevisao(rascunho, formatos, nomeDoPack).map((linha) => (
                      <div
                        key={linha.rotulo}
                        className="grid grid-cols-1 gap-1 py-2.5 sm:grid-cols-[minmax(0,180px)_minmax(0,1fr)] sm:gap-4"
                      >
                        <dt className="kicker">{linha.rotulo}</dt>
                        <dd className="break-words text-sm text-foreground">{linha.valor}</dd>
                      </div>
                    ))}
                  </dl>

                  <div className="rounded-md border border-warning/55 bg-warning/[0.08] px-4 py-3">
                    <p className="font-display text-sm font-semibold text-foreground">
                      O que acontece ao gerar
                    </p>
                    <p className="mt-1 text-pretty text-[13px] leading-relaxed text-foreground">
                      {fraseDeConsequencia(rascunho)}
                    </p>
                    <p className="mt-1 text-pretty text-[13px] leading-relaxed text-muted-foreground">
                      Reenviar este mesmo formulário não gera peça nova: o servidor reconhece o
                      pedido repetido e devolve o trabalho que já existe.
                    </p>
                  </div>

                  {motorConfigurado === false && (
                    <Indisponivel
                      titulo="O servidor não tem credencial de provedor"
                      motivo="Sem credencial, pedir peça falha na hora. A geração fica desabilitada até que alguém configure o provedor no servidor. Seu briefing continua salvo nesta tela."
                    />
                  )}

                  {tentouGerar && !podeGerar(rascunho) && (
                    <Indisponivel
                      titulo="Faltam respostas obrigatórias"
                      motivo="Volte às etapas marcadas como incompletas na trilha. Os campos com problema estão apontados lá."
                    />
                  )}

                  {criar.isError && (
                    <ErroDeLeitura
                      mensagem={mensagemDaFalha(criar.error)}
                      codigo={codigoDaFalha(criar.error)}
                      ressalva={
                        ehCodigo(criar.error, CODIGO.motorSemCredencial)
                          ? 'Isto não é problema do seu briefing: o servidor está sem credencial de provedor. Seu briefing continua preenchido.'
                          : ehCodigo(criar.error, CODIGO.modoIndisponivel)
                            ? 'O modo escolhido não está implementado neste ambiente. Volte à etapa do brand pack e escolha um modo habilitado.'
                            : 'Seu briefing continua preenchido. Nada foi perdido.'
                      }
                    />
                  )}
                </div>
              )}
            </Secao>

            <div className="flex flex-wrap items-center justify-between gap-3">
              <Button
                variant="outline"
                onClick={() => setEtapa(etapaAnterior(etapa))}
                disabled={etapa === ETAPAS[0]}
              >
                Voltar uma etapa
              </Button>
              {etapa === 'revisao' ? (
                <Button
                  onClick={() => void gerar()}
                  disabled={criar.isPending || motorConfigurado === false}
                  title={
                    motorConfigurado === false
                      ? 'O servidor não tem credencial de provedor. O pedido falharia na hora.'
                      : undefined
                  }
                >
                  <Sparkles className="h-4 w-4" aria-hidden />
                  {criar.isPending ? 'Enviando o pedido' : 'Gerar as peças'}
                </Button>
              ) : (
                <Button onClick={avancar}>Continuar</Button>
              )}
            </div>

            <p className="text-[12px] leading-relaxed text-muted-foreground" role="status">
              Este briefing não é apagado ao gerar. Se a criação falhar, ou se você voltar para
              cá, tudo continua preenchido.
            </p>
          </div>
        </div>
      </Corpo>
    </Layout>
  );
};

export default BriefingDeImagemPage;
