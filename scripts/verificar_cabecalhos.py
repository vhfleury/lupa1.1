"""Varredura dos cabeçalhos de segurança do proxy (Etapa 6.10).

Uso: `python scripts/verificar_cabecalhos.py [--url https://proxy:8443] [--exigir]`.

Pede algumas rotas (SPA, arquivo estático e API) e falha (saída 1) se faltar algum cabeçalho
obrigatório ou se a CSP afrouxar: `unsafe-inline`/`unsafe-eval`, curinga, `data:`/`blob:`/http
em script, estilo inline sem nonce/hash, ou diretivas de bloqueio ausentes. Sem `--exigir`, proxy
inacessível só gera aviso (saída 0): o passo roda em `verificar.sh` mesmo sem a stack no ar. O
certificado de desenvolvimento é autoassinado; a conferência do certificado fica desligada aqui
porque o que se testa são os cabeçalhos, não o TLS.
"""

import ssl
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence

URL_PADRAO = "https://proxy:8443"
ROTAS = ("/", "/login", "/inicio.js", "/api/saude")
OBRIGATORIOS: dict[str, str | None] = {
    "content-security-policy": None,
    "strict-transport-security": None,
    "permissions-policy": None,
    "cross-origin-opener-policy": "same-origin",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
}
PROIBIDOS_SEMPRE = ("'unsafe-inline'", "'unsafe-eval'", "'unsafe-hashes'", "*", "data:", "http:")
ESTILO_ANUNCIADOR = "'sha256-S8qMpvofolR8Mpjy4kQvEm7m1q8clzU4dfDH0AmvZjo='"
DIRETIVAS_EXATAS = {
    "default-src": {"'none'"},
    "script-src": {"'self'"},
    "object-src": {"'none'"},
    "frame-ancestors": {"'none'"},
    "base-uri": {"'none'"},
    # Só o estilo fixo do anunciador de rota do SvelteKit (aria-live), por hash (6.10).
    "style-src": {"'self'", "'unsafe-hashes'", ESTILO_ANUNCIADOR},
}
MIN_HSTS = 15_552_000  # 180 dias


def ler_csp(valor: str) -> dict[str, list[str]]:
    """Interpreta a CSP em diretiva → fontes.

    Args:
        valor: Valor do cabeçalho.

    Returns:
        Mapa de diretivas (minúsculas) para a lista de fontes.
    """
    diretivas: dict[str, list[str]] = {}
    for parte in valor.split(";"):
        itens = parte.split()
        if itens:
            diretivas[itens[0].lower()] = itens[1:]
    return diretivas


def problemas_csp(valor: str) -> list[str]:
    """Problemas da CSP em relação à política mínima do Lupa.

    Args:
        valor: Valor do cabeçalho `Content-Security-Policy`.

    Returns:
        Lista de problemas (vazia se a CSP está ao menos tão restrita quanto a exigida).
    """
    csp = ler_csp(valor)
    erros: list[str] = []
    for diretiva, esperado in DIRETIVAS_EXATAS.items():
        if set(csp.get(diretiva, [])) != esperado:
            erros.append(f"CSP {diretiva} deve ser {' '.join(sorted(esperado))}")
    for diretiva, fontes in csp.items():
        for proibido in PROIBIDOS_SEMPRE:
            if proibido == "'unsafe-hashes'" and diretiva == "style-src":
                continue  # conferido acima: só junto do hash fixo do anunciador
            if proibido in fontes:
                erros.append(f"CSP {diretiva} tem {proibido}")
        if diretiva.startswith(("script-src", "style-src")) and (
            "blob:" in fontes or any(f.startswith(("http", "https:")) for f in fontes)
        ):
            erros.append(f"CSP {diretiva} aceita origem externa")
    estilo = csp.get("style-src", csp.get("default-src", []))
    if not estilo:
        erros.append("CSP sem style-src")
    if "form-action" not in csp:
        erros.append("CSP sem form-action")
    return erros


def problemas(cabecalhos: Mapping[str, str]) -> list[str]:
    """Problemas de um conjunto de cabeçalhos de resposta.

    Args:
        cabecalhos: Cabeçalhos (nomes em qualquer caixa).

    Returns:
        Lista de problemas encontrados.
    """
    normal = {nome.lower(): valor for nome, valor in cabecalhos.items()}
    erros: list[str] = []
    for nome, esperado in OBRIGATORIOS.items():
        valor = normal.get(nome)
        if valor is None:
            erros.append(f"falta {nome}")
        elif esperado is not None and valor.strip() != esperado:
            erros.append(f"{nome} deve ser {esperado}, veio {valor}")
    if "content-security-policy" in normal:
        erros.extend(problemas_csp(normal["content-security-policy"]))
    hsts = normal.get("strict-transport-security", "")
    idade = [
        p.split("=", 1)[1] for p in hsts.replace(" ", "").split(";") if p.startswith("max-age=")
    ]
    if hsts and (not idade or not idade[0].isdigit() or int(idade[0]) < MIN_HSTS):
        erros.append("strict-transport-security com max-age menor que 180 dias")
    permissoes = normal.get("permissions-policy", "")
    for recurso in ("camera", "microphone", "geolocation"):
        if permissoes and f"{recurso}=()" not in permissoes.replace(" ", ""):
            erros.append(f"permissions-policy não bloqueia {recurso}")
    if "server" in normal:
        erros.append("cabeçalho server exposto")
    return erros


def _buscar(url: str) -> dict[str, str]:
    contexto = ssl.create_default_context()
    contexto.check_hostname = False
    contexto.verify_mode = ssl.CERT_NONE
    pedido = urllib.request.Request(url, method="GET")  # noqa: S310
    try:
        with urllib.request.urlopen(pedido, timeout=5, context=contexto) as resposta:  # noqa: S310
            return dict(resposta.headers.items())
    except urllib.error.HTTPError as erro:
        return dict(erro.headers.items())


def main(argumentos: Sequence[str]) -> int:
    """Ponto de entrada.

    Args:
        argumentos: Argumentos da linha de comando (sem o nome do programa).

    Returns:
        0 sem problemas (ou proxy fora do ar sem `--exigir`), 1 com problemas.
    """
    base = URL_PADRAO
    if "--url" in argumentos:
        base = argumentos[list(argumentos).index("--url") + 1]
    exigir = "--exigir" in argumentos
    total = 0
    for rota in ROTAS:
        try:
            cabecalhos = _buscar(base.rstrip("/") + rota)
        except (urllib.error.URLError, OSError) as erro:
            if not exigir:
                sys.stdout.write(f"cabecalhos: proxy indisponivel em {base} ({erro}); pulado\n")
                return 0
            sys.stdout.write(f"cabecalhos: falha ao buscar {rota}: {erro}\n")
            return 1
        for problema in problemas(cabecalhos):
            sys.stdout.write(f"cabecalhos: {rota}: {problema}\n")
            total += 1
    if total:
        return 1
    sys.stdout.write(f"cabecalhos: ok em {len(ROTAS)} rotas de {base}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
