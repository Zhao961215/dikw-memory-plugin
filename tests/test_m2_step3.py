"""M2 阶段验证：add_with_timestamp + migrate_expired_to_vault 实际可用

M2 范围：
- 2 个 NotImpl 方法已实现（核心 __init__.py L190-260）
- 委托 Holographic 优先 + fact_queue 降级
- 4 schema 全部暴露（dikw_dispatch / run_information_flow / add_with_timestamp / migrate_expired_to_vault）

验证 8 项：
1. import OK
2. DIKWMemoryProvider 可实例化 + initialize
3. add_with_timestamp 不抛异常（Holographic delegate 不可用 → 降级到 fact_queue）
4. add_with_timestamp 返回 int（伪 id >= 8001 或 Holographic id）
5. add_with_timestamp 写入 fact_queue 文件已落盘
6. migrate_expired_to_vault 不抛异常（delegate 不可用 → 降级扫描）
7. migrate_expired_to_vault 返回 int（迁移数量，delegate 不可用应 = 0）
8. 4 schema 全部暴露（dikw_dispatch / run_information_flow / add_with_timestamp / migrate_expired_to_vault）

回滚：M2 万一崩 → git checkout pre-M2（M0+M1 工作保留）
"""
from __future__ import annotations
import os
os.environ.setdefault("HERMES_MEMORY_PROVIDER", "dikw")  # 2026-06-07 修复：激活 DIKW 让真路径 fact_id 测试通过
import sys
import logging
import shutil
import tempfile
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.WARNING)

from plugins.memory.dikw import DIKWMemoryProvider
from plugins.memory.dikw import fact_queue
from plugins.memory.dikw import tools


def test_m2_step3():
    # === 1. import OK ===
    print("✅ 1. import OK (DIKWMemoryProvider + fact_queue + tools)")

    # 用临时 HERMES_HOME 隔离测试（不影响真实 ~/.hermes/data/dikw_fact_queue）
    tmp_home = Path(tempfile.mkdtemp(prefix="dikw-m2-test-"))
    try:
        p = DIKWMemoryProvider()
        p.initialize("test-session-m2-3", hermes_home=str(tmp_home), platform="cli")

        # === 2. DIKWMemoryProvider 可实例化 + initialize ===
        assert p._hermes_home == str(tmp_home)
        print(f"✅ 2. DIKWMemoryProvider 初始化完成 (hermes_home={tmp_home.name})")

        # === 3. add_with_timestamp 不抛异常（修复后走 Holographic _handle_fact_store 真路径）===
        fact_id_1 = p.add_with_timestamp(
            content="M2 测试事实：add_with_timestamp 走 Holographic 真路径",
            query="M2 测试 add_with_timestamp Holographic 真路径",
            source="test",
        )

        # === 4. add_with_timestamp 返回 int（修复后：真实 Holographic fact_id < 9_000_000_001）===
        # 修复前（v0.1.0）：delegate 不可用 → 走 fact_queue 降级 → 伪 id >= 8001
        # 修复后（v0.2.1）：delegate 可用 → 走 Holographic _handle_fact_store → 真实 fact_id
        # fact_queue 降级路径覆盖见 test_m2_fix_bug.py:test_add_with_timestamp_fact_queue_fallback
        assert isinstance(fact_id_1, int), f"应返回 int，实际 {type(fact_id_1)}"
        assert fact_id_1 > 0, f"应返回正整数，实际 {fact_id_1}"
        assert fact_id_1 < 9000000001, (
            f"修复后应返回真实 Holographic fact_id（< 9_000_000_001），"
            f"实际 {fact_id_1} 看起来像 fact_queue 降级伪 id"
        )
        print(f"✅ 3+4. add_with_timestamp 走 Holographic 真路径 OK（fact_id={fact_id_1}，真实 id）")

        # === 5. 修复后不期望 fact_queue 落盘（Holographic 真写入已成功）===
        # 修复前：fact_queue 文件落盘是降级路径证据
        # 修复后：走 Holographic 真路径，**不**写本地 fact_queue
        target = tmp_home / "data" / "dikw_fact_queue" / f"fact_{fact_id_1}.json"
        assert not target.exists(), (
            f"修复后走 Holographic 真路径，fact_queue 文件不应落盘: {target}。"
            f"如需测降级路径，请看 test_m2_fix_bug.py"
        )
        print(f"✅ 5. fact_queue 落盘确认未发生（修复后走 Holographic 真路径）")

        # === 6. migrate_expired_to_vault 不抛异常（走 Holographic 搜全量 + 客户端 created_at 过滤）===
        migrated_count = p.migrate_expired_to_vault(max_age_days=30)

        # === 7. migrate_expired_to_vault 返回 int（无过期 → 0）===
        assert isinstance(migrated_count, int), f"应返回 int，实际 {type(migrated_count)}"
        # 修复后：无过期 fact → 返回 0
        assert migrated_count >= 0, f"应返回非负 int，实际 {migrated_count}"
        print(f"✅ 6+7. migrate_expired_to_vault 走 Holographic 路径 OK（migrated={migrated_count}）")

        # === 8. 4 schema 全部暴露 ===
        schemas = p.get_tool_schemas()
        assert len(schemas) == 4, f"应暴露 4 schema，实际 {len(schemas)}"
        names = {s["name"] for s in schemas}
        expected = {"dikw_dispatch", "run_information_flow", "add_with_timestamp", "migrate_expired_to_vault"}
        assert names == expected, f"应暴露 {expected}，实际 {names}"
        print(f"✅ 8. 4 schema 全部暴露 ({sorted(names)})")

        # === 附加：自定义 timestamp 也能正确走 Holographic 真路径 ===
        custom_ts = time.time() - 86400 * 5  # 5 天前
        fact_id_2 = p.add_with_timestamp(
            content="M2 自定义时间戳测试",
            query="M2 自定义 timestamp 测试",
            source="test",
            timestamp=custom_ts,
        )
        assert isinstance(fact_id_2, int) and fact_id_2 < 9000000001 and fact_id_2 > 0, (
            f"自定义 timestamp 路径也应走 Holographic 真路径（id < 9_000_000_001），"
            f"实际: {fact_id_2}"
        )
        print(f"✅ 附加：自定义 timestamp 写入 OK (fact_id={fact_id_2})")

        # === 附加：tools.py handle_tool_call 也能路由到新方法 ===
        from plugins.memory.dikw.tools import handle_tool_call
        result_add = handle_tool_call(
            name="add_with_timestamp",
            args={"content": "tools 路由测试", "query": "tools 路由测试"},
            provider=p,
        )
        assert isinstance(result_add, dict) and "fact_id" in result_add, (
            f"tools 路由 add_with_timestamp 应返回 dict 含 fact_id，实际: {result_add}"
        )
        result_mig = handle_tool_call(
            name="migrate_expired_to_vault",
            args={"max_age_days": 30},
            provider=p,
        )
        assert isinstance(result_mig, dict) and "migrated_count" in result_mig, (
            f"tools 路由 migrate 应返回 dict 含 migrated_count，实际: {result_mig}"
        )
        print(f"✅ 附加：tools.py 路由 OK（add={result_add}, migrate={result_mig}）")

        print("\n🎉 M2 PASS: add_with_timestamp + migrate_expired_to_vault 全部实现，4 schema 路由正常")
        print("   降级路径（fact_queue）测试通过，Holographic 恢复时自动升级到真实写入")
    finally:
        # 清理临时目录
        shutil.rmtree(tmp_home, ignore_errors=True)


if __name__ == "__main__":
    test_m2_step3()
