/**
 * `/criativos/brand-packs` — os packs de identidade, somente leitura.
 *
 * ## Somente leitura nesta rodada, e a tela diz isso
 *
 * Não há botão de editar, criar ou desativar. Um botão que abre um formulário
 * que não persiste é pior que a ausência dele. O que a tela oferece é o que ela
 * consegue provar: nome, versão, estado, resumo dos tokens e o hash das fontes.
 *
 * ## Por que o resumo dos tokens é só a superfície
 *
 * Porque `tokens` é `Record<string, unknown>` no contrato: um pack pode ter
 * aninhamento arbitrário. Desenhar uma árvore completa aqui seria um editor de
 * JSON disfarçado. O que serve para reconhecer um pack é a paleta e o nome das
 * chaves de primeiro nível.
 */
import React from 'react';

import { Layout } from '@/components/layout/Layout';
import { CabecalhoDoEstudio, Corpo, Secao } from '@/components/criativos/comum/Painel';
import { Carregando, ErroDeLeitura, Vazio } from '@/components/criativos/comum/Estados';
import { Selo } from '@/components/criativos/comum/Selo';
import { hashCurto, instante } from '@/components/criativos/comum/formato';
import { useCriativosBrandPacks } from '@/hooks/useCriativosCatalogo';
import { codigoDaFalha, mensagemDaFalha } from '@/lib/criativosApi';
import { CircleCheck, CircleSlash } from 'lucide-react';

const HEX = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;

/** Achata o primeiro nível dos tokens em pares legíveis. Nada de árvore. */
function resumirTokens(tokens: Record<string, unknown>): { chave: string; valor: string }[] {
  return Object.entries(tokens)
    .slice(0, 12)
    .map(([chave, valor]) => ({
      chave,
      valor:
        valor === null
          ? 'não definido'
          : typeof valor === 'object'
            ? `${Object.keys(valor as object).length} chaves`
            : String(valor),
    }));
}

const BrandPacksPage: React.FC = () => {
  const { brandPacks, carregando, erro, recarregar } = useCriativosBrandPacks();

  return (
    <Layout>
      <CabecalhoDoEstudio
        kicker="Identidade"
        titulo="Brand packs"
        proposito="A identidade que governa paleta, tipografia e regra de logo nas peças. Nesta rodada a tela é somente leitura: nada aqui pode ser editado pelo navegador."
        voltar={{ para: '/criativos', rotulo: 'Estúdio Criativo' }}
      />

      <Corpo>
        <Secao
          titulo="Packs cadastrados"
          descricao="Cada pack é versionado. A versão usada por uma peça fica guardada na procedência dela."
        >
          {carregando ? (
            <Carregando rotulo="Lendo os brand packs" linhas={2} altura="h-28" />
          ) : erro ? (
            <ErroDeLeitura
              mensagem={mensagemDaFalha(erro)}
              codigo={codigoDaFalha(erro)}
              aoTentarDeNovo={recarregar}
            />
          ) : brandPacks.length ? (
            <ul className="space-y-3">
              {brandPacks.map((pack) => {
                const tokens = resumirTokens(pack.tokens);
                return (
                  <li key={pack.id} className="rounded-md border border-border bg-muted/30 p-3">
                    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
                      <div className="min-w-0">
                        <h3 className="font-display text-sm font-semibold text-foreground">
                          {pack.nome}
                        </h3>
                        <p className="mt-0.5 text-[12px] text-muted-foreground">
                          Identificador {pack.slug}, versão {pack.versao}. Criado em{' '}
                          {instante(pack.criadoEm)}.
                        </p>
                      </div>
                      {pack.ativo ? (
                        <Selo
                          glifo={CircleCheck}
                          palavra="Ativo"
                          descricao="Este pack é oferecido como padrão em novos briefings."
                          tom="sucesso"
                        />
                      ) : (
                        <Selo
                          glifo={CircleSlash}
                          palavra="Inativo"
                          descricao="Não é oferecido como padrão. Peças antigas que o usaram continuam válidas."
                          tom="neutro"
                        />
                      )}
                    </div>

                    <p className="mt-3 text-[12px] text-muted-foreground">
                      Fontes vendorizadas:{' '}
                      {pack.fontesHash ? (
                        <span className="font-mono" title={pack.fontesHash}>
                          {hashCurto(pack.fontesHash)}
                        </span>
                      ) : (
                        'este pack não vendoriza fonte própria'
                      )}
                    </p>

                    {tokens.length ? (
                      <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
                        {tokens.map((t) => (
                          <div key={t.chave} className="flex items-center gap-2">
                            {HEX.test(t.valor) && (
                              <span
                                className="h-3.5 w-3.5 shrink-0 rounded-sm border border-border"
                                style={{ backgroundColor: t.valor }}
                                aria-hidden
                              />
                            )}
                            <dt className="shrink-0 text-[12px] text-muted-foreground">
                              {t.chave}
                            </dt>
                            <dd className="min-w-0 truncate text-[12px] text-foreground">
                              {t.valor}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    ) : (
                      <p className="mt-3 text-[12px] text-muted-foreground">
                        Este pack não declarou tokens.
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          ) : (
            <Vazio
              titulo="Nenhum brand pack cadastrado"
              explicacao="Um brand pack guarda paleta, tipografia e regra de logo como dado. Sem pack, as peças saem sem identidade declarada."
            />
          )}
        </Secao>
      </Corpo>
    </Layout>
  );
};

export default BrandPacksPage;
