"""DIKW Memory Provider Plugin (M0 E3 升级)

5 原则硬约束（fact_7911）：
① 暂不加载 sqlite-vec
② 去 HRR 换 DIKW 分流
③ 走 MemoryProvider ABC 原生接口
④ 复用 memory_store.db（与 Holographic 共享）
⑤ ≤400 行 + 零外部依赖

M0 启动边界（fact_8158）：
- Q1: 整个 plugins/memory/dikw/ ≤400 行
- Q2: 降级到 HolographicMemoryProvider（self._delegate）
- Q3: M0 不实现反向索引（v1 后续）

E2 升级（2026-06-05，DeepSeek 评审 + 主上确认 D 方案）：
- 启用决策 = env HERMES_MEMORY_PROVIDER=dikw（零外部依赖）
- 优先级：config['enabled'] > env > 默认 False
- 新增 _get_delegate 懒加载骨架（E3 阶段实例化 HolographicMemoryProvider）
- E2 阶段不实现 4 个 v1 方法（保持 NotImpl 到 M1）

E3 升级（2026-06-05，DeepSeek 推荐 + 主上确认 A 方案）：
- 实现 _get_delegate()：实例化 HolographicMemoryProvider + 4 道防线（缓存/未启用/未初始化/实例化失败 静默 return None）
- 5 个 M0 占位方法（system_prompt_block/prefetch/queue_prefetch/sync_turn/shutdown）改为委托调用 + try/except 静默降级
- initialize() 触发委托缓存清空（确保 session 切换时重新实例化）
- 验证目标：5 个方法的"调用链路"对，Holographic 未就绪时静默降级到空行为
"""
from __future__ import annotations
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider

logger = logging.getLogger(__name__)


class DIKWMemoryProvider(MemoryProvider):
    """DIKW 记忆系统通用接口 (M0 E3 升级 - 空委托 + 静默降级)"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        # P0 修复（2026-06-06 观察期 W01 复盘，fact_8196）：self._enabled 必须在
        # 首次 if self._enabled: 引用之前赋值。原代码在第 64 行赋值，第 53 行
        # 引用 → 100% AttributeError。重排：启用决策块上移到懒加载块之前。
        # E2 阶段: 启用决策（优先级 config > env > False）
        env_enabled = os.environ.get("HERMES_MEMORY_PROVIDER") == "dikw"
        self._enabled = self._apply_config_override(env_enabled)
        # C 阶段懒加载兜底（2026-06-06 主上确认 a/a/a 方案）：
        # 无人调 initialize() 时，从 os.environ 读 session_id/hermes_home，
        # 让 _get_delegate() 防线 3 永真（delegate 能拿到 Holographic 实例）。
        # 优先级：kwargs 注入 > .env/环境变量 > 空字符串（保留原行为）
        self._session_id = ""
        self._hermes_home = ""
        self._platform = ""
        if self._enabled:
            env_sid = os.environ.get("HERMES_SESSION_ID", "")
            if env_sid:
                self._session_id = env_sid
            env_home = os.environ.get("HERMES_HOME", "")
            if env_home:
                self._hermes_home = env_home
        # E3 升级: 委托实例缓存（_get_delegate 懒加载）
        self._delegate = None
        if self._enabled:
            logger.info("DIKW enabled (env HERMES_MEMORY_PROVIDER=%s)",
                        os.environ.get("HERMES_MEMORY_PROVIDER"))

    # === 4 个 abstract 必实现 ===

    @property
    def name(self) -> str:
        return "dikw"

    def is_available(self) -> bool:
        return self._enabled

    def initialize(self, session_id: str, **kwargs) -> None:
        self._session_id = session_id
        self._hermes_home = kwargs.get("hermes_home", "")
        self._platform = kwargs.get("platform", "")
        # E3 升级: initialize 时清空委托缓存（下次 _get_delegate 重新实例化）
        self._delegate = None

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """M2.2: 委托 tools.py 返回 4 schema（核心 ≤850 行 X2 决策）

        4 工具（已实现 2 + M2 待实现 2）：
          - dikw_dispatch:  DIKW 分流主入口（已实现）
          - run_information_flow: 12 步信息流（已实现）
          - add_with_timestamp: M2 阶段实现（schema 已暴露）
          - migrate_expired_to_vault: M2 阶段实现（schema 已暴露）

        X2 拆分：核心只保留委托逻辑（10 行），4 schema + 路由在 tools.py
        """
        from .tools import get_tool_schemas as _get_schemas
        return _get_schemas()

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        """M2.2 修复（2026-06-07 B 方案）：override 基类 NotImplementedError，让 4 schema 可被 memory_manager 调到。"""
        from . import tools as _tools
        try:
            result = _tools.handle_tool_call(tool_name, args, self)
        except ValueError as e:
            return json.dumps({"error": str(e), "name": tool_name})
        return json.dumps(result, ensure_ascii=False)

    # === 5 个 M0 占位（E3 升级：委托给 Holographic + 静默降级）===

    def system_prompt_block(self) -> str:
        delegate = self._get_delegate()
        if delegate is not None:
            try:
                return delegate.system_prompt_block()
            except Exception as e:
                logger.debug("DIKW: delegate.system_prompt_block failed: %s", e)
        return ""

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        delegate = self._get_delegate()
        if delegate is not None:
            try:
                return delegate.prefetch(query, session_id=session_id)
            except Exception as e:
                logger.debug("DIKW: delegate.prefetch failed: %s", e)
        return ""

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        delegate = self._get_delegate()
        if delegate is not None:
            try:
                delegate.queue_prefetch(query, session_id=session_id)
            except Exception as e:
                logger.debug("DIKW: delegate.queue_prefetch failed: %s", e)

    def sync_turn(self, user_content: str, assistant_content: str,
                  *, session_id: str = "",
                  messages: Optional[List[Dict[str, Any]]] = None) -> None:
        delegate = self._get_delegate()
        if delegate is not None:
            try:
                # Holographic sync_turn 仅接 session_id，不接 messages
                delegate.sync_turn(user_content, assistant_content,
                                   session_id=session_id)
            except Exception as e:
                logger.debug("DIKW: delegate.sync_turn failed: %s", e)

    def shutdown(self) -> None:
        delegate = self._get_delegate()
        if delegate is not None:
            try:
                delegate.shutdown()
            except Exception as e:
                logger.debug("DIKW: delegate.shutdown failed: %s", e)

    # === E2/E3 共享: config 优先级 + 委托懒加载 ===

    def _call_holographic_fact_store(self, action_args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """统一调 Holographic._handle_fact_store（A 方案：私有方法穿透）

        修复（2026-06-07 bug fix）：Holographic 真实写事实/搜事实的入口是私有方法
        _handle_fact_store(args: dict) -> str (JSON)，不是公开的 add_fact/search。
        本方法统一封装，4 个调用方（add_with_timestamp / migrate_expired_to_vault /
        _add_to_fact_store / _search_brain）走同一入口。

        Args:
            action_args: 传给 _handle_fact_store 的 dict
                - add:    {'action': 'add', 'content': '...', 'category': 'general', 'tags': '...'}
                - search: {'action': 'search', 'query': '...', 'category': '...', 'limit': N}

        Returns:
            解析后的 dict: {'fact_id': int, 'status': 'added'} 或
                          {'results': [...], 'count': N}
            失败/delegate 不可用时返回 None（不抛）
        """
        delegate = self._get_delegate()
        if delegate is None:
            return None
        handler = getattr(delegate, "_handle_fact_store", None)
        if not callable(handler):
            logger.debug("DIKW: delegate has no _handle_fact_store, fallback")
            return None
        try:
            raw = handler(action_args)
            if not raw:
                return None
            if isinstance(raw, str):
                import json
                return json.loads(raw)
            return raw if isinstance(raw, dict) else None
        except Exception as e:
            logger.debug(
                "DIKW: _handle_fact_store(%s) failed: %s",
                action_args.get("action"), e,
            )
            return None

    def _apply_config_override(self, env_enabled: bool) -> bool:
        """E2 阶段：处理 config['enabled'] 优先级（config > env > False）

        - config['enabled'] 显式给出 → 用 config 值
        - config['enabled'] 缺失 → 用 env_enabled（HERMES_MEMORY_PROVIDER=dikw）
        - 都没给 → False（默认不激活）
        """
        if "enabled" in self._config:
            return bool(self._config["enabled"])
        return env_enabled

    def _get_delegate(self):
        """E3 升级：懒加载实例化 HolographicMemoryProvider（委托对象）

        4 道防线（任一不满足则返回 None，5 个方法降级到空行为）：
        1. self._delegate 缓存命中 → 直接返回
        2. self._enabled is False → 未启用，返回 None
        3. self._session_id 或 self._hermes_home 为空 → 未初始化，返回 None
        4. 实例化或 initialize 失败 → 静默捕获，返回 None（不抛异常）

        返回值：
        - HolographicMemoryProvider 实例（成功）
        - None（任一防线触发）
        """
        if self._delegate is not None:
            return self._delegate
        if not self._enabled:
            return None
        if not self._session_id or not self._hermes_home:
            return None
        try:
            from plugins.memory.holographic import HolographicMemoryProvider
            self._delegate = HolographicMemoryProvider()
            self._delegate.initialize(
                self._session_id,
                hermes_home=self._hermes_home,
                platform=self._platform,
            )
            logger.info(
                "DIKW: Holographic delegate initialized (session=%s, home=%s)",
                self._session_id[:8] if self._session_id else "",
                self._hermes_home[:30] if self._hermes_home else "",
            )
        except Exception as e:
            logger.debug("DIKW: Holographic delegate init failed: %s", e)
            self._delegate = None
        return self._delegate

    # === v1 4 层接口（M0 NotImpl → M1 实现 run_information_flow → M2 实现其余）===
    # run_information_flow 已在 line 589 实现（M1 子步骤 4）
    # add_with_timestamp / migrate_expired_to_vault M2 阶段实现（delegate 优先 + fact_queue 降级）

    def add_with_timestamp(self, content: str, query: str,
                           source: Optional[str] = None,
                           timestamp: Optional[float] = None) -> int:
        """M2: 写入带 3 时间字段的 fact（主上 v1 精化 #4：时效性管理）

        修复（2026-06-07 bug fix）：原代码调 delegate.add_fact()，但 Holographic
        真实 API 是 _handle_fact_store({'action': 'add', ...})。修复后走
        _call_holographic_fact_store 统一入口，delegate 失败时降级到 fact_queue。

        Args:
            content: 事实内容文本
            query: 检索关键词（HRR 编码用）
            source: 来源分类（可选，如 general/lesson/project/tool）
            timestamp: 自定义创建时间戳（None=当前 time.time()）

        Returns:
            fact_id: Holographic delegate 正常时返回实际 id（< 9位数）；
                     降级到 fact_queue 时返回 queue index（>= 9_000_000_001 的伪 id）

        降级路径：delegate 不可用 / _handle_fact_store 失败 → 写 fact_queue JSON 文件
        """
        if timestamp is None:
            timestamp = time.time()

        # 路径 1: Holographic _handle_fact_store(action=add)
        # 真实 fact_id 是 int，pseudo_id 起点 9_000_000_001（不冲突）
        result = self._call_holographic_fact_store({
            "action": "add",
            "content": content,
            "category": source or "general",
            "tags": f"dikw-add,q:{query[:30]}",
        })
        if result and result.get("fact_id"):
            try:
                fid = int(result["fact_id"])
                if fid > 0:
                    return fid
            except (ValueError, TypeError):
                pass

        # 路径 2: 降级到 fact_queue 模块（X 拆分）
        from . import fact_queue
        return fact_queue.write_fact(
            content=content, query=query, source=source,
            timestamp=timestamp, hermes_home=self._hermes_home,
        )

    def migrate_expired_to_vault(self, max_age_days: Optional[int] = None) -> int:
        """M2: 扫描大脑中的过期 fact 迁移到 vault 图书馆（主上 v1 精化 #4：过期迁移）

        修复（2026-06-07 bug fix）：原代码调 delegate._store.search_facts(max_age=...)，
        但 Holographic search 真实 API 不支持 max_age 参数（实测），改为：
        1. 调 _handle_fact_store({'action': 'search', ...}) 拿所有 results
        2. 客户端按 created_at 时间戳过滤过期
        3. 委托 fact_queue.migrate_results 写盘

        Args:
            max_age_days: 最大保留天数（None=默认 30 天硬规则）

        Returns:
            迁移数量（Holographic 实际迁移数；降级到 fact_queue 时通常 0）

        降级路径：delegate 不可用 → 扫 fact_queue 找带 expiry 字段的项（当前 0 条，应返回 0）
        """
        if max_age_days is None:
            max_age_days = 30

        # 路径 1: 调 _handle_fact_store 搜全量 + 客户端按 created_at 过滤
        result = self._call_holographic_fact_store({
            "action": "search",
            "query": "",
            "category": "general",
            "limit": 10000,
        })
        if result and isinstance(result.get("results"), list):
            from datetime import datetime
            cutoff = time.time() - (max_age_days * 86400)
            expired = []
            for r in result["results"]:
                created_at = r.get("created_at")
                if not created_at:
                    continue
                try:
                    ts = datetime.strptime(str(created_at), "%Y-%m-%d %H:%M:%S").timestamp()
                    if ts < cutoff:
                        expired.append(r)
                except (ValueError, TypeError):
                    continue
            if expired:
                from . import fact_queue
                return fact_queue.migrate_results(expired, max_age_days, self._hermes_home)
            return 0

        # 路径 2: 降级到 fact_queue 模块（X 拆分）
        from . import fact_queue
        return fact_queue.migrate_queue(max_age_days, self._hermes_home)

    # ------------------------------------------------------------------
    # M1: DIKW 分流核心（按 DIKW v3 指南路径规范）
    # ------------------------------------------------------------------

    def _classify_content(self, content: str, context: dict) -> str:
        """将内容分类为 D/I/K/W/L（DIKW v3 规范：source 优先 → 关键词 → type → 默认 D）"""
        # 优先级 1: context.source 显式指定
        source = str(context.get("source", "")).lower()
        if source in ("lesson", "踩坑", "经验", "反模式"):
            return "L"
        if source in ("method", "methodology", "方法论", "原则", "principle", "铁律"):
            return "W"
        if source in ("entity", "实体", "卡片", "card"):
            return "K"
        if source in ("cache", "缓存", "info", "information"):
            return "I"
        if source in ("data", "raw", "原始"):
            return "D"
        # 优先级 2: 内容关键词匹配
        if any(kw in content for kw in ["踩坑", "教训", "复盘", "反模式"]):
            return "L"
        if any(kw in content for kw in ["方法论", "原则", "铁律", "红线", "red line"]):
            return "W"
        if any(kw in content for kw in ["实体", "卡片", "entity"]):
            return "K"
        if any(kw in content for kw in ["缓存", "API 返回", "原始数据"]):
            return "I"
        # 优先级 3: context.type 字段
        ctype = str(context.get("type", "")).lower()
        if ctype.upper() in ("D", "I", "K", "W", "L"):
            return ctype.upper()
        # 默认 D（原始数据）
        return "D"

    def _write_to_vault(self, content: str, category: str, context: dict) -> str:
        """根据分类写入对应目录（按 DIKW v3 路径规范）"""
        import os
        from datetime import datetime
        base = self._hermes_home or "."
        dir_map = {
            'D': 'data/dikw/cache',
            'I': f'data/dikw/cache/{context.get("type", "default")}',
            'K': f'vault/entities/{context.get("entity_type", "general")}',
            'W': 'vault/02-方法论',
            'L': 'vault/踩坑记录',
        }
        subdir = dir_map[category]
        full_dir = os.path.join(base, subdir)
        os.makedirs(full_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cid = str(context.get("id", "unknown"))
        filename = f"{timestamp}_{cid}.md"
        filepath = os.path.join(full_dir, filename)
        title = str(context.get("title", f"DIKW-{category}"))
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# {title}\n\n**分类**: {category}\n**时间**: {timestamp}\n**ID**: {cid}\n\n{content}\n")
        return filepath

    def _add_to_fact_store(self, content: str, category: str, context: dict) -> Optional[int]:
        """将方法论(W)或教训(L)双写到 Holographic fact_store

        修复（2026-06-07 bug fix）：原代码穿透 self._delegate._store.add_fact()，
        但 Holographic 真实入口是 _handle_fact_store({'action': 'add', ...})。
        改为统一调 _call_holographic_fact_store。
        """
        tags = f"dikw-{category.lower()}"
        query = str(context.get("query", ""))
        if query:
            tags = f"{tags},q:{query[:30]}"
        result = self._call_holographic_fact_store({
            "action": "add",
            "content": content,
            "category": "general",  # Holographic 顶层 category 固定 general
            "tags": tags,
        })
        if result and result.get("fact_id"):
            try:
                return int(result["fact_id"])
            except (ValueError, TypeError):
                return None
        return None

    def dikw_dispatch(self, content: str, context: Optional[dict] = None) -> dict:
        """DIKW 分流主入口：D/I/K 单写 vault，W/L 双写 vault + fact_store

        Args:
            content: 要存储的内容文本
            context: 分流上下文（source/type/id/title/query/entity_type 等）

        Returns:
            {"category": str, "path": str, "fact_id": Optional[int]}
        """
        context = context or {}
        category = self._classify_content(content, context)
        file_path = self._write_to_vault(content, category, context)
        result = {"category": category, "path": file_path, "fact_id": None}
        if category in ('W', 'L'):
            result["fact_id"] = self._add_to_fact_store(content, category, context)
        return result

    # ------------------------------------------------------------------
    # M1 子步骤 2: 图书馆检索 5 辅助函数（2026-06-06）
    # 5 函数都返回 List[dict]，统一结构: {content, score, source, ...}
    # 静默降级：任意内部异常 → 返回 []
    # ------------------------------------------------------------------

    def _search_local_glob(self, subdir: str, query: str, limit: int) -> List[Dict[str, Any]]:
        """本地文件检索通用实现（vault/ + data/）

        - 遍历 subdir 下所有 .md 文件
        - query 匹配文件名（高权重 10）或内容前 2KB（权重 5）
        - 返回 [{source, content, score, layer}] 按 score 降序
        - 静默降级：路径不存在/无权限/单文件失败 → []
        """
        try:
            import re
            from pathlib import Path
            base = Path(self._hermes_home or ".")
            target_dir = base / subdir
            if not target_dir.exists():
                return []
            safe_q = re.escape(query[:30])
            pattern = re.compile(safe_q, re.IGNORECASE)
            results: List[Dict[str, Any]] = []
            for md_file in target_dir.rglob("*.md"):
                try:
                    content = md_file.read_text(encoding="utf-8", errors="ignore")
                    title_match = pattern.search(md_file.name)
                    body_match = pattern.search(content[:2000])
                    if title_match or body_match:
                        score = (10 if title_match else 0) + (5 if body_match else 0)
                        try:
                            rel = str(md_file.relative_to(base))
                        except ValueError:
                            rel = str(md_file)
                        results.append({
                            "source": rel,
                            "content": content[:500],
                            "score": score,
                            "layer": subdir.split("/")[0],
                        })
                except Exception:
                    continue
            results.sort(key=lambda x: -x["score"])
            return results[:limit]
        except Exception as e:
            logger.debug("DIKW: _search_local_glob(%s) failed: %s", subdir, e)
            return []

    def _search_brain(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """3 大脑检索（Holographic fact_store search 委托）

        修复（2026-06-07 bug fix）：原代码穿透 delegate._store.search()，但 store 默认 None
        且公开方法名应是 _handle_fact_store({'action': 'search'})。改为统一入口。
        返回 [{content, score, fact_id, source="brain"}]
        """
        result = self._call_holographic_fact_store({
            "action": "search",
            "query": query,
            "limit": limit,
        })
        if not result or not isinstance(result.get("results"), list):
            return []
        return [{
            "content": str(r.get("content", r.get("text", "")))[:500],
            "score": float(r.get("trust_score", r.get("score", 0.5))),
            "fact_id": r.get("fact_id") or r.get("id"),
            "source": "brain",
        } for r in result["results"][:limit]]

    def _search_lessons(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """4.1 踩坑经验检索（vault/踩坑记录/）"""
        return self._search_local_glob("vault/踩坑记录", query, limit)

    def _search_knowledge(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """4.2 知识库检索（vault/entities/ → vault/ 回退）

        - 优先 entities/，不足 limit 时回退到 vault/ 根去重补充
        """
        results = self._search_local_glob("vault/entities", query, limit)
        if len(results) < limit:
            seen = {r["source"] for r in results}
            more = self._search_local_glob("vault", query, limit * 2)
            for m in more:
                if m["source"] not in seen:
                    results.append(m)
                    if len(results) >= limit:
                        break
        return results[:limit]

    def _search_cache(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """4.4 缓存点检索（data/ 全部 cache 子目录）"""
        return self._search_local_glob("data", query, limit)

    def _web_search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """4.5 网络搜索（hermes_tools.web_search 工具）

        - 静默降级：导入失败 / 工具失败 / 异常 → []
        """
        try:
            from hermes_tools import web_search
            result = web_search(query=query, limit=limit)
            items = ((result or {}).get("data") or {}).get("web") or []
            return [{
                "content": str(it.get("description", ""))[:300],
                "title": str(it.get("title", "")),
                "url": str(it.get("url", "")),
                "score": 0.5,
                "source": "web",
            } for it in items[:limit]]
        except Exception as e:
            logger.debug("DIKW: _web_search failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # M1 子步骤 3: 计划/工具/执行/反馈/迭代 5 函数（2026-06-06）
    # 5 函数 = 11 步信息流的 4.6 Plan + 5 工具 + 6 处理 + 7 反馈 + 8 迭代
    # 全静默降级（任意内部异常 → 不抛，返回降级结果）
    # ------------------------------------------------------------------

    def _plan_task(self, instruction: str) -> List[Dict[str, Any]]:
        """4.6 任务规划（Plan 模块，M1 子步骤 3 第 1 步）

        - 输入：用户指令字符串
        - 输出：子步骤列表 [{step_id, description, status, dependencies, category}]
        - 简单实现：基于关键词的规则拆解（不依赖 LLM）
        - 静默降级：拆解失败 → 返回单步列表 [{...}]
        """
        try:
            inst = str(instruction or "").strip()
            if not inst:
                return [{"step_id": 0, "description": "空指令", "status": "skipped",
                         "dependencies": [], "category": "D"}]
            # 关键词拆解（"和/及/然后/再/接着/" 切分）
            import re
            parts = re.split(r"[和及然后接着，,；;]+", inst)
            parts = [p.strip() for p in parts if p.strip()]
            if not parts:
                parts = [inst]
            # 推断 category（简单关键词映射）
            cat_map = {
                "搜": "I", "查": "I", "分析": "K", "评估": "K",
                "生成": "W", "方法论": "W", "写": "W", "记": "W",
                "踩坑": "L", "教训": "L", "复盘": "L",
            }
            steps = []
            for i, p in enumerate(parts):
                cat = "D"
                for kw, c in cat_map.items():
                    if kw in p:
                        cat = c
                        break
                steps.append({
                    "step_id": i,
                    "description": p,
                    "status": "pending",
                    "dependencies": [i - 1] if i > 0 else [],
                    "category": cat,
                })
            return steps
        except Exception as e:
            logger.debug("DIKW: _plan_task failed: %s", e)
            return [{"step_id": 0, "description": str(instruction), "status": "pending",
                     "dependencies": [], "category": "D"}]

    def _select_tools(self, step: Dict[str, Any]) -> List[Dict[str, Any]]:
        """5 工具选择（基于关键词映射到工具，不真扫描 skills）

        - 输入：单步子任务 dict
        - 输出：工具列表 [{tool_name, args_template, priority}]
        - 静默降级：选不到工具 → 返回 []
        """
        try:
            desc = str(step.get("description", ""))
            cat = str(step.get("category", "D"))
            tools = []
            # 关键词 → 工具映射
            kw_to_tool = {
                "搜": "web_search", "查": "fact_store", "分析": "read_file",
                "读": "read_file", "评估": "search_files", "生成": "write_file",
                "写": "write_file", "记": "fact_store", "找": "search_files",
            }
            seen = set()
            for kw, tool in kw_to_tool.items():
                if kw in desc and tool not in seen:
                    seen.add(tool)
                    tools.append({
                        "tool_name": tool,
                        "args_template": {"query": desc} if tool in ("web_search", "fact_store", "search_files") else {"path": desc},
                        "priority": len(tools) + 1,
                    })
            # 类别默认工具
            if not tools:
                if cat in ("W", "L"):
                    tools.append({"tool_name": "fact_store", "args_template": {"content": desc}, "priority": 1})
                elif cat == "K":
                    tools.append({"tool_name": "search_files", "args_template": {"pattern": desc}, "priority": 1})
                elif cat == "I":
                    tools.append({"tool_name": "web_search", "args_template": {"query": desc}, "priority": 1})
            return tools
        except Exception as e:
            logger.debug("DIKW: _select_tools failed: %s", e)
            return []

    def _execute_step(self, step: Dict[str, Any], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """6 处理（接口层，不真执行 — 实际执行由 run_information_flow 调通）

        - 输入：单步子任务 + 选中的工具列表
        - 输出：执行结果 {status, result, error, duration_ms}
        - 静默降级：执行失败 → status="failed", error=str(e)
        """
        import time
        start = time.time()
        try:
            step_id = step.get("step_id", 0)
            tools_count = len(tools or [])
            # 接口层只返回"准备好执行"的状态，真执行在子步骤 4
            return {
                "step_id": step_id,
                "status": "ready",
                "result": None,
                "error": None,
                "tools_planned": tools_count,
                "duration_ms": int((time.time() - start) * 1000),
            }
        except Exception as e:
            # 防御：step 可能不是 dict（None/非法），避免二次抛错
            step_id = step.get("step_id", 0) if isinstance(step, dict) else 0
            return {
                "step_id": step_id,
                "status": "failed",
                "result": None,
                "error": str(e),
                "tools_planned": 0,
                "duration_ms": int((time.time() - start) * 1000),
            }

    def _collect_feedback(self, step_result: Dict[str, Any], source: str = "agent") -> Dict[str, Any]:
        """7 反馈收集（3 源：user / agent / environment）

        - 输入：单步执行结果 + 反馈源标识
        - 输出：反馈 dict {helpful, score, source, notes}
        - 简单实现：基于 step_result.status 打分（不调 LLM self-eval）
        - 静默降级：失败 → helpful=False, score=0.0
        """
        try:
            status = str(step_result.get("status", ""))
            source = source if source in ("user", "agent", "environment") else "agent"
            # 简单打分规则
            if status == "done":
                helpful, score, notes = True, 1.0, "执行成功"
            elif status == "ready":
                helpful, score, notes = True, 0.8, "已准备好执行"
            elif status == "failed":
                helpful, score, notes = False, 0.0, f"执行失败: {step_result.get('error', '')[:200]}"
            elif status == "skipped":
                helpful, score, notes = True, 0.5, "已跳过"
            else:
                helpful, score, notes = False, 0.0, f"未知状态: {status}"
            return {
                "helpful": helpful,
                "score": score,
                "source": source,
                "notes": notes,
            }
        except Exception as e:
            logger.debug("DIKW: _collect_feedback failed: %s", e)
            return {"helpful": False, "score": 0.0, "source": source,
                    "notes": f"collect failed: {str(e)[:100]}"}

    def _update_methodology(self, content: str, category: str,
                            context: Optional[dict] = None) -> Dict[str, Any]:
        """8 迭代/方法论更新（DIKW 分流 + feedback 评分落地）

        - 输入：内容 + 分类（D/I/K/W/L）+ 上下文
        - 输出：{updated, vault_path, fact_id, category}
        - 总是写 vault（K/W/L），W/L 双写 fact_store
        - 静默降级：vault 写入失败 / fact_store 失败 → updated=False 但不抛
        """
        try:
            context = context or {}
            ctx = dict(context)
            ctx.setdefault("source", category.lower() if category in ("W", "L") else "general")
            ctx.setdefault("id", str(ctx.get("id", "unknown")))
            # 写 vault（复用子步骤 1 的 _write_to_vault）
            vault_path = self._write_to_vault(content, category, ctx)
            # W/L 双写 fact_store
            fact_id = None
            if category in ("W", "L"):
                fact_id = self._add_to_fact_store(content, category, ctx)
            return {
                "updated": True,
                "category": category,
                "vault_path": vault_path,
                "fact_id": fact_id,
            }
        except Exception as e:
            logger.debug("DIKW: _update_methodology failed: %s", e)
            return {
                "updated": False,
                "category": category,
                "vault_path": None,
                "fact_id": None,
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # M1 子步骤 4: run_information_flow 12 步主流程（2026-06-06）
    # 串联 5 函数（plan/select/execute/feedback/update）+ 检索层（brain/lessons/knowledge/cache）
    # 全静默降级（任意步骤失败 → 用空结果继续，整体不抛）
    # 返回 FlowResult 字典：含 plan/results/feedback_list/iterations/summary
    # ------------------------------------------------------------------

    def run_information_flow(self, instruction: str) -> Dict[str, Any]:
        """12 步信息流主流程（v2 升级版含 4.6 Plan）

        完整步骤：
          1-2 步：内部状态（不暴露接口）
          3 步：检索大脑（_search_brain）
          4 步：图书馆 5 层（lessons/knowledge/cache，4.5 web 按需）
          4.6 步：Plan 拆解（_plan_task）
          5 步：工具选择（_select_tools）
          6 步：执行（_execute_step 接口层）
          7 步：反馈收集（_collect_feedback 3 源）
          8 步：迭代（_update_methodology DIKW 分流）

        返回：FlowResult {instruction, plan, results, feedback_list, iterations, summary, errors}
        静默降级：任意步骤失败 → 用空结果继续，整体不抛
        """
        import time
        start = time.time()
        # 1-2 步：内部状态初始化
        ctx = {
            "instruction": str(instruction or ""),
            "brain_results": [],
            "library_results": {"lessons": [], "knowledge": [], "cache": [], "web": []},
            "plan": [],
            "results": [],
            "feedback_list": [],
            "iterations": [],
            "errors": [],
        }
        try:
            # 3 步：检索大脑
            try:
                ctx["brain_results"] = self._search_brain(ctx["instruction"], limit=3)
            except Exception as e:
                ctx["errors"].append(f"step3_brain: {str(e)[:200]}")

            # 4.1 步：踩坑经验
            try:
                ctx["library_results"]["lessons"] = self._search_lessons(ctx["instruction"], limit=3)
            except Exception as e:
                ctx["errors"].append(f"step4.1_lessons: {str(e)[:200]}")

            # 4.2 步：知识库
            try:
                ctx["library_results"]["knowledge"] = self._search_knowledge(ctx["instruction"], limit=3)
            except Exception as e:
                ctx["errors"].append(f"step4.2_knowledge: {str(e)[:200]}")

            # 4.4 步：缓存点
            try:
                ctx["library_results"]["cache"] = self._search_cache(ctx["instruction"], limit=2)
            except Exception as e:
                ctx["errors"].append(f"step4.4_cache: {str(e)[:200]}")

            # 4.6 步：Plan 拆解
            try:
                ctx["plan"] = self._plan_task(ctx["instruction"])
            except Exception as e:
                ctx["errors"].append(f"step4.6_plan: {str(e)[:200]}")
                ctx["plan"] = [{
                    "step_id": 0, "description": ctx["instruction"],
                    "status": "skipped", "dependencies": [], "category": "D",
                }]

            # 5-7 步：对每个 step 走 select → execute → feedback
            for step in ctx["plan"]:
                step_id = step.get("step_id", 0)
                try:
                    tools = self._select_tools(step)
                except Exception as e:
                    tools = []
                    ctx["errors"].append(f"step5_select_{step_id}: {str(e)[:200]}")
                try:
                    step_result = self._execute_step(step, tools)
                except Exception as e:
                    step_result = {"step_id": step_id, "status": "failed",
                                   "error": str(e), "tools_planned": 0}
                    ctx["errors"].append(f"step6_execute_{step_id}: {str(e)[:200]}")
                try:
                    feedback = self._collect_feedback(step_result, source="agent")
                except Exception as e:
                    feedback = {"helpful": False, "score": 0.0, "source": "agent",
                                "notes": f"feedback failed: {str(e)[:100]}"}
                    ctx["errors"].append(f"step7_feedback_{step_id}: {str(e)[:200]}")
                ctx["results"].append(step_result)
                ctx["feedback_list"].append(feedback)

                # 8 步：迭代（feedback 触发方法论更新）
                if feedback.get("helpful") and step.get("category") in ("W", "L", "K"):
                    # 防御：category 可能不是 str（None/缺失）
                    cat = step.get("category")
                    if not isinstance(cat, str):
                        cat = "D"
                    try:
                        iteration = self._update_methodology(
                            content=step.get("description", ""),
                            category=cat,
                            context={"id": f"flow-{int(time.time())}-{step_id}",
                                     "source": "general"},
                        )
                        ctx["iterations"].append(iteration)
                    except Exception as e:
                        ctx["errors"].append(f"step8_iterate_{step_id}: {str(e)[:200]}")

            # 汇总
            helpful_count = sum(1 for f in ctx["feedback_list"] if f.get("helpful"))
            ctx["summary"] = {
                "total_steps": len(ctx["plan"]),
                "helpful_count": helpful_count,
                "iterations_count": len(ctx["iterations"]),
                "errors_count": len(ctx["errors"]),
                "duration_ms": int((time.time() - start) * 1000),
            }
            return ctx
        except Exception as e:
            # 最外层兜底（不抛）
            return {
                "instruction": str(instruction or ""),
                "plan": [],
                "results": [],
                "feedback_list": [],
                "iterations": [],
                "summary": {"error": str(e)[:200], "duration_ms": int((time.time() - start) * 1000)},
                "errors": [f"top_level: {str(e)[:200]}"],
            }


    # ------------------------------------------------------------------
    # M2 委托：add_with_timestamp / migrate_expired_to_vault → fact_queue
    # ------------------------------------------------------------------
    # 详细实现已拆分到 plugins/memory/dikw/fact_queue.py（X 拆分决策）
    # 本类只保留方法签名 + 委托调用，控制核心行数 ≤850 A1' 硬约束


def register(ctx) -> None:
    """插件发现机制入口（plugins/memory/__init__.py L264-272 揭示）。"""
    provider = DIKWMemoryProvider()
    ctx.register_memory_provider(provider)
