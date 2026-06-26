import infra.persistence.models  # noqa: F401
from infra.persistence.db import Base, engine

def main():
    Base.metadata.create_all(bind=engine)
    print("GP.TIME.1A aplicada com sucesso.")

if __name__ == "__main__":
    main()