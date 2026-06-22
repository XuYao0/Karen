# Final Review Fix Report

## 修复内容

1. 修复 `pyproject.toml` 的 setuptools 打包配置，显式包含 `companion_bot.services` 子包。
2. 在 `tests/test_config.py` 增加 packaging/import smoke：
   - 断言 `pyproject.toml` 中 `tool.setuptools.packages` 包含 `companion_bot.services`
   - 断言 `companion_bot.services.memory` 可导入
3. 将 `companion_bot/services/memory.py` 从 `@app.on_event("startup")` 迁移到 FastAPI lifespan context manager，并保留启动时清空 `_memory_store` 的行为。
4. 在 `tests/test_memory_service.py` 增加启动阶段清空旧内存数据的回归测试。
5. 在 `README.md` 增加 Required environment variables 小节，明确 `TELEGRAM_BOT_TOKEN` 仅 `telegram-gateway` 需要。
6. 保留并纳入 `docs/superpowers/plans/2026-06-22-telegram-http-rest-multiservice.md` 的既有计划更新。

## TDD / 验证证据

### Red

先写测试后运行：

```bash
.venv/bin/python -m pytest tests/test_config.py tests/test_memory_service.py -v
```

结果：

- `tests/test_config.py::test_setuptools_packages_include_service_subpackage` 失败
- 失败原因：`pyproject.toml` 里只有 `["companion_bot"]`
- warnings 中出现 `companion_bot/services/memory.py` 的 `on_event` 弃用告警

### Green

实现最小修复后重跑：

```bash
.venv/bin/python -m pytest tests/test_config.py tests/test_memory_service.py -v
```

结果：`9 passed, 1 warning`

- 新 warning 仅剩 FastAPI/TestClient 对上游 `httpx` 兼容层的第三方弃用告警
- `memory.py` 自身的 `on_event` 弃用告警已消失

## 测试命令和结果

1. 定向回归测试

```bash
.venv/bin/python -m pytest tests/test_config.py tests/test_memory_service.py -v
```

结果：通过，`9 passed, 1 warning`

2. 全量测试

```bash
.venv/bin/python -m pytest -v
```

结果：通过，`17 passed, 1 warning`

3. packaging smoke 额外检查

尝试运行：

```bash
.venv/bin/python -m pip wheel . --no-deps -w /tmp/karen-wheel-smoke
```

结果：当前 `.venv` 中没有 `pip` 模块，命令失败：`No module named pip`

额外确认：

```bash
.venv/bin/python -c "import build; print(build.__file__)"
```

结果：当前 `.venv` 中没有 `build` 模块

结论：本地缺少现成的构建工具链，因此本次以 pytest 中的 packaging/import smoke 作为回归覆盖；同时该测试已在旧配置下实际失败，能证明修复必要性。

## 变更文件

- `pyproject.toml`
- `companion_bot/services/memory.py`
- `tests/test_config.py`
- `tests/test_memory_service.py`
- `README.md`
- `docs/superpowers/plans/2026-06-22-telegram-http-rest-multiservice.md`

## 自查结论

- 修复范围限制在 review findings 指定文件内
- 未修改 chat service 或 telegram gateway 行为
- 打包配置、memory lifespan 行为、README 说明均已覆盖到测试或文档
- 全量测试通过
- 未计划提交 `__pycache__`、`.venv`、测试缓存等生成物

## 疑虑

1. 当前测试环境仍有一条来自 `fastapi.testclient` / `starlette.testclient` 对 `httpx` 兼容层的第三方弃用告警；这不是本次 review finding 范围内的问题。
2. 由于 `.venv` 缺少 `pip`/`build`，无法在本地直接完成 wheel 构建级 smoke；不过已有真实 red-green 的 packaging 配置测试覆盖该回归点。
