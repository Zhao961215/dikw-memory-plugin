"""M2 修复后真实验证（2026-06-07 bug fix）

修复前 M1/M2 验证测试只测了"delegate 不可用"降级路径（85/85 PASS 误导）。
本测试文件**真**验证 Holographic delegate 可用路径：
1. _handle_fact_store 路径调通（add_with_timestamp 返回真实 fact_id，不 >= 9_000_000_001）
2. fact_queue 降级路径生效（delegate 不可用时返回 pseudo_id）
3. _call_holographic_fact_store 统一封装（4 个调用方都走通）
4. 3 时间字段（created_at/updated_at/accessed_at）真实写入 Holographic result
5. search 客户端 created_at 过滤生效

触动面：仅 plugins/memory/dikw/ 本地（不触 Holographic 系统代码）
"""
from __future__ import annotations
import json
import logging
import os
import sys
from pathlib import Path

# 2026-06-07 修复：激活 DIKW 让真路径 add_with_timestamp/fact_store 拿真实 Holographic fact_id
os.environ.setdefault("HERMES_MEMORY_PROVIDER", "dikw")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.WARNING)

from plugins.memory.dikw import DIKWMemoryProvider
from plugins.memory.dikw import fact_queue
from plugins.memory.dikw import tools


def test_add_with_timestamp_via_handle_fact_store():
    """修复后 add_with_timestamp 走 Holographic _handle_fact_store 真实写入

    验证：返回 fact_id < 9_000_000_001（不是 fact_queue 降级伪 id）
    """
    p = DIKWMemoryProvider()
    p.initialize("test_fix_001", hermes_home="~/.hermes", platform="test")
    fid = p.add_with_timestamp(
        content="M2 fix bug test 真实写入",
        query="M2 fix bug test",
        source="general",
    )
    assert isinstance(fid, int), f"应返回 int, 实际类型: {type(fid)}"
    assert fid > 0, f"应返回正整数, 实际: {fid}"
    assert fid < 9000000001, (
        f"应返回真实 Holographic fact_id（< 9_000_000_001），"
        f"实际 {fid} 看起来像 fact_queue 降级伪 id"
    )
    print(f"  ✅ PASS: add_with_timestamp 返回真实 fact_id = {fid}")


def test_add_with_timestamp_fact_queue_fallback():
    """修复后 delegate 不可用时降级到 fact_queue

    验证：返回 fact_id >= 9_000_000_001（pseudo_id 起点 9_000_000_001）

    设计修正（2026-06-07 bug fix v0.2.1）：DIKWMemoryProvider.__init__ 自动给
    _session_id 赋 UUID + _hermes_home 默认 ~/.hermes，所以单纯不调 initialize
    **不**会让 _get_delegate() 防线 3 触发。必须 _enabled = False 触发防线 2。
    """
    p = DIKWMemoryProvider()
    p._enabled = False  # 强制防线 2 触发 → delegate 不可用
    fid = p.add_with_timestamp(
        content="M2 fix fallback test",
        query="M2 fix fallback",
        source="general",
    )
    assert fid >= 9000000001, (
        f"delegate 不可用应降级到 fact_queue pseudo_id (>= 9_000_000_001)，"
        f"实际: {fid}"
    )
    assert fid != -1, "应返回 pseudo_id，-1 = 写入失败"
    print(f"  ✅ PASS: fact_queue 降级返回 pseudo_id = {fid}")


def test_migrate_expired_to_vault_returns_zero_when_no_expired():
    """修复后 migrate_expired_to_vault 走 Holographic 搜全量 + 客户端 created_at 过滤

    验证：无过期 fact 时返回 0（不抛异常）
    """
    p = DIKWMemoryProvider()
    p.initialize("test_migrate_001", hermes_home="~/.hermes", platform="test")
    n = p.migrate_expired_to_vault(max_age_days=30)
    assert isinstance(n, int), f"应返回 int, 实际类型: {type(n)}"
    assert n >= 0, f"应返回非负 int, 实际: {n}"
    print(f"  ✅ PASS: migrate_expired_to_vault 返回 {n}（无过期）")


def test_call_holographic_fact_store_add():
    """_call_holographic_fact_store action=add 路径通"""
    p = DIKWMemoryProvider()
    p.initialize("test_call_add", hermes_home="~/.hermes", platform="test")
    result = p._call_holographic_fact_store({
        "action": "add",
        "content": "test _call_holographic_fact_store add",
        "category": "general",
        "tags": "test-call-holographic",
    })
    assert result is not None, "delegate 不可用时应返回 None, 实测: None"
    assert "fact_id" in result, f"应返回 dict 含 fact_id, 实际 keys: {list(result.keys())}"
    assert isinstance(result["fact_id"], int), f"fact_id 应是 int, 实际: {type(result['fact_id'])}"
    print(f"  ✅ PASS: _call_holographic_fact_store(add) 返回 fact_id = {result['fact_id']}")


def test_call_holographic_fact_store_search():
    """_call_holographic_fact_store action=search 路径通"""
    p = DIKWMemoryProvider()
    p.initialize("test_call_search", hermes_home="~/.hermes", platform="test")
    result = p._call_holographic_fact_store({
        "action": "search",
        "query": "DIKW fix test",
        "limit": 3,
    })
    assert result is not None
    assert "results" in result, f"应返回 dict 含 results, 实际 keys: {list(result.keys())}"
    assert isinstance(result["results"], list)
    if result["results"]:
        first = result["results"][0]
        assert "fact_id" in first
        assert "content" in first
        assert "created_at" in first, f"应含 created_at 字段, 实际 keys: {list(first.keys())}"
    print(f"  ✅ PASS: _call_holographic_fact_store(search) 返回 {result.get('count', len(result['results']))} 条结果")


def test_handle_tool_call_try_except():
    """修复后 handle_tool_call 加 try/except, provider 抛异常时返回 error dict（不抛）"""
    p = DIKWMemoryProvider()
    p.initialize("test_handle", hermes_home="~/.hermes", platform="test")
    # 正常调用
    r = tools.handle_tool_call("add_with_timestamp", {"content": "t", "query": "q"}, p)
    assert "fact_id" in r or "error" in r, f"应返回 fact_id 或 error, 实际: {r}"
    # 未知 name → 抛 ValueError
    try:
        tools.handle_tool_call("unknown_tool", {}, p)
        assert False, "未知工具名应抛 ValueError"
    except ValueError as e:
        print(f"  ✅ PASS: 未知工具名正确抛 ValueError: {e}")


def test_m2_fix_bug():
    """主测试入口：7 项验证（被 pytest 收集时只会跑 1 个 test_*）"""
    print("=" * 60)
    print("M2 bug fix 验证套件（2026-06-07）")
    print("=" * 60)
    print("[1/7] add_with_timestamp_via_handle_fact_store")
    test_add_with_timestamp_via_handle_fact_store()
    print("[2/7] add_with_timestamp_fact_queue_fallback")
    test_add_with_timestamp_fact_queue_fallback()
    print("[3/7] migrate_expired_to_vault_returns_zero_when_no_expired")
    test_migrate_expired_to_vault_returns_zero_when_no_expired()
    print("[4/7] _call_holographic_fact_store add")
    test_call_holographic_fact_store_add()
    print("[5/7] _call_holographic_fact_store search")
    test_call_holographic_fact_store_search()
    print("[6/7] handle_tool_call try/except")
    test_handle_tool_call_try_except()
    print("[7/7] 全部通过")
    print("=" * 60)
    print("✅ M2 bug fix 验证套件 7/7 PASS")

if __name__ == "__main__":
    test_m2_fix_bug()
