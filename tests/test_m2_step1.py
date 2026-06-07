"""M2.1 验证：get_tool_schemas() 暴露 2 个已实现工具的 schema

M2.1 范围（仅暴露 schema，不实现 handle_tool_call 路由，留到 M2.2）：
- 已暴露: dikw_dispatch + run_information_flow
- 未暴露（等 M2.2）: add_with_timestamp + migrate_expired_to_vault

验证 7 项：
1. import OK
2. get_tool_schemas() 返回 list
3. list 长度 = 2
4. dikw_dispatch schema 字段完整（name/description/parameters）
5. dikw_dispatch parameters 含 content (required) + context (optional)
6. run_information_flow schema 字段完整
7. run_information_flow parameters 含 instruction (required)

回滚：M2.1 万一崩 → git checkout pre-M2.1
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


def test_m2_step1():
    # === 1. import OK ===
    print("✅ 1. import OK (DIKWMemoryProvider)")

    p = DIKWMemoryProvider()
    p.initialize("test-session-m2-1", hermes_home="/tmp/test-hermes", platform="cli")

    # === 2. get_tool_schemas() 返回 list ===
    schemas = p.get_tool_schemas()
    assert isinstance(schemas, list), f"应返回 list，实际 {type(schemas)}"
    print(f"✅ 2. get_tool_schemas() 返回 list ({len(schemas)} 个)")

    # === 3. list 长度 = 4（M2.2 委托 tools.py 后 = 4，> 2 即可）===
    assert len(schemas) >= 2, f"应返回 ≥ 2 个 schema，实际 {len(schemas)}"
    print(f"✅ 3. list 长度 = {len(schemas)} (M2.2 委托 tools.py 后 4 个，期望 ≥2)")

    # === 4. dikw_dispatch schema 字段完整 ===
    dispatch = next((s for s in schemas if s["name"] == "dikw_dispatch"), None)
    assert dispatch is not None, "应包含 dikw_dispatch schema"
    for key in ("name", "description", "parameters"):
        assert key in dispatch, f"dikw_dispatch schema 缺 {key} 字段"
    assert dispatch["name"] == "dikw_dispatch"
    assert "DIKW 分流" in dispatch["description"] or "DIKW" in dispatch["description"]
    print(f"✅ 4. dikw_dispatch schema 字段完整 (name/description/parameters)")

    # === 5. dikw_dispatch parameters 含 content (required) + context (optional) ===
    params = dispatch["parameters"]
    assert params["type"] == "object", "parameters.type 应为 object"
    assert "content" in params["properties"], "parameters 应含 content"
    assert "content" in params["required"], "content 应为 required"
    assert params["properties"]["content"]["type"] == "string", "content.type 应为 string"
    # context 是可选（不在 required 中）
    assert "context" in params["properties"], "parameters 应含 context（可选）"
    assert "context" not in params["required"], "context 应为 optional（不在 required）"
    print(f"✅ 5. dikw_dispatch parameters OK (content required + context optional)")

    # === 6. run_information_flow schema 字段完整 ===
    run_flow = next((s for s in schemas if s["name"] == "run_information_flow"), None)
    assert run_flow is not None, "应包含 run_information_flow schema"
    for key in ("name", "description", "parameters"):
        assert key in run_flow, f"run_information_flow schema 缺 {key} 字段"
    assert run_flow["name"] == "run_information_flow"
    assert "12 步" in run_flow["description"] or "信息流" in run_flow["description"]
    print(f"✅ 6. run_information_flow schema 字段完整")

    # === 7. run_information_flow parameters 含 instruction (required) ===
    rparams = run_flow["parameters"]
    assert rparams["type"] == "object", "parameters.type 应为 object"
    assert "instruction" in rparams["properties"], "parameters 应含 instruction"
    assert "instruction" in rparams["required"], "instruction 应为 required"
    assert rparams["properties"]["instruction"]["type"] == "string"
    # M2.2 范围验证：4 个 schema 全部暴露（add_with_timestamp + migrate 已暴露，方法实现等 M2 阶段）
    all_names = {s["name"] for s in schemas}
    assert "dikw_dispatch" in all_names, "应暴露 dikw_dispatch"
    assert "run_information_flow" in all_names, "应暴露 run_information_flow"
    assert "add_with_timestamp" in all_names, "M2.2 应暴露 add_with_timestamp"
    assert "migrate_expired_to_vault" in all_names, "M2.2 应暴露 migrate_expired_to_vault"
    print(f"✅ 7. run_information_flow parameters OK + M2.2 范围验证（4 schema 全部暴露）")

    print("\n🎉 M2.1 PASS: get_tool_schemas() 暴露 2 schema（dikw_dispatch + run_information_flow），格式符合 OpenAI function calling 标准")


if __name__ == "__main__":
    test_m2_step1()
