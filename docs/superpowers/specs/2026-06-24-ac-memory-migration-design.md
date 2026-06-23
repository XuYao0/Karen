# AC Memory Migration Design

## Goal

把 `~/friends/ac` 原型中的在线记忆结构完整、适配地迁移到 Karen 项目，让 memory-service 不再只是保存扁平记录，而是能按用户维护“人物状态、当前事件、压缩事件”，并把这些上下文提供给 chat-service 的 LLM 回复链路。

## Source Prototype

迁移参考 `~/friends/ac`：

- `memory.py`：`PersonState`、`EventMemory`、`AgentMemory` 是核心。
- `schema.py`：`UtteranceInput` 和 `EmotionPrediction` 描述一次输入与推理结果。
- `agent.py`：每次 step 的顺序是先取历史上下文，再生成预测，再更新记忆。

Karen 项目不是情绪识别 benchmark，所以不会照搬 `EmotionRecognitionAgent` 的任务目标和 prompt。迁移重点是在线记忆的数据结构、检索顺序、追加事件、溢出压缩、按人物状态积累事实与推断的能力。

## Scope

本次实现包含：

- 新增项目内的 memory domain 模块，承载从 `ac.memory` 适配来的结构。
- 保留现有 `/v1/users/{user_id}/memories` GET/POST API，避免破坏当前测试和手动调试命令。
- 新增面向 chat-service 的 memory context/update API。
- chat-service 在调用 LLM 前获取 memory context，并把上下文作为一条 system message 传给 LLM。
- chat-service 在生成回复后调用 memory update API，记录用户输入、Karen 回复、渠道、UTC 时间。
- 单进程内存实现继续作为当前默认存储，不引入数据库。

本次不包含：

- 长期持久化存储。
- 复杂向量检索。
- 从历史 Telegram 记录批量回填。
- 多轮历史原文全部传给 LLM。
- 使用 LLM 做结构化记忆抽取。当前先用确定性规则更新用户状态，后续再引入模型抽取。

## Architecture

新增 `companion_bot/memory.py` 作为纯 Python domain 层。该模块不依赖 FastAPI、HTTP 或 LLM，负责：

- `PersonState`：维护某个参与者的目标、需求、关切、近期事件、行为模式、解释模式、特质备注和关系。
- `EventMemory`：维护一次可观察事件。
- `AgentMemory`：维护单个用户会话的在线记忆，并提供 `retrieve_context()` 与 `update()`。
- `ConversationTurn`：Karen 项目中的一次对话输入，替代 `ac.schema.UtteranceInput`。

`companion_bot/services/memory.py` 继续作为 REST 服务入口：

- `_memory_store` 保留为兼容旧 API 的扁平记录存储。
- 新增 `_agent_memories: dict[str, AgentMemory]`，按 `user_id` 管理在线记忆。
- 新增 `POST /v1/users/{user_id}/memory/context`，接收当前消息元数据，返回调用 LLM 前可用的上下文。
- 新增 `POST /v1/users/{user_id}/memory/turns`，在回复生成后更新在线记忆。

`companion_bot/services/chat.py` 负责串联：

1. 收到 `ChatReplyRequest`。
2. 从 memory-service 取当前消息之前的 memory context。
3. 调用 LLM，messages 顺序为 Karen system prompt、memory context system prompt、当前用户消息。
4. 无论 LLM 成功还是 fallback，都尝试写入 memory turn。
5. memory-service 不可用时继续回复，并记录日志。

## Data Model

`ConversationTurn` 字段：

- `user_id: str`
- `channel: str`
- `message_text: str`
- `message_timestamp: str | None`
- `assistant_reply: str | None`

`PersonState` 保留 `ac` 的字段，但在 Karen 中默认人物名为 `"user"`；后续多角色来源可以复用同一结构。

`EventMemory` 字段适配为：

- `time: str`：优先使用 UTC ISO 时间，否则为 `"current"`。
- `location: str`：使用渠道名，例如 `"telegram"`。
- `characters: list[str]`：当前为 `["user"]`，有 assistant 回复时包含 `"Karen"`。
- `action: str`：一句紧凑的可观察事件描述。
- `known_scope: str`：`"observable_so_far"` 或 `"compressed_from_observed_history"`。

`AgentMemory.retrieve_context(turn)` 返回：

- `speaker_state`
- `recent_current_events`
- `compressed_events`
- `known_characters`

`AgentMemory.update(turn)` 返回：

- `updated_person`
- `added_current_event`
- `compressed_events_added`
- `feedback_mode`

## REST API

### Context

`POST /v1/users/{user_id}/memory/context`

Request:

```json
{
  "channel": "telegram",
  "message_text": "有点饿了",
  "message_timestamp": "2026-06-22T09:22:00+00:00"
}
```

Response:

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

### Turn Update

`POST /v1/users/{user_id}/memory/turns`

Request:

```json
{
  "channel": "telegram",
  "message_text": "有点饿了",
  "message_timestamp": "2026-06-22T09:22:00+00:00",
  "assistant_reply": "啊，那要不要一起吃点什么？"
}
```

Response:

```json
{
  "updated": true,
  "memory_update": {
    "updated_person": {
      "name": "user",
      "goals": [],
      "needs": [],
      "concerns": [],
      "recent_events": [
        "2026-06-22T09:22:00+00:00 via telegram: user said: 有点饿了 | Karen replied: 啊，那要不要一起吃点什么？"
      ],
      "behavior_patterns": [],
      "interpretation_patterns": [],
      "traits_or_notes": [],
      "relationships": {}
    },
    "added_current_event": {
      "time": "2026-06-22T09:22:00+00:00",
      "location": "telegram",
      "characters": ["user", "Karen"],
      "action": "user said \"有点饿了\". Karen replied \"啊，那要不要一起吃点什么？\".",
      "known_scope": "observable_so_far"
    },
    "compressed_events_added": [],
    "feedback_mode": "conversation_observation"
  }
}
```

## LLM Context Format

chat-service 把 memory context 格式化为一条 system message：

```text
Known memory context before the latest user message:
<compact JSON>
Use it only as background. Do not claim certainty beyond it.
```

如果 context 为空，不发送这条 memory system message，避免污染首轮回复。

## Error Handling

- context 获取失败：记录 `Failed to fetch memory context...`，LLM 仍使用当前消息回复。
- context payload 无法解析：记录 `Invalid memory context payload...`，继续回复。
- turn update 失败：记录 `Failed to store conversation turn...`，回复不受影响。
- memory-service 启动时清空内存，与当前测试和本地开发行为一致。

## Testing

新增或更新测试覆盖：

- domain 层：空记忆 context、更新后 context、超过当前事件窗口后压缩。
- memory-service：新 context API、新 turn update API、启动清空在线记忆。
- chat-service：LLM 请求包含 memory context system message；memory-service 失败时仍 fallback/回复；成功回复后写入 turn update。
- 兼容性：旧 `/memories` GET/POST 继续可用。

## Migration Notes

当前实现仍是进程内存。它适合本地 Telegram 连通性验证和下一步产品体验迭代，但服务重启会丢失记忆。后续持久化时应把 `AgentMemory.to_dict()` 与对应 `from_dict()` 作为存储边界，而不是让 FastAPI 层直接操作内部对象。
