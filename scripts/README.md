# Validador de fichas

`scripts/validar.py` percorre `tribunais/` e confere a estrutura das fichas. Usa só a biblioteca padrão do Python 3 e lê cada arquivo Markdown uma vez.

Rode a partir da raiz do repositório:

```bash
python scripts/validar.py
```

O status 0 significa que não há erros. Avisos não alteram o status. O status 1 indica erro de estrutura ou, com `--readme-check`, divergência do `README.md` da raiz.

## O que é ficha

É ficha o `.md` que contém uma linha neste formato:

```text
- **Identificador:** `id`
```

O `id` fica entre crases, sem outro texto na linha. READMEs e notas sem essa linha ficam fora da contagem de IDs. O validador ainda avisa quando um `.md` que não se chama README traz a linha `- **Identidade:**` e não traz identificador.

## Erros

Cada item abaixo encerra o processo com status 1:

- o mesmo identificador em mais de um ponto do repositório, inclusive duas vezes no mesmo arquivo
- ficha sem linha `- **Órgão:**`
- ficha sem linha `- **Espécie:**`
- ficha sem linha `- **Fonte:**` (`Fonte documental` e outros rótulos não substituem essa linha)
- identificador com espaço em branco ou letra maiúscula

## Avisos

Não mudam o status:

- ficha sem linha que comece com `- **Situação`
- valor dessa linha que contenha `não informad` ou `não confirmad`, sem distinguir maiúsculas
- arquivo que não é README, tem `- **Identidade:**` e não tem identificador

## Estatísticas

A saída traz:

- fichas, ocorrências de identificador e IDs únicos
- órgãos: o primeiro diretório sob `tribunais/` com ao menos uma ficha, e quantas fichas cada um tem
- linhas de página sem texto extraível, em qualquer `.md` sob `tribunais/`
- fichas com o título `## Revisão documental pendente`

Uma linha entra na contagem de páginas sem texto quando casa `Página( \d+)? sem texto extraível` ou começa com `[Transcrição retida`. Cada linha conta uma vez, mesmo que os dois critérios apareçam juntos.

## Opções

```bash
python scripts/validar.py --json estatisticas.json
python scripts/validar.py --readme-check
```

`--json` grava as estatísticas em UTF-8. Os números saem como inteiros. `por_orgao` vem em ordem alfabética da sigla. `readme.confere` é `true` quando a primeira ocorrência de `N IDs únicos em M órgãos` no `README.md` da raiz bate com a contagem. O milhar nesse enunciado usa ponto (`43.997`).

`--readme-check` transforma essa divergência, ou a ausência do enunciado, em status 1. Sem a opção, a comparação aparece no relatório e não muda o status.

O workflow [`.github/workflows/validar.yml`](../.github/workflows/validar.yml) roda `python scripts/validar.py` em pull request e no push da `main`, com Python 3.12. Não passa `--readme-check`. Erro já presente numa ficha faz o job falhar; o log traz a contagem por tipo e uma amostra de até 20 erros, alternando os tipos.
