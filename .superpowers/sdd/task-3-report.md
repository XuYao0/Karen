# Task 3: Chat Service Report

## 实现计划
- 在 `companion_bot/services/chat.py` 中把本地占位回复改为 LLM 调用链，使用 `load_llm_settings()` 与 `generate_chat_reply(...)`。
- `POST /v1/chat/reply` 继续读取 memory 并写入 interaction note，但本任务明确不把 memory 或历史消息发给 LLM，只发送 system prompt 与最新用户消息。
- `ChatReplyRequest` 补充 `message_timestamp: str | None`，对外兼容 Task 4 的时间透传接口。
- LLM 失败时返回固定中文 fallback：`我在认真想怎么回应你，但刚刚有点卡住了。你可以再发我一次，我会继续陪你。`
- 测试只覆盖 brief 要求的三条路径：最新消息直连 LLM、LLM 失败 fallback、memory 服务失败不阻断 LLM 成功。

## 测试计划
- 先改 `tests/test_chat_service.py`，再运行 `.venv/bin/python -m pytest tests/test_chat_service.py -v` 获取 RED。
- 实现后运行 `.venv/bin/python -m pytest tests/test_chat_service.py tests/test_llm.py -v` 获取 GREEN。
- 若 `.venv/bin/python` 不可用，再退回 `uv run --extra dev pytest ...`。

## TDD Evidence
- RED: `./.venv/bin/python -m pytest tests/test_chat_service.py -v`，3 个测试全部失败；失败点分别是 chat service 仍返回本地英文 placeholder，而不是 DeepSeek 回复、中文 fallback、以及 memory 失败下的 LLM 成功回复。
- GREEN: `./.venv/bin/python -m pytest tests/test_chat_service.py tests/test_llm.py -v`，`7 passed, 1 warning`。
- 相关回归: 本任务按 brief 额外运行了 `tests/test_llm.py`，确认 chat-service 接线没有破坏现有 LLM client 行为。

## 变更文件
- `.superpowers/sdd/task-3-report.md`
- `companion_bot/services/chat.py`
- `tests/test_chat_service.py`

## 自查结论
- 已严格按 brief 接入 `load_llm_settings()`、`ChatMessage`、`LLMClientError`、`generate_chat_reply(...)`，没有改 Telegram gateway、README 或 LLM client。
- chat-service 发给 LLM 的消息只包含固定 system prompt 和最新 `message_text`，没有发送 memory 内容，也没有引入历史消息。
- 保留 memory GET/POST；memory 服务失败只记日志，不阻断回复生成；LLM 配置错误或请求失败统一走指定中文 fallback。
- `message_timestamp: str | None` 已加入请求模型，但本任务没有消费该字段，符合 brief 的接口产出要求。
- 测试只覆盖本任务要求的行为，没有额外扩展功能或引入测试噪声。

## 疑虑
- 无

## 实现内容
- `companion_bot/services/chat.py`
  - 引入 `load_llm_settings` 与 `generate_chat_reply`。
  - 新增 `SYSTEM_PROMPT` 和指定的中文 `LLM_FALLBACK_REPLY` 常量。
  - 将 `build_reply` 改为异步 LLM 调用，只发送 system + 最新用户消息。
  - `ChatReplyRequest` 增加 `message_timestamp: str | None = None`。
  - `reply()` 保留 memory 拉取与 interaction note 写入，但不再基于 memory 拼接本地回复。
- `tests/test_chat_service.py`
  - 新增“只发送最新消息到 DeepSeek”的成功路径测试，并断言 memory 内容未进入 LLM 请求体。
  - 新增 DeepSeek 503 时返回指定中文 fallback 的测试。
  - 更新 memory 服务失败测试，验证 memory 故障不会阻断 LLM 成功回复。
  - 保留并强化 interaction note POST 载荷断言。

## 测试命令和结果
- `./.venv/bin/python -m pytest tests/test_chat_service.py -v`
  - 结果：FAILED，3 failed。用于 RED。
- `./.venv/bin/python -m pytest tests/test_chat_service.py tests/test_llm.py -v`
  - 结果：PASSED，7 passed，1 条 FastAPI/Starlette 现有 warning。
