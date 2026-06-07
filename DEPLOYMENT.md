# DIKW Memory Plugin — 部署文档

> 2026-06-07 v1.0.1  
> 独立仓库：`https://github.com/Zhao961215/dikw-memory-plugin`

## 1. 概述

DIKW 记忆插件从 hermes-agent bundled plugin 拆分为独立 Git 仓库，通过 `hermes plugins install` 原生机制安装。

核心变更（vs bundled 版本）：
- **独立仓库**：可 `git clone` 后一键安装，不依赖 hermes-agent 源码
- **兼容两种加载路径**：bundled (`plugins/memory/dikw/`) 和 user-installed (`~/.hermes/plugins/dikw/`)
- **`_import_sibling()` 修复**：解决 user-installed 路径下相对导入失败问题

## 2. 系统要求

- Hermes Agent（任意版本，含 `hermes plugins` 子命令）
- Python 3.11+（venv 隔离环境）
- 磁盘空间：~150 KB（插件文件 + 测试）

## 3. 安装（3 种方式）

### 3.1 一行安装（推荐）

```bash
curl -fsSL https://raw.githubusercontent.com/Zhao961215/dikw-memory-plugin/main/install.sh | bash
```

### 3.2 手动安装

```bash
# 1. 克隆仓库
git clone https://github.com/Zhao961215/dikw-memory-plugin.git /tmp/dikw-memory-plugin

# 2. 安装到 hermes
hermes plugins install Zhao961215/dikw-memory-plugin --enable

# 3. 重命名目录（必须！hermes plugins install 默认目录名 = dikw-memory-plugin）
mv ~/.hermes/plugins/dikw-memory-plugin ~/.hermes/plugins/dikw

# 4. 配置环境变量
echo "HERMES_MEMORY_PROVIDER=dikw" >> ~/.hermes/.env

# 5. 如已有 bundled DIKW，先备份移除
# mv ~/.hermes/hermes-agent/plugins/memory/dikw /tmp/dikw_bundled_backup/

# 6. 重启
hermes gateway restart
```

### 3.3 本地安装（开发/调试）

```bash
# 从本地目录安装（不通过 GitHub）
cp -r /path/to/dikw-memory-plugin ~/.hermes/plugins/dikw
echo "HERMES_MEMORY_PROVIDER=dikw" >> ~/.hermes/.env
hermes gateway restart
```

## 4. 验证

```bash
# 1. 插件已注册
hermes plugins list | grep dikw
# → dikw  enabled

# 2. 工具已暴露（在新会话中检查）
# fact_store / fact_feedback / dikw_dispatch / run_information_flow
# add_with_timestamp / migrate_expired_to_vault

# 3. 端到端测试
cd ~/.hermes/plugins/dikw
python -m pytest tests/test_e1.py -v
python -m pytest tests/test_e3.py -v
```

## 5. 回滚

### 5.1 回滚到 bundled DIKW

```bash
# 禁用并移除 user-installed DIKW
hermes plugins disable dikw
hermes plugins remove dikw

# 恢复 bundled DIKW（如已备份）
cp -r /tmp/dikw_bundled_backup/dikw ~/.hermes/hermes-agent/plugins/memory/dikw

hermes gateway restart
```

### 5.2 自动回滚脚本

```bash
bash /tmp/dikw_rollback_20260607_154426/rollback.sh
```

## 6. 目录结构

### 6.1 user-installed 路径（安装后）

```
~/.hermes/plugins/dikw/
├── __init__.py           ← DIKWMemoryProvider（422 KB）
├── tools.py              ← 4 工具 schema + 路由
├── fact_queue.py         ← fact 队列降级模块
└── tests/                ← 12 个测试文件
```

### 6.2 bundled 路径（如需恢复）

```
~/.hermes/hermes-agent/plugins/memory/dikw/
└── （同 user-installed 结构）
```

### 6.3 配置文件

```
~/.hermes/.env              ← HERMES_MEMORY_PROVIDER=dikw
~/.hermes/config.yaml       ← toolsets: [...]（可选，加 'memory'）
```

## 7. 本次修复记录（v1.0.1）

### 问题：`No module named '_hermes_user_memory'`

**症状**：新会话中 `fact_store` 返回错误：
```
No module named '_hermes_user_memory'
```

**根因**：user-installed 路径 `~/.hermes/plugins/dikw/` 下，Python 相对导入 `from .tools import ...` 会尝试 `_hermes_user_memory.tools`（因为插件被加载到 `_hermes_user_memory` namespace），但该 namespace 不是 Python package，无 `__init__.py` → 导入失败。

**修复**：`__init__.py` 新增 `_import_sibling()` 静态方法：
```python
@staticmethod
def _import_sibling(name):
    """兼容 bundled + user-installed 两种路径的兄弟模块导入"""
    try:
        # bundled 路径：标准相对导入
        return importlib.import_module(f'.{name}', __package__)
    except (ImportError, ValueError):
        # user-installed 路径：文件路径导入
        spec = importlib.util.spec_from_file_location(
            name,
            Path(__file__).parent / f'{name}.py'
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
```

替换 `__init__.py` 中 **5 处** `from .tools import` / `from .fact_queue import` → `_import_sibling('tools')` / `_import_sibling('fact_queue')`。

### 问题：目录重命名

**根因**：`hermes plugins install` 默认目录名 = GitHub 仓库名（`dikw-memory-plugin`），而 `find_provider_dir` 需要目录名 = provider 名（`dikw`）。

**修复**：`install.sh` 新增 [4/5] 步骤自动重命名；手动安装需 `mv`。

## 8. 状态备份

| 路径 | 内容 | 状态 |
|------|------|------|
| `/tmp/dikw_bundled_disabled/` | bundled DIKW（已移走） | ⏸️ 禁用 |
| `/tmp/dikw_rollback_20260607_154426/` | 完整回滚包（bundled DIKW + .env + rollback.sh）| ✅ 可用 |
| `/tmp/dikw-standalone/` | 独立仓库工作副本（含修复） | 🔄 当前工作目录 |
| `~/.hermes/plugins/dikw/` | user-installed DIKW（已启用 + 修复） | ✅ 运行中 |
| `~/.hermes/hermes-agent/plugins/memory/` | bundled providers（DIKW 已清空） | ⚠️ DIKW 空缺 |

## 9. 速查卡

| 操作 | 命令 |
|------|------|
| 查看插件状态 | `hermes plugins list \| grep dikw` |
| 启用 DIKW | `hermes plugins enable dikw` |
| 禁用 DIKW | `hermes plugins disable dikw` |
| 移除 DIKW | `hermes plugins remove dikw` |
| 查看记忆状态 | `hermes memory status` |
| 重载配置 | `hermes gateway restart` |
| 跑测试 | `cd ~/.hermes/plugins/dikw && python -m pytest tests/ -v` |
