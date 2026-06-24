# Karen 项目架构

## 当前目标

Karen 当前是一个以 Telegram 为首个入口的 AI friend。系统被拆成几个本地服务，核心目标是让渠道接入、对话生成、记忆管理彼此解耦：

- Telegram gateway 只负责和 Telegram 交互。
- chat-service 负责编排一次回复生成。
- memory-service 负责维护用户记忆。
- LLM client 负责调用 DeepSeek 等 OpenAI-compatible 模型。

当前实现仍是本地多进程架构，memory 使用进程内存，重启 `memory-service` 后会清空。

## 组件职责

### `companion_bot.telegram_gateway`

Telegram 入口层。

职责：

- 启动 Telegram bot polling。
- 处理 `/start`。
- 处理文本消息。
- 拒绝非文本消息和未知命令。
- 把 Telegram 用户 ID 规范化成项目内部 `user_id`，例如 `telegram:5953370224`。
- 把 Telegram message time 转成 UTC ISO 8601 字符串。
- 调用 chat-service 的 `POST /v1/chat/reply`。
- 如果 chat-service 不可用，返回 Telegram 侧 fallback。

它不直接调用 LLM，也不直接读写 memory-service。

### `companion_bot.services.chat`

对话编排层。

职责：

- 接收渠道层传来的 `user_id`、`channel`、`message_text`、`message_timestamp`。
- 向 memory-service 读取当前消息之前可用的 memory context。
- 把 Karen 的 system prompt、memory context、当前用户消息组合成 LLM messages。
- 调用 LLM client 生成回复。
- LLM 失败时返回温和 fallback。
- 无论 LLM 成功还是 fallback，都尝试把本轮 completed turn 写回 memory-service。

chat-service 是当前最核心的 orchestration 层，但不保存记忆，也不直接知道 Telegram SDK。

### `companion_bot.services.memory`

记忆 HTTP 服务层。

职责：

- 保留旧的 flat memory API：
  - `GET /v1/users/{user_id}/memories`
  - `POST /v1/users/{user_id}/memories`
- 提供新的对话记忆 API：
  - `POST /v1/users/{user_id}/memory/context`
  - `POST /v1/users/{user_id}/memory/turns`
- 按 `user_id` 管理 `AgentMemory`。
- 服务启动时清空进程内 store。

旧 flat memory 和新 conversation memory 是两套存储，当前不会互相同步。

### `companion_bot.memory`

纯 domain 层，不依赖 FastAPI、Telegram、HTTP 或 LLM。

核心结构：

- `ConversationTurn`：一次用户输入和可选 Karen 回复。
- `PersonState`：用户画像式状态，包括近期事件、需求、关切等字段。
- `EventMemory`：一次可观察事件。
- `AgentMemory`：单个用户的在线记忆容器。

`AgentMemory.retrieve_context()` 有一个重要约束：如果请求里带了可解析的 `message_timestamp`，只会重放严格早于该时间点的已观察 turn，避免“未来记忆”泄漏到当前消息之前。

如果 `message_timestamp` 缺失，则使用当前在线上下文。  
如果传入非法 timestamp，则返回空上下文，避免错误时间边界导致未来记忆泄漏。

### `companion_bot.llm`

LLM provider adapter。

当前只支持 `deepseek` provider，但接口按 OpenAI-compatible chat completions 的 messages 结构组织：

- `ChatMessage(role, content)`
- `generate_chat_reply(messages, settings)`

DeepSeek 请求体目前包含：

- `model`
- `messages`
- `reasoning_effort`
- `thinking`，可通过 `LLM_THINKING_ENABLED` 关闭
- `stream: false`

### `companion_bot.config`

环境变量配置层。

主要配置：

- `TELEGRAM_BOT_TOKEN`
- `CHAT_SERVICE_URL`
- `MEMORY_SERVICE_URL`
- `DEEPSEEK_API_KEY`
- `LLM_PROVIDER`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `LLM_REASONING_EFFORT`
- `LLM_THINKING_ENABLED`

## 服务关系

本地默认端口：

- memory-service: `http://127.0.0.1:8001`
- chat-service: `http://127.0.0.1:8002`
- telegram-gateway: 无 HTTP 端口，通过 Telegram polling 收消息

依赖方向：

```text
Telegram
  -> telegram-gateway
  -> chat-service
  -> memory-service
  -> chat-service
  -> DeepSeek / LLM provider
  -> chat-service
  -> memory-service
  -> chat-service
  -> telegram-gateway
  -> Telegram
```

memory-service 不调用 chat-service。  
LLM client 不调用 memory-service。  
Telegram gateway 不调用 memory-service 或 LLM。

## 数据流示例一：Telegram 文本消息正常生成回复

假设用户在 Telegram 发送：

```text
有点饿了
```

Telegram message 中带有用户 ID 和消息时间。gateway 会构造：

```json
{
  "user_id": "telegram:5953370224",
  "channel": "telegram",
  "message_text": "有点饿了",
  "message_timestamp": "2026-06-22T09:22:00+00:00"
}
```

然后调用：

```text
POST http://127.0.0.1:8002/v1/chat/reply
```

chat-service 收到请求后，先向 memory-service 查询当前消息之前的记忆：

```text
POST http://127.0.0.1:8001/v1/users/telegram:5953370224/memory/context
```

请求体：

```json
{
  "channel": "telegram",
  "message_text": "有点饿了",
  "message_timestamp": "2026-06-22T09:22:00+00:00"
}
```

如果这是第一次对话，memory-service 返回空 context：

```json
{
  "user_id": "telegram:5953370224",
  "context": {
    "speaker_state": null,
    "recent_current_events": [],
    "compressed_events": [],
    "known_characters": []
  }
}
```

chat-service 发现 context 为空，就不会向 LLM messages 插入 memory system message。最终传给 LLM 的 messages 形状是：

```json
[
  {
    "role": "system",
    "content": "You are Karen, a warm and emotionally present AI friend. Reply naturally and briefly."
  },
  {
    "role": "user",
    "content": "有点饿了"
  }
]
```

LLM 返回：

```text
啊，那要不要一起吃点什么？你手边有零食，还是想我推荐做点简单的？
```

chat-service 再把 completed turn 写回 memory-service：

```text
POST http://127.0.0.1:8001/v1/users/telegram:5953370224/memory/turns
```

请求体：

```json
{
  "channel": "telegram",
  "message_text": "有点饿了",
  "message_timestamp": "2026-06-22T09:22:00+00:00",
  "assistant_reply": "啊，那要不要一起吃点什么？你手边有零食，还是想我推荐做点简单的？"
}
```

memory-service 内部会把它变成一个 `ConversationTurn`，更新该用户的 `AgentMemory`：

- `observed_turns` 追加本轮 turn。
- `current_events` 追加一条可观察事件。
- `people["user"].recent_events` 追加一条近期事件描述。
- 如果 `current_events` 超过窗口上限，会压缩早期事件到 `compressed_events`。

最后 chat-service 把 reply 返回给 telegram-gateway，gateway 调用 Telegram API 发回用户。

## 数据流示例二：第二次消息带上 memory context

用户之后又发送：

```text
还想吃甜的
```

gateway 仍然调用 chat-service：

```json
{
  "user_id": "telegram:5953370224",
  "channel": "telegram",
  "message_text": "还想吃甜的",
  "message_timestamp": "2026-06-22T09:25:00+00:00"
}
```

chat-service 查询 memory context。因为 memory-service 已经观察到 `09:22` 的上一轮 turn，并且它早于 `09:25`，所以返回的 context 可能包含：

```json
{
  "speaker_state": {
    "name": "user",
    "goals": [],
    "needs": [],
    "concerns": [],
    "recent_events": [
      "2026-06-22T09:22:00+00:00 via telegram: user said: 有点饿了 | Karen replied: 啊，那要不要一起吃点什么？你手边有零食，还是想我推荐做点简单的？"
    ],
    "behavior_patterns": [],
    "interpretation_patterns": [],
    "traits_or_notes": [],
    "relationships": {}
  },
  "recent_current_events": [
    {
      "time": "2026-06-22T09:22:00+00:00",
      "location": "telegram",
      "characters": ["user", "Karen"],
      "action": "user said \"有点饿了\". Karen replied \"啊，那要不要一起吃点什么？你手边有零食，还是想我推荐做点简单的？\".",
      "known_scope": "observable_so_far"
    }
  ],
  "compressed_events": [],
  "known_characters": ["user"]
}
```

这次 chat-service 会把 memory context 转成第二条 system message：

```text
Known memory context before the latest user message:
{"speaker_state":{...},"recent_current_events":[...],"compressed_events":[],"known_characters":["user"]}
Use it only as background. Do not claim certainty beyond it.
```

传给 LLM 的 messages 变成：

```json
[
  {"role": "system", "content": "You are Karen, ..."},
  {"role": "system", "content": "Known memory context before the latest user message:\n..."},
  {"role": "user", "content": "还想吃甜的"}
]
```

LLM 因此能知道用户刚刚说过饿了，但 system message 也明确要求它只把这些当背景，不要夸大确定性。

## 数据流示例三：避免未来记忆泄漏

memory-service 的 context 查询使用 `message_timestamp` 作为时间边界。

例如 memory-service 已经保存了一条较晚事件：

```json
{
  "message_text": "晚上一起吃饭",
  "message_timestamp": "2026-06-22T10:05:00+00:00",
  "assistant_reply": "好，我记住了。"
}
```

如果之后查询一个更早时间点的 context：

```json
{
  "channel": "telegram",
  "message_text": "早上在忙什么",
  "message_timestamp": "2026-06-22T09:00:00+00:00"
}
```

`AgentMemory.retrieve_context()` 会只重放严格早于 `09:00` 的 observed turns。`10:05` 的事件不会进入 context。

返回结果会是空 context：

```json
{
  "speaker_state": null,
  "recent_current_events": [],
  "compressed_events": [],
  "known_characters": []
}
```

如果请求带了非法 timestamp，例如 `"not-a-timestamp"`，domain 层也会返回空 context，而不是退回全量 snapshot。这样能避免 timestamp 序列化错误导致未来记忆泄漏。

如果请求完全不带 `message_timestamp`，系统会使用当前在线上下文。这是为了兼容没有时间字段的渠道或手动调试请求。

## 数据流示例四：LLM 调用失败

如果 DeepSeek 超时、返回非 2xx、或者 response shape 不符合预期：

1. `companion_bot.llm.generate_chat_reply()` 抛出 `LLMClientError`。
2. chat-service 捕获异常。
3. 日志记录 provider、model、user_id、channel、error_type。
4. chat-service 返回 fallback：

```text
我在认真想怎么回应你，但刚刚有点卡住了。你可以再发我一次，我会继续陪你。
```

即使使用 fallback，chat-service 仍会尝试写入 `/memory/turns`：

```json
{
  "channel": "telegram",
  "message_text": "你好",
  "message_timestamp": "2026-06-22T06:46:00+00:00",
  "assistant_reply": "我在认真想怎么回应你，但刚刚有点卡住了。你可以再发我一次，我会继续陪你。"
}
```

这样 memory 里仍能记录用户发过什么，以及 Karen 当时没有成功生成真实 LLM 回复。

## 数据流示例五：memory-service 不可用

如果 chat-service 查询 memory context 失败：

1. `fetch_memory_context()` 捕获 `httpx.HTTPError`。
2. 记录日志。
3. 返回 `{}`。
4. chat-service 不插入 memory system message，只用 Karen system prompt 和当前用户消息调用 LLM。

如果 chat-service 写入 completed turn 失败：

1. `store_conversation_turn()` 捕获 `httpx.HTTPError`。
2. 记录日志。
3. 不影响已经生成的 reply。

所以 memory-service 故障会导致“本轮无法读写记忆”，但不会阻断聊天。

## 数据流示例六：chat-service 不可用

如果 telegram-gateway 调用 chat-service 失败，例如 chat-service 没启动：

1. `fetch_chat_reply()` 抛出 HTTP 或解析异常。
2. gateway 捕获异常。
3. gateway 返回 Telegram 侧 fallback：

```text
I'm here, but I had trouble thinking clearly for a moment. Please send that again.
```

这个 fallback 发生在 Telegram gateway 层，因此不会写入 memory-service。

## 当前 memory 结构

conversation memory 每个 `user_id` 一个 `AgentMemory`：

```text
_agent_memories["telegram:5953370224"] -> AgentMemory
```

`AgentMemory` 内部主要有：

- `people`
  - 当前默认只使用 `"user"` 作为人物键。
  - 存近期事件、需求、关切等结构化字段。
- `current_events`
  - 最近窗口内的可观察事件。
  - 默认最多保留 8 条当前事件。
- `compressed_events`
  - 超出窗口的事件会被压缩成 summary event。
- `observed_turns`
  - 完整 observed turns，用于按 timestamp replay 可见上下文。
  - 当前没有持久化落库，也没有长期裁剪策略。

`to_dict()` 会导出 `observed_turns`，因为未来如果用它做持久化边界，timestamp replay 需要这些原始 turn。

## API 摘要

### chat-service

```text
POST /v1/chat/reply
```

Request:

```json
{
  "user_id": "telegram:123",
  "channel": "telegram",
  "message_text": "你好",
  "message_timestamp": "2026-06-22T06:46:00+00:00"
}
```

Response:

```json
{
  "reply_text": "我在。"
}
```

### memory-service legacy flat memory

```text
GET /v1/users/{user_id}/memories
POST /v1/users/{user_id}/memories
```

这套 API 只保存 `kind/content/source` 扁平记录。它是兼容接口，不参与新的 conversation memory context。

### memory-service conversation memory

```text
POST /v1/users/{user_id}/memory/context
POST /v1/users/{user_id}/memory/turns
```

`/memory/context` 用于“生成回复之前”取上下文。  
`/memory/turns` 用于“生成回复之后”写入本轮观测。

## 当前限制

- memory 是进程内存，重启丢失。
- `observed_turns` 目前 append-only，长期运行需要裁剪或持久化策略。
- 当前只支持 Telegram 渠道，但 HTTP API 已经有 `channel` 字段。
- 当前只支持 DeepSeek provider，但 LLM messages 按 OpenAI-compatible 格式组织。
- memory 更新是确定性规则，不做 LLM 结构化抽取。
- legacy flat memory 和 conversation memory 暂不互通。

## 启动顺序

建议本地用三个终端启动：

```bash
python3 -m companion_bot.services.memory
```

```bash
python3 -m companion_bot.services.chat
```

```bash
python3 -m companion_bot.telegram_gateway
```

如果使用虚拟环境，则替换为对应 `.venv/bin/python`。  
chat-service 需要能读到 `DEEPSEEK_API_KEY`。  
telegram-gateway 需要能读到 `TELEGRAM_BOT_TOKEN`。
