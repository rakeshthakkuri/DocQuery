from sqlalchemy import Column, String
from database import Base 

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, index=True)  # Google sub (subject)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    picture = Column(String)

    def __repr__(self):
        return f"<User(id='{self.id}', email='{self.email}')>"