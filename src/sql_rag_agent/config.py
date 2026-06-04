from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = ROOT / ".env"


@dataclass(frozen=True)
class LLMConfig:
    api_key: str | None = None
    base_url: str | None = None
    model: str = "gpt-4o-mini"
    enabled: bool = True

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "LLMConfig":
        env_path = Path(env_file) if env_file is not None else DEFAULT_ENV_FILE
        dotenv_config = dotenv_values(env_path) if env_path.exists() else {}
        enabled_value = (
            os.getenv("SQL_AGENT_USE_LLM")
            or dotenv_config.get("SQL_AGENT_USE_LLM")
            or "true"
        )
        return cls(
            api_key=os.getenv("OPENAI_API_KEY") or dotenv_config.get("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE") or dotenv_config.get("OPENAI_API_BASE"),
            model=(
                os.getenv("SQL_AGENT_LLM_MODEL")
                or dotenv_config.get("SQL_AGENT_LLM_MODEL")
                or os.getenv("OPENAI_MODEL")
                or dotenv_config.get("OPENAI_MODEL")
                or "gpt-5.4-nano"
            ),
            enabled=enabled_value.lower() not in {"0", "false", "no", "off"},
        )

    @property
    def is_configured(self) -> bool:
        return self.enabled and bool(self.api_key)


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = "127.0.0.1"
    port: int = 5432
    dbname: str = "datathon_2026"
    user: str = "postgres"
    password: str | None = None

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "DatabaseConfig":
        env_path = Path(env_file) if env_file is not None else DEFAULT_ENV_FILE
        dotenv_config = dotenv_values(env_path) if env_path.exists() else {}
        return cls(
            host=os.getenv("PGHOST") or dotenv_config.get("PGHOST") or "127.0.0.1",
            port=int(os.getenv("PGPORT") or dotenv_config.get("PGPORT") or "5432"),
            dbname=os.getenv("PGDATABASE") or dotenv_config.get("PGDATABASE") or "datathon_2026",
            user=os.getenv("PGUSER") or dotenv_config.get("PGUSER") or "postgres",
            password=os.getenv("PGPASSWORD") or dotenv_config.get("PGPASSWORD"),
        )

    def to_psycopg_kwargs(self) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
        }
        if self.password:
            kwargs["password"] = self.password
        return kwargs


DEFAULT_ROW_LIMIT = 100
DEFAULT_STATEMENT_TIMEOUT_MS = 5000
