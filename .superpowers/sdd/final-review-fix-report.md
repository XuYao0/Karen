# Final Review Fix Report

## 修复内容

1. 在 `companion_bot/services/chat.py` 的 LLM fallback 路径补齐诊断日志字段：
   - `provider`
   - `model`
   - `user_id`
   - `channel`
   - `error_type`
2. 对配置加载失败场景使用 `provider=unknown`、`model=unknown`，同时记录真实异常类型 `RuntimeError`。
3. 保持日志不输出 `DEEPSEEK_API_KEY` 或 `settings.api_key`，并增加回归测试防止 secret 泄漏。
4. 在 `tests/test_chat_service.py` 与 `tests/test_config.py` 新增 `autouse` fixture，统一清理：
   - `DEEPSEEK_API_KEY`
   - `LLM_PROVIDER`
   - `LLM_BASE_URL`
   - `LLM_MODEL`
   - `LLM_REASONING_EFFORT`
   - `LLM_THINKING_ENABLED`
5. 在 `README.md` 明确 `chat-service` 启动示例需要 `DEEPSEEK_API_KEY=...`。
6. 按“文档先行”补充本次修复的设计文档与实施计划：
   - `docs/superpowers/specs/2026-06-22-llm-fallback-diagnostics-design.md`
   - `docs/superpowers/plans/2026-06-22-llm-fallback-diagnostics.md`

## RED / GREEN 证据

### Red

先改测试，再运行：

```bash
.venv/bin/python -m pytest tests/test_chat_service.py tests/test_config.py -v
```

结果：失败，`2 failed, 18 passed`

失败点：

- `tests/test_chat_service.py::test_chat_reply_logs_provider_model_and_error_type_on_llm_failure`
  - 原因：日志里没有 `provider=deepseek`、`model=deepseek-v4-pro`、`error_type=LLMClientError`
- `tests/test_chat_service.py::test_chat_reply_logs_unknown_provider_and_model_on_settings_failure`
  - 原因：日志里没有 `provider=unknown`、`model=unknown`、`error_type=RuntimeError`

这证明 reviewer 指出的日志缺口真实存在。

### Green

最小实现后重跑同一命令：

```bash
.venv/bin/python -m pytest tests/test_chat_service.py tests/test_config.py -v
```

结果：通过，`20 passed, 1 warning`

说明：

- fallback 日志现在能区分配置错误与 LLM client 错误
- 日志断言确认未出现 `deepseek-key`
- env 清理 fixture 生效，相关测试不再依赖外部环境预置值

## 测试命令和结果

1. 定向回归：

```bash
.venv/bin/python -m pytest tests/test_chat_service.py tests/test_config.py -v
```

结果：通过，`20 passed, 1 warning`

2. 全量回归：

```bash
.venv/bin/python -m pytest -v
```

结果：通过，`35 passed, 1 warning`

3. warning 说明：

- 唯一 warning 来自 `fastapi.testclient` / `starlette.testclient` 对 `httpx` 兼容层的第三方弃用告警，不属于本次 review finding 范围。

## 变更文件

- `companion_bot/services/chat.py`
- `tests/test_chat_service.py`
- `tests/test_config.py`
- `README.md`
- `docs/superpowers/specs/2026-06-22-llm-fallback-diagnostics-design.md`
- `docs/superpowers/plans/2026-06-22-llm-fallback-diagnostics.md`
- `.superpowers/sdd/final-review-fix-report.md`

## 自查结论

- 修改范围符合任务约束，没有跨到 Telegram gateway 或 LLM client。
- TDD 顺序满足要求：先写测试，拿到 RED，再补最小实现转 GREEN。
- fallback 日志现在覆盖 reviewer 要求的全部字段。
- 配置失败时按要求记录 `unknown` 占位值。
- README 启动说明已补齐真实依赖。
- 未纳入 `__pycache__`、`.pytest_cache`、`.venv` 等生成物。

## 疑虑

1. 当前实现使用 `logger.exception()` 输出 traceback；本次仓内异常路径没有携带 API key，因此新增回归能覆盖当前 secret 泄漏风险，但未来若下游异常 message 拼接敏感信息，仍建议统一引入日志脱敏策略。
2. 全量测试仍存在一条上游第三方弃用 warning，本次未处理。
