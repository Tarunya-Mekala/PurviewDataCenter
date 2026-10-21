from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from alembic.script import ScriptDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Base, engine
import app.models

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def process_revision_directives(migration_context, revision, directives):
    if not directives:
        return

    migration_script = directives[0]
    head_revision = ScriptDirectory.from_config(config).get_current_head()
    try:
        next_revision = int(head_revision.lstrip("0") or "0") + 1 if head_revision else 1
    except ValueError:
        next_revision = 1
    migration_script.rev_id = f"{next_revision:03d}"


def run_migrations_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=engine.url.drivername.startswith("sqlite"),
        process_revision_directives=process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=engine.url.drivername.startswith("sqlite"),
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
