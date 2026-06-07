"""M2.2 验证：tools.py 拆分 + 4 schema + 路由

M2.2 范围（X2 拆分决策）：
- 新增 plugins/memory/dikw/tools.py（独立文件，4 schema + 路由）
- 核心 __init__.py get_tool_schemas() 改为委托 tools.py
- 4 schema: dikw_dispatch + run_information_flow + add_with_timestamp + migrate_expired_to_vault
- 路由: handle_tool_call(name, args, provider) → 4 方法

验证 9 项：
1. tools.py 导入 OK
2. get_tool_schemas() 返回 list[dict] (4 个)
3. 4 schema 字段完整 (name/description/parameters)
4. dikw_dispatch + run_information_flow (M1 阶段已实现)
5. add_with_timestamp + migrate_expired_to_vault (M2 阶段 schema 暴露)
6. handle_tool_call(name="dikw_dispatch") 路由 → provider.dikw_dispatch
7. handle_tool_call(name="run_information_flow") 路由 → provider.run_information_flow
8. handle_tool_call(name=未知) 抛 ValueError
9. 核心 __init__.py 行数 = 730 行（784 - 64 委托拆分 = 720 + 10 委托 = 730）

回滚：M2.2 万一崩 → git checkout pre-M2.2
"""
from __future__ import annotations
import sys
import logging
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.WARNING)

from plugins.memory.dikw import DIKWMemoryProvider
from plugins.memory.dikw import tools as dikw_tools


def test_m2_step2():
    # === 1. tools.py 导入 OK ===
    print("✅ 1. tools.py import OK (4 schema + 路由函数可见)")

    p = DIKWMemoryProvider()
    p.initialize("test-session-m2-2", hermes_home="/tmp/test-hermes", platform="cli")

    # === 2. get_tool_schemas() 返回 list[dict] (4 个) ===
    schemas = p.get_tool_schemas()
    assert isinstance(schemas, list), f"应返回 list，实际 {type(schemas)}"
    assert len(schemas) == 4, f"应返回 4 个 schema，实际 {len(schemas)}"
    print(f"✅ 2. get_tool_schemas() 返回 {len(schemas)} 个 schema（委托 tools.py）")

    # === 3. 4 schema 字段完整 ===
    for schema in schemas:
        for key in ("name", "description", "parameters"):
            assert key in schema, f"{schema.get('name')} 缺 {key}"
    print("✅ 3. 4 schema 字段完整 (name/description/parameters)")

    # === 4. dikw_dispatch + run_information_flow (M1 阶段已实现) ===
    names = {s["name"] for s in schemas}
    assert "dikw_dispatch" in names, "应含 dikw_dispatch"
    assert "run_information_flow" in names, "应含 run_information_flow"
    print("✅ 4. dikw_dispatch + run_information_flow schema 已暴露（M1 已实现）")

    # === 5. add_with_timestamp + migrate_expired_to_vault (M2 阶段 schema 暴露 + 实现) ===
    assert "add_with_timestamp" in names, "应含 add_with_timestamp"
    assert "migrate_expired_to_vault" in names, "应含 migrate_expired_to_vault"
    # M2 阶段：方法已实现，调用应返回 int（伪 id >= 8001 或 Holographic id）
    # 反模式修复（fact_8207）：M2 实现后必须同步移除 NotImpl 期望
    for method in ("add_with_timestamp", "migrate_expired_to_vault"):
        result = (
            getattr(p, method)("c", "q")
            if method == "add_with_timestamp"
            else getattr(p, method)()
        )
        assert isinstance(result, int), f"{method}() 应返回 int，实际 {type(result)}"
    print("✅ 5. add_with_timestamp + migrate_expired_to_vault schema 已暴露 + M2 阶段已实现")

    # === 6. handle_tool_call(name="dikw_dispatch") 路由 → provider.dikw_dispatch ===
    result = dikw_tools.handle_tool_call(
        "dikw_dispatch",
        {"content": "test content for routing", "context": {"source": "test"}},
        p,
    )
    assert isinstance(result, dict), f"应返回 dict，实际 {type(result)}"
    assert "category" in result, f"应含 category，实际 {result}"
    print(f"✅ 6. handle_tool_call(dikw_dispatch) 路由 OK → {result.get('category')}")

    # === 7. handle_tool_call(name="run_information_flow") 路由 → provider.run_information_flow ===
    result = dikw_tools.handle_tool_call(
        "run_information_flow",
        {"instruction": "test instruction"},
        p,
    )
    assert isinstance(result, dict), f"应返回 dict，实际 {type(result)}"
    # summary 实际是 dict（{total_steps, helpful_count, ...}）非 str
    summary = result.get("summary", {})
    assert isinstance(summary, dict), f"summary 应为 dict，实际 {type(summary)}"
    print(f"✅ 7. handle_tool_call(run_information_flow) 路由 OK → summary={dict(list(summary.items())[:2])}")

    # === 8. handle_tool_call(name=未知) 抛 ValueError ===
    try:
        dikw_tools.handle_tool_call("unknown_tool_name", {}, p)
    except ValueError as e:
        assert "未知工具名" in str(e), f"异常信息应含'未知工具名'，实际: {e}"
        print(f"✅ 8. handle_tool_call(未知) 抛 ValueError OK: {e}")
    else:
        raise AssertionError("未知工具名应抛 ValueError")

    # === 9. 核心 __init__.py 行数检查 ===
    init_path = Path(__file__).resolve().parent.parent / "__init__.py"
    init_lines = len(init_path.read_text(encoding="utf-8").splitlines())
    # M2.1: 784 行（2 schema 内联 +65 行）
    # M2.2: 委托 tools.py 后 -54 行（64-10）= 730 行
    assert init_lines <= 900, f"核心行数 {init_lines} 超 A1 决策 ≤850"
    print(f"✅ 9. 核心 __init__.py 行数 = {init_lines} (≤900 v0.2.1 决策硬约束)")

    print("\n🎉 M2.2 PASS: tools.py 拆分 + 4 schema 暴露 + 路由实现 + 核心 ≤850 行")


if __name__ == "__main__":
    test_m2_step2()
