# DeepSeek LLM Connectivity Design

## Context

Karen 当前已经有 Telegram gateway、chat-service 和 memory-service 三个本地服务。Telegram gateway 能通过 long polling 收到用户消息，并通过 HTTP REST 把消息转给 chat-service。chat-service 目前只返回本地占位回复，还没有真实 LLM 调用。

本阶段目标是先打通 DeepSeek 连通性，让 Telegram 用户发来的最新一条消息能经过 chat-service 调用 DeepSeek 并返回模型回复。长期仍要保留多模型扩展能力，因为多数目标模型支持 OpenAI-compatible messages，但会有各自独有参数。

## Goals

- 让 chat-service 能调用 DeepSeek chat completions API。
- 保持 LLM 调用代码独立于 Telegram gateway。
- 只把 Telegram 最新一条消息传给 DeepSeek，不带历史对话。
- Telegram gateway 把消息 UTC 时间透传给 chat-service。
- chat-service 请求模型中保留 `message_timestamp` 字段，第一版不做用户时区推断。
- DeepSeek API key 使用现有环境变量 `DEEPSEEK_API_KEY`。
- DeepSeek 默认模型使用 `deepseek-v4-pro`。
- 支持 DeepSeek provider-specific 参数：
  - `"thinking": {"type": "enabled"}`
  - `"reasoning_effort": "high"`
  - `"stream": false`
- LLM 调用失败时返回透明但温和的 fallback，而不是暴露技术错误。

## Non-Goals

- 不实现对话历史存储。
- 不把 memory-service 的记忆写入 prompt。
- 不实现多 provider 完整插件系统。
- 不实现 streaming。
- 不实现工具调用、函数调用或多模态输入。
- 不做用户本地时区推断。
- 不在 Telegram gateway 中直接调用 LLM。

## Architecture

新增一个小型 LLM client 层，作为 chat-service 的内部依赖。第一版只实现 DeepSeek provider，但接口按 OpenAI-compatible chat completion 组织。

推荐模块边界：

- `companion_bot.config`
  - 增加 `LLMSettings`。
  - 增加 `load_llm_settings()`。
  - 从环境变量读取 provider、base URL、API key、model 和 provider-specific 参数。

- `companion_bot/llm.py`
  - 定义 OpenAI-compatible message 数据结构。
  - 定义 `generate_chat_reply()` 或等价 async 函数。
  - 使用 `httpx.AsyncClient` 调用 DeepSeek。
  - 只向调用方返回最终文本，不泄漏 provider 响应细节。

- `companion_bot/services/chat.py`
  - 扩展 `ChatReplyRequest`，新增 `message_timestamp: str | None = None`。
  - 构造 system + user messages。
  - 调用 LLM client 获取回复。
  - LLM 失败时返回温和 fallback。
  - memory read/write 保持 best-effort，不阻塞 LLM MVP。

- `companion_bot/telegram_gateway.py`
  - 从 `update.message.date` 读取 Telegram 消息时间。
  - 转成 UTC ISO 8601 字符串。
  - 在调用 chat-service 时带上 `message_timestamp`。

## Configuration

Required:

- `DEEPSEEK_API_KEY`: DeepSeek API key。

Optional:

- `LLM_PROVIDER`: 默认 `deepseek`。
- `LLM_BASE_URL`: 默认 `https://api.deepseek.com`。
- `LLM_MODEL`: 默认 `deepseek-v4-pro`。
- `LLM_REASONING_EFFORT`: 默认 `high`。
- `LLM_THINKING_ENABLED`: 默认 `true`。

第一版只支持 `LLM_PROVIDER=deepseek`。如果配置成其他 provider，chat-service 启动或调用时应给出明确错误，避免静默降级到错误模型。

## DeepSeek Request

DeepSeek 调用使用 OpenAI-compatible chat completions endpoint：

```http
POST https://api.deepseek.com/chat/completions
Authorization: Bearer ${DEEPSEEK_API_KEY}
Content-Type: application/json
```

默认 request body：

```json
{
  "model": "deepseek-v4-pro",
  "messages": [
    {
      "role": "system",
      "content": "You are Karen, a warm and emotionally present AI friend. Reply naturally and briefly."
    },
    {
      "role": "user",
      "content": "Hello!"
    }
  ],
  "thinking": {"type": "enabled"},
  "reasoning_effort": "high",
  "stream": false
}
```

Provider-specific 参数只在 DeepSeek client 内组装。chat-service 不直接关心 `thinking` 或 `reasoning_effort` 的具体格式。

## Chat Request Contract

`POST /v1/chat/reply` request 增加可选时间字段：

```json
{
  "user_id": "telegram:123456",
  "channel": "telegram",
  "message_text": "你好",
  "message_timestamp": "2026-06-22T06:46:00+00:00"
}
```

第一版 LLM prompt 只使用 `message_text`。`message_timestamp` 先进入 REST 合约，供日志、测试和未来 prompt 编排使用。

## Fallback Behavior

LLM 请求失败、超时、非 2xx 响应或响应结构异常时，chat-service 返回：

```text
我在认真想怎么回应你，但刚刚有点卡住了。你可以再发我一次，我会继续陪你。
```

日志应记录 provider、model、user_id 和错误类型，但不能打印 API key。

## Error Handling

- 缺少 `DEEPSEEK_API_KEY` 时，LLM client 返回可诊断错误，chat-service 对用户返回 fallback。
- DeepSeek HTTP 超时、连接失败和 4xx/5xx 响应都走 fallback。
- DeepSeek 响应如果没有 `choices[0].message.content`，也走 fallback。
- memory-service 失败仍按现有逻辑 best-effort，不影响 LLM 回复。
- Telegram gateway 如果 chat-service 失败，继续使用 gateway 本地 fallback。

## Testing Strategy

Unit and integration-style tests:

- 配置测试：
  - `DEEPSEEK_API_KEY` 从环境变量读取。
  - 默认模型为 `deepseek-v4-pro`。
  - 默认 base URL 为 `https://api.deepseek.com`。
  - 默认 DeepSeek provider-specific 参数启用 thinking 和 high reasoning effort。

- LLM client 测试：
  - 使用 `respx` mock DeepSeek endpoint。
  - 断言请求 header 包含 bearer token。
  - 断言 body 包含 `model`、OpenAI-compatible `messages`、`thinking`、`reasoning_effort`、`stream: false`。
  - 断言正常响应返回 `choices[0].message.content`。
  - 断言 HTTP 失败或响应结构异常时抛出/返回可由 chat-service fallback 的错误。

- chat-service 测试：
  - `POST /v1/chat/reply` 调用 DeepSeek 并返回模型文本。
  - DeepSeek 失败时返回中文透明 fallback。
  - 请求模型接受 `message_timestamp` 字段。
  - 第一版只把最新用户消息传给 DeepSeek，不带历史消息。

- telegram-gateway 测试：
  - fake Telegram message 带 `date` 时，gateway 转发 UTC ISO 8601 `message_timestamp`。

External tests against real DeepSeek API are not required in automated tests. 本地可以用真实 `DEEPSEEK_API_KEY` 做手动 smoke test。

## Rollout

第一版完成后，本地运行仍是三个服务：

```bash
.venv/bin/python -m companion_bot.services.memory
.venv/bin/python -m companion_bot.services.chat
TELEGRAM_BOT_TOKEN=... .venv/bin/python -m companion_bot.telegram_gateway
```

chat-service 额外需要：

```bash
export DEEPSEEK_API_KEY=...
```

如果 `DEEPSEEK_API_KEY` 缺失，Telegram 仍能收到 fallback，但不会得到真实模型回复。

## Future Extensions

- 增加 conversation history 存储与最近 N 轮上下文。
- 将 memory-service 的用户记忆编排进 prompt。
- 增加 provider registry，让 OpenAI、DeepSeek、Qwen 等 provider 共享基础 OpenAI-compatible 消息接口。
- 增加 provider-specific `extra_body` 配置，避免把独有参数写死。
- 支持 streaming，并由 Telegram gateway 做渐进式发送或 typing indicator。
