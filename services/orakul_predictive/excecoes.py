"""Falhas explícitas do Predictive Core V1. Nenhuma vira zero silencioso."""

from __future__ import annotations


class OrakulPredictiveError(Exception):
    """Erro de domínio do núcleo preditivo."""


class VazamentoDeFuturo(OrakulPredictiveError):
    """Feature, alvo ou split usa informação posterior ao as-of."""


class DatasetInsuficiente(OrakulPredictiveError):
    """Amostra menor que o mínimo; não é vitória nem promoção."""


class ContratoInvalido(OrakulPredictiveError):
    """Registro sem procedência, unidade, fuso ou identidade canônica."""


class DefinicaoDeAlvoIncompativel(OrakulPredictiveError):
    """Tentativa de comparar modelos ou outcomes com alvos diferentes."""


class PopulacaoIncompativel(DefinicaoDeAlvoIncompativel):
    """Comparação usa conta, janela, cenário ou pair_ids diferentes."""


class ConflitoDeIdempotencia(ContratoInvalido):
    """A mesma identidade idempotente recebeu um payload diferente."""


class MoedaOuFusoIncompativel(OrakulPredictiveError):
    """Mistura de unidade monetária ou timezone."""


class PromocaoRecusada(OrakulPredictiveError):
    """Challenger não reúne evidência para sequer propor promoção."""


class IsolamentoViolado(OrakulPredictiveError):
    """Tentativa de rede, .env, Supabase ou mutação externa."""
