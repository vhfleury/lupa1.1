"""Renderização de uma página do original como imagem PNG (Etapa 6.6), só dentro do sandbox.

O cliente nunca recebe o PDF cru nem o texto extraído: o servidor desenha a página como imagem.
O filho do sandbox (`main`) abre o PDF, DESLIGA todas as camadas opcionais (OCG), recorta à
`CropBox` (`page.rect`) e não desenha anotações; devolve o PNG em base64 e o tamanho da página
em pontos. Assim, texto numa camada opcional ou fora da área visível não aparece na imagem.

Limitação registrada: a imagem mostra o que o PDF desenha. Texto branco sobre branco ou em
fonte minúscula fica invisível na imagem (como para o leitor humano), mas um conteúdo que o
próprio PDF desenha visível (por exemplo, instrução impressa no corpo) aparece normalmente; os
alertas de saneamento da 4D continuam sendo a fonte para isso.

O lado do servidor (`renderizar`) guarda o PNG e o tamanho no object storage, por página e
zoom, sob o prefixo `renderizacao/<versao>/` seguido da chave do objeto de origem (que já leva
gabinete e processo); a segunda visualização não abre o PDF de novo.
"""

import base64
import io
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lupa.ingestao.sandbox import LimitesSandbox, executar
from lupa.ingestao.storage import ObjectStorage, ObjetoAusenteError

VERSAO_RENDERIZACAO = "6.6.0"
MODULO_RENDERIZACAO = "lupa.ingestao.renderizacao"
ZOOM_PADRAO = 2.0
ZOOM_MINIMO = 0.5
ZOOM_MAXIMO = 4.0
LIMITES_RENDERIZACAO = LimitesSandbox(memoria_mb=768, cpu_segundos=30, tempo_segundos=45)


class RenderizacaoError(RuntimeError):
    """A página não pôde ser renderizada (PDF ilegível, limite de recurso, página inexistente)."""


@dataclass(frozen=True)
class PaginaRenderizada:
    """Imagem da página e o tamanho dela em pontos PDF.

    Attributes:
        png: Imagem PNG.
        largura: Largura da página (`CropBox`) em pontos.
        altura: Altura da página em pontos.
    """

    png: bytes
    largura: float
    altura: float


def desenhar(dados: bytes, numero: int, zoom: float) -> dict[str, Any]:
    """Desenha a página `numero` (1-based) sem camadas opcionais, recortada à `CropBox`.

    Args:
        dados: Bytes do PDF.
        numero: Página, a partir de 1.
        zoom: Escala (1.0 = 72 dpi).

    Returns:
        `{"ok": true, "png": base64, "largura", "altura", "camadas_desligadas"}` ou
        `{"ok": false, "erro": ...}`.
    """
    import fitz

    try:
        documento = fitz.open(stream=dados, filetype="pdf")
    except Exception:
        return {"ok": False, "erro": "abertura"}
    if documento.needs_pass or not 1 <= numero <= documento.page_count:
        return {"ok": False, "erro": "pagina"}
    camadas = list(documento.get_ocgs())
    if camadas:
        documento.set_layer(-1, on=[], off=camadas)
        for configuracao in documento.layer_ui_configs():
            documento.set_layer_ui_config(configuracao["number"], action=2)
    pagina = documento[numero - 1]
    area = pagina.rect
    imagem = pagina.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=area, alpha=False, annots=False)
    return {
        "ok": True,
        "png": base64.b64encode(imagem.tobytes("png")).decode("ascii"),
        "largura": float(area.width),
        "altura": float(area.height),
        "camadas_desligadas": len(camadas),
    }


def main(argv: list[str] | None = None) -> None:  # pragma: no cover (roda no processo filho)
    """Ponto de entrada do processo filho: `[caminho, pagina, zoom]`.

    Args:
        argv: Argumentos (padrão: `sys.argv[1:]`).
    """
    from lupa.ingestao.parser_pdf import EXIT_MEMORIA, bloquear_rede

    bloquear_rede()
    caminho, numero, zoom = argv or sys.argv[1:]
    try:
        resultado = desenhar(Path(caminho).read_bytes(), int(numero), float(zoom))
    except MemoryError:
        sys.exit(EXIT_MEMORIA)
    sys.stdout.write(json.dumps(resultado))
    sys.stdout.flush()


def chave_cache(chave_origem: str, numero: int, zoom: float) -> str:
    """Chave do PNG em cache no storage.

    Args:
        chave_origem: Chave do PDF de origem (gabinete/processo/hash).
        numero: Página no PDF de origem.
        zoom: Escala.

    Returns:
        Chave do objeto PNG (o tamanho fica em `<chave>.json`).
    """
    return f"renderizacao/{VERSAO_RENDERIZACAO}/{chave_origem}/{numero}-{zoom:.2f}.png"


def _do_cache(storage: ObjectStorage, chave: str) -> PaginaRenderizada | None:
    try:
        png = storage.ler(chave)
        medidas = json.loads(storage.ler(f"{chave}.json"))
    except ObjetoAusenteError:
        return None
    return PaginaRenderizada(png, float(medidas["largura"]), float(medidas["altura"]))


def renderizar(
    storage: ObjectStorage,
    chave_origem: str,
    numero: int,
    zoom: float = ZOOM_PADRAO,
    limites: LimitesSandbox = LIMITES_RENDERIZACAO,
) -> PaginaRenderizada:
    """Imagem da página, do cache ou renderizada no sandbox (e guardada no cache).

    Args:
        storage: Object storage (origem e cache).
        chave_origem: Chave do PDF de origem.
        numero: Página no PDF de origem (1-based).
        zoom: Escala, entre `ZOOM_MINIMO` e `ZOOM_MAXIMO`.
        limites: Limites do sandbox.

    Returns:
        Página renderizada.

    Raises:
        RenderizacaoError: Origem ausente, PDF ilegível, página inexistente ou limite excedido.
    """
    zoom = min(max(zoom, ZOOM_MINIMO), ZOOM_MAXIMO)
    chave = chave_cache(chave_origem, numero, zoom)
    em_cache = _do_cache(storage, chave)
    if em_cache is not None:
        return em_cache
    try:
        dados = storage.ler(chave_origem)
    except ObjetoAusenteError:
        raise RenderizacaoError("origem ausente") from None
    with tempfile.TemporaryDirectory(prefix="lupa-render-") as diretorio:
        caminho = Path(diretorio) / "origem.pdf"
        caminho.write_bytes(dados)
        caminho.chmod(0o600)
        resultado = executar(MODULO_RENDERIZACAO, [str(caminho), str(numero), str(zoom)], limites)
    if not resultado.ok or not resultado.dados.get("ok"):
        raise RenderizacaoError(str(resultado.dados.get("erro") or resultado.motivo_falha))
    pagina = PaginaRenderizada(
        base64.b64decode(resultado.dados["png"]),
        float(resultado.dados["largura"]),
        float(resultado.dados["altura"]),
    )
    storage.gravar(chave, io.BytesIO(pagina.png))
    medidas = {"largura": pagina.largura, "altura": pagina.altura}
    storage.gravar(f"{chave}.json", io.BytesIO(json.dumps(medidas).encode()))
    return pagina
