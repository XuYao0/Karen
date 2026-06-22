# Task 2: Memory Service 报告

## 实现内容

- 新增 `companion_bot/services/__init__.py`，作为 services 包标记。
- 新增 `companion_bot/services/memory.py`，实现独立的 FastAPI memory-service。
- 新增 `tests/test_memory_service.py`，覆盖 GET/POST memories API。
- 新增 `docs/superpowers/plans/2026-06-22-task-2-memory-service.md`，记录本任务的实施方案。

memory-service 目前提供：

- `GET /v1/users/{user_id}/memories`
- `POST /v1/users/{user_id}/memories`

存储方式为进程内 `defaultdict(list)`，启动时清空内存，符合 brief 对临时内存存储的要求。

## 测试命令和结果

### RED

命令：

```bash
/home/xuyao/karen/.worktrees/telegram-http-rest-multiservice-dev/.venv/bin/python -m pytest tests/test_memory_service.py -v
```

结果：

- 收集阶段失败，错误为 `ModuleNotFoundError: No module named 'companion_bot.services'`
- 这符合 TDD 预期，证明测试确实先于实现失败

### GREEN

命令：

```bash
/home/xuyao/karen/.worktrees/telegram-http-rest-multiservice-dev/.venv/bin/python -m pytest tests/test_memory_service.py -v
```

结果：

- `2 passed`

### 回归检查

命令：

```bash
/home/xuyao/karen/.worktrees/telegram-http-rest-multiservice-dev/.venv/bin/python -m pytest -v
```

结果：

- `6 passed`

## TDD Evidence

- RED：`tests/test_memory_service.py` 在 import 阶段因 `companion_bot.services.memory` 不存在而失败。
- GREEN：补齐 `companion_bot/services/__init__.py` 和 `companion_bot/services/memory.py` 后，两个 memory-service 用例通过。

## 变更文件

- `companion_bot/services/__init__.py`
- `companion_bot/services/memory.py`
- `tests/test_memory_service.py`
- `docs/superpowers/plans/2026-06-22-task-2-memory-service.md`

## 自查结论

- REST 契约与 brief 一致。
- GET 新用户返回空列表。
- POST 后同一用户可以取回刚写入的 memory。
- 没有实现 chat service 或 telegram gateway。
- 工作区测试通过。

## 疑虑

- FastAPI 和 Starlette 在当前环境里会输出已知弃用警告，来自 `TestClient` 和 `@app.on_event("startup")`。
- 这些警告不影响当前任务验收，但后续如果升级依赖，可能需要再做兼容调整。
