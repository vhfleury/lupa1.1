"""Cofre de chaves com interface própria: HashiCorp Vault (Transit) e memória (testes).

Mesmo padrão do `ObjectStorage`: a aplicação só conhece o protocolo `Cofre`; a implementação é
escolhida por configuração (`LUPA_COFRE_BACKEND`). As chaves mestras NUNCA saem do cofre: a
aplicação manda bytes para cifrar ou decifrar (wrap/unwrap das chaves de dados) e recebe um
token opaco. Nomes de chave seguem `lupa-gabinete-<id>` (envelope das DEKs dos processos) e
`lupa-gabinete-<id>-identidades` (tabela de identidades dos réus).
"""

import base64
import os
import threading
from typing import Any, Protocol
from uuid import UUID

import httpx
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from lupa.config import Settings

PREFIXO_CHAVE = "lupa-gabinete-"
# Chave Transit só para a verificação de saúde (Etapa 8.1); criada por vault_inicializar.
CHAVE_SAUDE = "lupa-saude"
SUFIXO_IDENTIDADES = "-identidades"
TAMANHO_NONCE = 12
STATUS_PROIBIDO = 403
STATUS_AUSENTE = 404


class CofreError(RuntimeError):
    """Falha ao falar com o cofre (indisponível, selado, sem permissão)."""


class ChaveAusenteError(LookupError):
    """A chave pedida não existe no cofre (nunca criada ou destruída)."""


class TokenInvalidoError(ValueError):
    """O token não foi produzido por esta chave (ou foi adulterado)."""


def nome_chave_gabinete(gabinete_id: UUID) -> str:
    """Nome da chave Transit do gabinete (envelope das DEKs).

    Args:
        gabinete_id: Gabinete.

    Returns:
        `lupa-gabinete-<id>`.
    """
    return f"{PREFIXO_CHAVE}{gabinete_id}"


def nome_chave_identidades(gabinete_id: UUID) -> str:
    """Nome da chave Transit das identidades dos réus do gabinete.

    Args:
        gabinete_id: Gabinete.

    Returns:
        `lupa-gabinete-<id>-identidades`.
    """
    return f"{nome_chave_gabinete(gabinete_id)}{SUFIXO_IDENTIDADES}"


class Cofre(Protocol):
    """Contrato do cofre de chaves (subconjunto do Transit do Vault)."""

    def criar_chave(self, nome: str) -> None:
        """Cria a chave (sem erro se já existir)."""

    def existe_chave(self, nome: str) -> bool:
        """Diz se a chave existe."""

    def cifrar(self, nome: str, dados: bytes) -> str:
        """Cifra `dados` com a versão corrente da chave; lança `ChaveAusenteError`."""

    def decifrar(self, nome: str, token: str) -> bytes:
        """Decifra o token; lança `ChaveAusenteError` ou `TokenInvalidoError`."""

    def rotacionar(self, nome: str) -> None:
        """Cria uma versão nova da chave; as antigas continuam decifrando."""

    def recifrar(self, nome: str, token: str) -> str:
        """Recifra o token com a versão corrente sem expor o conteúdo (rewrap)."""

    def destruir_chave(self, nome: str) -> None:
        """Apaga a chave e todas as versões (irreversível)."""


class CofreMemoria:
    """Cofre em memória com AES-GCM, para testes e desenvolvimento sem Vault."""

    def __init__(self) -> None:
        """Cria o cofre vazio."""
        self._chaves: dict[str, list[bytes]] = {}
        self._trava = threading.Lock()

    def criar_chave(self, nome: str) -> None:
        """Cria a chave se não existir.

        Args:
            nome: Nome da chave.
        """
        with self._trava:
            self._chaves.setdefault(nome, [AESGCM.generate_key(bit_length=256)])

    def existe_chave(self, nome: str) -> bool:
        """Diz se a chave existe.

        Args:
            nome: Nome da chave.

        Returns:
            Verdadeiro se existir.
        """
        return nome in self._chaves

    def _versoes(self, nome: str) -> list[bytes]:
        try:
            return self._chaves[nome]
        except KeyError:
            raise ChaveAusenteError(nome) from None

    def cifrar(self, nome: str, dados: bytes) -> str:
        """Cifra com a última versão.

        Args:
            nome: Nome da chave.
            dados: Bytes em claro.

        Returns:
            Token `mem:v<n>:<base64>`.

        Raises:
            ChaveAusenteError: Chave inexistente.
        """
        versoes = self._versoes(nome)
        nonce = os.urandom(TAMANHO_NONCE)
        cifrado = AESGCM(versoes[-1]).encrypt(nonce, dados, nome.encode())
        return f"mem:v{len(versoes)}:{base64.b64encode(nonce + cifrado).decode()}"

    def decifrar(self, nome: str, token: str) -> bytes:
        """Decifra o token.

        Args:
            nome: Nome da chave.
            token: Token de `cifrar`.

        Returns:
            Bytes em claro.

        Raises:
            ChaveAusenteError: Chave inexistente.
            TokenInvalidoError: Token malformado, de outra chave ou adulterado.
        """
        versoes = self._versoes(nome)
        try:
            _, versao, corpo = token.split(":", 2)
            chave = versoes[int(versao.removeprefix("v")) - 1]
            bruto = base64.b64decode(corpo)
            return AESGCM(chave).decrypt(
                bruto[:TAMANHO_NONCE], bruto[TAMANHO_NONCE:], nome.encode()
            )
        except (ValueError, IndexError, InvalidTag):
            raise TokenInvalidoError(nome) from None

    def rotacionar(self, nome: str) -> None:
        """Acrescenta uma versão nova.

        Args:
            nome: Nome da chave.
        """
        with self._trava:
            self._versoes(nome).append(AESGCM.generate_key(bit_length=256))

    def recifrar(self, nome: str, token: str) -> str:
        """Recifra com a versão corrente.

        Args:
            nome: Nome da chave.
            token: Token antigo.

        Returns:
            Token novo.
        """
        return self.cifrar(nome, self.decifrar(nome, token))

    def destruir_chave(self, nome: str) -> None:
        """Apaga a chave.

        Args:
            nome: Nome da chave.
        """
        with self._trava:
            self._chaves.pop(nome, None)


class CofreVault:
    """Cofre HashiCorp Vault pelo Transit engine, autenticado por AppRole (HTTP via httpx).

    O token do AppRole é obtido no primeiro uso e renovado (novo login) quando o Vault responde
    403; o `secret_id` nunca é registrado em log.
    """

    def __init__(
        self,
        endereco: str,
        role_id: str,
        secret_id: str,
        *,
        montagem: str = "transit",
        timeout: float = 5.0,
        cliente: httpx.Client | None = None,
    ) -> None:
        """Cria o adaptador (sem conectar).

        Args:
            endereco: URL do Vault (`http://vault:8200`).
            role_id: Role ID do AppRole.
            secret_id: Secret ID do AppRole.
            montagem: Caminho do Transit engine.
            timeout: Tempo máximo de cada chamada, em segundos.
            cliente: Cliente HTTP (injetável nos testes).
        """
        self._cliente = cliente or httpx.Client(base_url=endereco, timeout=timeout)
        self._role_id = role_id
        self._secret_id = secret_id
        self._montagem = montagem.strip("/")
        self._token: str | None = None
        self._trava = threading.Lock()

    def _login(self) -> str:
        resposta = self._cliente.post(
            "/v1/auth/approle/login",
            json={"role_id": self._role_id, "secret_id": self._secret_id},
        )
        if resposta.status_code != httpx.codes.OK:
            raise CofreError(f"login AppRole recusado ({resposta.status_code})")
        token = str(resposta.json()["auth"]["client_token"])
        self._token = token
        return token

    def _chamar(self, metodo: str, caminho: str, corpo: dict[str, Any] | None = None) -> Any:
        for tentativa in range(2):
            with self._trava:
                token = self._token if self._token and tentativa == 0 else self._login()
            try:
                resposta = self._cliente.request(
                    metodo,
                    f"/v1/{self._montagem}/{caminho}",
                    json=corpo,
                    headers={"X-Vault-Token": token},
                )
            except httpx.HTTPError as erro:
                raise CofreError(f"vault inacessível: {type(erro).__name__}") from None
            if resposta.status_code == STATUS_PROIBIDO and tentativa == 0:
                continue
            return resposta
        return resposta

    def _dados(self, resposta: httpx.Response, nome: str) -> dict[str, Any]:
        if resposta.status_code in (httpx.codes.OK, httpx.codes.NO_CONTENT):
            if resposta.status_code == httpx.codes.NO_CONTENT or not resposta.content:
                return {}
            return dict(resposta.json().get("data") or {})
        erros = (
            " ".join(str(e) for e in (resposta.json().get("errors") or []))
            if (resposta.content)
            else ""
        )
        if resposta.status_code == STATUS_AUSENTE or "not found" in erros:
            raise ChaveAusenteError(nome)
        if "message authentication failed" in erros or "invalid ciphertext" in erros:
            raise TokenInvalidoError(nome)
        if resposta.status_code == STATUS_PROIBIDO and not self.existe_chave(nome):
            raise ChaveAusenteError(nome)
        raise CofreError(f"vault respondeu {resposta.status_code}")

    def criar_chave(self, nome: str) -> None:
        """Cria a chave `aes256-gcm96`, exportação proibida (idempotente).

        Args:
            nome: Nome da chave.
        """
        resposta = self._chamar("POST", f"keys/{nome}", {"type": "aes256-gcm96"})
        self._dados(resposta, nome)

    def existe_chave(self, nome: str) -> bool:
        """Diz se a chave existe.

        Args:
            nome: Nome da chave.

        Returns:
            Verdadeiro se existir.
        """
        resposta = self._chamar("GET", f"keys/{nome}")
        if resposta.status_code == httpx.codes.OK:
            return True
        if resposta.status_code == STATUS_AUSENTE:
            return False
        raise CofreError(f"vault respondeu {resposta.status_code}")

    def cifrar(self, nome: str, dados: bytes) -> str:
        """Cifra com a versão corrente da chave.

        Args:
            nome: Nome da chave.
            dados: Bytes em claro.

        Returns:
            Token `vault:v<n>:...`.
        """
        corpo = {"plaintext": base64.b64encode(dados).decode()}
        return str(self._dados(self._chamar("POST", f"encrypt/{nome}", corpo), nome)["ciphertext"])

    def decifrar(self, nome: str, token: str) -> bytes:
        """Decifra o token.

        Args:
            nome: Nome da chave.
            token: Token de `cifrar`.

        Returns:
            Bytes em claro.
        """
        dados = self._dados(self._chamar("POST", f"decrypt/{nome}", {"ciphertext": token}), nome)
        return base64.b64decode(dados["plaintext"])

    def rotacionar(self, nome: str) -> None:
        """Cria uma versão nova da chave.

        Args:
            nome: Nome da chave.
        """
        self._dados(self._chamar("POST", f"keys/{nome}/rotate"), nome)

    def recifrar(self, nome: str, token: str) -> str:
        """Rewrap no próprio Vault (o conteúdo não sai em claro).

        Args:
            nome: Nome da chave.
            token: Token antigo.

        Returns:
            Token novo.
        """
        dados = self._dados(self._chamar("POST", f"rewrap/{nome}", {"ciphertext": token}), nome)
        return str(dados["ciphertext"])

    def destruir_chave(self, nome: str) -> None:
        """Libera a exclusão e apaga a chave (sem erro se não existir).

        Args:
            nome: Nome da chave.
        """
        if not self.existe_chave(nome):
            return
        try:
            self._dados(
                self._chamar("POST", f"keys/{nome}/config", {"deletion_allowed": True}), nome
            )
        except ChaveAusenteError:
            return
        self._dados(self._chamar("DELETE", f"keys/{nome}"), nome)


COFRE_MEMORIA_COMPARTILHADO = CofreMemoria()


def criar_cofre(settings: Settings) -> Cofre:
    """Escolhe a implementação pelo `cofre_backend` da configuração.

    O cofre em memória é um só por processo Python, para a API, o worker e os testes verem as
    mesmas chaves; ele é recusado em produção.

    Sem `LUPA_VAULT_ROLE_ID`/`LUPA_VAULT_SECRET_ID` (Vault ainda não inicializado), o cofre é
    criado assim mesmo e cada operação falha com `CofreError` no login; a API sobe e responde
    à saúde, mas não lê nem grava conteúdo de autos.

    Args:
        settings: Configuração.

    Returns:
        Cofre Vault ou em memória.

    Raises:
        CofreError: Backend em memória em produção.
    """
    if settings.cofre_backend == "memoria":
        if settings.ambiente == "producao":
            raise CofreError("cofre em memória recusado em produção")
        return COFRE_MEMORIA_COMPARTILHADO
    role_id = settings.vault_role_id.get_secret_value() if settings.vault_role_id else ""
    secret_id = settings.vault_secret_id.get_secret_value() if settings.vault_secret_id else ""
    return CofreVault(
        settings.vault_endereco,
        role_id,
        secret_id,
        montagem=settings.vault_transit_montagem,
        timeout=settings.vault_timeout_segundos,
    )
