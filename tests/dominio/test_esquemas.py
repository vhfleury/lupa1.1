"""Testes dos esquemas pydantic e do número CNJ (sem banco)."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from lupa.dominio.cnj import NumeroCnjInvalidoError, validar_numero_cnj
from lupa.dominio.enums import (
    Materia,
    MetodoClassificacao,
    OrigemPeca,
    PapelUsuario,
    ResultadoAchado,
    TipoPagina,
    TipoPeca,
)
from lupa.dominio.esquemas import (
    Achado,
    Anotacao,
    Evidencia,
    Fato,
    Pagina,
    Peca,
    Processo,
    Usuario,
    calcular_hash,
)
from tests.conftest import FabricaFato, gerar_numero_cnj


def test_numero_cnj_com_digito_correto_e_aceito() -> None:
    """Número gerado com o módulo 97 passa na validação."""
    numero = gerar_numero_cnj(123)
    assert validar_numero_cnj(numero) == numero


def test_numero_cnj_com_digito_errado_e_rejeitado() -> None:
    """Trocar o dígito verificador torna o número inválido."""
    numero = gerar_numero_cnj(123)
    digito_errado = f"{(int(numero[8:10]) + 1) % 100:02d}"
    adulterado = f"{numero[:8]}{digito_errado}{numero[10:]}"
    with pytest.raises(NumeroCnjInvalidoError, match="dígito"):
        validar_numero_cnj(adulterado)


def test_numero_cnj_fora_do_formato_e_rejeitado() -> None:
    """Formato diferente de NNNNNNN-DD.AAAA.J.TR.OOOO é rejeitado."""
    with pytest.raises(NumeroCnjInvalidoError, match="formato"):
        validar_numero_cnj("123-45.2025.8.09.0001")


def test_processo_com_cnj_de_digito_errado_e_rejeitado_pelo_pydantic() -> None:
    """O esquema `Processo` aplica a validação CNJ."""
    numero = gerar_numero_cnj(7)
    adulterado = numero.replace(numero[8:10], f"{(int(numero[8:10]) + 1) % 100:02d}", 1)
    with pytest.raises(ValidationError):
        Processo(
            gabinete_id=uuid4(),
            numero_cnj=adulterado,
            classe="Apelação Criminal",
            materia=Materia.CRIMINAL,
            sigiloso=False,
            criado_por=uuid4(),
        )


def test_fato_sem_evidencia_e_rejeitado_pelo_pydantic(fabrica_fato: FabricaFato) -> None:
    """`Fato.evidencias` exige ao menos um item."""
    dados = fabrica_fato().model_dump()
    dados["evidencias"] = ()
    with pytest.raises(ValidationError, match="evidencias"):
        Fato(**dados)


def test_fato_com_evidencia_e_aceito_e_imutavel(fabrica_fato: FabricaFato) -> None:
    """Fato válido é criado e não pode ser alterado depois."""
    fato = fabrica_fato()
    assert len(fato.evidencias) == 1
    with pytest.raises(ValidationError):
        fato.confianca = 0.1  # type: ignore[misc]


def test_evidencia_calcula_hash_do_trecho_quando_omitido() -> None:
    """`hash_trecho` vira sha256(trecho) se não informado."""
    evidencia = Evidencia(pagina_id=uuid4(), trecho="abc", inicio=0, fim=3)
    assert evidencia.hash_trecho == calcular_hash("abc")


def test_evidencia_com_hash_divergente_e_rejeitada() -> None:
    """Hash informado precisa corresponder ao trecho."""
    with pytest.raises(ValidationError, match="hash_trecho"):
        Evidencia(pagina_id=uuid4(), trecho="abc", hash_trecho="0" * 64, inicio=0, fim=3)


def test_evidencia_com_fim_nao_maior_que_inicio_e_rejeitada() -> None:
    """`fim` deve ser maior que `inicio`."""
    with pytest.raises(ValidationError, match="fim deve ser maior"):
        Evidencia(pagina_id=uuid4(), trecho="abc", inicio=5, fim=5)


def test_peca_com_pagina_final_antes_da_inicial_e_rejeitada() -> None:
    """`pagina_final >= pagina_inicial`."""
    with pytest.raises(ValidationError, match="pagina_final"):
        Peca(
            arquivo_id=uuid4(),
            tipo=TipoPeca.SENTENCA,
            pagina_inicial=10,
            pagina_final=9,
            confianca=1.0,
            metodo=MetodoClassificacao.REGRA,
            origem=OrigemPeca.JUIZO,
        )


def test_peca_de_uma_pagina_e_aceita() -> None:
    """Página inicial igual à final é válida."""
    peca = Peca(
        arquivo_id=uuid4(),
        tipo=TipoPeca.CERTIDAO,
        pagina_inicial=3,
        pagina_final=3,
        confianca=0.5,
        metodo=MetodoClassificacao.MANUAL,
        origem=OrigemPeca.DESCONHECIDA,
    )
    assert peca.pagina_final == 3


def test_pagina_calcula_e_confere_hash_do_texto() -> None:
    """`hash_texto` é calculado e, se informado, conferido."""
    pagina = Pagina(arquivo_id=uuid4(), numero=1, tipo=TipoPagina.NATIVA, texto="x")
    assert pagina.hash_texto == calcular_hash("x")
    with pytest.raises(ValidationError, match="hash_texto"):
        Pagina(arquivo_id=uuid4(), numero=1, tipo=TipoPagina.OCR, texto="x", hash_texto="y")


def test_achado_com_resultado_fora_do_enum_e_rejeitado() -> None:
    """`resultado` só aceita conforme, atencao ou verificar."""
    with pytest.raises(ValidationError, match="resultado"):
        Achado(
            processo_id=uuid4(),
            validacao="tempestividade",
            versao_catalogo="1",
            resultado="talvez",
            explicacao="-",
        )
    achado = Achado(
        processo_id=uuid4(),
        validacao="tempestividade",
        versao_catalogo="1",
        resultado=ResultadoAchado.VERIFICAR,
        explicacao="-",
    )
    assert achado.resultado is ResultadoAchado.VERIFICAR


def test_anotacao_exige_exatamente_um_alvo() -> None:
    """Anotação aponta para um achado ou um fato, nunca ambos nem nenhum."""
    with pytest.raises(ValidationError, match="exatamente um"):
        Anotacao(usuario_id=uuid4(), texto="nota")
    with pytest.raises(ValidationError, match="exatamente um"):
        Anotacao(achado_id=uuid4(), fato_id=uuid4(), usuario_id=uuid4(), texto="nota")
    assert Anotacao(fato_id=uuid4(), usuario_id=uuid4(), texto="nota").achado_id is None


def test_somente_administrador_fica_sem_gabinete() -> None:
    """Assessor precisa de gabinete; administrador não pode ter."""
    with pytest.raises(ValidationError, match="administrador"):
        Usuario(gabinete_id=None, nome_usuario="a", papel=PapelUsuario.ASSESSOR, senha_hash="h")
    with pytest.raises(ValidationError, match="administrador"):
        Usuario(
            gabinete_id=uuid4(), nome_usuario="b", papel=PapelUsuario.ADMINISTRADOR, senha_hash="h"
        )
    admin = Usuario(
        gabinete_id=None, nome_usuario="c", papel=PapelUsuario.ADMINISTRADOR, senha_hash="h"
    )
    assert "senha_hash" not in repr(admin)
