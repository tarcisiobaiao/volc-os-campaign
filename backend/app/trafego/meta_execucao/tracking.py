"""Public presentation of the exact tracking emitted by the compiler. No IO."""
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from . import compilador
from .contrato import ErroDeNascimentoMeta, _url_https


def apresentar_tracking(destino: str = "") -> dict:
    template = compilador.TRACKING_GAM_ADSET_ID
    erro = None
    previa = None
    if destino.strip():
        try:
            partes = urlsplit(_url_https(destino))
            previa = urlunsplit(partes._replace(query="&".join(filter(None, [partes.query, template]))))
        except ErroDeNascimentoMeta as exc:
            erro = {"codigo": exc.codigo, "mensagem": str(exc)}
        except ValueError:
            erro = {"codigo": "META_DESTINATION_INVALID", "mensagem": "Confira a URL HTTPS do destino."}
    return {
        "template": template,
        "parametros": [{"nome": k, "valor": v} for k, v in parse_qsl(template)],
        "revenue_join": compilador.JOIN_DE_RECEITA,
        "grao": "ADSET",
        "campo_api": "AdCreative.url_tags",
        "previa_url": previa,
        "destino_valido": previa is not None,
        "erro": erro,
        "prova": "TEMPLATE_LOCAL",
        "efeito_externo": "NENHUM",
    }
