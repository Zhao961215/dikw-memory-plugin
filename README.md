# DIKW Memory Plugin

> **一行安装，5 分钟拥有完整 DIKW 记忆系统。**
>
> 基于 Hermes Agent 的 MemoryProvider 插件，实现 12 步信息流 + 4 层 DIKW 自动分流 + 终身学习。

## 是什么

DIKW（Data → Information → Knowledge → Wisdom）记忆插件让你的 Hermes Agent：

- **自动记住**每次对话的方法论和踩坑经验
- **智能检索**：大脑（Holographic）+ 图书馆（vault）双层检索
- **自动分流**：动态数据进缓存，方法论进大脑，完整文档进图书馆
- **终身学习**：越用越懂你，30 次会话后知识覆盖率从 30% → 62%

## 安装

### 一行安装（推荐）

```bash
curl -fsSL https://raw.githubusercontent.com/Zhao961215/dikw-memory-plugin/main/install.sh | bash
```

### 手动安装

```bash
# 1. 安装插件
hermes plugins install Zhao961215/dikw-memory-plugin
hermes plugins enable dikw

# 2. 配置环境变量
echo "HERMES_MEMORY_PROVIDER=dikw" >> ~/.hermes/.env

# 3. 重启
hermes gateway restart
```

## 验证

```bash
# 检查插件状态
hermes plugins list | grep dikw
# → dikw  enabled  ...

# 检查记忆系统
hermes memory status
```

## 目录结构

```
~/.hermes/plugins/dikw/
├── __init__.py      # 核心：DIKWMemoryProvider（继承 MemoryProvider ABC）
├── fact_queue.py    # 异步事实队列
├── tools.py         # 工具 schema（fact_store / fact_feedback / dikw_dispatch）
├── install.sh       # 一键安装脚本
└── tests/           # 85 项测试（M0 E1 → M2 step3 全覆盖）
```

## 工作原理

```
指令 → Agent → 大脑（Holographic）→ 图书馆 5 层
  ↓
踩坑经验 → 知识库 → 近期对话 → 缓存点 → 网络搜索
  ↓
Plan 拆解 → 工具选择 → 处理数据 → 反馈 → DIKW 分流 → 迭代
```

## 依赖

- **Hermes Agent** ≥ v0.15
- **Holographic 插件**（Hermes 内置，自动启用）
- **零外部服务**：纯 SQLite，不需要 Docker / API / MCP

## 回滚

```bash
hermes plugins remove dikw
# 恢复 .env 中的 HERMES_MEMORY_PROVIDER 为 holographic
sed -i 's/HERMES_MEMORY_PROVIDER=dikw/HERMES_MEMORY_PROVIDER=holographic/' ~/.hermes/.env
hermes gateway restart
```

## 许可

MIT
