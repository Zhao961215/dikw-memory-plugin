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
hermes plugins install Zhao961215/dikw-memory-plugin --enable

# 2. 重命名目录（hermes plugins install 默认目录名 = dikw-memory-plugin）
mv ~/.hermes/plugins/dikw-memory-plugin ~/.hermes/plugins/dikw

# 3. 配置环境变量
echo "HERMES_MEMORY_PROVIDER=dikw" >> ~/.hermes/.env

# 4. 如果已有 bundled DIKW，先移除（备份后）
# rm -rf ~/.hermes/hermes-agent/plugins/memory/dikw

# 5. 重启
hermes gateway restart
```

## 验证

```bash
# 查看插件状态
hermes plugins list | grep dikw

# 查看记忆状态
hermes memory status

# 在对话中测试 fact_store 工具可用性
```

## 工具概览

| 工具 | 功能 | 来源 |
|------|------|------|
| `fact_store` | 存事实 + 搜记忆（FTS5 + HRR 双引擎）| Holographic backend |
| `fact_feedback` | 给事实打分（校准信任度）| Holographic backend |
| `dikw_dispatch` | DIKW 分流主入口（D/I/K/W/L 5 类）| DIKW |
| `run_information_flow` | 12 步信息流主流程 | DIKW |
| `add_with_timestamp` | 带 3 时间字段的 fact 写入 | DIKW |
| `migrate_expired_to_vault` | 过期事实迁移到图书馆 | DIKW |

## 版本

| 版本 | 日期 | 变更 |
|------|------|------|
| **v1.0.1** | 2026-06-07 | 修复 user-installed 路径下相对导入失败（`_hermes_user_memory` 模块找不到），新增 `_import_sibling()` 兼容 bundled + user-installed 两种部署路径 |
| v1.0.0 | 2026-06-07 | 首次发布：从 bundled plugin 拆分为独立仓库 |

## 回滚

```bash
hermes plugins remove dikw
# 如需恢复 bundled DIKW:
# cp -r /path/to/backup/dikw ~/.hermes/hermes-agent/plugins/memory/dikw
hermes gateway restart
```

## 架构

```
~/.hermes/plugins/dikw/           ← user-installed 路径
├── __init__.py                   ← DIKWMemoryProvider（MemoryProvider ABC 子类）
├── tools.py                      ← 4 工具 schema + 路由
├── fact_queue.py                 ← fact 队列降级模块
├── tests/                        ← 测试套件（E1/E2/E3/M1/M2）
│   ├── test_e1.py                ← M0 单文件骨架验证
│   ├── test_e2.py                ← E2 config 激活验证
│   ├── test_e3.py                ← E3 delegate 委托验证
│   ├── test_m1.py                ← M1 dikw_dispatch 4 方法
│   ├── test_m1_step2.py          ← M1 图书馆检索 5 辅助函数
│   ├── test_m1_step3.py          ← M1 run_information_flow 12 步
│   ├── test_m1_step4.py          ← M1 DIKW 分流闭环
│   ├── test_m2_step1.py          ← M2 get_tool_schemas
│   ├── test_m2_step2.py          ← M2 handle_tool_call
│   ├── test_m2_step3.py          ← M2 add_with_timestamp + migrate
│   ├── test_m2_fix_bug.py        ← M2 bug fix validation
│   └── test_integration_real.py   ← 集成测试
├── install.sh                    ← 一键安装脚本
└── README.md                     ← 本文件
```

## License

MIT
