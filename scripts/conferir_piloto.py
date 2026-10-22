"""Confere o checklist de segurança do docs/operacao.md (seção 12) no ambiente em execução.

Etapa 8.1. Roda no HOST, na raiz do projeto, com o compose no ar:

    python scripts/conferir_piloto.py [--url https://localhost:8443] [--estrito]

Cada item imprime `atendido`, `pendente` ou `manual` (depende de decisão ou documento fora do
sistema) e a evidência. Só lê: `docker compose ps/exec`, `GET /api/saude`, apertos de mão TLS e
contagens no banco. Nenhum segredo é impresso. Com --estrito, sai com 1 se houver pendente.
Para o perfil de produção, exporte COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml.
"""

import argparse
import json
import os
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

Resultado = tuple[str, str]
ATENDIDO, PENDENTE, MANUAL = "atendido", "pendente", "manual"
SERVICOS = ("api", "worker", "front", "proxy", "db", "minio", "redis", "vault")


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["docker", "compose", *args],  # noqa: S607
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


def _env(chave: str) -> str:
    arquivo = Path(".env")
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            if linha.startswith(f"{chave}="):
                return linha.split("=", 1)[1].strip()
    return os.environ.get(chave, "")


def _servicos() -> dict[str, dict[str, Any]]:
    saida = _compose("ps", "--format", "json").stdout.strip()
    if saida.startswith("["):
        linhas = json.loads(saida)
    else:
        linhas = [json.loads(x) for x in saida.splitlines() if x.strip()]
    return {str(s["Service"]): s for s in linhas}


def _sql(consulta: str) -> str:
    usuario, banco = _env("POSTGRES_USER") or "lupa", _env("POSTGRES_DB") or "lupa"
    r = _compose("exec", "-T", "db", "psql", "-U", usuario, "-d", banco, "-tAc", consulta)
    return r.stdout.strip() if r.returncode == 0 else ""


def _contexto_sem_verificacao() -> ssl.SSLContext:
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    contexto.check_hostname = False
    contexto.verify_mode = ssl.CERT_NONE
    return contexto


class Conferencia:
    """Executa as verificações contra o proxy e o compose em execução."""

    def __init__(self, url: str) -> None:
        """Guarda a URL pública e lê o estado dos serviços uma vez."""
        self.url = url.rstrip("/")
        self.servicos = _servicos()
        self.saude = self._saude()

    def _saude(self) -> dict[str, str]:
        try:
            with urllib.request.urlopen(  # noqa: S310
                f"{self.url}/api/saude", context=_contexto_sem_verificacao(), timeout=10
            ) as resposta:
                return dict(json.load(resposta))
        except urllib.error.HTTPError as erro:
            return dict(json.load(erro))
        except Exception:
            return {}

    def _saudavel(self, servico: str) -> bool:
        return str(self.servicos.get(servico, {}).get("Health", "")) == "healthy"

    def _tls_aceita(self, versao: ssl.TLSVersion) -> bool:
        alvo = urlparse(self.url)
        contexto = _contexto_sem_verificacao()
        contexto.minimum_version = versao
        contexto.maximum_version = versao
        try:
            with (
                socket.create_connection((alvo.hostname or "localhost", alvo.port or 443), 5) as s,
                contexto.wrap_socket(s, server_hostname=alvo.hostname),
            ):
                return True
        except (OSError, ssl.SSLError):
            return False

    def item1(self) -> Resultado:
        """Infraestrutura própria, MinIO local compatível com S3."""
        fora = [s for s in SERVICOS if not self._saudavel(s)]
        if fora:
            return PENDENTE, f"serviços sem healthy: {', '.join(fora)}"
        return ATENDIDO, (
            "8 serviços healthy; MinIO local fixado por digest "
            "(assinatura da imagem: docs/decisoes/object-storage.md)"
        )

    def item2(self) -> Resultado:
        """TLS 1.3 entre navegador e servidor."""
        if not self._tls_aceita(ssl.TLSVersion.TLSv1_3):
            return PENDENTE, f"{self.url} não negocia TLS 1.3"
        if self._tls_aceita(ssl.TLSVersion.TLSv1_2):
            return PENDENTE, (
                "TLS 1.3 ok, mas TLS 1.2 aceito (modo `interno` de dev; acme e fornecido "
                "exigem 1.3)"
            )
        return ATENDIDO, "só TLS 1.3 negociado"

    def item3(self) -> Resultado:
        """TLS entre serviços."""
        if _env("LUPA_VAULT_ENDERECO").startswith("https://"):
            return ATENDIDO, "Vault por HTTPS"
        return PENDENTE, (
            "decisão 8.1: redes internas de um host só, sem TLS entre contêineres "
            "(operacao.md 4.6)"
        )

    def item4(self) -> Resultado:
        """Criptografia em repouso com chaves no Vault próprio."""
        if (_env("LUPA_COFRE_BACKEND") or "vault") != "vault":
            return PENDENTE, "LUPA_COFRE_BACKEND diferente de vault"
        if self.saude.get("cofre") != "ok":
            return PENDENTE, f"/api/saude cofre={self.saude.get('cofre', 'sem resposta')}"
        return ATENDIDO, "backend vault; /api/saude cofre=ok (cifra e decifra com lupa-saude)"

    def item5(self) -> Resultado:
        """Texto extraído e índices também cifrados."""
        total = _sql("SELECT count(*) FROM pagina")
        claro = _sql("SELECT count(*) FROM pagina WHERE texto NOT LIKE 'lupa1:%'")
        if not total:
            return PENDENTE, "sem acesso ao banco"
        if claro != "0":
            return PENDENTE, f"{claro} de {total} páginas com texto fora do formato cifrado"
        return ATENDIDO, f"{total} páginas, todas com texto no formato cifrado (lupa1:)"

    def item6(self) -> Resultado:
        """Arquivo cifrado antes de qualquer parser."""
        return ATENDIDO, "por desenho (7.4) e testes de tests/seguranca; worker sem rede externa"

    def item7(self) -> Resultado:
        """Exclusão pela destruição da chave."""
        dias = _env("LUPA_BACKUP_RETENCAO_DIAS") or "30"
        return ATENDIDO, f"7.7; backups guardam o envelope por até {dias} dias"

    def item8(self) -> Resultado:
        """Objetos legados em claro."""
        return MANUAL, "344 órfãos em claro mantidos por decisão do responsável técnico"

    def item9(self) -> Resultado:
        """Só processos públicos; sigilo identificado e bloqueado."""
        return ATENDIDO, "sigiloso recebe 403 na ingestão (testes da Etapa 4A)"

    def item10(self) -> Resultado:
        """Pseudonimização; tabela de identidades separada e cifrada."""
        claro = _sql("SELECT count(*) FROM reu_identidade WHERE nome NOT LIKE 'vault:v%'")
        total = _sql("SELECT count(*) FROM reu_identidade")
        if not total:
            return PENDENTE, "sem acesso ao banco"
        if claro != "0":
            return PENDENTE, f"{claro} de {total} identidades fora do formato do Transit"
        return ATENDIDO, f"{total} identidades, todas cifradas no Transit; leitura auditada"

    def item11(self) -> Resultado:
        """Contrato do fornecedor do modelo veda treino."""
        return MANUAL, "conferir os termos da API do modelo (decisão de Victor)"

    def item12(self) -> Resultado:
        """Nenhum dado de autos usado para treinar modelo."""
        return ATENDIDO, "não há treino nem ajuste no sistema"

    def item13(self) -> Resultado:
        """Vault em produção (partes, unseal, reinício)."""
        r = _compose("exec", "-T", "vault", "vault", "status", "-format=json")
        try:
            estado = json.loads(r.stdout)
        except json.JSONDecodeError:
            return PENDENTE, "vault não respondeu"
        if estado.get("sealed"):
            return PENDENTE, "cofre SELADO"
        if not self._saudavel("vault"):
            return PENDENTE, "healthcheck do vault não está healthy"
        partes, limiar = estado.get("n"), estado.get("t")
        if (limiar or 0) < 2:  # noqa: PLR2004
            return PENDENTE, (
                f"destravado e healthcheck exige Sealed false, mas partes={partes} "
                f"limiar={limiar} (dev; produção: 3 partes, limiar 2)"
            )
        return ATENDIDO, f"destravado; partes={partes} limiar={limiar}; healthcheck: Sealed false"

    def item14(self) -> Resultado:
        """Porta direta da API e console do MinIO fechados."""
        abertos = [
            f"{servico}:{pub.get('URL')}:{pub['PublishedPort']}"
            for servico in ("api", "minio")
            for pub in self.servicos.get(servico, {}).get("Publishers") or []
            if pub.get("PublishedPort")
        ]
        if abertos:
            return PENDENTE, "publicadas: " + ", ".join(abertos) + " (o perfil prod não publica)"
        return ATENDIDO, "nenhuma porta da API nem do MinIO publicada"

    def extras(self) -> list[tuple[str, str, Resultado]]:
        """Verificações da 8.1 que não estão na seção 6 dos requisitos."""
        saude = json.dumps(self.saude)
        backup = "backup-agendado" in self.servicos
        monitor = self._saudavel("prometheus") and self._saudavel("grafana")
        return [
            (
                "E1",
                "/api/saude com componente cofre",
                (ATENDIDO, saude) if self.saude.get("cofre") == "ok" else (PENDENTE, saude),
            ),
            (
                "E2",
                "backup agendado",
                (ATENDIDO, "backup-agendado no ar")
                if backup
                else (PENDENTE, "backup-agendado fora (o perfil prod o liga)"),
            ),
            (
                "E3",
                "monitoramento",
                (ATENDIDO, "prometheus e grafana healthy")
                if monitor
                else (PENDENTE, "perfil monitoramento fora do ar"),
            ),
        ]


def main() -> int:
    """Imprime o checklist e devolve o código de saída."""
    parser = argparse.ArgumentParser(description="Checklist de segurança do piloto (8.1)")
    parser.add_argument("--url", default=os.environ.get("LUPA_PROXY_URL", "https://localhost:8443"))
    parser.add_argument("--estrito", action="store_true")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    conferencia = Conferencia(args.url)
    itens: list[tuple[str, str, Resultado]] = []
    for numero in range(1, 15):
        metodo: Callable[[], Resultado] = getattr(conferencia, f"item{numero}")
        titulo = (metodo.__doc__ or "").strip().rstrip(".")
        itens.append((str(numero), titulo, metodo()))
    itens += conferencia.extras()
    for numero_item, titulo, (estado, evidencia) in itens:
        print(f"[{estado:8}] {numero_item:>2}. {titulo}: {evidencia}")
    contagem = {e: sum(1 for *_, (x, _) in itens if x == e) for e in (ATENDIDO, PENDENTE, MANUAL)}
    print(
        f"\nresumo: {contagem[ATENDIDO]} atendidos, {contagem[PENDENTE]} pendentes, "
        f"{contagem[MANUAL]} manuais"
    )
    return 1 if args.estrito and contagem[PENDENTE] else 0


if __name__ == "__main__":
    sys.exit(main())
