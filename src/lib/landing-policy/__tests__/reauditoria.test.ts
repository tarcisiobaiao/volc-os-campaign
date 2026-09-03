/**
 * O contrato da REAUDITORIA na tela: NADA PULA ETAPA, e desconhecido não é verde.
 *
 * Cada teste é uma contraprova de um caminho por onde a tela poderia confirmar
 * sem prova, pintar verde sem elegibilidade, ou apresentar como "nada mudou"
 * uma comparação que nunca foi feita.
 */
import { describe, expect, it } from 'vitest';

import {
  bloqueiosPorDono,
  criarClienteDeReauditoria,
  curto,
  ehConflitoDeProva,
  estadoDaProva,
  etapaDaReauditoria,
  mensagemDoErro,
  podeConfirmar,
  textoDoDiff,
  textoDoDono,
  type ProvaDaReauditoria,
} from '@/lib/landing-policy/reauditoria';

const HASH = 'a'.repeat(64);

function prova(troca: Partial<ProvaDaReauditoria> = {}): ProvaDaReauditoria {
  return {
    schema: 'landing_policy_reaudit_proof.v1',
    url_canonica: 'https://exemplo.com.br/r/x',
    impressao_da_prova: HASH,
    elegivel: true,
    veredito: 'approved',
    motivos: [],
    bloqueios: [],
    riscos: [],
    desconhecidos: [],
    recibo_candidato: { fingerprint_scope: 'live', content_fingerprint: 'f'.repeat(64) },
    inventario_de_links: [],
    diff_com_o_recibo_anterior: {
      tinha_recibo: true,
      escopo_anterior: 'live',
      impressao_anterior_12: '111111111111',
      impressao_agora_12: '111111111111',
      mudou: false,
      comparavel: true,
    },
    lido_em_epoch: 1_770_000_000,
    lido_em: '2026-02-02T00:00:00+00:00',
    ...troca,
  };
}

const SEM_ESTADO = { lendo: false, conflito: false, erro: null, confirmadaCom: null };

describe('a ordem das duas etapas não pode ser pulada', () => {
  it('sem prova não há o que confirmar', () => {
    const etapa = etapaDaReauditoria({ prova: null, ...SEM_ESTADO });
    expect(etapa).toBe('SEM_PROVA');
    expect(podeConfirmar(null, etapa)).toBe(false);
  });

  it('prova REPROVADA não habilita o botão — a tela não contorna o portão', () => {
    const reprovada = prova({
      elegivel: false,
      veredito: 'blocked',
      bloqueios: [{
        code: 'LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO',
        severity: 'blocker',
        message: 'x',
        owner: 'funil',
      }],
    });
    const etapa = etapaDaReauditoria({ prova: reprovada, ...SEM_ESTADO });
    expect(etapa).toBe('REPROVADO');
    expect(podeConfirmar(reprovada, etapa)).toBe(false);
  });

  it('prova elegível habilita, e carrega o hash daquela mesma prova', () => {
    const p = prova();
    const etapa = etapaDaReauditoria({ prova: p, ...SEM_ESTADO });
    expect(etapa).toBe('PROVADO');
    expect(podeConfirmar(p, etapa)).toBe(true);
    expect(p.impressao_da_prova).toHaveLength(64);
  });

  it('uma prova NOVA depois de confirmada volta a pedir confirmação', () => {
    // ⚠️ Sem isto, o "confirmado" ficaria por cima de uma leitura que ninguém
    // aprovou — o verde por ausência, de novo.
    const nova = prova({ impressao_da_prova: 'b'.repeat(64) });
    expect(etapaDaReauditoria({ ...SEM_ESTADO, prova: nova, confirmadaCom: HASH }))
      .toBe('PROVADO');
    expect(etapaDaReauditoria({ ...SEM_ESTADO, prova: prova(), confirmadaCom: HASH }))
      .toBe('CONFIRMADO');
  });

  it('conflito e erro vencem a prova em tela', () => {
    expect(etapaDaReauditoria({ ...SEM_ESTADO, prova: prova(), conflito: true }))
      .toBe('CONFLITO');
    expect(etapaDaReauditoria({ ...SEM_ESTADO, prova: prova(), erro: 'caiu' }))
      .toBe('ERRO');
  });
});

describe('desconhecido nunca pinta verde', () => {
  it('sem bloqueio e sem elegibilidade é INDETERMINADO, não BLOQUEADO', () => {
    // ⚠️ São coisas diferentes: BLOQUEADO é "olhei e achei"; INDETERMINADO é
    // "faltou olhar" — e só o segundo é resolvido lendo de novo.
    expect(estadoDaProva(prova({
      elegivel: false,
      desconhecidos: [{ verificacao: 'live_drift', motivo: 'sem hash aprovado' }],
    }))).toBe('INDETERMINADO');
  });

  it('prova ausente é INDETERMINADO, nunca APTO', () => {
    expect(estadoDaProva(null)).toBe('INDETERMINADO');
  });

  it('bloqueio é BLOQUEADO e elegível é APTO', () => {
    expect(estadoDaProva(prova({
      elegivel: false,
      bloqueios: [{ code: 'X', severity: 'blocker', message: 'm', owner: 'funil' }],
    }))).toBe('BLOQUEADO');
    expect(estadoDaProva(prova())).toBe('APTO');
  });
});

describe('o diff não colapsa "não deu para comparar" em "nada mudou"', () => {
  it('recibo de artefato diz que NÃO havia com o que comparar', () => {
    const texto = textoDoDiff({
      tinha_recibo: true,
      escopo_anterior: 'artifact',
      impressao_anterior_12: '999999999999',
      impressao_agora_12: '111111111111',
      mudou: false,
      comparavel: false,
    });
    expect(texto).toContain('artifact');
    expect(texto).not.toContain('é a mesma');
  });

  it('sem recibo anterior é primeira avaliação, e não "igual"', () => {
    const texto = textoDoDiff({
      tinha_recibo: false,
      escopo_anterior: null,
      impressao_anterior_12: null,
      impressao_agora_12: '111111111111',
      mudou: false,
      comparavel: false,
    });
    expect(texto).toContain('Primeira avaliação');
  });

  it('comparável e igual afirma que é a mesma página', () => {
    expect(textoDoDiff(prova().diff_com_o_recibo_anterior)).toContain('a mesma');
  });
});

describe('o dono de cada bloqueio', () => {
  it('agrupa por dono, e o dono é o do backend', () => {
    const grupos = bloqueiosPorDono([
      { code: 'LINK_EXTERNO_NO_CHROME', severity: 'blocker', message: 'a', owner: 'tema/WordPress' },
      { code: 'LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO', severity: 'blocker', message: 'b', owner: 'funil' },
      { code: 'OUTRO', severity: 'blocker', message: 'c', owner: 'funil' },
    ]);
    expect(grupos.map((g) => g.dono)).toEqual(['funil', 'tema/WordPress']);
    expect(grupos[0].itens).toHaveLength(2);
  });

  it('dono vazio não vira "funil" por conveniência', () => {
    // ⚠️ Atribuir um dono que o backend não mandou faria a tela inventar
    // procedência e mandar o operador consertar onde não há o que consertar.
    const grupos = bloqueiosPorDono([
      { code: 'X', severity: 'blocker', message: 'm', owner: '' },
    ]);
    expect(grupos[0].dono).toBe('dono não atribuído');
    expect(textoDoDono('')).toBe('dono não atribuído');
  });
});

describe('o transporte', () => {
  it('confirmar manda APENAS a impressão — nunca o recibo candidato', async () => {
    // ⚠️ Se o corpo carregasse o candidato, o cliente escolheria o que vai ser
    // gravado e o hash viraria crachá: quem tem o texto entra.
    const chamadas: { caminho: string; init?: RequestInit }[] = [];
    const cliente = criarClienteDeReauditoria(async (caminho, init) => {
      chamadas.push({ caminho, init });
      return {} as never;
    });

    await cliente.provar(7, 2);
    await cliente.confirmar(7, 2, HASH);

    expect(chamadas[0].caminho).toBe('/api/publicacao/redator/runs/7/reauditar/2/provar');
    expect(chamadas[0].init?.body).toBeUndefined();
    expect(chamadas[1].caminho).toBe('/api/publicacao/redator/runs/7/reauditar/2/confirmar');
    expect(JSON.parse(String(chamadas[1].init?.body))).toEqual({ impressao_da_prova: HASH });
  });

  it('o conflito é reconhecido pela FORMA, não pelo texto da mensagem', () => {
    // Casar por mensagem é como um erro traduzido deixa de ser reconhecido.
    expect(ehConflitoDeProva({ detail: { proxima_acao: 'provar de novo' } })).toBe(true);
    expect(ehConflitoDeProva({ corpo: { detail: { proxima_acao: 'provar de novo' } } })).toBe(true);
    expect(ehConflitoDeProva({ detail: { erro: 'a página mudou' } })).toBe(false);
    expect(ehConflitoDeProva(new Error('a página mudou'))).toBe(false);
  });

  it('a mensagem sai de detail string, de detail.erro ou do Error', () => {
    expect(mensagemDoErro({ detail: 'sem URL' })).toBe('sem URL');
    expect(mensagemDoErro({ detail: { erro: 'HTTP 404' } })).toBe('HTTP 404');
    expect(mensagemDoErro(new Error('rede caiu'))).toBe('rede caiu');
    expect(mensagemDoErro({})).toContain('não concluiu');
  });
});

describe('o hash nunca aparece inteiro', () => {
  it('doze caracteres, e um travessão quando não há hash', () => {
    expect(curto(HASH)).toHaveLength(12);
    expect(curto(null)).toBe('—');
    expect(curto('')).toBe('—');
  });
});
