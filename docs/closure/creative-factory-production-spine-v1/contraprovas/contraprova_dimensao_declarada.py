"""Contraprova: o gate de dimensao do operario julga a DECLARACAO do motor.

`bytes_` e `sha256` ja foram movidos para a medida do disco por este exato
motivo — a dimensao ficou para tras. Um motor que grava 64x64 e declara
1200x628 chega a `rendered`, com recibo, apontando para um PNG que nao serve a
canal nenhum.
"""
import hashlib, sys, tempfile
from pathlib import Path
sys.path.insert(0, "backend"); sys.path.insert(0, ".")
from app.criativo.bancada.contrato import Artefato, Encomenda, SaidaPedida
from app.criativo.bancada.deposito import DepositoDeTrabalhos
from app.criativo.bancada.operario import Operario
from volc_ads.criativo.adaptadores.medir_imagem import medir

PNG_64 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000400000004008060000008ffd"
    "5b6c0000001b4944415478da63fcffff3f0326c8288a2c00d1a20e00c8bd0a"
    "a1cbbb2f4f0000000049454e44ae426082"
)


class MotorQueMenteNaDimensao:
    slug, versao = "mentiroso", "1"

    def versoes_congeladas(self): return {"motor": "1"}

    def produzir(self, encomenda, dir_trabalho):
        p = Path(dir_trabalho) / "peca.png"
        p.write_bytes(PNG_64)                     # 64x64 de verdade
        return (Artefato("1x1", str(p), "image/png", len(PNG_64),
                         hashlib.sha256(PNG_64).hexdigest(),
                         1200, 628),)             # declara 1200x628


raiz = Path(tempfile.mkdtemp())
d = DepositoDeTrabalhos(raiz / "fila.db")
op = Operario(d, {"mentiroso": MotorQueMenteNaDimensao()}, raiz / "t", nome="op")
d.enfileirar(Encomenda(
    receita_id="r", tenant_id="t", motor_slug="mentiroso", modo_slug="m",
    finalidade_slug="f", seed=1,
    saidas=(SaidaPedida("1x1", 1200, 628, "imagem", "image/png"),)))
final = op.trabalhar_uma_vez()

print("estado:", final.estado.value)
if final.recibo:
    gate = [v for v in final.recibo["validacoes"] if v["gate"] == "dimensao"]
    for g in gate:
        print("gate dimensao:", g["resultado"], g["detalhe"])
    caminho = Path(final.recibo["artefatos"][0]["caminho"])
    print("medida real  :", medir(caminho.read_bytes()))
    print("VEREDITO: o trabalho concluiu com recibo apontando para PNG que nao serve a canal nenhum"
          if final.estado.value == "rendered" else "recusou (correto)")
else:
    print("falha:", final.falha)
