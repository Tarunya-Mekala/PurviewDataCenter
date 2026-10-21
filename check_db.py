from sqlalchemy import create_engine, inspect, text
from app.core.config import settings

print('Connecting to:', settings.DATABASE_URL)
try:
    engine = create_engine(settings.DATABASE_URL)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print('Tables in DB:', tables)
    for t in tables:
        with engine.connect() as conn:
            cnt = conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
            print(f'  {t}: {cnt} rows')
except Exception as e:
    print('Error:', e)
