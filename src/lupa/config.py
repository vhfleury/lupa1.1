"""Leitura e validação da configuração do Lupa por variáveis de ambiente."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    """Configuração da aplicação; falha na criação se faltar variável obrigatória."""

    model_config = SettingsConfigDict(env_prefix="LUPA_", extra="ignore")

    ambiente: str = Field(default="producao", pattern="^(producao|desenvolvimento|teste)$")
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR)$")
    database_url: SecretStr
    minio_endpoint: str = Field(min_length=1)
    minio_bucket: str = Field(min_length=3)
    minio_access_key: SecretStr
    minio_secret_key: SecretStr
    minio_secure: bool = False
    timeout_saude_segundos: float = Field(default=2.0, gt=0)
    db_usuario_app: str | None = None
    db_senha_app: SecretStr | None = None
    geoip_caminho: Path | None = None
    storage_backend: Literal["s3", "memoria"] = "s3"
    storage_regiao: str = "us-east-1"
    redis_url: SecretStr = SecretStr("redis://redis:6379/0")
    fila_ingestao: str = "ingestao"
    upload_limite_bytes: int = Field(default=512 * 1024 * 1024, gt=0)
    ingestao_dir_temporario: Path | None = None
    sandbox_memoria_mb: int = Field(default=1024, ge=64)
    sandbox_cpu_segundos: int = Field(default=60, ge=1)
    sandbox_tempo_segundos: float = Field(default=120.0, gt=0)
    zip_max_entradas: int = Field(default=2000, ge=1)
    zip_max_razao: float = Field(default=100.0, gt=1)
    zip_max_descomprimido_bytes: int = Field(default=4 * 1024 * 1024 * 1024, gt=0)
    lease_segundos: int = Field(default=300, ge=1)
    max_tentativas: int = Field(default=3, ge=1)
    max_retentativas: int = Field(default=2, ge=0)
    extracao_paginas_por_lote: int = Field(default=8, ge=1)
    extracao_lotes_por_job: int = Field(default=4, ge=1)
    extracao_lotes_por_gabinete: int = Field(default=4, ge=1)
    extracao_fatia_paginas: int = Field(default=400, ge=0)
    modelo: str = Field(default="claude-opus-5-5", min_length=1)
    agente_max_paginas_originais: int = Field(default=20, ge=0)
    agente_max_caracteres_pergunta: int = Field(default=2000, ge=10)
    agente_max_tokens_chamada: int = Field(default=200_000, ge=1)
    agente_max_tokens_conversa: int = Field(default=1_000_000, ge=1)
    agente_max_tokens_processo: int = Field(default=5_000_000, ge=1)
    agente_max_turnos: int = Field(default=12, ge=1)
    agente_max_resumos_dossie: int = Field(default=10, ge=0)
    cofre_backend: Literal["vault", "memoria"] = "vault"
    vault_endereco: str = "http://vault:8200"
    vault_role_id: SecretStr | None = None
    vault_secret_id: SecretStr | None = None
    vault_transit_montagem: str = "transit"
    vault_timeout_segundos: float = Field(default=5.0, gt=0)
    busca_max_paginas: int = Field(default=5000, ge=1)
    # Etapa 8.1: token do Prometheus para GET /metricas/servico (sem ele, a rota responde 404).
    metricas_token: SecretStr | None = None

    def url_banco_aplicacao(self) -> str:
        """URL usada pela API em tempo de execução.

        Com `LUPA_DB_USUARIO_APP` e `LUPA_DB_SENHA_APP` definidos, troca o usuário de
        `database_url` (dono das tabelas, usado nas migrações) pelo usuário de conexão sem
        superusuário, membro de `lupa_app`. Sem eles, usa `database_url` como está.

        Returns:
            URL do banco para a aplicação.
        """
        url = self.database_url.get_secret_value()
        if not self.db_usuario_app or self.db_senha_app is None:
            return url
        return (
            make_url(url)
            .set(username=self.db_usuario_app, password=self.db_senha_app.get_secret_value())
            .render_as_string(hide_password=False)
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna a configuração carregada uma única vez.

    Returns:
        A instância de `Settings` validada.
    """
    return Settings()
