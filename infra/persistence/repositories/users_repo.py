from sqlalchemy.orm import Session
from infra.persistence.models import UserModel

class UsersRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_username(self, username: str):
        return self.db.query(UserModel).filter(UserModel.username == username).first()

    def get_by_id(self, user_id: str):
        return self.db.query(UserModel).filter(UserModel.id == user_id).first()

    def list_all(self):
        return self.db.query(UserModel).order_by(UserModel.username.asc()).all()

    def save(self, user: UserModel):
        self.db.add(user)
        self.db.flush()
        self.db.refresh(user)
        return user
