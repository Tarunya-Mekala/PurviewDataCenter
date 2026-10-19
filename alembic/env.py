from logging.config import fileConfig
from pathlib import Path
import sys

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alembic import context
from alembic.script import ScriptDirectory

from app.core.config import settings
from app.core.database import Base, engine

# Import all models so Alembic detects all tables and metadata
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

if settings.DATABASE_URL:
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


def process_revision_directives(context, revision, directives):
    """Ensure revisions are named sequentially: 001, 002, 003, etc."""
    if not directives:
        return
    migration_script = directives[0]
    head_revision = ScriptDirectory.from_config(context.config).get_current_head()

    if head_revision is None:
        new_rev_id = 1
    else:
        try:
            last_rev_id = int(head_revision.lstrip("0") or "0")
            new_rev_id = last_rev_id + 1
        except ValueError:
            new_rev_id = 1

    migration_script.rev_id = f"{new_rev_id:03d}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = str(engine.url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=engine.url.drivername.startswith("sqlite"),
        process_revision_directives=process_revision_directives,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    is_sqlite = engine.url.drivername.startswith("sqlite")
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=is_sqlite,
            process_revision_directives=process_revision_directives,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
