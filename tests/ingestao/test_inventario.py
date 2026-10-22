"""Testes do inventário seguro de ZIP."""

import hashlib
import zipfile
from pathlib import Path

import pytest

from lupa.dominio.enums import MotivoQuarentena
from lupa.ingestao import inventario
from lupa.ingestao.inventario import LimitesZip, ZipRecusadoError, caminho_seguro, inventariar
from tests.ingestao.arquivos import pdf_minimo, zip_cifrado, zip_com_info, zip_de


def _gravar(tmp_path: Path, dados: bytes) -> Path:
    caminho = tmp_path / "entrada.zip"
    caminho.write_bytes(dados)
    destino = tmp_path / "extraido"
    destino.mkdir()
    return caminho


def _recusa(tmp_path: Path, dados: bytes, limites: LimitesZip | None = None) -> ZipRecusadoError:
    caminho = _gravar(tmp_path, dados)
    with pytest.raises(ZipRecusadoError) as erro:
        inventariar(caminho, tmp_path / "extraido", limites or LimitesZip())
    return erro.value


def test_manifesto_ordenado_por_nome_com_hash_e_tamanho(tmp_path: Path) -> None:
    """Entradas gravadas fora de ordem saem ordenadas; diretórios são ignorados."""
    conteudos = {"b/2.pdf": pdf_minimo(2), "a.pdf": pdf_minimo(1), "b/": b""}
    caminho = _gravar(tmp_path, zip_de(conteudos))
    extraidas = inventariar(caminho, tmp_path / "extraido", LimitesZip())
    assert [e.manifesto.nome for e in extraidas] == ["a.pdf", "b/2.pdf"]
    assert [e.manifesto.ordem for e in extraidas] == [1, 2]
    for entrada in extraidas:
        original = conteudos[entrada.manifesto.nome]
        assert entrada.manifesto.sha256 == hashlib.sha256(original).hexdigest()
        assert entrada.manifesto.tamanho_bytes == len(original)
        assert entrada.caminho.read_bytes() == original
        assert entrada.caminho.parent == tmp_path / "extraido"


@pytest.mark.parametrize(
    "nome",
    ["../fora.pdf", "a/../../fora.pdf", "/etc/passwd", "C:/x.pdf", "a\\..\\b.pdf", ""],
)
def test_caminho_inseguro(nome: str) -> None:
    """Subida de diretório, absoluto, unidade e barra invertida são recusados."""
    assert not caminho_seguro(nome)


def test_caminho_relativo_simples_e_seguro() -> None:
    """Subpastas relativas são aceitas."""
    assert caminho_seguro("pecas/01 - denuncia.pdf")


def test_caminho_com_ponto_ponto_e_zip_malicioso(tmp_path: Path) -> None:
    """ZIP slip recusado com motivo."""
    erro = _recusa(tmp_path, zip_de({"../../evil.pdf": pdf_minimo()}))
    assert erro.motivo is MotivoQuarentena.ZIP_MALICIOSO
    assert "caminho" in erro.detalhe


def test_link_simbolico_recusado(tmp_path: Path) -> None:
    """Entrada com modo de link simbólico."""
    info = zipfile.ZipInfo("link.pdf")
    info.external_attr = 0o120777 << 16
    erro = _recusa(tmp_path, zip_com_info(info, b"/etc/passwd"))
    assert (erro.motivo, erro.detalhe) == (MotivoQuarentena.ZIP_MALICIOSO, "link simbólico")


def test_entrada_cifrada_vai_para_senha(tmp_path: Path) -> None:
    """Bit de criptografia ligado: quarentena por senha."""
    assert _recusa(tmp_path, zip_cifrado()).motivo is MotivoQuarentena.SENHA


def test_quantidade_de_entradas_acima_do_limite(tmp_path: Path) -> None:
    """Mais entradas que o permitido."""
    dados = zip_de({f"{n}.pdf": b"%PDF-" for n in range(5)})
    erro = _recusa(tmp_path, dados, LimitesZip(max_entradas=4))
    assert "quantidade" in erro.detalhe


def test_zip_bomb_detectada_pela_razao_de_compressao(tmp_path: Path) -> None:
    """10 MB de zeros comprimem mais de 100:1."""
    erro = _recusa(tmp_path, zip_de({"a.pdf": b"\x00" * (10 * 1024 * 1024)}))
    assert (erro.motivo, erro.detalhe) == (
        MotivoQuarentena.ZIP_MALICIOSO,
        "razão de compressão acima do limite",
    )


def test_tamanho_total_descomprimido_acima_do_limite(tmp_path: Path) -> None:
    """Soma declarada acima do limite, sem extrair."""
    dados = zip_de({"a.pdf": pdf_minimo(), "b.pdf": pdf_minimo()}, metodo=zipfile.ZIP_STORED)
    erro = _recusa(tmp_path, dados, LimitesZip(max_descomprimido_bytes=len(pdf_minimo()) + 10))
    assert "tamanho" in erro.detalhe


def test_limite_imposto_sobre_bytes_lidos_mesmo_com_cabecalho_mentiroso(tmp_path: Path) -> None:
    """A extração conta os bytes reais, não o tamanho declarado."""
    caminho = _gravar(tmp_path, zip_de({"a.pdf": pdf_minimo()}))
    with zipfile.ZipFile(caminho) as arquivo, pytest.raises(ZipRecusadoError):
        inventario._extrair(arquivo, arquivo.infolist()[0], tmp_path / "x", restante=10)


def test_nomes_repetidos_e_zip_vazio(tmp_path: Path) -> None:
    """Entrada duplicada é maliciosa; ZIP sem arquivos é tipo inválido."""
    duplicado = zip_com_info(zipfile.ZipInfo("a.pdf"), b"1")
    with zipfile.ZipFile(_gravar(tmp_path, duplicado), "a") as arquivo, pytest.warns(UserWarning):
        arquivo.writestr("a.pdf", b"2")
    with pytest.raises(ZipRecusadoError) as erro:
        inventariar(tmp_path / "entrada.zip", tmp_path / "extraido", LimitesZip())
    assert "repetidos" in erro.value.detalhe
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    vazio_zip = zip_de({"pasta/": b""})
    assert _recusa(vazio, vazio_zip).motivo is MotivoQuarentena.TIPO_INVALIDO


def test_zip_ilegivel_e_crc_errado_sao_corrompidos(tmp_path: Path) -> None:
    """Lixo com assinatura ZIP e conteúdo adulterado (CRC) vão para `corrompido`."""
    assert _recusa(tmp_path, b"PK\x03\x04" + b"\x01" * 80).motivo is MotivoQuarentena.CORROMPIDO
    dados = bytearray(zip_de({"a.pdf": b"%PDF-conteudo-sintetico"}, metodo=zipfile.ZIP_STORED))
    posicao = dados.index(b"conteudo")
    dados[posicao] ^= 0xFF
    outro = tmp_path / "crc"
    outro.mkdir()
    assert _recusa(outro, bytes(dados)).motivo is MotivoQuarentena.CORROMPIDO


def test_compressao_nao_suportada_e_corrompido(tmp_path: Path) -> None:
    """Método de compressão desconhecido."""
    dados = bytearray(zip_de({"a.pdf": b"%PDF-x"}, metodo=zipfile.ZIP_STORED))
    for assinatura in (b"PK\x03\x04", b"PK\x01\x02"):
        inicio = dados.index(assinatura)
        deslocamento = 8 if assinatura == b"PK\x03\x04" else 10
        dados[inicio + deslocamento : inicio + deslocamento + 2] = (99).to_bytes(2, "little")
    assert _recusa(tmp_path, bytes(dados)).motivo is MotivoQuarentena.CORROMPIDO
