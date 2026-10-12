"""
LLM 客户端 — DeepSeek API + LangFuse 可观测性

LangFuse 是可选的：配置后自动追踪每次 LLM 调用的 token 消耗、延迟、成本。
未配置时正常运行，不影响功能。
"""

from openai import OpenAI
from langchain_openai import ChatOpenAI
from novelist.config import settings


# ═══════════════════════════════════════════
# 客户端创建（含 LangFuse 追踪）
# ═══════════════════════════════════════════

_openai_client: OpenAI | None = None
_langfuse_initialized = False


def _init_langfuse():
    """初始化 LangFuse（如果已配置）"""
    global _langfuse_initialized
    if _langfuse_initialized or not settings.langfuse_enabled:
        return
    try:
        import langfuse
        langfuse.Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        _langfuse_initialized = True
        print(f"📊 LangFuse 追踪已启用")
    except Exception as e:
        print(f"⚠️  LangFuse 初始化失败: {e}")


def _get_openai_client() -> OpenAI:
    """延迟创建 OpenAI 客户端（含 LangFuse 包装）"""
    global _openai_client
    if _openai_client is None:
        if not settings.deepseek_api_key:
            raise RuntimeError("DeepSeek API Key 未设置！请在 .env 文件中设置 DEEPSEEK_API_KEY")

        _init_langfuse()

        if settings.langfuse_enabled:
            # 使用 LangFuse 包装的 OpenAI 客户端 — 自动追踪所有调用
            try:
                from langfuse.openai import OpenAI as LangfuseOpenAI
                _openai_client = LangfuseOpenAI(
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_base_url,
                )
            except Exception:
                _openai_client = OpenAI(
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_base_url,
                )
        else:
            _openai_client = OpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )
    return _openai_client


# ═══════════════════════════════════════════
# API
# ═══════════════════════════════════════════

def chat(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.8,
    max_tokens: int = 4096,
) -> str:
    """简单对话 — 发 system + user，返回文本"""
    client = _get_openai_client()
    response = client.chat.completions.create(
        model=settings.deepseek_model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content or ""


def get_chat_model(temperature: float = 0.8) -> ChatOpenAI:
    """返回 LangChain 兼容的 ChatOpenAI 实例（指向 DeepSeek）"""
    _init_langfuse()

    kwargs = {
        "model": settings.deepseek_model,
        "api_key": settings.deepseek_api_key,
        "base_url": settings.deepseek_base_url,
        "temperature": temperature,
    }

    # LangChain + LangFuse 集成
    if settings.langfuse_enabled:
        try:
            from langfuse.langchain import CallbackHandler
            kwargs["callbacks"] = [CallbackHandler()]
        except Exception:
            pass

    return ChatOpenAI(**kwargs)
