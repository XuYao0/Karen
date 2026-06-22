# Task 1 报告

## 实现内容
- 新增 `pyproject.toml`，补齐项目元数据、运行依赖、测试依赖和 pytest 配置。
- 新增 `README.md`，写入 task brief 指定的初始说明、启动方式和默认服务地址。
- 新增 `companion_bot/__init__.py`、`companion_bot/http.py`、`companion_bot/config.py`，提供 `GatewaySettings`、`ChatSettings`、`load_gateway_settings()`、`load_chat_settings()`、`normalize_base_url()` 和 `DEFAULT_HTTP_TIMEOUT_SECONDS`。
- 新增 `tests/test_config.py`，覆盖 token 必填、默认 URL、URL 归一化。

## 测试命令和结果
- `pytest tests/test_config.py -v`
  - 结果：失败，原因是环境里没有全局 `pytest` 命令。
- `uv run --extra dev pytest tests/test_config.py -v`
  - 结果：4 passed。

## TDD Evidence
- RED：临时移走 `companion_bot/` 后运行 `uv run --extra dev pytest tests/test_config.py -v`，收到了 `ModuleNotFoundError: No module named 'companion_bot'`，确认测试确实会因为缺少实现而失败。
- GREEN：恢复实现后再次运行同一命令，4 个测试全部通过。

## 变更文件
- `pyproject.toml`
- `README.md`
- `companion_bot/__init__.py`
- `companion_bot/config.py`
- `companion_bot/http.py`
- `tests/test_config.py`

## 自查结论
- 只实现了 Task 1 要求的 scaffold、配置读取和基础测试，没有实现后续 memory/chat/telegram gateway 功能。
- 运行结果干净，聚焦测试通过。
- `uv` 生成的临时产物已清理，不保留额外提交噪声。

## 疑虑
- `README.md` 中引用的后续服务入口目前还没有实现，这是按 brief 保留的预告性内容，不影响 Task 1 验收。
