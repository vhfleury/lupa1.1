"""Recusa do backup por falta de espaço (Etapa 7.10, revisão 7.1-7.9, item 5).

Força a estimativa com ``LUPA_BACKUP_ESTIMATIVA_BYTES`` (1 EB): o espaço exigido
(2 x estimativa + 2 GB) passa de qualquer disco, e o script tem de recusar antes de medir o banco,
gerar a chave do mês ou abrir a área de trabalho. Nada é lido do banco nem do bucket.

Só roda no host com Docker e ``LUPA_VERIFICAR_BACKUP=1``, como o teste de restauração.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integracao, pytest.mark.backup]

RAIZ = Path(__file__).resolve().parents[2]
UM_EXABYTE = str(10**18)

if os.environ.get("LUPA_VERIFICAR_BACKUP") != "1":
    pytest.skip("defina LUPA_VERIFICAR_BACKUP=1 (host com Docker)", allow_module_level=True)
if shutil.which("docker") is None:
    pytest.fail("LUPA_VERIFICAR_BACKUP=1 exige Docker no host", pytrace=False)


def _comando_backup() -> list[str]:
    if sys.platform == "win32":
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(RAIZ / "scripts" / "backup.ps1")]  # fmt: skip
    return ["bash", str(RAIZ / "scripts" / "backup.sh")]


def test_backup_recusa_sem_o_dobro_da_estimativa_livre(tmp_path: Path) -> None:
    """Estimativa forçada acima do disco: sai com erro, registra a recusa e não grava nada."""
    backups, chaves = tmp_path / "backups", tmp_path / "chaves"
    backups.mkdir()
    chaves.mkdir()
    env = os.environ | {
        "LUPA_BACKUP_DIR": backups.as_posix(),
        "LUPA_BACKUP_CHAVES_DIR": chaves.as_posix(),
        "LUPA_BACKUP_ESTIMATIVA_BYTES": UM_EXABYTE,
    }
    resultado = subprocess.run(  # noqa: S603 - comando fixo do teste
        _comando_backup(), cwd=RAIZ, env=env, capture_output=True, text=True,
        encoding="utf-8", check=False,
    )  # fmt: skip
    assert resultado.returncode != 0, resultado.stdout
    assert "espaco livre insuficiente" in resultado.stderr
    assert sorted(p.name for p in backups.iterdir()) == ["backup.log"]
    log = (backups / "backup.log").read_text(encoding="utf-8")
    assert f"estimativa_bytes={UM_EXABYTE}" in log and "RECUSADO" in log
    assert list(chaves.iterdir()) == []
