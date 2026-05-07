"""Database engine factory for JIP Data Core connection."""

import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

log = structlog.get_logger()

_REQUIRED_ENV_VARS = [
    "JIP_DB_HOST",
    "JIP_DB_PORT",
    "JIP_DB_NAME",
    "JIP_DB_USER",
    "JIP_DB_PASSWORD",
]


def _validate_env() -> dict[str, str]:
    missing = [v for v in _REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        log.error("missing_env_vars", vars=missing)
        sys.exit(f"FATAL: Missing required environment variables: {', '.join(missing)}")

    config = {v: os.environ[v] for v in _REQUIRED_ENV_VARS}
    config["JIP_DB_SSL_MODE"] = os.environ.get("JIP_DB_SSL_MODE", "require")
    config["JIP_DB_SSL_CA_PATH"] = os.environ.get("JIP_DB_SSL_CA_PATH", "")

    if config["JIP_DB_SSL_MODE"] in ("verify-ca", "verify-full"):
        ca_path = Path(config["JIP_DB_SSL_CA_PATH"])
        if not ca_path.exists():
            sys.exit(f"FATAL: SSL CA file not found at {ca_path.resolve()}")

    return config


def get_engine() -> Engine:
    config = _validate_env()

    sslmode = config["JIP_DB_SSL_MODE"]
    ssl_params = f"?sslmode={sslmode}"
    if config["JIP_DB_SSL_CA_PATH"] and sslmode in ("verify-ca", "verify-full"):
        ssl_params += f"&sslrootcert={config['JIP_DB_SSL_CA_PATH']}"

    url = (
        f"postgresql+psycopg2://{quote_plus(config['JIP_DB_USER'])}:"
        f"{quote_plus(config['JIP_DB_PASSWORD'])}@"
        f"{config['JIP_DB_HOST']}:{config['JIP_DB_PORT']}/"
        f"{config['JIP_DB_NAME']}"
        f"{ssl_params}"
    )

    engine = create_engine(
        url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )

    log.info(
        "engine_created",
        host=config["JIP_DB_HOST"],
        db=config["JIP_DB_NAME"],
        user=config["JIP_DB_USER"],
    )
    return engine


def sanity_check() -> None:
    engine = get_engine()
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
        db_name = conn.execute(text("SELECT current_database()")).scalar()

    log.info("sanity_check_passed", version=version, database=db_name)
    print(f"✓ Connected successfully")
    print(f"  PostgreSQL: {version}")
    print(f"  Database:   {db_name}")


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    sanity_check()
