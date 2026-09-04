# Gates

## Prova focal ampliada

```text
pytest:
  424 passed
  0 failed
```

O recorte cobre builders/planos de Display, Demand Gen e PMax, o novo contrato
anti-expansão de URL, registros de prova/criação, manifesto e portões do Hub,
fronteira HTTP Demand Gen/Display, capacidades e plano persistido.

## Higiene

- `git diff --check`: verde.
- JSONs do pacote de fechamento: válidos.
- `scripts/verificar_segredos.py`: nenhum padrão forte.
- Gemini final: modelo efetivo `gemini-3.1-pro-preview`, zero tool calls.

## Não executado

- Suíte monolítica do repositório: fora do corte 80/20 desta retomada.
- `validate_only` Google Ads real: não autorizado e desnecessário para a
  adjudicação do checkpoint.
- Qualquer mutate externo: não executado.
