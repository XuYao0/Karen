# LLM Fallback Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `chat-service` fallback logs diagnostically complete and deterministic under test without leaking secrets.

**Architecture:** Keep the behavior localized to `companion_bot/services/chat.py`, using loaded LLM settings when available and `unknown` placeholders when configuration fails. Add test fixtures to isolate LLM-related environment variables and update README startup guidance.

**Tech Stack:** Python 3.11+, FastAPI, pytest, respx, caplog.

## Global Constraints

- 只能修改 `companion_bot/services/chat.py`、`tests/test_chat_service.py`、`tests/test_config.py`、`README.md`，以及修复报告文件。
- 必须先写/调整测试并拿到 RED 证据，再改实现。
- fallback 日志必须记录 `provider`、`model`、`user_id`、`channel`、`error_type`。
- 配置失败时 `provider` 和 `model` 记为 `unknown`。
- 不能把 API key 写入日志。
- 测试需清理 `DEEPSEEK_API_KEY`、`LLM_PROVIDER`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_REASONING_EFFORT`、`LLM_THINKING_ENABLED`。
- README 需要明确 `chat-service` 启动示例依赖 `DEEPSEEK_API_KEY=...`。

---

### Task 1: 用测试锁定日志与环境行为

**Files:**
- Modify: `tests/test_chat_service.py`
- Modify: `tests/test_config.py`

**Interfaces:**
- Consumes: `companion_bot.services.chat.app`
- Produces: fallback 日志字段与 env 清理回归测试

- [ ] **Step 1: 增加 autouse env 清理 fixture**
- [ ] **Step 2: 新增 LLM 失败日志断言测试**
- [ ] **Step 3: 新增配置失败日志断言测试**
- [ ] **Step 4: 运行 `.venv/bin/python -m pytest tests/test_chat_service.py tests/test_config.py -v`，确认先红**

### Task 2: 最小实现满足日志要求

**Files:**
- Modify: `companion_bot/services/chat.py`

**Interfaces:**
- Produces: `build_reply(request: ChatReplyRequest) -> str`

- [ ] **Step 1: 在 `build_reply()` 内拆出 settings 加载结果**
- [ ] **Step 2: 统一异常日志，补齐 provider/model/error_type**
- [ ] **Step 3: 保持 fallback 文案与现有接口不变**
- [ ] **Step 4: 重跑 focused pytest，确认转绿**

### Task 3: 文档与收尾

**Files:**
- Modify: `README.md`
- Create: `.superpowers/sdd/final-review-fix-report.md`

**Interfaces:**
- Produces: 明确的 chat-service 启动示例与 reviewer fix 报告

- [ ] **Step 1: 更新 README 启动示例**
- [ ] **Step 2: 运行 `.venv/bin/python -m pytest -v` 做全量验证**
- [ ] **Step 3: 写入 RED/GREEN 证据、测试结果、自查结论到修复报告**
- [ ] **Step 4: `git add` 后提交 `fix: improve llm fallback diagnostics`**
