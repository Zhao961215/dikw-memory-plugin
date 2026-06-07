"""DIKW Memory Provider 工具层（M2.2 拆分）

X2 决策：从 __init__.py 核心拆分出本文件，专门承载 4 工具 schema + 路由。
- 不计入 A1 硬约束（850 行）的核心预算
- 独立维护工具层，核心只保留委托逻辑

4 工具（M2.2 范围）：
  1. dikw_dispatch            — DIKW 分流主入口（已实现 in __init__）
  2. run_information_flow     — 12 步信息流（已实现 in __init__）
  3. add_with_timestamp       — 时效性管理（M2 阶段）
  4. migrate_expired_to_vault  — 过期迁移（M2 阶段）

ABC 定义（agent/memory_provider.py L134-141）：
  schema = {name, description, parameters (JSON Schema)}
"""
from __future__ import annotations
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("plugins.memory.dikw.tools")


# === 4 schema 定义 ===

_SCHEMA_DIKW_DISPATCH: Dict[str, Any] = {
    "name": "dikw_dispatch",
    "description": (
        "DIKW 分流主入口：自动将内容分类为 D/I/K/W/L 5 类，"
        "D/I/K 单写 vault，W/L 双写 vault + fact_store。"
        "返回 {category, path, fact_id}。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "要存储的内容文本（必填）",
            },
            "context": {
                "type": "object",
                "description": (
                    "分流上下文（可选）："
                    "{source, type, id, title, query, entity_type}"
                ),
                "properties": {
                    "source": {"type": "string", "description": "来源标识"},
                    "type": {"type": "string", "description": "内容类型"},
                    "query": {"type": "string", "description": "检索关键词"},
                    "title": {"type": "string", "description": "标题（用于 K 类文件名）"},
                },
            },
        },
        "required": ["content"],
    },
}

_SCHEMA_RUN_FLOW: Dict[str, Any] = {
    "name": "run_information_flow",
    "description": (
        "12 步信息流主流程：检索大脑→图书馆 5 层→Plan 拆解→"
        "工具选择→执行→反馈→迭代（DIKW 分流）。"
        "返回 FlowResult {plan, results, feedback_list, iterations, summary}。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "instruction": {
                "type": "string",
                "description": "用户的指令文本（必填）",
            },
        },
        "required": ["instruction"],
    },
}

_SCHEMA_ADD_WITH_TS: Dict[str, Any] = {
    "name": "add_with_timestamp",
    "description": (
        "带 3 时间字段（created_at/updated_at/accessed_at）的 fact 写入："
        "实现时效性管理（主上 v1 精化原话 #4）。"
        "返回 {fact_id, created_at, updated_at}。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "事实内容文本（必填）",
            },
            "query": {
                "type": "string",
                "description": "检索关键词（必填，HRR 编码用）",
            },
            "source": {
                "type": "string",
                "description": "来源分类（可选，如 general/lesson/project）",
            },
        },
        "required": ["content", "query"],
    },
}

_SCHEMA_MIGRATE: Dict[str, Any] = {
    "name": "migrate_expired_to_vault",
    "description": (
        "扫描大脑中的过期事实（30/90 天硬规则），"
        "迁移到 vault 图书馆便于回溯和查阅。"
        "返回 {migrated_count, remaining_count}。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "max_age_days": {
                "type": "integer",
                "description": "最大保留天数（默认 30/90）",
            },
        },
    },
}


# === 4 schema 聚合 + 路由 ===

ALL_SCHEMAS: List[Dict[str, Any]] = [
    _SCHEMA_DIKW_DISPATCH,
    _SCHEMA_RUN_FLOW,
    _SCHEMA_ADD_WITH_TS,
    _SCHEMA_MIGRATE,
]


def get_tool_schemas() -> List[Dict[str, Any]]:
    """M2.2: 返回 4 个工具的 schema（OpenAI function calling 格式）

    返回：4 schema dict 的列表
    静默降级：方法本身不抛异常
    """
    return list(ALL_SCHEMAS)


# === 路由实现（handle_tool_call 4 工具名字 → 4 方法）===

def handle_tool_call(
    name: str,
    args: Dict[str, Any],
    provider: Any,
) -> Dict[str, Any]:
    """M2.2: 工具路由 — 4 工具名字 → 4 方法

    修复（2026-06-07 bug fix）：每个方法加 try/except 包裹，provider 抛异常时
    返回 dict 包含 error 字段（不抛 ValueError 阻断 session 端调用）。

    Args:
        name: 工具名字（dikw_dispatch / run_information_flow / ...）
        args: 工具参数 dict
        provider: DIKWMemoryProvider 实例（提供委托方法）

    Returns:
        工具执行结果 dict（不同工具返回结构不同）

    Raises:
        ValueError: 未知工具名
    """
    try:
        if name == "dikw_dispatch":
            return provider.dikw_dispatch(
                content=args.get("content", ""),
                context=args.get("context"),
            )
        if name == "run_information_flow":
            return provider.run_information_flow(
                instruction=args.get("instruction", ""),
            )
        if name == "add_with_timestamp":
            fid = provider.add_with_timestamp(
                content=args.get("content", ""),
                query=args.get("query", ""),
                source=args.get("source"),
            )
            return {"fact_id": fid, "created_at": None, "updated_at": None}
        if name == "migrate_expired_to_vault":
            n = provider.migrate_expired_to_vault(
                max_age_days=args.get("max_age_days"),
            )
            return {"migrated_count": n, "remaining_count": None}
    except Exception as e:
        logger.debug("DIKW: handle_tool_call(%s) failed: %s", name, e)
        return {"error": f"{name} failed: {str(e)[:200]}", "name": name}
    raise ValueError(f"未知工具名: {name}（DIKW provider 不支持）")


def get_handler(name: str) -> Optional[Callable[..., Dict[str, Any]]]:
    """返回指定工具的 partial handler（仅 name 部分绑定）

    修复（2026-06-07 bug fix）：加 ALL_SCHEMAS 校验 + name 不存在时返回 None。
    使用场景：session 端按 name 索引 handler，args 由 session 端传入
    """
    if name not in (s["name"] for s in ALL_SCHEMAS):
        return None
    return lambda args, provider: handle_tool_call(name, args, provider)
