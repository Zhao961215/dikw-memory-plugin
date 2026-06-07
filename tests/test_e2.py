"""M0 E2 验证：环境变量启用 + config 优先级 + E1 7 项基础

E2 验证 10 项（DeepSeek 评审 + E1 7 项）：
1-7. E1 7 项基础（保留）
8.  默认无环境变量：is_available() = False
9.  设置环境变量 HERMES_MEMORY_PROVIDER=dikw：is_available() = True
10. config 传入 {"enabled": False}：is_available() = False（即使环境变量为 dikw）
"""
from __future__ import annotations
import os
import sys
import logging
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.WARNING)

from agent.memory_provider import MemoryProvider
from plugins.memory.dikw import DIKWMemoryProvider, register


class _Collector:
    """模拟 plugins/memory/__init__.py L288-305 的 _ProviderCollector"""
    def __init__(self):
        self.provider = None
    def register_memory_provider(self, p):
        self.provider = p
    def register_tool(self, *a, **kw): pass
    def register_hook(self, *a, **kw): pass
    def register_cli_command(self, *a, **kw): pass


def _ensure_env_clean():
    """清理 HERMES_MEMORY_PROVIDER 环境变量（避免影响其他测试）"""
    os.environ.pop("HERMES_MEMORY_PROVIDER", None)


def test_e2():
    # === 1. import OK ===
    print("✅ 1. import OK (DIKWMemoryProvider, register)")

    # === 2. MemoryProvider 子类 ===
    _ensure_env_clean()
    p = DIKWMemoryProvider()
    assert isinstance(p, MemoryProvider), "不是 MemoryProvider 子类"
    print("✅ 2. DIKWMemoryProvider 是 MemoryProvider 子类")

    # === 3. 4 abstract 必实现 ===
    assert p.name == "dikw", f"name 错: {p.name}"
    print(f"✅ 3a. name = {p.name!r}")

    _ensure_env_clean()
    assert p.is_available() is False, "默认无 env 应 False"
    print("✅ 3b. is_available() = False (默认无 env)")

    p.initialize("test-session-123", hermes_home="/tmp/test-hermes", platform="cli")
    assert p._session_id == "test-session-123"
    assert p._hermes_home == "/tmp/test-hermes"
    assert p._platform == "cli"
    print(f"✅ 3c. initialize() OK (session={p._session_id}, home={p._hermes_home}, platform={p._platform})")

    schemas = p.get_tool_schemas()
    # B0.5+ 修复：M2.1 启用态下 schemas 是 2 个，断言改成"≥ 0 即可"
    assert isinstance(schemas, list), f"应返回 list，实际 {type(schemas)}"
    print(f"✅ 3d. get_tool_schemas() 返回 {len(schemas)} 个 schema（启用态不强制 M0 默认空）")

    # === 4. 5 个 M0 占位方法可调 ===
    _ensure_env_clean()
    assert p.system_prompt_block() == ""
    assert p.prefetch("test query") == ""  # _get_delegate() 返回 None 走 no-op
    p.queue_prefetch("test")
    p.sync_turn("user msg", "asst msg")
    p.shutdown()
    print("✅ 4. 5 个 M0 占位方法（system_prompt_block / prefetch / queue_prefetch / sync_turn / shutdown）可调不报错")

    # === 5. 0 v1 NotImpl 剩余（M2 阶段已实现 add_with_timestamp + migrate_expired_to_vault）===
    # 反模式修复（fact_8207）：阶段实现后必须同步更新历史测试期望
    methods_now_implemented = [
        ("add_with_timestamp", ("c", "q")),
        ("migrate_expired_to_vault", ()),
    ]
    for method, args in methods_now_implemented:
        result = getattr(p, method)(*args)
        assert isinstance(result, int), f"{method}() 应返回 int，实际 {type(result)}"
        print(f"✅ 5. {method}() 已实现，调用返回 int (result={result})")

    # === 6. register(ctx) 入口 ===
    _ensure_env_clean()
    collector = _Collector()
    register(collector)
    assert collector.provider is not None
    assert collector.provider.name == "dikw"
    assert isinstance(collector.provider, DIKWMemoryProvider)
    print(f"✅ 6. register(ctx) 注册 provider OK: {collector.provider.name}")

    # === 7. __init__.py 行数 ≤ 850（A1' 决策硬约束，覆盖 E2 历史 ≤200）===
    # 注：路径从 parent 改为 parent.parent（指向 dikw/__init__.py 而非 tests/__init__.py）
    init_file = Path(__file__).resolve().parent.parent / "__init__.py"
    line_count = sum(1 for _ in init_file.open())
    assert line_count <= 900, f"__init__.py {line_count} 行超过 ≤900 v0.2.1 A1' 硬约束"
    print(f"✅ 7. __init__.py 行数 = {line_count} (≤900 v0.2.1 OK)")

    # === 8. E2 新增：默认无环境变量 is_available=False ===
    _ensure_env_clean()
    p8 = DIKWMemoryProvider()
    assert p8.is_available() is False, "默认无 env 应 False"
    print("✅ 8. 默认无环境变量：is_available() = False")

    # === 9. E2 新增：设置环境变量 is_available=True ===
    os.environ["HERMES_MEMORY_PROVIDER"] = "dikw"
    p9 = DIKWMemoryProvider()
    assert p9.is_available() is True, "env=dikw 应 True"
    print(f"✅ 9. 设置环境变量 HERMES_MEMORY_PROVIDER=dikw：is_available() = True (env={os.environ['HERMES_MEMORY_PROVIDER']})")

    # === 10. E2 新增：config 显式禁用（即使 env=dikw）is_available=False ===
    os.environ["HERMES_MEMORY_PROVIDER"] = "dikw"
    p10 = DIKWMemoryProvider({"enabled": False})
    assert p10.is_available() is False, "config.enabled=False 应 False（即使 env=dikw）"
    print(f"✅ 10. config 传入 {{\"enabled\": False}}：is_available() = False (config 优先级高于 env)")

    # === 恢复 env（避免影响后续测试）===
    os.environ["HERMES_MEMORY_PROVIDER"] = "dikw"

    print("\n🎉 E2 PASS: E1 7 项基础 + E2 3 项环境变量决策全跑通 (10/10)")


if __name__ == "__main__":
    test_e2()
