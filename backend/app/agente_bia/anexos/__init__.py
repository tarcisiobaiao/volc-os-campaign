"""Anexos da Bia: imagens (visão nativa do Hermes) e documentos (texto extraído).

Medido no Hermes v0.18.0 instalado (15/10/2026, `api_server._normalize_multimodal_content`):

- imagem entra como parte `image_url` com `data:image/...;base64,` — nenhuma
  URL externa é buscada;
- `file`/`input_file` são RECUSADOS (`unsupported_content_type`).

Por isso PDF, TXT, CSV e DOCX viram texto NO SERVIDOR, no momento do upload
(um PDF sem camada de texto é recusado antes do envio, nunca "visto"), e o
texto entra na mensagem como bloco de DADO não confiável, delimitado por nonce.

    dominio.py   tipos aceitos, assinatura pelos bytes, limites, nome normalizado
    extracao.py  saneamento de imagem (sem EXIF) e extração de texto
    armazem.py   armazenamento privado no host do backend: dono, cota, retenção
"""
