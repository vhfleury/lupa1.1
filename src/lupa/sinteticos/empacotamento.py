"""Empacota o mesmo conteúdo nos três cenários e grava os gabaritos.

- ``zip_por_peca``: ZIP com um PDF por peça, nomes ``NNN_tipo_AAAA-MM-DD.pdf``.
- ``pdf_indice``: PDF único com páginas de índice de movimentações no início e um bookmark por
  peça (apontando para a folha física, já deslocada pelo índice).
- ``pdf_liso``: PDF único, sem bookmarks nem índice.

O conteúdo do gabarito (peças, folhas, eventos, resultado esperado) é idêntico nos três; mudam
``processo.cenario``, ``processo.diagnostico_esperado`` e ``arquivos``.
"""

import zipfile
from dataclasses import dataclass
from pathlib import Path

import fitz

from lupa.sinteticos.gabarito import (
    DIAGNOSTICO_ESPERADO,
    ArquivoGabarito,
    Cenario,
    Gabarito,
    PecaGabarito,
    ProcessoGabarito,
    VetorInjecao,
)
from lupa.sinteticos.gerador import Conteudo
from lupa.sinteticos.injecao import INJECOES, xmp_com_instrucao
from lupa.sinteticos.paginacao import ALTURA, FONTE, FONTE_NEGRITO, LARGURA, MARGEM_ESQUERDA

LINHAS_POR_INDICE = 40
NOME_PDF = "autos.pdf"
NOME_ZIP = "autos.zip"
NOME_GABARITO = "gabarito.json"


@dataclass(frozen=True)
class ArquivoGerado:
    """Arquivo escrito em disco.

    Attributes:
        cenario: Cenário.
        caminho: Caminho do arquivo de autos.
        gabarito: Caminho do gabarito.
        bytes: Tamanho do arquivo de autos.
    """

    cenario: Cenario
    caminho: Path
    gabarito: Path
    bytes: int


def nome_peca(peca: PecaGabarito) -> str:
    """Nome do PDF da peça no ZIP.

    Args:
        peca: Peça do gabarito.

    Returns:
        ``NNN_tipo_AAAA-MM-DD.pdf``.
    """
    return f"{peca.indice:03d}_{peca.tipo.value}_{peca.data.isoformat()}.pdf"


def _salvar(documento: fitz.Document, conteudo: Conteudo) -> bytes:
    if VetorInjecao.METADADO_XMP in conteudo.roteiro.configuracao.injecoes:
        documento.set_xml_metadata(xmp_com_instrucao(INJECOES[VetorInjecao.METADADO_XMP].texto))
    documento.set_metadata({"producer": "lupa-sinteticos", "title": "Autos sintéticos"})
    return bytes(documento.tobytes(garbage=3, deflate=True))


def linhas_indice(conteudo: Conteudo, deslocamento: int) -> list[str]:
    """Linhas do índice de movimentações.

    Args:
        conteudo: Conteúdo gerado.
        deslocamento: Páginas de índice antes do conteúdo.

    Returns:
        Uma linha por peça, com número, data, título e folha física.
    """
    return [
        f"Movimentação {p.indice:03d} - {p.data.strftime('%d/%m/%Y')} - {p.titulo} - "
        f"fls. {p.pagina_inicial + deslocamento}"
        for p in conteudo.pecas
    ]


def _paginas_indice(documento: fitz.Document, conteudo: Conteudo) -> int:
    quantidade = -(-len(conteudo.pecas) // LINHAS_POR_INDICE)
    linhas = linhas_indice(conteudo, quantidade)
    for n in range(quantidade):
        pagina = documento.new_page(width=LARGURA, height=ALTURA)
        escritor = fitz.TextWriter(pagina.rect)
        escritor.append(
            (MARGEM_ESQUERDA, 60), "ÍNDICE DE MOVIMENTAÇÕES", font=FONTE_NEGRITO, fontsize=13
        )
        escritor.append(
            (MARGEM_ESQUERDA, 78), f"Processo nº {conteudo.numero}", font=FONTE, fontsize=10
        )
        bloco = linhas[n * LINHAS_POR_INDICE : (n + 1) * LINHAS_POR_INDICE]
        for i, linha in enumerate(bloco):
            escritor.append((MARGEM_ESQUERDA, 104 + 17 * i), linha, font=FONTE, fontsize=9.5)
        escritor.write_text(pagina)
    return quantidade


def _gabarito(conteudo: Conteudo, cenario: Cenario, arquivos: list[ArquivoGabarito]) -> Gabarito:
    processo = ProcessoGabarito(
        numero_cnj=conteudo.numero,
        cenario=cenario,
        diagnostico_esperado=DIAGNOSTICO_ESPERADO[cenario],
        semente=conteudo.roteiro.configuracao.semente,
        data_referencia=conteudo.referencia,
    )
    return Gabarito(
        processo=processo, pecas=conteudo.pecas, paginas=conteudo.paginas,
        eventos=conteudo.eventos, resultado_esperado=conteudo.resultado_esperado,
        arquivos=tuple(arquivos), injecoes=conteudo.injecoes,
    )  # fmt: skip


def _gravar(
    destino: Path, nome: str, dados: bytes, gabarito: Gabarito, cenario: Cenario
) -> ArquivoGerado:
    pasta = destino / cenario.value
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / nome
    caminho.write_bytes(dados)
    caminho_gabarito = pasta / NOME_GABARITO
    caminho_gabarito.write_text(gabarito.model_dump_json(indent=1), encoding="utf-8")
    return ArquivoGerado(cenario, caminho, caminho_gabarito, len(dados))


def exportar_zip(conteudo: Conteudo, destino: Path) -> ArquivoGerado:
    """Grava o cenário ZIP com um PDF por peça.

    Args:
        conteudo: Conteúdo gerado.
        destino: Pasta do processo.

    Returns:
        Arquivo gerado.
    """
    arquivos: list[ArquivoGabarito] = []
    caminho_temp = destino / f".{NOME_ZIP}.tmp"
    destino.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(caminho_temp, "w", compression=zipfile.ZIP_STORED) as zip_saida:
        for peca in conteudo.pecas:
            parte = fitz.open()
            parte.insert_pdf(
                conteudo.documento, from_page=peca.pagina_inicial - 1, to_page=peca.pagina_final - 1
            )
            nome = nome_peca(peca)
            zip_saida.writestr(nome, _salvar(parte, conteudo))
            parte.close()
            arquivos.append(
                ArquivoGabarito(
                    nome=nome, folhas=tuple(range(peca.pagina_inicial, peca.pagina_final + 1))
                )
            )
    dados = caminho_temp.read_bytes()
    caminho_temp.unlink()
    return _gravar(
        destino,
        NOME_ZIP,
        dados,
        _gabarito(conteudo, Cenario.ZIP_POR_PECA, arquivos),
        Cenario.ZIP_POR_PECA,
    )


def exportar_indice(conteudo: Conteudo, destino: Path) -> ArquivoGerado:
    """Grava o cenário PDF único com índice de movimentações e bookmarks.

    Args:
        conteudo: Conteúdo gerado.
        destino: Pasta do processo.

    Returns:
        Arquivo gerado.
    """
    documento = fitz.open()
    deslocamento = _paginas_indice(documento, conteudo)
    documento.insert_pdf(conteudo.documento)
    sumario = [
        [
            1,
            f"{p.indice:03d} - {p.titulo} - {p.data.strftime('%d/%m/%Y')}",
            p.pagina_inicial + deslocamento,
        ]
        for p in conteudo.pecas
    ]
    documento.set_toc(sumario)
    folhas: tuple[int | None, ...] = (None,) * deslocamento + tuple(
        range(1, len(conteudo.paginas) + 1)
    )
    gabarito = _gabarito(
        conteudo, Cenario.PDF_INDICE, [ArquivoGabarito(nome=NOME_PDF, folhas=folhas)]
    )
    dados = _salvar(documento, conteudo)
    documento.close()
    return _gravar(destino, NOME_PDF, dados, gabarito, Cenario.PDF_INDICE)


def exportar_liso(conteudo: Conteudo, destino: Path) -> ArquivoGerado:
    """Grava o cenário PDF único liso.

    Args:
        conteudo: Conteúdo gerado.
        destino: Pasta do processo.

    Returns:
        Arquivo gerado.
    """
    documento = fitz.open()
    documento.insert_pdf(conteudo.documento)
    folhas = tuple(range(1, len(conteudo.paginas) + 1))
    gabarito = _gabarito(
        conteudo, Cenario.PDF_LISO, [ArquivoGabarito(nome=NOME_PDF, folhas=folhas)]
    )
    dados = _salvar(documento, conteudo)
    documento.close()
    return _gravar(destino, NOME_PDF, dados, gabarito, Cenario.PDF_LISO)


EXPORTADORES = {
    Cenario.ZIP_POR_PECA: exportar_zip,
    Cenario.PDF_INDICE: exportar_indice,
    Cenario.PDF_LISO: exportar_liso,
}


def exportar(
    conteudo: Conteudo, destino: Path, cenarios: tuple[Cenario, ...] = tuple(Cenario)
) -> list[ArquivoGerado]:
    """Grava os cenários pedidos, cada um em ``destino/<cenario>/`` com seu gabarito.

    Args:
        conteudo: Conteúdo gerado.
        destino: Pasta do processo.
        cenarios: Cenários a gravar.

    Returns:
        Arquivos gerados.
    """
    return [EXPORTADORES[c](conteudo, destino) for c in cenarios]
