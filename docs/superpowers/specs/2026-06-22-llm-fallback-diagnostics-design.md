# LLM Fallback Diagnostics Design

## Context

`chat-service` 已经接入 DeepSeek，但 `companion_bot/services/chat.py` 在 LLM 失败时只记录了 `user_id` 和 `channel`。reviewer 要求 fallback 日志补齐 `provider`、`model`、`user_id`、`channel`、`error_type`，并且不能把 API key 写进日志。与此同时，现有相关测试依赖进程环境，若开发机或 CI 预置了 `LLM_PROVIDER`、`LLM_BASE_URL` 等变量，测试可能出现非确定性结果。

## Goals

- 在 LLM fallback 路径记录完整诊断字段：`provider`、`model`、`user_id`、`channel`、`error_type`。
- 当配置加载失败时，日志仍输出 `provider=unknown`、`model=unknown` 和实际异常类型。
- 保证日志中不出现 `DEEPSEEK_API_KEY` 或 `settings.api_key`。
- 为 chat/config 相关测试增加统一 env 清理，消除外部环境干扰。
- 在 README 中明确 `chat-service` 启动示例需要显式传入 `DEEPSEEK_API_KEY=...`。

## Non-Goals

- 不修改 Telegram gateway。
- 不修改 `companion_bot/llm.py` 的请求/响应协议。
- 不调整用户可见 fallback 文案。

## Design

### Chat fallback logging

将 `load_llm_settings()` 和 `generate_chat_reply()` 的异常诊断统一收敛到 `build_reply()` 内部：

- 先尝试加载 `settings`。
- 如果 `settings` 加载成功，再调用 `generate_chat_reply()`。
- 对 `RuntimeError` 和 `LLMClientError` 统一记录异常日志。
- 记录字段：
  - `provider=settings.provider`，否则 `unknown`
  - `model=settings.model`，否则 `unknown`
  - `user_id=request.user_id`
  - `channel=request.channel`
  - `error_type=type(exc).__name__`
- 日志 message 本身不拼接任何敏感值，不输出 `api_key`。

### Test isolation

在 `tests/test_chat_service.py` 和 `tests/test_config.py` 各加一个 `autouse` fixture，统一清理：

- `DEEPSEEK_API_KEY`
- `LLM_PROVIDER`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `LLM_REASONING_EFFORT`
- `LLM_THINKING_ENABLED`

每个测试只显式设置自己需要的环境变量。

### README clarification

将 `chat-service` 启动示例改为：

```bash
DEEPSEEK_API_KEY=your-key python -m companion_bot.services.chat
```

避免用户按当前示例启动后误以为真实 LLM 会自动生效。

## Testing Strategy

- 在 `tests/test_chat_service.py` 新增/调整日志断言：
  - LLM HTTP 失败时，日志包含 `provider=deepseek`、`model=deepseek-v4-pro`、`error_type=LLMClientError`。
  - 配置失败时，日志包含 `provider=unknown`、`model=unknown`、`error_type=RuntimeError`。
  - 日志文本不包含 `deepseek-key`。
- 在 `tests/test_config.py` 使用 env 清理 fixture，验证配置默认值测试不受外部环境污染。
- 运行 reviewer 指定的 focused/full pytest 命令。

## Risks

- `logger.exception()` 会自动带 traceback，若异常 message 来自底层库且包含敏感信息，仍可能外溢。本次仓内错误路径不拼接 API key，当前风险可接受，但后续若接入更多 provider，建议把敏感信息脱敏策略下沉到统一日志层。
