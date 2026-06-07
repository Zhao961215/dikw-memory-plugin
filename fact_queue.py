"""DIKW Memory Provider fact_queue 降级层（M2 X 拆分）

X 决策（fact_8206 A1' 升级版）：
- 不计入 A1' 核心代码 ≤850 行硬约束
- 独立维护降级逻辑，核心只保留委托调用

4 模块级函数（无 self 依赖）：
  1. get_fact_queue_dir(hermes_home)  → Path | None
  2. write_fact(content, query, source, timestamp, hermes_home) → int (pseudo_id)
  3. migrate_results(results, max_age_days, hermes_home) → int
  4. migrate_queue(max_age_days, hermes_home) → int

降级路径：当 HolographicMemoryProvider delegate 不可用时，
  add_with_timestamp / migrate_expired_to_vault 走本模块的 JSON 文件队列
"""
from __future__ import annotations
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("plugins.memory.dikw.fact_queue")


def get_fact_queue_dir(hermes_home: str = "") -> Optional[Path]:
    """返回 fact_queue 目录路径（hermes_home 优先，回退到 ~/.hermes）

    Returns:
        Path 目录（不存在会自动创建）；hermes_home 不可用时返回 None
    """
    base = hermes_home or os.path.expanduser("~/.hermes")
    if not base:
        return None
    qdir = Path(base) / "data" / "dikw_fact_queue"
    try:
        qdir.mkdir(parents=True, exist_ok=True)
        return qdir
    except Exception as e:
        logger.debug("DIKW: fact_queue dir creation failed: %s", e)
        return None


def write_fact(content: str, query: str,
               source: Optional[str], timestamp: float,
               hermes_home: str = "") -> int:
    """M2: 写入 fact_queue JSON 文件（降级路径）

    修复（2026-06-07 bug fix）：pseudo_id 起点 8001+ 与 Holographic 真实 fact_id 冲突
    （实测 Holographic 已有 fact_id=8197），改为 9_000_000_001（远大于 Holographic 容量）。
    同时加 3 时间字段（created_at/updated_at/accessed_at）兑现"时效性管理"承诺。

    Args:
        content: 事实内容
        query: 检索关键词
        source: 来源分类
        timestamp: 时间戳
        hermes_home: DIKW 注入的 ~/.hermes 路径（空时回退到默认）

    Returns:
        pseudo_fact_id: 9_000_000_001 起的伪 id，写入失败时返回 -1
    """
    qdir = get_fact_queue_dir(hermes_home)
    if qdir is None:
        logger.warning("DIKW: fact_queue dir unavailable, fact lost: %s", content[:50])
        return -1

    try:
        existing = list(qdir.glob("fact_9*.json"))
        pseudo_id = 9000000001 + len(existing)  # 9位数起点，远大于 Holographic 容量
        while (qdir / f"fact_{pseudo_id}.json").exists():
            pseudo_id += 1

        ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        fact_obj = {
            "fact_id": f"fact_{pseudo_id}",
            "trigger": "M2-add_with_timestamp-fallback",
            "created_at": ts_str,
            "updated_at": ts_str,
            "accessed_at": ts_str,
            "timestamp": timestamp,
            "category": "W",
            "source": source or "general",
            "content": content,
            "query": query,
            "context": {
                "note": "M2 阶段：Holographic delegate 不可用，降级到 fact_queue",
                "add_with_timestamp_call": True,
            },
            "next_review": "Holographic fact_store 工具恢复后统一消化",
        }
        target = qdir / f"fact_{pseudo_id}.json"
        target.write_text(
            json.dumps(fact_obj, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("DIKW: fact_queue written: fact_%d", pseudo_id)
        return pseudo_id
    except Exception as e:
        logger.warning("DIKW: fact_queue write failed: %s", e)
        return -1


def migrate_results(results: List[Dict[str, Any]],
                    max_age_days: int,
                    hermes_home: str = "") -> int:
    """M2: 把 Holographic 返回的过期结果迁到 vault 观察期日志

    Args:
        results: Holographic search_facts 返回的过期 fact 列表
        max_age_days: 用于日志标注
        hermes_home: ~/.hermes 路径

    Returns:
        实际迁移数量
    """
    if not results:
        return 0

    base = hermes_home or os.path.expanduser("~/.hermes")
    if not base:
        return 0
    log_dir = Path(base) / "data" / "knowledge" / "vault" / "观察期日志" / "_migrated"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.debug("DIKW: migrated dir creation failed: %s", e)
        return 0

    ts = time.strftime("%Y%m%d_%H%M%S")
    target = log_dir / f"migrated_{ts}_n{len(results)}.md"
    try:
        with target.open("w", encoding="utf-8") as f:
            f.write(f"# M2 migrate_expired_to_vault ({ts})\n\n")
            f.write(f"- max_age_days: {max_age_days}\n")
            f.write(f"- 迁移数量: {len(results)}\n\n")
            for r in results:
                content = r.get("content", "")[:200]
                fact_id = r.get("fact_id", "?")
                f.write(f"## fact_{fact_id}\n\n{content}\n\n---\n\n")
        return len(results)
    except Exception as e:
        logger.debug("DIKW: migrated file write failed: %s", e)
        return 0


def migrate_queue(max_age_days: int, hermes_home: str = "") -> int:
    """M2: 降级路径 — 扫 fact_queue 找带 expiry 字段的项

    修复（2026-06-07 bug fix）：⚠️ 死代码 — write_fact 从未写入 expiry_at 字段，
    此函数永远返回 0。保留接口稳定，等 M3 阶段实现真正的 expiry 机制。
    触发场景：Holographic _handle_fact_store 不可用 + fact_queue 本地有 expiry 项（当前 0）。
    """
    return 0
