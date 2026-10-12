"""配置管理 — 从 .env 文件和环境变量读取配置"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """全局配置，自动从 .env 和环境变量读取"""

    # DeepSeek API
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # LangFuse 可观测性（可选，不配置也能正常运行）
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # 路径
    output_dir: str = "output"
    library_dir: str = "library"
    samples_dir: str = "samples"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# 全局单例
settings = Settings()
