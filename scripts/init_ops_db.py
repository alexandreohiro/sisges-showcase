import infra.persistence.models  # noqa: F401
from sqlalchemy import inspect

from infra.persistence.db import Base, engine

def main():
    print("DB:", engine.url)
    Base.metadata.create_all(bind=engine)
    tables = inspect(engine).get_table_names()
    print("TABLES:", tables)

if __name__ == "__main__":
    main()