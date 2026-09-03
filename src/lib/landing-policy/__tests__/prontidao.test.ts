/**
 * O contrato desta camada, em teste: DESCONHECIDO NUNCA VIRA PRONTO.
 *
 * Cada teste aqui é uma contraprova de um caminho por onde a tela poderia
 * pintar verde sem prova. O agrupamento é por caminho, não por função, porque é
 * o caminho que se pode reabrir numa refatoração.
 */
import { describe, expect, it } from 'vitest';

import {
  avisoBarraOLancamento,
  estadoDaPublicacao,
  leituraDoDestinoPago,
  pendenciasDoDestino,
  reciboDoPortador,
  resumoDoDestino,
  textoDaProntidao,
  tomDaProntidao,
} from '@/lib/landing-policy/prontidao';
import { portadorApto, reciboApto } from './recibos';

const AGORA = 1_756_900_000;
const ler = (portador: unknown, over: Record<string, unknown> = {}) =>
  leituraDoDestinoPago(portador, { agora_epoch: AGORA, status_wp: 'publish', ...over });

describe('tomDaProntidao — falha fechada no mapeamento estado → tom', () => {
  it('nada além de APTO pinta positivo, nem um estado que alguém invente', () => {
    // Os casts simulam o que chegaria de um servidor que emitisse um estado
    // novo, ou nenhum. Nenhum deles pode virar verde: é o defeito inteiro desta
    // sprint reintroduzido pela paleta.
    const estranho = (v: unknown) => tomDaProntidao(v as never);
    expect(estranho(undefined)).toBe('ignorado');
    expect(estranho(null)).toBe('ignorado');
    expect(estranho('')).toBe('ignorado');
    expect(estranho('PRONTO')).toBe('ignorado');
    expect(estranho('ESTADO_QUE_ALGUEM_INVENTAR')).toBe('ignorado');
  });

  it('só APTO pinta positivo — nenhum outro estado é "provado"', () => {
    expect(tomDaProntidao('APTO')).toBe('provado');
    expect(tomDaProntidao('BLOQUEADO')).toBe('negado');
    expect(tomDaProntidao('INDETERMINADO')).toBe('ignorado');
    expect(tomDaProntidao('NAO_AVALIADO')).toBe('ausente');
    // A do Google é cinza para sempre: ela não fica verde porque o resto ficou.
    expect(tomDaProntidao('DESCONHECIDA_POR_CONTRATO')).toBe('ignorado');
  });

  it('nunca diz "sem dados" — cada estado tem a frase que pede a ação dele', () => {
    expect(textoDaProntidao('INDETERMINADO')).toBe('não se sabe');
    expect(textoDaProntidao('NAO_AVALIADO')).toBe('não avaliado neste ponto');
    expect(textoDaProntidao('DESCONHECIDA_POR_CONTRATO')).toContain('continuará');
  });
});

describe('estadoDaPublicacao — o fail-open medido em NovaCampanhaPage ~499', () => {
  it('status_wp null NÃO é "LP no ar": é INDETERMINADO', () => {
    // ⚠️ A linha antiga era `pronto={status_wp !== 'draft'}`, que devolvia
    // `true` para `null` — ou seja, marcava a etapa como pronta exatamente
    // quando o servidor nunca tinha conseguido ler o WordPress.
    expect(estadoDaPublicacao(null)).toBe('INDETERMINADO');
    expect(estadoDaPublicacao(undefined)).toBe('INDETERMINADO');
    expect(estadoDaPublicacao('')).toBe('INDETERMINADO');
  });

  it('só `publish` abre; rascunho e qualquer status novo BLOQUEIAM', () => {
    expect(estadoDaPublicacao('publish')).toBe('APTO');
    expect(estadoDaPublicacao('draft')).toBe('BLOQUEADO');
    expect(estadoDaPublicacao('pending')).toBe('BLOQUEADO');
    expect(estadoDaPublicacao('status_novo_do_wordpress')).toBe('BLOQUEADO');
  });
});

describe('reciboDoPortador', () => {
  it('acha o recibo sob a chave de transporte, e aceita o recibo cru', () => {
    expect(reciboDoPortador(portadorApto())).not.toBeNull();
    expect(reciboDoPortador(reciboApto())).not.toBeNull();
  });

  it('devolve null para portador que não é objeto, ou sem a chave', () => {
    expect(reciboDoPortador(null)).toBeNull();
    expect(reciboDoPortador('um recibo, prometo')).toBeNull();
    expect(reciboDoPortador([])).toBeNull();
    expect(reciboDoPortador({ post_id: 2152, status_wp: 'publish' })).toBeNull();
    // Chave presente com lixo dentro também é ausência.
    expect(reciboDoPortador({ landing_policy_receipt: 'sim' })).toBeNull();
  });
});

describe('leituraDoDestinoPago — o caminho apto', () => {
  it('recibo apto, publicado e no ponto de campanha libera', () => {
    const l = ler(portadorApto());
    expect(l.pode_seguir).toBe(true);
    expect(l.apto_para_campanha).toBe(true);
    expect(l.perguntas.volc).toBe('APTO');
    expect(l.perguntas.publicacao).toBe('APTO');
    expect(l.perguntas.campanha).toBe('APTO');
    expect(l.recusas).toEqual([]);
    expect(pendenciasDoDestino(l)).toEqual([]);
  });

  it('mesmo apto, a aprovação do Google continua DESCONHECIDA', () => {
    // ⚠️ A contraprova central do painel: verde em tudo não produz, em lugar
    // nenhum, uma afirmação sobre o revisor do Google.
    const l = ler(portadorApto());
    expect(l.perguntas.google).toBe('DESCONHECIDA_POR_CONTRATO');
    expect(tomDaProntidao(l.perguntas.google)).not.toBe('provado');
    expect(resumoDoDestino(l)).toContain('Google desconhecido');
  });
});

describe('leituraDoDestinoPago — desconhecido não vira pronto', () => {
  it('SEM RECIBO: indeterminado, nunca apto', () => {
    // O caso que este arquivo existe para não deixar passar: uma resposta em
    // que ninguém avaliou a página é indistinguível, na forma, de uma em que a
    // página passou — a não ser que a ausência tenha um estado próprio.
    const l = ler({ post_id: 1, status_wp: 'publish' });
    expect(l.sem_recibo).toBe(true);
    expect(l.pode_seguir).toBe(false);
    expect(l.apto_para_campanha).toBe(false);
    expect(l.perguntas.volc).toBe('INDETERMINADO');
    expect(l.recusas.join(' ')).toContain('nenhum recibo de política');
  });

  it('DESCONHECIDO sem nenhum bloqueio reprova — o defeito do handoff anterior', () => {
    // ⚠️ Esta é a razão de `pode_seguir` não ser `bloqueadores.length === 0`.
    // Aqui não há um único bloqueio: há uma verificação exigida que não pôde
    // ser concluída, e o portão do backend já devolve `paid_destination_ready:
    // false` por causa dela. Uma tela que testasse só bloqueios publicaria.
    const l = ler(portadorApto({
      paid_destination_ready: false,
      readiness: { volc_gate: 'indeterminate', live_verified: false,
                   google_approval: 'unknown', google_approval_note: 'n/a' },
      unknowns: [{ verificacao: 'live_drift', motivo: 'a página não respondeu em 10 s' }],
    }));
    expect(l.bloqueadores).toEqual([]);
    expect(l.desconhecidos).toHaveLength(1);
    expect(l.pode_seguir).toBe(false);
    expect(l.perguntas.volc).toBe('INDETERMINADO');
    expect(l.recusas.join(' ')).toContain('verificação(ões) que não puderam ser feitas');
  });

  it('recibo que diz "pronto" mas lista desconhecido continua reprovado', () => {
    // Recibo malformado, ou de um backend adiantado: a tela não escolhe a
    // leitura mais permissiva entre duas afirmações que se contradizem.
    const l = ler(portadorApto({
      unknowns: [{ verificacao: 'redirect_chain', motivo: 'sem leitura' }],
    }));
    expect(l.pode_seguir).toBe(false);
  });

  it('readiness.volc_gate diferente de "ready" reprova, mesmo com o booleano true', () => {
    const l = ler(portadorApto({
      readiness: { volc_gate: 'indeterminate', live_verified: true,
                   google_approval: 'unknown', google_approval_note: '' },
    }));
    expect(l.pode_seguir).toBe(false);
  });
});

describe('leituraDoDestinoPago — evidência com prazo', () => {
  it('recibo sem carimbo comparável não é fresco: reprova', () => {
    // `observed_at_epoch: null` é "esta avaliação não é datável". Uma avaliação
    // sem data não pode ser chamada de fresca sem virar afirmação sem prova.
    const l = ler(portadorApto({ observed_at_epoch: null }));
    expect(l.pode_seguir).toBe(false);
    expect(l.recusas.join(' ')).toContain('carimbo comparável');
  });

  it('evidência fora da janela de frescor reprova, mesmo aprovada', () => {
    const l = ler(portadorApto({ observed_at_epoch: AGORA - 86401 }));
    expect(l.pode_seguir).toBe(false);
    expect(l.recusas.join(' ')).toContain('janela de frescor');
  });

  it('dentro da janela, a mesma evidência vale', () => {
    expect(ler(portadorApto({ observed_at_epoch: AGORA - 86399 })).pode_seguir).toBe(true);
  });

  it('versão de política antiga reprova', () => {
    const l = ler(portadorApto({ policy_contract_version: 'paid_destination_policy_spine.v1' }));
    expect(l.pode_seguir).toBe(false);
    expect(l.recusas.join(' ')).toContain('política vigente');
  });
});

describe('leituraDoDestinoPago — o ponto do portão não se empresta', () => {
  it('recibo de pré-publicação não elege destino de campanha', () => {
    // O papel é FORÇADO para destino pago só no ponto de campanha; aprovação
    // obtida antes de publicar foi medida com rigor menor.
    const l = ler(portadorApto({ gate_point: 'pre_publication_wordpress' }));
    expect(l.pode_seguir).toBe(true);
    expect(l.apto_para_campanha).toBe(false);
    expect(l.perguntas.campanha).toBe('NAO_AVALIADO');
  });

  it('no redator, onde a pergunta é outra, o mesmo recibo não vira recusa', () => {
    const l = leituraDoDestinoPago(portadorApto({ gate_point: 'pre_publication_wordpress' }), {
      agora_epoch: AGORA, status_wp: 'publish', exige_ponto_de_campanha: false,
    });
    expect(l.apto_para_campanha).toBe(true);
    expect(l.recusas).toEqual([]);
  });
});

describe('leituraDoDestinoPago — bloqueio, deriva e papel', () => {
  it('bloqueio do servidor fecha, e o achado chega inteiro na tela', () => {
    const l = ler(portadorApto({
      paid_destination_ready: false,
      readiness: { volc_gate: 'blocked', live_verified: true,
                   google_approval: 'unknown', google_approval_note: '' },
      blockers: [{ code: 'LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO', severity: 'blocker',
                   message: 'Sete hyperlinks externos clicáveis no destino pago.' }],
    }));
    expect(l.pode_seguir).toBe(false);
    expect(l.perguntas.volc).toBe('BLOQUEADO');
    expect(l.bloqueadores[0].codigo).toBe('LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO');
    expect(resumoDoDestino(l)).toBe('destino bloqueado');
  });

  it('DERIVA_AO_VIVO acende a deriva mesmo chegando como risco', () => {
    const l = ler(portadorApto({
      risks: [{ code: 'DERIVA_AO_VIVO', severity: 'risk',
                message: 'A impressão canônica mudou desde o hash aprovado.' }],
    }));
    expect(l.deriva).toBe('BLOQUEADO');
  });

  it('sem verificação ao vivo, a deriva é INDETERMINADA — não "sem deriva"', () => {
    const l = ler(portadorApto({
      readiness: { volc_gate: 'ready', live_verified: false,
                   google_approval: 'unknown', google_approval_note: '' },
    }));
    expect(l.deriva).toBe('INDETERMINADO');
    expect(l.perguntas.ao_vivo).toBe('INDETERMINADO');
  });

  it('o papel exibido é o do SERVIDOR, e a divergência do declarado é preservada', () => {
    // Campo vindo do cliente nunca relaxa o papel; a tela mostra os dois para
    // que o operador entenda por que o rigor subiu, e nunca troca um pelo outro.
    const l = ler(portadorApto({ role: 'paid_destination', role_declared: 'organic_article' }));
    expect(l.papel_avaliado).toBe('paid_destination');
    expect(l.papel_declarado).toBe('organic_article');
  });
});

describe('leituraDoDestinoPago — o recibo é lido, não confiado', () => {
  it('achado sem mensagem não vira linha em branco na lista de bloqueios', () => {
    const l = ler(portadorApto({
      paid_destination_ready: false,
      readiness: { volc_gate: 'blocked', live_verified: true,
                   google_approval: 'unknown', google_approval_note: '' },
      blockers: [{ code: 'PAGINA_PONTE' }],
    }));
    expect(l.bloqueadores[0].mensagem).toContain('sem mensagem');
  });

  it('lixo no lugar das listas não derruba a leitura nem a torna permissiva', () => {
    const l = ler(portadorApto({
      blockers: 'nenhum', unknowns: null, risks: 42, observations: undefined,
    }));
    expect(l.bloqueadores).toEqual([]);
    expect(l.desconhecidos).toEqual([]);
    // ⚠️ E ainda assim aprova, porque as outras travas continuam de pé: o
    // recibo segue dizendo `ready`, fresco e da versão certa. O teste existe
    // para provar que a leitura degrada sem explodir — não para sugerir que
    // lixo é aceitável.
    expect(l.pode_seguir).toBe(true);
  });

  it('a origem da evidência admite não ser sabida em vez de inventar procedência', () => {
    const l = ler(portadorApto({
      readiness: { volc_gate: 'ready', live_verified: false,
                   google_approval: 'unknown', google_approval_note: '' },
    }));
    expect(l.origem_da_evidencia).toContain('não declarada no recibo');
  });
});

describe('avisoBarraOLancamento — o cliente não decide o que bloqueia', () => {
  it('severidade não reconhecida BARRA', () => {
    // ⚠️ O conserto do `Set(['LP_EM_RASCUNHO','URL_PROVISORIA'])`: qualquer
    // código de política que não estivesse naquela lista virava observação
    // recolhida enquanto `podeLancar` seguia verdadeiro. Agora a lista é a das
    // que PASSAM, e um valor novo do servidor barra por padrão.
    expect(avisoBarraOLancamento('bloqueio')).toBe(true);
    expect(avisoBarraOLancamento('severidade_nova_do_servidor')).toBe(true);
    expect(avisoBarraOLancamento(undefined)).toBe(true);
    expect(avisoBarraOLancamento(null)).toBe(true);
    expect(avisoBarraOLancamento('')).toBe(true);
    expect(avisoBarraOLancamento(3)).toBe(true);
  });

  it('só informação e atenção passam', () => {
    expect(avisoBarraOLancamento('informacao')).toBe(false);
    expect(avisoBarraOLancamento('atencao')).toBe(false);
  });
});

describe('as pendências da barra fixa', () => {
  it('a forma curta acompanha a longa em número e em ordem', () => {
    const l = leituraDoDestinoPago(portadorApto({
      policy_contract_version: 'v1', observed_at_epoch: null,
    }), { agora_epoch: AGORA, status_wp: null });
    expect(l.pendencias).toHaveLength(l.recusas.length);
    expect(l.pendencias.length).toBeGreaterThan(1);
    // Curtas o bastante para caber na barra, que mostra duas e conta o resto.
    for (const p of l.pendencias) expect(p.length).toBeLessThanOrEqual(40);
  });

  it('status_wp null aparece como pendência de LEITURA, não de publicação', () => {
    // As duas pedem coisas opostas: uma pede publicar, a outra pede ler. Um
    // texto só para as duas mandaria o operador publicar uma página que talvez
    // já esteja publicada.
    const l = leituraDoDestinoPago(portadorApto(), { agora_epoch: AGORA, status_wp: null });
    expect(l.recusas.join(' ')).toContain('ler o status da página');
    expect(l.apto_para_campanha).toBe(false);
    expect(resumoDoDestino(l)).toBe('destino indeterminado');
  });
});
