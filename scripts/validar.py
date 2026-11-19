#!/usr/bin/env python3
"""Valida fichas Markdown em tribunais/. Lê cada arquivo uma vez."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

ID_PREFIX = "- **Identificador:** `"
ORGAO_PREFIX = "- **Órgão:**"
ESPECIE_PREFIX = "- **Espécie:**"
FONTE_PREFIX = "- **Fonte:**"
SITUACAO_PREFIX = "- **Situação"
IDENTIDADE_PREFIX = "- **Identidade:**"
REVISAO_PREFIX = "## Revisão documental pendente"
TRANSCRICAO_PREFIX = "[Transcrição retida"
PAGINA_MARCA = "Página"
PAGINA_ALVO = " sem texto extraível"

HEADLINE = re.compile(
    r"(?<![\d.])(\d{1,3}(?:\.\d{3})*)\s+IDs únicos em\s+"
    r"(\d{1,3}(?:\.\d{3})*)\s+órgãos"
)

ORDEM_ERROS = (
    "duplicata",
    "identificador_invalido",
    "sem_orgao",
    "sem_especie",
    "sem_fonte",
    "leitura",
)
ORDEM_AVISOS = (
    "sem_situacao",
    "situacao_incerta",
    "identidade_sem_identificador",
)
LIMITE_AMOSTRA = 20


def formato_br(numero: int) -> str:
    return f"{numero:,}".replace(",", ".")


def inteiro_br(texto: str) -> int:
    return int(texto.replace(".", ""))


def pagina_sem_texto(linha: str) -> bool:
    """Casa `Página( \\d+)? sem texto extraível` em qualquer ponto da linha."""
    inicio = 0
    tamanho = len(PAGINA_MARCA)
    while True:
        posicao = linha.find(PAGINA_MARCA, inicio)
        if posicao < 0:
            return False
        resto = linha[posicao + tamanho :]
        if resto.startswith(PAGINA_ALVO):
            return True
        if resto.startswith(" "):
            indice = 1
            while indice < len(resto) and resto[indice].isdigit():
                indice += 1
            if indice > 1 and resto[indice:].startswith(PAGINA_ALVO):
                return True
        inicio = posicao + tamanho


def situacao_incerta(valor: str) -> bool:
    texto = valor.casefold()
    return "não informad" in texto or "não confirmad" in texto


def descobrir_raiz() -> Path:
    cwd = Path.cwd()
    if (cwd / "tribunais").is_dir():
        return cwd
    candidato = Path(__file__).resolve().parent.parent
    if (candidato / "tribunais").is_dir():
        return candidato
    return cwd


def caminho_relativo(raiz: str, arquivo: str) -> str:
    return os.path.relpath(arquivo, raiz).replace(os.sep, "/")


def orgao_de(relativo: str) -> str | None:
    partes = relativo.split("/")
    if len(partes) > 2 and partes[0] == "tribunais":
        return partes[1]
    return None


def motivos_identificador(identificador: str) -> list[str]:
    motivos: list[str] = []
    if any(caractere.isspace() for caractere in identificador):
        motivos.append("espaço em branco")
    if any(caractere.isupper() for caractere in identificador):
        motivos.append("maiúscula")
    return motivos


class Relatorio:
    def __init__(self) -> None:
        self.fichas = 0
        self.fichas_sem_diretorio = 0
        self.por_orgao: Counter[str] = Counter()
        self.paginas_sem_texto = 0
        self.revisao_documental_pendente = 0
        self.markdown_lidos = 0
        self.ids: dict[str, list[tuple[str, int]]] = {}
        self.erros_por_tipo: Counter[str] = Counter()
        self.amostra_erros: dict[str, list[dict[str, str]]] = {}
        self.avisos_por_tipo: Counter[str] = Counter()
        self.amostra_avisos: dict[str, list[dict[str, str]]] = {}

    def registrar(self, grupo: str, tipo: str, arquivo: str, detalhe: str) -> None:
        if grupo == "erro":
            contagem = self.erros_por_tipo
            amostra = self.amostra_erros
        else:
            contagem = self.avisos_por_tipo
            amostra = self.amostra_avisos
        contagem[tipo] += 1
        balde = amostra.setdefault(tipo, [])
        if len(balde) < LIMITE_AMOSTRA:
            balde.append({"tipo": tipo, "arquivo": arquivo, "detalhe": detalhe})


def amostra_alternada(
    baldes: dict[str, list[dict[str, str]]], ordem: tuple[str, ...]
) -> list[dict[str, str]]:
    tipos = [tipo for tipo in ordem if baldes.get(tipo)]
    for tipo in sorted(baldes):
        if tipo not in tipos and baldes[tipo]:
            tipos.append(tipo)
    saida: list[dict[str, str]] = []
    indice = 0
    while len(saida) < LIMITE_AMOSTRA:
        avancou = False
        for tipo in tipos:
            itens = baldes[tipo]
            if indice < len(itens):
                saida.append(itens[indice])
                avancou = True
                if len(saida) >= LIMITE_AMOSTRA:
                    break
        if not avancou:
            break
        indice += 1
    return saida


def listar_markdown(tribunais: str) -> list[str]:
    arquivos: list[str] = []
    for diretorio, subdirs, nomes in os.walk(tribunais):
        subdirs.sort()
        for nome in sorted(nomes):
            if nome.endswith(".md"):
                arquivos.append(os.path.join(diretorio, nome))
    return arquivos


def varrer(raiz: Path) -> Relatorio:
    relatorio = Relatorio()
    raiz_txt = str(raiz)
    tribunais = os.path.join(raiz_txt, "tribunais")
    for arquivo in listar_markdown(tribunais):
        relatorio.markdown_lidos += 1
        relativo = caminho_relativo(raiz_txt, arquivo)
        try:
            with open(arquivo, "r", encoding="utf-8") as handle:
                texto = handle.read()
        except UnicodeDecodeError as exc:
            relatorio.registrar(
                "erro",
                "leitura",
                relativo,
                f"não é UTF-8 ({exc.reason})",
            )
            continue
        analisar_arquivo(relatorio, relativo, texto, os.path.basename(arquivo))
    registrar_duplicatas(relatorio)
    return relatorio


def analisar_arquivo(
    relatorio: Relatorio, relativo: str, texto: str, nome: str
) -> None:
    identificadores: list[tuple[str, int]] = []
    tem_orgao = False
    tem_especie = False
    tem_fonte = False
    tem_situacao = False
    incerta = False
    tem_identidade = False
    tem_revisao = False
    for numero, bruta in enumerate(texto.splitlines(), 1):
        linha = bruta.rstrip()
        if linha.startswith(TRANSCRICAO_PREFIX) or pagina_sem_texto(linha):
            relatorio.paginas_sem_texto += 1
        campo = linha.lstrip()
        if (
            campo.startswith(ID_PREFIX)
            and campo.endswith("`")
            and campo.count("`") == 2
        ):
            identificadores.append((campo[len(ID_PREFIX) : -1], numero))
        elif campo.startswith(ORGAO_PREFIX):
            tem_orgao = True
        elif campo.startswith(ESPECIE_PREFIX):
            tem_especie = True
        elif campo.startswith(FONTE_PREFIX):
            tem_fonte = True
        elif campo.startswith(SITUACAO_PREFIX):
            tem_situacao = True
            _rotulo, _sep, valor = campo.partition(":**")
            if situacao_incerta(valor):
                incerta = True
        elif campo.startswith(IDENTIDADE_PREFIX):
            tem_identidade = True
        if campo.startswith(REVISAO_PREFIX):
            tem_revisao = True

    if not identificadores:
        if tem_identidade and nome.lower() != "readme.md":
            relatorio.registrar(
                "aviso",
                "identidade_sem_identificador",
                relativo,
                "tem `- **Identidade:**` e não tem identificador",
            )
        return

    relatorio.fichas += 1
    orgao = orgao_de(relativo)
    if orgao is None:
        relatorio.fichas_sem_diretorio += 1
    else:
        relatorio.por_orgao[orgao] += 1
    if tem_revisao:
        relatorio.revisao_documental_pendente += 1
    if not tem_orgao:
        relatorio.registrar(
            "erro",
            "sem_orgao",
            relativo,
            "falta linha `- **Órgão:**`",
        )
    if not tem_especie:
        relatorio.registrar(
            "erro",
            "sem_especie",
            relativo,
            "falta linha `- **Espécie:**`",
        )
    if not tem_fonte:
        relatorio.registrar(
            "erro",
            "sem_fonte",
            relativo,
            "falta linha `- **Fonte:**`",
        )
    if not tem_situacao:
        relatorio.registrar(
            "aviso",
            "sem_situacao",
            relativo,
            "falta linha que comece com `- **Situação`",
        )
    elif incerta:
        relatorio.registrar(
            "aviso",
            "situacao_incerta",
            relativo,
            "Situação casa com “não informad” ou “não confirmad”",
        )
    for identificador, numero in identificadores:
        relatorio.ids.setdefault(identificador, []).append((relativo, numero))
        motivos = motivos_identificador(identificador)
        if motivos:
            relatorio.registrar(
                "erro",
                "identificador_invalido",
                f"{relativo}:{numero}",
                f"`{identificador}` tem {' e '.join(motivos)}",
            )


def registrar_duplicatas(relatorio: Relatorio) -> None:
    for identificador in sorted(relatorio.ids):
        locais = sorted(relatorio.ids[identificador])
        if len(locais) < 2:
            continue
        mostrados = [f"{caminho}:{numero}" for caminho, numero in locais[:8]]
        extra = len(locais) - len(mostrados)
        texto = ", ".join(mostrados)
        if extra:
            texto += f" e mais {extra}"
        relatorio.registrar(
            "erro",
            "duplicata",
            mostrados[0],
            f"`{identificador}` aparece {len(locais)} vezes ({texto})",
        )


def ler_enunciado(raiz: Path) -> tuple[int | None, int | None]:
    caminho = raiz / "README.md"
    if not caminho.is_file():
        return None, None
    texto = caminho.read_text(encoding="utf-8")
    texto = texto.replace("\u00a0", " ").replace("\u202f", " ")
    achado = HEADLINE.search(texto)
    if achado is None:
        return None, None
    return inteiro_br(achado.group(1)), inteiro_br(achado.group(2))


def montar_stats(
    relatorio: Relatorio,
    enunciado: tuple[int | None, int | None],
    tempo: float,
    amostra: list[dict[str, str]],
) -> dict[str, object]:
    ids_unicos = len(relatorio.ids)
    ocorrencias = sum(len(locais) for locais in relatorio.ids.values())
    declarado_ids, declarado_orgaos = enunciado
    if declarado_ids is None or declarado_orgaos is None:
        confere: bool | None = None
    else:
        confere = (
            declarado_ids == ids_unicos
            and declarado_orgaos == len(relatorio.por_orgao)
        )
    return {
        "fichas": relatorio.fichas,
        "ids_unicos": ids_unicos,
        "ocorrencias_identificador": ocorrencias,
        "orgaos": len(relatorio.por_orgao),
        "fichas_sem_diretorio_de_orgao": relatorio.fichas_sem_diretorio,
        "por_orgao": dict(sorted(relatorio.por_orgao.items())),
        "paginas_sem_texto": relatorio.paginas_sem_texto,
        "revisao_documental_pendente": relatorio.revisao_documental_pendente,
        "markdown_lidos": relatorio.markdown_lidos,
        "identidade_sem_identificador": relatorio.avisos_por_tipo[
            "identidade_sem_identificador"
        ],
        "erros_total": sum(relatorio.erros_por_tipo.values()),
        "erros_por_tipo": dict(sorted(relatorio.erros_por_tipo.items())),
        "avisos_total": sum(relatorio.avisos_por_tipo.values()),
        "avisos_por_tipo": dict(sorted(relatorio.avisos_por_tipo.items())),
        "amostra_erros": amostra,
        "readme": {
            "ids": declarado_ids,
            "orgaos": declarado_orgaos,
            "confere": confere,
        },
        "tempo_segundos": round(tempo, 3),
    }


def imprimir_contagens(titulo: str, contagem: Counter[str], ordem: tuple[str, ...]) -> None:
    print(f"{titulo}: {formato_br(sum(contagem.values()))}")
    tipos = [tipo for tipo in ordem if contagem[tipo]]
    for tipo in sorted(contagem):
        if tipo not in tipos:
            tipos.append(tipo)
    for tipo in tipos:
        print(f"  {tipo}: {formato_br(contagem[tipo])}")


def imprimir_relatorio(
    relatorio: Relatorio,
    stats: dict[str, object],
    amostra: list[dict[str, str]],
    checar_readme: bool,
) -> None:
    ids_unicos = int(stats["ids_unicos"])
    orgaos = int(stats["orgaos"])
    print(f"Fichas: {formato_br(relatorio.fichas)}")
    print(f"IDs únicos: {formato_br(ids_unicos)}")
    print(
        "Ocorrências de identificador: "
        f"{formato_br(int(stats['ocorrencias_identificador']))}"
    )
    print(f"Órgãos com ficha: {formato_br(orgaos)}")
    if relatorio.fichas_sem_diretorio:
        print(
            "Fichas fora de um diretório de órgão: "
            f"{formato_br(relatorio.fichas_sem_diretorio)}"
        )
    print(f"Páginas sem texto extraível: {formato_br(relatorio.paginas_sem_texto)}")
    print(
        "Fichas com revisão documental pendente: "
        f"{formato_br(relatorio.revisao_documental_pendente)}"
    )
    print(f"Markdown lidos: {formato_br(relatorio.markdown_lidos)}")
    print()
    readme = stats["readme"]
    assert isinstance(readme, dict)
    if readme["ids"] is None:
        print("README.md: não achei o enunciado “N IDs únicos em M órgãos”.")
    else:
        print(
            "README.md declara "
            f"{formato_br(int(readme['ids']))} IDs únicos em "
            f"{formato_br(int(readme['orgaos']))} órgãos."
        )
        print(
            "Contagem: "
            f"{formato_br(ids_unicos)} IDs únicos em {formato_br(orgaos)} órgãos."
        )
        if readme["confere"]:
            print("Conferência do README: ok.")
        elif checar_readme:
            print("Conferência do README: divergente.")
        else:
            print("Conferência do README: divergente (sem --readme-check).")
    print()
    imprimir_contagens("Erros", relatorio.erros_por_tipo, ORDEM_ERROS)
    if amostra:
        print()
        print(f"Amostra de erros ({len(amostra)} de {formato_br(int(stats['erros_total']))}):")
        for item in amostra:
            print(f"  [{item['tipo']}] {item['arquivo']}: {item['detalhe']}")
    print()
    imprimir_contagens("Avisos", relatorio.avisos_por_tipo, ORDEM_AVISOS)
    print()
    print("Por órgão:")
    if not relatorio.por_orgao:
        print("  (nenhum)")
    largura = max((len(nome) for nome in relatorio.por_orgao), default=0)
    for nome, quantidade in sorted(
        relatorio.por_orgao.items(), key=lambda item: (-item[1], item[0])
    ):
        print(f"  {nome:<{largura}}  {formato_br(quantidade)}")
    print()
    print(f"Tempo: {stats['tempo_segundos']} s")


def analisar_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida as fichas Markdown em tribunais/."
    )
    parser.add_argument(
        "--json",
        metavar="ARQUIVO",
        help="Grava as estatísticas neste arquivo JSON.",
    )
    parser.add_argument(
        "--readme-check",
        action="store_true",
        help="Falha se o README.md da raiz divergir da contagem.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = analisar_args(argv)
    inicio = time.perf_counter()
    raiz = descobrir_raiz()
    if not (raiz / "tribunais").is_dir():
        print(f"Não achei tribunais/ a partir de {raiz}.", file=sys.stderr)
        return 1
    relatorio = varrer(raiz)
    fechamento = (
        sum(relatorio.por_orgao.values()) + relatorio.fichas_sem_diretorio
    )
    if fechamento != relatorio.fichas:
        print(
            "Contagem interna de órgãos não fecha com as fichas.",
            file=sys.stderr,
        )
        return 1
    enunciado = ler_enunciado(raiz)
    amostra = amostra_alternada(relatorio.amostra_erros, ORDEM_ERROS)
    stats = montar_stats(
        relatorio, enunciado, time.perf_counter() - inicio, amostra
    )
    imprimir_relatorio(relatorio, stats, amostra, args.readme_check)
    if args.json:
        try:
            Path(args.json).write_text(
                json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"Não gravei o JSON: {exc}", file=sys.stderr)
            return 1
    readme = stats["readme"]
    assert isinstance(readme, dict)
    readme_falha = args.readme_check and readme["confere"] is not True
    if int(stats["erros_total"]) or readme_falha:
        print()
        print("Resultado: FALHA")
        return 1
    print()
    print("Resultado: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
