"""Cria o único administrador do Lupa a partir de variáveis de ambiente, se ainda não existir.

Uso (no contêiner): `LUPA_ADMIN_USUARIO=... LUPA_ADMIN_SENHA=... python scripts/criar_admin.py`.
A senha precisa seguir a política (12+ caracteres, fora da lista comum) e será trocada no
primeiro acesso; o MFA é cadastrado no primeiro login.
"""

import os
import sys

from lupa.acesso.instalacao import criar_admin
from lupa.config import get_settings
from lupa.logging import configurar_logging

if __name__ == "__main__":
    configurar_logging()
    sys.exit(criar_admin(get_settings(), os.environ))
