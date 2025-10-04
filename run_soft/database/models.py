from database.base_models import BaseModel
from sqlalchemy import String, Boolean
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy import Integer
import re


class Base(DeclarativeBase):
    pass


class SoftBaseModel(BaseModel):
    __tablename__ = "klok_base"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)