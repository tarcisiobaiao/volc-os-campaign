/**
 * ERROS DO CONTRATO → FRASE HUMANA, decidida pela `codigo`.
 *
 * E o cliente: o `{"detail": {codigo, mensagem, detalhe}}` do FastAPI chega à
 * tela como `ErroDaGestao` com a `codigo` intacta — é dela que a tela decide.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ErroDaGestao, gestaoApi, trocarFonteDeToken } from '../../gestaoApi';
import { erroLegivel } from '../erros';

const erro = (codigo: string, status = 409, detalhe?: unknown) =>
  new ErroDaGestao(`mensagem do servidor para ${codigo}`, status, { codigo, mensagem: 'x', detalhe });

describe('os 409 do contrato viram frase de operação', () => {
  it('regra_ausente', () => {
    expect(erroLegivel(erro('regra_ausente')).titulo).toBe('Não há regra de gestão publicada para esta conta.');
  });
  it('regra_exige_delta', () => {
    expect(erroLegivel(erro('regra_exige_delta')).titulo).toBe('Este tipo de ação ainda não é aceito pelo ledger.');
  });
  it('regra_exige_delta mostra o que a regra aceita sem delta; teto_sem_delta mostra o teto', () => {
    expect(
      erroLegivel(erro('regra_exige_delta', 409, { operacao: 'status', operacoes_sem_delta_da_regra: ['negativa.keyword'] }))
        .proximoPasso,
    ).toMatch(/negativa\.keyword/);
    const t = erroLegivel(erro('teto_sem_delta', 409, { teto: { max_itens: 50 }, motivo: '60 itens > 50' }));
    expect(t.titulo).toMatch(/teto/);
    expect(t.proximoPasso).toMatch(/60 itens > 50/);
  });
  it('antes_divergiu diz que nada foi enviado e quais campos mudaram', () => {
    const e = erroLegivel(erro('antes_divergiu', 409, { campos: ['verba_diaria_micros'] }));
    expect(e.titulo).toMatch(/Nada foi enviado/);
    expect(e.proximoPasso).toMatch(/verba_diaria_micros/);
  });
  it('campanha_nao_importada sugere importar', () => {
    expect(erroLegivel(erro('campanha_nao_importada')).sugere).toBe('importar');
  });
  it('verificar_antes e sem_resposta sugerem verificar; sem_resposta é incerto', () => {
    expect(erroLegivel(erro('verificar_antes')).sugere).toBe('verificar');
    const s = erroLegivel(erro('sem_resposta', 503));
    expect(s.incerto).toBe(true);
    expect(s.titulo).toMatch(/PODE ter mudado/);
  });
  it('evidencia_insuficiente lista os faltantes; em_carencia diz até quando', () => {
    expect(erroLegivel(erro('evidencia_insuficiente', 409, { faltantes: ['impressoes'] })).proximoPasso).toMatch(/impressoes/);
    expect(erroLegivel(erro('em_carencia', 409, { ate: '2026-10-09T10:00:00Z' })).proximoPasso).toMatch(/2026-10-09/);
  });
  it('todos os 409 da tabela têm frase própria (nenhum cai na mensagem crua)', () => {
    const codigos = [
      'regra_ausente', 'campanha_nao_importada', 'evidencia_insuficiente', 'regra_exige_delta',
      'teto_sem_delta', 'limite_pct', 'limite_absoluto', 'teto_orcamento', 'moeda_do_teto', 'antes_velho',
      'diff_divergente', 'ja_decidida', 'proposta_expirada', 'exige_aprovacao_humana',
      'em_carencia', 'antes_divergiu', 'verificar_antes', 'aplicacao_em_andamento',
      'escrita_bloqueada', 'nada_a_reverter', 'irreversivel', 'estado_mudou_depois',
      'reversao_ja_existe', 'banco_recusou', 'estado_invalido', 'campanha_removida',
      'regra_invalida', 'plataforma',
    ];
    for (const c of codigos) {
      const e = erroLegivel(erro(c));
      expect(e.titulo, c).not.toMatch(/mensagem do servidor/);
      expect(e.codigo).toBe(c);
      expect(e.tecnica).toBe(`mensagem do servidor para ${c}`);
    }
  });
  it('código desconhecido cai na mensagem do servidor, e 403 sem código é papel', () => {
    expect(erroLegivel(erro('codigo_novo', 409)).titulo).toBe('mensagem do servidor para codigo_novo');
    expect(erroLegivel(new ErroDaGestao('Esta operação exige papel administrativo.', 403)).titulo).toMatch(/administrativo/);
  });
});

describe('o cliente preserva a codigo do contrato', () => {
  let restaurar: () => void = () => {};
  afterEach(() => {
    restaurar();
    vi.unstubAllGlobals();
  });

  it('409 com detail objeto vira ErroDaGestao com codigo e detalhe', async () => {
    restaurar = trocarFonteDeToken(async () => 'token-de-teste');
    const fetchFalso = vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { codigo: 'regra_ausente', mensagem: 'sem regra', detalhe: { regra_chave: 'gestao_manual_google' } } }),
        { status: 409, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetchFalso);
    const p = gestaoApi.propor({
      customer_id: '5478096539',
      acao: { tipo: 'orcamento.diario', campaign_id: '24278665189', amount_micros: 33_000_000 },
      motivo: 'teste',
    });
    await expect(p).rejects.toMatchObject({ status: 409, codigo: 'regra_ausente', detalhe: { regra_chave: 'gestao_manual_google' } });
    const [url, init] = fetchFalso.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/api\/trafego\/gestao\/propostas$/);
    expect(init.method).toBe('POST');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer token-de-teste');
    expect(JSON.parse(String(init.body)).acao.tipo).toBe('orcamento.diario');
  });

  it('sem sessão, falha antes da rede', async () => {
    restaurar = trocarFonteDeToken(async () => null);
    const fetchFalso = vi.fn();
    vi.stubGlobal('fetch', fetchFalso);
    await expect(gestaoApi.propostas('5478096539')).rejects.toMatchObject({ status: 401 });
    expect(fetchFalso).not.toHaveBeenCalled();
  });
});
