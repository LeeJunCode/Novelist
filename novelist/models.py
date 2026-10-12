"""数据库模型 — 小说、角色、章节（SQLite + SQLAlchemy）"""

from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session

# === 数据库初始化 ===
DB_PATH = Path(__file__).parent.parent / "novelist.db"
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)


class Base(DeclarativeBase):
    pass


# === 模型定义 ===

class Novel(Base):
    """小说主表"""
    __tablename__ = "novels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), default="未命名")
    genre: Mapped[str] = mapped_column(String(50), default="")       # 题材
    theme: Mapped[str] = mapped_column(String(200), default="")      # 主题
    style: Mapped[str] = mapped_column(String(100), default="")      # 写作风格
    status: Mapped[str] = mapped_column(String(20), default="planning")  # planning/writing/completed
    config_json: Mapped[str] = mapped_column(Text, default="{}")     # 扩展配置 (JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    characters: Mapped[list["Character"]] = relationship(back_populates="novel", cascade="all, delete-orphan")
    chapters: Mapped[list["Chapter"]] = relationship(back_populates="novel", cascade="all, delete-orphan")


class Character(Base):
    """角色表"""
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    novel_id: Mapped[int] = mapped_column(Integer, ForeignKey("novels.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100))
    role_type: Mapped[str] = mapped_column(String(30), default="supporting")  # protagonist/antagonist/supporting
    personality: Mapped[str] = mapped_column(Text, default="")    # 性格描述
    background: Mapped[str] = mapped_column(Text, default="")     # 背景故事
    abilities: Mapped[str] = mapped_column(Text, default="")      # 能力/特长
    appearance: Mapped[str] = mapped_column(Text, default="")     # 外貌描述
    relationships: Mapped[str] = mapped_column(Text, default="")  # 人物关系

    novel: Mapped["Novel"] = relationship(back_populates="characters")


class Chapter(Base):
    """章节表"""
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    novel_id: Mapped[int] = mapped_column(Integer, ForeignKey("novels.id"), nullable=False)
    volume: Mapped[int] = mapped_column(Integer, default=1)       # 卷号
    number: Mapped[int] = mapped_column(Integer, default=1)       # 章节序号
    title: Mapped[str] = mapped_column(String(200), default="")   # 章节标题
    summary: Mapped[str] = mapped_column(Text, default="")        # 本章大纲摘要
    content: Mapped[str] = mapped_column(Text, default="")        # 正文
    word_count: Mapped[int] = mapped_column(Integer, default=0)   # 字数
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft/reviewed/approved
    version: Mapped[int] = mapped_column(Integer, default=1)      # 修改版本号
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    novel: Mapped["Novel"] = relationship(back_populates="chapters")


# === 初始化 ===
def init_db():
    """创建所有表（幂等）"""
    Base.metadata.create_all(engine)


def get_session() -> Session:
    """获取数据库会话"""
    return Session(engine)
