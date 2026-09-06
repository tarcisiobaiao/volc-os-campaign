"""Os detectores de pixel — e a razão de nenhum estar registrado hoje.

## O inventário, feito antes de escrever qualquer coisa

Este servidor NÃO tem motor de OCR nem de visão. Medido, não suposto:

- o venv traz `pillow` e nada mais do gênero — sem `pytesseract`, `easyocr`,
  `opencv`, `rapidocr`, `paddleocr`, `torch`, `transformers`, `ultralytics`;
- `app/llm/` (Gemini e OpenAI) é TEXT-ONLY: o contrato é
  `complete(system, user) -> str` e o payload carrega apenas `parts[{text}]`,
  sem `inline_data`;
- `visual_proof` valida URL, host e metadados de captura — não lê pixel;
- `landing_policy` e `publisher_quality` são léxico e HTTP;
- o Pillow que existe é usado para MEDIR dimensão e para DESENHAR texto
  (`bancada/adaptadores/tipografico.py`), nunca para ler.

## O que este pacote faz, então

Ele traz o adaptador ESCRITO e PRONTO para o motor que falta, e uma função de
registro que só registra quando o motor existe de verdade. Nada aqui inventa
capacidade: se o import falhar, ninguém é registrado, o portão continua
devolvendo `GATE_UNAVAILABLE` e a mídia paga continua bloqueada.

⚠️ Essa é a parte que importa. A tentação seria registrar um detector que
sempre devolve "não vi nada" — e isso transformaria "não consegui olhar" em
"olhei e está limpo", que é exatamente a confusão que deixou uma peça com marca
de banco ir ao ar. Um detector mudo é pior que detector nenhum, porque some com
o `ERROR` do recibo.
"""
from .ocr_tesseract import DetectorOcrTesseract, registrar_detectores_disponiveis

__all__ = ["DetectorOcrTesseract", "registrar_detectores_disponiveis"]
