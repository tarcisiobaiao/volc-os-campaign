"""On-device Apple Vision OCR. No image leaves the Mac.

Only texto_na_imagem is declared: text recognition cannot identify an unlettered
logo. This detector never claims marca_visual or complete paid-media clearance.
The binary is compiled from the bundled, hash-addressed Objective-C source into a
private temporary directory. No user-provided executable/path is accepted.
"""
from __future__ import annotations

import hashlib
import io
import json
import platform
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from ..inspecao import CAPACIDADE_TEXTO_NA_IMAGEM, LeituraDePixel


class OcrAppleIndisponivel(RuntimeError):
    pass


class DetectorOcrApple:
    nome = "ocr.apple_vision"
    capacidades = (CAPACIDADE_TEXTO_NA_IMAGEM,)
    deterministico = False

    def __init__(self, binary: Path, version: str):
        self._binary = binary
        self.versao = version

    @classmethod
    def se_disponivel(cls):
        if platform.system() != "Darwin" or not Path("/usr/bin/clang").is_file():
            return None
        source = Path(__file__).with_suffix(".m")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        directory = Path(tempfile.mkdtemp(prefix="volc-ocr-apple-"))
        binary = directory / "ocr"
        try:
            subprocess.run(["/usr/bin/clang", "-fobjc-arc", "-framework", "Foundation",
                            "-framework", "Vision", str(source), "-o", str(binary)],
                           capture_output=True, timeout=45, check=True)
        except (OSError, subprocess.SubprocessError):
            return None
        return cls(binary, f"macOS-{platform.mac_ver()[0]}:source-{digest}")

    def inspecionar(self, bytes_da_peca: bytes, *, mime: str) -> LeituraDePixel:
        if mime not in {"image/jpeg", "image/png", "image/webp"} or not bytes_da_peca or len(bytes_da_peca) > 12 * 1024 * 1024:
            raise OcrAppleIndisponivel("Formato ou tamanho de imagem inválido para OCR.")
        try:
            with Image.open(io.BytesIO(bytes_da_peca)) as image:
                if image.width * image.height > 30_000_000 or Image.MIME.get(image.format) != mime:
                    raise ValueError("image dimensions or mime mismatch")
                image.verify()
            process = subprocess.run([str(self._binary)], input=bytes_da_peca,
                                     capture_output=True, timeout=30, check=True)
            result = json.loads(process.stdout)
            if result.get("completed") is not True or not isinstance(result.get("text"), str):
                raise ValueError("incomplete OCR")
            return LeituraDePixel(texto=result["text"], rotulos=())
        except (OSError, ValueError, subprocess.SubprocessError):
            raise OcrAppleIndisponivel("A inspeção local não concluiu a leitura da imagem.") from None


def registrar_ocr_apple() -> bool:
    from ..inspecao import detectores_de_pixel_registrados, registrar_detector_de_pixel
    if any(d.nome == DetectorOcrApple.nome for d in detectores_de_pixel_registrados()):
        return True
    detector = DetectorOcrApple.se_disponivel()
    if detector is None:
        return False
    registrar_detector_de_pixel(detector)
    return True
