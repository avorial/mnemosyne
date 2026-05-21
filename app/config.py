import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"required env var {name} is not set")
    return value


@dataclass(frozen=True)
class Config:
    secret_key: str
    magic_link_email: str
    base_url: str

    db_path: Path
    vault_personal_path: Path
    vault_work_path: Path
    secrets_path: Path

    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str

    asana_pat_file: Path

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def asana_pat(self) -> str:
        """Read the Asana PAT from disk on each call.

        Tiny file, cheap read, never cached so rotating the secret on disk
        takes effect without a restart.
        """
        if not self.asana_pat_file.exists():
            return ""
        return self.asana_pat_file.read_text().strip()


def load() -> Config:
    return Config(
        secret_key=_required("SECRET_KEY"),
        magic_link_email=_required("MAGIC_LINK_EMAIL").lower().strip(),
        base_url=_required("BASE_URL").rstrip("/"),
        db_path=Path(os.environ.get("DB_PATH", "/mnt/mnemosyne/mnemosyne.db")),
        vault_personal_path=Path(os.environ.get("VAULT_PERSONAL_PATH", "/mnt/mnemosyne/vault-notes")),
        vault_work_path=Path(os.environ.get("VAULT_WORK_PATH", "/mnt/mnemosyne/vault-work")),
        secrets_path=Path(os.environ.get("SECRETS_PATH", "/mnt/mnemosyne/secrets")),
        smtp_host=os.environ.get("SMTP_HOST", ""),
        smtp_port=int(os.environ.get("SMTP_PORT", "587")),
        smtp_user=os.environ.get("SMTP_USER", ""),
        smtp_password=os.environ.get("SMTP_PASSWORD", ""),
        smtp_from=os.environ.get("SMTP_FROM", ""),
        asana_pat_file=Path(os.environ.get("ASANA_PAT_FILE", "/mnt/mnemosyne/secrets/asana_pat")),
    )


config = load()
