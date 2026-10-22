"""Restauração do backup cifrado em ambiente limpo (Etapa 7.8).

Pelo caminho documentado em ``docs/backup.md``: ingere um processo sintético pequeno num banco e
num bucket de teste, roda ``scripts/backup.ps1`` (Windows) ou ``scripts/backup.sh``, apaga o banco
e o bucket, restaura com ``scripts/restaurar.*`` em banco e bucket novos e confere, linha a linha
(impressão de cada tabela) e byte a byte (SHA-256 de cada objeto), que tudo voltou. Por fim, o
expurgo com o relógio 31 dias à frente apaga o backup e destrói a chave do mês, com registro
encadeado no log.

Só roda no host com Docker e ``LUPA_VERIFICAR_BACKUP=1`` (passo opcional do ``verificar.ps1``);
dentro do contêiner da API não há Docker e o teste é pulado.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.integracao, pytest.mark.backup]

RAIZ = Path(__file__).resolve().parents[2]
TABELAS = ("processo", "arquivo", "pagina", "peca", "evidencia", "fato", "achado", "reu")
ESTADOS_OK = {"concluido", "em_revisao"}
CABECALHO_AGE = b"age-encryption.org/v1"

if os.environ.get("LUPA_VERIFICAR_BACKUP") != "1":
    pytest.skip("defina LUPA_VERIFICAR_BACKUP=1 (host com Docker)", allow_module_level=True)
if shutil.which("docker") is None:
    pytest.fail("LUPA_VERIFICAR_BACKUP=1 exige Docker no host", pytrace=False)


def _rodar(
    comando: list[str], entrada: str | None = None, env: dict[str, str] | None = None
) -> str:
    resultado = subprocess.run(  # noqa: S603 - comandos fixos do teste
        comando, cwd=RAIZ, input=entrada, env=env, capture_output=True, text=True,
        encoding="utf-8", check=False,
    )  # fmt: skip
    if resultado.returncode != 0:
        raise AssertionError(f"{comando[:4]} falhou:\n{resultado.stdout}\n{resultado.stderr}")
    return resultado.stdout


def _sql(banco: str, consulta: str) -> str:
    return _rodar(
        ["docker", "compose", "exec", "-T", "db", "sh", "-c",
         f'psql -U "$POSTGRES_USER" -d {banco} -v ON_ERROR_STOP=1 -tAc "$0"', consulta]
    )  # fmt: skip


def _no_db(comando: str) -> None:
    _rodar(["docker", "compose", "exec", "-T", "db", "sh", "-c", comando])


def _mc(comando: str) -> str:
    preparo = (
        "export HOME=/tmp/h; mc alias set lupa http://minio:9000 "
        '"$LUPA_MINIO_ACCESS_KEY" "$LUPA_MINIO_SECRET_KEY" >/dev/null; '
    )
    return _rodar(
        ["docker", "compose", "--profile", "backup", "run", "--rm", "-T", "backup", "-c",
         preparo + comando]
    )  # fmt: skip


def _script(nome: str, env: dict[str, str], *argumentos: str) -> str:
    if sys.platform == "win32":
        comando = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                   str(RAIZ / "scripts" / f"{nome}.ps1"), *argumentos]  # fmt: skip
    else:
        comando = ["bash", str(RAIZ / "scripts" / f"{nome}.sh"), *argumentos]
    return _rodar(comando, env=env)


def _impressao(banco: str) -> dict[str, str]:
    """Contagem e md5 do texto de todas as linhas de cada tabela, em ordem de id."""
    # Nomes de tabela vêm da constante TABELAS.
    partes = [
        "SELECT '" + t + "', count(*), coalesce(md5(string_agg(x::text, ',' ORDER BY x.id)), '-') "
        "FROM " + t + " x"
        for t in TABELAS
    ]
    linhas = _sql(banco, " UNION ALL ".join(partes)).strip().splitlines()
    return {linha.split("|")[0]: linha.split("|", 1)[1] for linha in linhas}


def _objetos(bucket: str) -> str:
    """SHA-256 de cada objeto, lido em fluxo (nada gravado na camada do contêiner)."""
    return _mc(
        f"mc find lupa/{bucket} | sort | while read -r o; do "
        'printf "%s %s\n" "$(mc cat "$o" | sha256sum | cut -d" " -f1)" "${o#lupa/*/}"; done'
    )


def test_backup_cifrado_restaura_processo_em_ambiente_limpo(tmp_path: Path) -> None:
    """Backup, perda total, restauração em limpo e expurgo com destruição da chave."""
    sufixo = uuid4().hex[:8]
    banco_o, banco_d = f"lupa_bkp_o_{sufixo}", f"lupa_bkp_d_{sufixo}"
    bucket_o, bucket_d = f"lupa-bkp-o-{sufixo}", f"lupa-bkp-d-{sufixo}"
    backups, chaves = tmp_path / "backups", tmp_path / "chaves"
    backups.mkdir()
    chaves.mkdir()
    env = os.environ | {
        "LUPA_BACKUP_DIR": backups.as_posix(),
        "LUPA_BACKUP_CHAVES_DIR": chaves.as_posix(),
    }
    try:
        # 1. Banco e bucket de teste com um processo sintético ingerido pelo worker real.
        _no_db(f'createdb -U "$POSTGRES_USER" {banco_o}')
        _mc(f"mc mb lupa/{bucket_o} >/dev/null")
        semeado = _rodar(
            ["docker", "compose", "exec", "-T", "api", "sh", "-c",
             f'export LUPA_DATABASE_URL="${{LUPA_DATABASE_URL%/*}}/{banco_o}" '
             f"LUPA_MINIO_BUCKET={bucket_o}; "
             "alembic -c src/lupa/migrations/alembic.ini upgrade head >&2 && python -"],
            entrada=(Path(__file__).parent / "semear.py").read_text(encoding="utf-8"),
        )  # fmt: skip
        resultado = json.loads(semeado.strip().splitlines()[-1])
        assert resultado["estado"] in ESTADOS_OK, resultado
        antes = _impressao(banco_o)
        for tabela in ("processo", "pagina", "fato", "achado"):
            assert int(antes[tabela].split("|")[0]) > 0, f"{tabela} vazia: {antes}"
        objetos_antes = _objetos(bucket_o)
        assert objetos_antes.strip(), "bucket de teste sem objetos"

        # 2. Backup pelo script documentado: um arquivo age, nada em claro.
        nome = (
            _script("backup", env | {"LUPA_BACKUP_BANCO": banco_o, "LUPA_BACKUP_BUCKET": bucket_o})
            .strip()
            .splitlines()[-1]
        )
        arquivo = backups / nome
        assert arquivo.is_file(), nome
        conteudo = arquivo.read_bytes()
        assert conteudo.startswith(CABECALHO_AGE)
        assert b"PGDMP" not in conteudo
        # Só o .age e o log; a área de trabalho em claro (.trabalho-*) foi apagada.
        assert sorted(p.name for p in backups.iterdir()) == sorted([nome, "backup.log"])
        log_backup = (backups / "backup.log").read_text(encoding="utf-8")
        assert "estimativa_bytes=" in log_backup and "exigido_bytes=" in log_backup
        periodo = nome.split("-")[1] + "-" + nome.split("-")[2]
        assert (chaves / f"chave-{periodo}.txt").is_file()

        # 3. Perda total: banco e bucket de teste apagados.
        _no_db(f'dropdb -U "$POSTGRES_USER" --force {banco_o}')
        _mc(f"mc rb --force lupa/{bucket_o} >/dev/null")

        # 4. Restauração em banco e bucket limpos, pelo script documentado.
        _script(
            "restaurar",
            env | {"LUPA_RESTAURAR_BANCO": banco_d, "LUPA_RESTAURAR_BUCKET": bucket_d},
            nome,
        )
        assert _impressao(banco_d) == antes
        assert _objetos(bucket_d) == objetos_antes

        # 5. Expurgo 31 dias depois: o backup sai e a chave do mês, sem backup vivo, é destruída.
        daqui_31_dias = str(int(time.time()) + 31 * 86400)
        _script("expurgar_backups", env | {"LUPA_BACKUP_AGORA": daqui_31_dias})
        assert not arquivo.exists()
        assert not (chaves / f"chave-{periodo}.txt").exists()
        log = (chaves / "destruicoes.log").read_text(encoding="utf-8").strip().splitlines()
        assert len(log) == 1 and f"periodo={periodo}" in log[0]
        linha, _, hash_gravado = log[0].rpartition(" hash=")
        conteudo_linha, _, anterior = linha.rpartition(" anterior=")
        esperado = hashlib.sha256(f"{anterior}|{conteudo_linha}".encode()).hexdigest()
        assert hash_gravado == esperado
    finally:
        for banco in (banco_o, banco_d):
            _no_db(f'dropdb -U "$POSTGRES_USER" --force --if-exists {banco}')
        _mc(f"mc rb --force lupa/{bucket_o} lupa/{bucket_d} >/dev/null 2>&1 || true")
