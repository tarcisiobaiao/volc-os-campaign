"""A porta HTTP da PRENSA — recebe uma spec, devolve PNG e recibo.

## O que esta camada é, e o que ela deliberadamente NÃO é

É um envelope. Ela não decide tipografia, não escolhe layout, não julga
qualidade: `motor/render.py` faz tudo isso e continua sendo a autoridade. Aqui
só existe o que um serviço precisa ter e um script de linha de comando não tem —
uma fronteira, um contrato de erro e um recibo.

Manter fino é a regra: no dia em que a PRENSA mudar de versão, este arquivo não
deveria precisar mudar junto. Se ele começar a interpretar a spec, virou um
segundo motor e a pergunta "o que gerou esta peça?" volta a ter duas respostas.

## Por que subprocesso e não import

`motor/render.py` resolve caminhos relativos ao PRÓPRIO arquivo
(`AQUI = Path(__file__).parent`, linha 12) e faz `sys.path.insert`. Importá-lo
de fora funcionaria hoje e quebraria em silêncio no dia em que alguém movesse
um asset — que é a classe de bug mais cara de todas. Rodar como o motor foi
escrito para rodar mantém a garantia de reprodutibilidade que ele oferece, e o
custo é um `fork` por peça, irrelevante ao lado de um screenshot de navegador.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

MOTOR = Path(__file__).parent / "motor"
#: Teto de tempo por peça. Um screenshot de navegador que passa disto está
#: travado, não lento — e um serviço que espera para sempre derruba a fila.
TIMEOUT_SEGUNDOS = 120

app = FastAPI(title="PRENSA", version="1.0.0")


class PedidoDeRender(BaseModel):
    """Uma spec resolvida da PRENSA e para onde escrever."""

    spec: dict = Field(description="post.spec resolvido, o mesmo que render.py lê do disco")
    sufixo: str = Field(default="", max_length=40)


@app.get("/saude")
def saude() -> dict:
    """Prova que o motor sobe E que o navegador existe.

    Responder "ok" sem conferir o Chrome deixaria o serviço passar no
    healthcheck e falhar em toda peça — que é pior que não subir.
    """
    try:
        versao = subprocess.run(
            ["google-chrome", "--version"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
    except Exception as erro:  # noqa: BLE001
        raise HTTPException(503, {"codigo": "PRENSA_SEM_NAVEGADOR", "detalhe": str(erro)[:200]})
    return {"status": "ok", "navegador": versao, "motor": str(MOTOR)}


@app.post("/render")
def render(pedido: PedidoDeRender) -> JSONResponse:
    """Roda a PRENSA sobre a spec e devolve os artefatos que ela escreveu.

    Os PNG voltam em base64 no corpo. Não é elegante, e é o certo aqui: o
    alternativo seria montar um volume compartilhado entre este container e
    quem chama, e volume compartilhado transforma uma fronteira de processo
    numa fronteira de sistema de arquivos — mais frágil e mais difícil de
    auditar do que bytes num corpo de resposta.
    """
    import base64

    with tempfile.TemporaryDirectory(dir=MOTOR / "out") as pasta:
        trabalho = Path(pasta)
        nome = f"api_{uuid.uuid4().hex[:12]}"
        arquivo = trabalho / f"{nome}.resolvido.json"
        arquivo.write_text(json.dumps(pedido.spec, ensure_ascii=False), encoding="utf-8")

        argumentos = [sys.executable, "render.py", str(arquivo.relative_to(MOTOR))]
        if pedido.sufixo:
            argumentos += ["--sufixo", pedido.sufixo]

        processo = subprocess.run(
            argumentos, cwd=MOTOR, capture_output=True, text=True,
            timeout=TIMEOUT_SEGUNDOS,
        )
        if processo.returncode != 0:
            # A saída do motor viaja INTEIRA no erro: a PRENSA falha fechado com
            # motivo nomeado, e engolir esse motivo transformaria um gate útil
            # num 500 mudo.
            raise HTTPException(422, {
                "codigo": "PRENSA_RECUSOU",
                "saida": processo.stdout[-4000:],
                "erro": processo.stderr[-4000:],
            })

        artefatos = []
        for produzido in sorted(trabalho.glob("*.png")):
            recibo = produzido.with_suffix(".veredito.json")
            pixelgate = produzido.with_suffix(".pixelgate.json")
            artefatos.append({
                "nome": produzido.name,
                "png_base64": base64.b64encode(produzido.read_bytes()).decode(),
                "veredito": json.loads(recibo.read_text()) if recibo.exists() else None,
                "pixelgate": json.loads(pixelgate.read_text()) if pixelgate.exists() else None,
            })

    if not artefatos:
        raise HTTPException(422, {
            "codigo": "PRENSA_SEM_ARTEFATO",
            "detalhe": "o motor terminou sem escrever PNG; a escada de gates é fail-closed",
            "saida": processo.stdout[-4000:],
        })
    return JSONResponse({"artefatos": artefatos, "saida": processo.stdout[-4000:]})
