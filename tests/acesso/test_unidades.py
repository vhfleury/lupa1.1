"""Testes unitários de senhas, TOTP e matriz de permissões (sem banco)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pyotp
import pytest
from argon2 import PasswordHasher

from lupa.acesso import mfa, senhas
from lupa.acesso.papeis import MATRIZ, Escopo, Permissao, pode, tem_permissao
from lupa.dominio.enums import PapelUsuario

AGORA = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)


def test_hash_argon2id_confere_e_rejeita_senha_errada() -> None:
    """O hash é argon2id e só confere com a senha certa."""
    hash_ = senhas.gerar_hash("senha-longa-de-teste")
    assert hash_.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert senhas.verificar_senha(hash_, "senha-longa-de-teste")
    assert not senhas.verificar_senha(hash_, "outra-senha-qualquer")
    assert not senhas.verificar_senha("nao-e-hash", "x")
    assert not senhas.precisa_rehash(hash_)


def test_hash_com_parametros_antigos_precisa_rehash() -> None:
    """Hash gerado com parâmetros diferentes é sinalizado para regravação."""
    antigo = PasswordHasher(time_cost=1, memory_cost=8192).hash("x" * 12)
    assert senhas.precisa_rehash(antigo)


@pytest.mark.parametrize(
    ("senha", "motivo"),
    [
        ("curta", "12 caracteres"),
        ("q1w2e3r4t5y6", "mais comuns"),
        ("QWERTY123456", "mais comuns"),
        ("meu-joao.silva-2026", "nome de usuário"),
        ("aaaaaaaaaaaaaaab", "repetidos"),
    ],
)
def test_politica_recusa_senhas_fracas(senha: str, motivo: str) -> None:
    """Política: 12+, fora da lista comum, sem o nome de usuário, sem repetição trivial."""
    with pytest.raises(senhas.SenhaFracaError, match=motivo):
        senhas.validar_politica(senha, "joao.silva")


def test_politica_aceita_frase_longa_sem_caracteres_especiais() -> None:
    """Não exige caractere especial."""
    senhas.validar_politica("cavalo bateria grampo correto", "joao.silva")


def test_lista_embutida_tem_dez_mil_senhas() -> None:
    """A lista embutida tem as 10 mil senhas mais comuns."""
    assert len(senhas.senhas_comuns()) >= 9_900
    assert "password" in senhas.senhas_comuns()


def test_senha_temporaria_e_aleatoria_e_atende_politica() -> None:
    """A senha temporária é longa, distinta a cada chamada e passa na política."""
    primeira, segunda = senhas.gerar_senha_temporaria(), senhas.gerar_senha_temporaria()
    assert primeira != segunda
    senhas.validar_politica(primeira, "qualquer")


def test_totp_aceita_passo_atual_e_vizinhos() -> None:
    """Janela de tolerância de um passo para cada lado."""
    segredo = mfa.gerar_segredo()
    totp = pyotp.TOTP(segredo)
    for deslocamento in (-30, 0, 30):
        codigo = totp.at(AGORA + timedelta(seconds=deslocamento))
        assert mfa.verificar_codigo(segredo, codigo, None, AGORA) is not None
    assert (
        mfa.verificar_codigo(segredo, totp.at(AGORA + timedelta(seconds=90)), None, AGORA) is None
    )


def test_totp_recusa_codigo_reutilizado() -> None:
    """Depois de aceito, o mesmo passo (e anteriores) é recusado."""
    segredo = mfa.gerar_segredo()
    codigo = pyotp.TOTP(segredo).at(AGORA)
    passo = mfa.verificar_codigo(segredo, codigo, None, AGORA)
    assert passo is not None
    assert mfa.verificar_codigo(segredo, codigo, passo, AGORA) is None


def test_provisionamento_traz_uri_otpauth() -> None:
    """A URI do QR identifica o emissor e o usuário."""
    dados = mfa.provisionar(mfa.gerar_segredo(), "maria")
    assert dados.uri.startswith("otpauth://totp/Lupa:maria?")
    assert "issuer=Lupa" in dados.uri


def test_matriz_segue_a_tabela_do_plano() -> None:
    """Cada linha da tabela de permissões do plano, por papel."""
    esperado = {
        Permissao.VER_PROCESSO: (True, True, True),
        Permissao.SUBIR_PROCESSO: (True, True, True),
        Permissao.ANOTAR: (True, True, True),
        Permissao.VER_AUDITORIA: (False, True, True),
        Permissao.GERIR_ASSESSOR: (False, True, True),
        Permissao.RESETAR_ASSESSOR: (False, True, True),
        Permissao.GERIR_DESEMBARGADOR: (False, False, True),
        Permissao.GERIR_GABINETES: (False, False, True),
    }
    papeis = (PapelUsuario.ASSESSOR, PapelUsuario.DESEMBARGADOR, PapelUsuario.ADMINISTRADOR)
    for permissao, linha in esperado.items():
        assert tuple(tem_permissao(p, permissao) for p in papeis) == linha, permissao
    assert set(MATRIZ[PapelUsuario.ADMINISTRADOR].values()) == {Escopo.TODOS}


def test_escopo_de_gabinete_so_vale_no_proprio() -> None:
    """Desembargador gere assessores só do próprio gabinete; admin em todos."""
    proprio, outro = uuid4(), uuid4()
    gerir = Permissao.GERIR_ASSESSOR
    assert pode(PapelUsuario.DESEMBARGADOR, gerir, proprio, proprio)
    assert not pode(PapelUsuario.DESEMBARGADOR, gerir, proprio, outro)
    assert not pode(PapelUsuario.ASSESSOR, gerir, proprio, proprio)
    assert pode(PapelUsuario.ADMINISTRADOR, gerir, None, outro)
    assert not pode(PapelUsuario.DESEMBARGADOR, gerir, None, None)
