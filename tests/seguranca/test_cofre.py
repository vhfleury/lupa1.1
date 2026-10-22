"""Contrato do `Cofre` nas duas implementações (Etapa 7.2) e erros do adaptador do Vault."""

import base64
import json
import os
from collections.abc import Iterator
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from lupa.config import Settings
from lupa.seguranca.cofre import (
    ChaveAusenteError,
    Cofre,
    CofreError,
    CofreMemoria,
    CofreVault,
    TokenInvalidoError,
    criar_cofre,
    nome_chave_gabinete,
    nome_chave_identidades,
)


def cofre_vault_do_ambiente() -> CofreVault:
    """Cofre Vault das variáveis `LUPA_VAULT_*` do contêiner, ou pula o teste.

    Returns:
        O cofre, já com login conferido.
    """
    role_id = os.environ.get("LUPA_VAULT_ROLE_ID", "")
    secret_id = os.environ.get("LUPA_VAULT_SECRET_ID", "")
    endereco = os.environ.get("LUPA_VAULT_ENDERECO", "http://vault:8200")
    if not role_id or not secret_id or role_id.startswith("preenchido"):
        pytest.skip("Vault não configurado (rode scripts/vault_inicializar.sh)")
    cofre = CofreVault(endereco, role_id, secret_id, timeout=3)
    try:
        cofre.existe_chave("lupa-gabinete-sondagem")
    except CofreError:
        pytest.skip("Vault inacessível ou selado")
    return cofre


@pytest.fixture(params=["memoria", pytest.param("vault", marks=pytest.mark.integracao)])
def cofre(request: pytest.FixtureRequest) -> Iterator[Cofre]:
    """Cofre de cada implementação."""
    yield CofreMemoria() if request.param == "memoria" else cofre_vault_do_ambiente()


def test_contrato_cifrar_decifrar_rotacionar_recifrar_destruir(cofre: Cofre) -> None:
    """Ciclo completo de uma chave de gabinete."""
    gabinete = uuid4()
    nome = nome_chave_gabinete(gabinete)
    assert nome_chave_identidades(gabinete) == f"{nome}-identidades"
    assert not cofre.existe_chave(nome)
    cofre.criar_chave(nome)
    cofre.criar_chave(nome)
    assert cofre.existe_chave(nome)
    token = cofre.cifrar(nome, b"dek-sintetica-32-bytes-000000000")
    assert "dek-sintetica" not in token
    assert cofre.decifrar(nome, token) == b"dek-sintetica-32-bytes-000000000"
    cofre.rotacionar(nome)
    novo = cofre.recifrar(nome, token)
    assert novo != token and novo.split(":")[1] == "v2"
    assert cofre.decifrar(nome, novo) == cofre.decifrar(nome, token)
    outra = nome_chave_gabinete(uuid4())
    cofre.criar_chave(outra)
    with pytest.raises(TokenInvalidoError):
        cofre.decifrar(outra, token)
    cofre.destruir_chave(nome)
    cofre.destruir_chave(nome)
    cofre.destruir_chave(outra)
    assert not cofre.existe_chave(nome)
    with pytest.raises(ChaveAusenteError):
        cofre.decifrar(nome, novo)
    with pytest.raises(ChaveAusenteError):
        cofre.cifrar(nome, b"x")


def test_criar_cofre_escolhe_backend_e_recusa_memoria_em_producao(
    settings_ficticias: Settings,
) -> None:
    """Memória fora de produção; Vault por padrão; memória recusada em produção."""
    memoria = settings_ficticias.model_copy(update={"cofre_backend": "memoria"})
    assert isinstance(criar_cofre(memoria), CofreMemoria)
    vault = settings_ficticias.model_copy(
        update={
            "cofre_backend": "vault",
            "vault_role_id": SecretStr("r"),
            "vault_secret_id": SecretStr("s"),
        }
    )
    assert isinstance(criar_cofre(vault), CofreVault)
    sem_approle = settings_ficticias.model_copy(
        update={"cofre_backend": "vault", "vault_role_id": None, "vault_secret_id": None}
    )
    assert isinstance(criar_cofre(sem_approle), CofreVault)
    with pytest.raises(CofreError):
        criar_cofre(memoria.model_copy(update={"ambiente": "producao"}))


class VaultFalso:
    """Transporte HTTP que imita o Transit o suficiente para os caminhos de erro."""

    def __init__(self) -> None:
        """Começa sem logins e sem chaves."""
        self.logins = 0
        self.negar_proxima = False
        self.chaves: set[str] = set()

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        """Responde ao pedido.

        Args:
            pedido: Pedido HTTP.

        Returns:
            Resposta imitando o Vault.
        """
        caminho = pedido.url.path
        if caminho == "/v1/auth/approle/login":
            self.logins += 1
            if json.loads(pedido.content)["secret_id"] != "certo":  # noqa: S105
                return httpx.Response(400, json={"errors": ["invalid secret id"]})
            return httpx.Response(200, json={"auth": {"client_token": f"t{self.logins}"}})
        if self.negar_proxima:
            self.negar_proxima = False
            return httpx.Response(403, json={"errors": ["permission denied"]})
        return self._transit(pedido, caminho.removeprefix("/v1/transit/").split("/"))

    def _transit(self, pedido: httpx.Request, partes: list[str]) -> httpx.Response:
        acao, nome = partes[0], partes[1]
        if acao == "keys" and pedido.method == "POST" and len(partes) == 2:
            self.chaves.add(nome)
            return httpx.Response(204)
        if nome not in self.chaves:
            return self._ausente(acao, pedido.method)
        if acao == "encrypt":
            claro = json.loads(pedido.content)["plaintext"]
            return httpx.Response(200, json={"data": {"ciphertext": f"vault:v1:{claro}"}})
        if acao == "decrypt":
            token = json.loads(pedido.content)["ciphertext"]
            if not token.startswith("vault:v1:"):
                return httpx.Response(400, json={"errors": ["invalid ciphertext: no prefix"]})
            return httpx.Response(
                200, json={"data": {"plaintext": token.removeprefix("vault:v1:")}}
            )
        if acao == "keys" and pedido.method == "DELETE":
            self.chaves.discard(nome)
            return httpx.Response(204)
        if acao == "rewrap":
            return httpx.Response(200, json={"data": {"ciphertext": "vault:v2:x"}})
        return httpx.Response(200, json={"data": {}})

    def _ausente(self, acao: str, metodo: str) -> httpx.Response:
        if acao == "keys" and metodo == "GET":
            return httpx.Response(404)
        if acao == "encrypt":
            return httpx.Response(403, json={"errors": ["permission denied"]})
        return httpx.Response(400, json={"errors": ["encryption key not found"]})


def _vault(falso: VaultFalso, secret_id: str = "certo") -> CofreVault:  # noqa: S107
    cliente = httpx.Client(base_url="http://vault:8200", transport=httpx.MockTransport(falso))
    return CofreVault("http://vault:8200", "role", secret_id, cliente=cliente)


def test_vault_falso_faz_login_renova_em_403_e_mapeia_erros() -> None:
    """Login preguiçoso, novo login após 403, chave ausente e token inválido."""
    falso = VaultFalso()
    cofre = _vault(falso)
    cofre.criar_chave("lupa-gabinete-a")
    assert falso.logins == 1
    token = cofre.cifrar("lupa-gabinete-a", b"abc")
    assert base64.b64encode(b"abc").decode() in token
    falso.negar_proxima = True
    assert cofre.decifrar("lupa-gabinete-a", token) == b"abc"
    assert falso.logins == 2
    assert cofre.existe_chave("lupa-gabinete-a")
    with pytest.raises(TokenInvalidoError):
        cofre.decifrar("lupa-gabinete-a", "lixo")
    with pytest.raises(ChaveAusenteError):
        cofre.cifrar("lupa-gabinete-b", b"abc")
    with pytest.raises(ChaveAusenteError):
        cofre.decifrar("lupa-gabinete-b", token)
    cofre.rotacionar("lupa-gabinete-a")
    assert cofre.recifrar("lupa-gabinete-a", token) == "vault:v2:x"
    cofre.destruir_chave("lupa-gabinete-a")
    cofre.destruir_chave("lupa-gabinete-a")
    assert not cofre.existe_chave("lupa-gabinete-a")


def _transporte(resposta: httpx.Response | None) -> httpx.Client:
    def _responder(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.path.endswith("/login"):
            return httpx.Response(200, json={"auth": {"client_token": "t"}})
        if resposta is None:
            raise httpx.ConnectError("recusado")
        return resposta

    return httpx.Client(base_url="http://vault:8200", transport=httpx.MockTransport(_responder))


def test_vault_falso_login_recusado_inacessivel_e_erro_interno() -> None:
    """Secret ID errado, servidor fora do ar e erro 500 viram `CofreError` sem vazar segredo."""
    with pytest.raises(CofreError) as erro:
        _vault(VaultFalso(), "errado").existe_chave("lupa-gabinete-a")
    assert "errado" not in str(erro.value)
    with pytest.raises(CofreError):
        CofreVault("http://vault:8200", "r", "s", cliente=_transporte(None)).cifrar("k", b"x")
    quebrado = CofreVault(
        "http://vault:8200", "r", "s",
        cliente=_transporte(httpx.Response(500, json={"errors": ["interno"]})),
    )  # fmt: skip
    with pytest.raises(CofreError):
        quebrado.existe_chave("k")
    with pytest.raises(CofreError):
        quebrado.cifrar("k", b"x")


def test_cofre_memoria_token_malformado() -> None:
    """Token malformado ou de versão inexistente: `TokenInvalidoError`."""
    cofre = CofreMemoria()
    cofre.criar_chave("k")
    for token in ("lixo", "mem:v9:AAAA", "mem:v1:@@"):
        with pytest.raises(TokenInvalidoError):
            cofre.decifrar("k", token)
