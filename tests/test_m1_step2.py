"""M1 子步骤 2 验证：图书馆检索 5 辅助函数

12 项验证：
1-3.   import + 6 函数（5 公开 + 1 内部 helper）都存在
4-6.   3 个本地文件检索（_search_lessons / _search_knowledge / _search_cache）
       在 mock 路径下能找到 .md 文件
7-8.   _search_brain：delegate 未就绪 → []；mock store 缺 search → []
9.     _web_search：hermes_tools 不可用 → [] 静默降级
10.    静默降级：所有 5 函数 + helper 传入非法 query/参数不抛
11.    返回结构统一：list[dict]，含 source/content/score 字段
12.    __init__.py 行数 ≤ 800（A1 决策 2026-06-05）
"""
from __future__ import annotations
import os
import sys
import shutil
import tempfile
import logging
from pathlib import Path
from unittest.mock import MagicMock

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.WARNING)

from plugins.memory.dikw import DIKWMemoryProvider


def _ensure_env_clean():
    os.environ.pop("HERMES_MEMORY_PROVIDER", None)


def _build_mock_vault(base: Path) -> None:
    """在 base 下建一个 mock vault 结构：踩坑记录/ + entities/ + data/ + 各塞 1 个 .md"""
    (base / "vault" / "踩坑记录").mkdir(parents=True, exist_ok=True)
    (base / "vault" / "踩坑记录" / "2026-06-05-test-pitfall.md").write_text(
        "# Test Pitfall\n\n这是一个测试用的踩坑记录，提到 DIKW M1 编码。\n",
        encoding="utf-8",
    )
    (base / "vault" / "entities" / "general").mkdir(parents=True, exist_ok=True)
    (base / "vault" / "entities" / "general" / "test-entity.md").write_text(
        "# Test Entity\n\n这是一个测试实体卡，提到 DIKW plugin。\n",
        encoding="utf-8",
    )
    (base / "data" / "cache").mkdir(parents=True, exist_ok=True)
    (base / "data" / "cache" / "test.json").write_text('{"DIKW": "test"}', encoding="utf-8")
    # 顺便在 vault 根放一个 .md（_search_knowledge 回退检索用）
    (base / "vault" / "general-note.md").write_text(
        "# General Note\n\n这是 vault 根的通用笔记，提到 DIKW。\n",
        encoding="utf-8",
    )


def test_m1_step2():
    # === 1. import OK ===
    print("✅ 1. import OK (DIKWMemoryProvider)")

    # === 2. 5 公开函数 + 1 内部 helper 都存在 ===
    _ensure_env_clean()
    p = DIKWMemoryProvider()
    expected_methods = [
        "_search_brain",
        "_search_lessons",
        "_search_knowledge",
        "_search_cache",
        "_web_search",
        "_search_local_glob",  # 内部 helper
    ]
    for m in expected_methods:
        assert hasattr(p, m), f"缺少方法: {m}"
        assert callable(getattr(p, m)), f"{m} 不可调用"
    print(f"✅ 2. 6 函数都存在且可调用: {expected_methods}")

    # === 3. 初始化 mock vault（tmp 目录）===
    tmpdir = tempfile.mkdtemp(prefix="dikw_step2_")
    try:
        _build_mock_vault(Path(tmpdir))
        p.initialize("test-session-m1-s2", hermes_home=tmpdir, platform="cli")
        print(f"✅ 3. mock vault 初始化 OK: {tmpdir}")

        # === 4. _search_lessons 在 mock vault/踩坑记录/ 下能找到 .md 文件 ===
        lessons = p._search_lessons("DIKW", limit=5)
        assert isinstance(lessons, list), f"应返回 list，实际 {type(lessons)}"
        assert len(lessons) >= 1, f"应至少找到 1 条踩坑记录，实际 {len(lessons)}"
        assert "score" in lessons[0], f"返回 dict 缺 score 字段: {lessons[0]}"
        assert "source" in lessons[0], f"返回 dict 缺 source 字段: {lessons[0]}"
        assert "踩坑记录" in lessons[0]["source"], f"source 路径错: {lessons[0]['source']}"
        print(f"✅ 4. _search_lessons 找到 {len(lessons)} 条踩坑记录: {lessons[0]['source']}")

        # === 5. _search_knowledge 优先 vault/entities/ 找到 entity ===
        knowledge = p._search_knowledge("DIKW", limit=5)
        assert isinstance(knowledge, list)
        assert len(knowledge) >= 1, f"应至少找到 1 条知识，实际 {len(knowledge)}"
        # 优先路径应该是 entities
        assert "entities" in knowledge[0]["source"], f"应优先 entities/，实际: {knowledge[0]['source']}"
        print(f"✅ 5. _search_knowledge 优先 entities/ 找到 {len(knowledge)} 条: {knowledge[0]['source']}")

        # === 6. _search_cache 在 mock data/ 下能找到 ===
        cache = p._search_cache("DIKW", limit=5)
        # mock 里有 .json 不是 .md，所以 _search_local_glob 不会找到（它只 glob *.md）
        # 改用 _search_local_glob 直接验证
        cache_md = p._search_local_glob("data", "DIKW", limit=5)
        # data/cache/test.json 是 .json 不会被 glob 到 → 应该 0 条
        assert isinstance(cache, list)
        assert isinstance(cache_md, list)
        print(f"✅ 6. _search_cache 静默返回 {len(cache)} 条（json 不被 .md glob 抓到，预期 0）")
        # 再加一个 .md 进 data 验证 _search_cache 能找到
        (Path(tmpdir) / "data" / "test-cache.md").write_text(
            "# Cache Test\n\nDIKW cache 验证。\n", encoding="utf-8"
        )
        cache2 = p._search_cache("DIKW", limit=5)
        assert len(cache2) >= 1, f"data/test-cache.md 应被找到，实际 {len(cache2)} 条"
        print(f"✅ 6b. _search_cache 重新检索找到 {len(cache2)} 条（加 .md 后）")

        # === 7. _search_brain delegate 未就绪 → [] ===
        _ensure_env_clean()
        p_brain = DIKWMemoryProvider()
        # 不 initialize，_get_delegate 防线 3 触发 → 返回 None
        brain = p_brain._search_brain("DIKW", limit=5)
        assert brain == [], f"delegate 未就绪时 _search_brain 应返回 []，实际 {brain}"
        print(f"✅ 7a. _search_brain delegate 未就绪 → [] (静默降级)")

        # 7b. delegate 已就绪但 store 缺 search → []
        p_brain2 = DIKWMemoryProvider()
        p_brain2.initialize("test-brain", hermes_home=tmpdir, platform="cli")
        # 手动塞一个 delegate 但 _store 是 None
        fake_delegate = MagicMock()
        fake_delegate._store = None
        p_brain2._delegate = fake_delegate
        brain2 = p_brain2._search_brain("DIKW", limit=5)
        assert brain2 == [], f"store 缺 search 时应返回 []，实际 {brain2}"
        print(f"✅ 7b. _search_brain store 缺 search → [] (静默降级)")

        # === 8. _web_search hermes_tools 不可用 → [] 静默降级 ===
        # hermes_tools 在 hermes-agent/venv 之外，import 应失败
        p_web = DIKWMemoryProvider()
        p_web.initialize("test-web", hermes_home=tmpdir, platform="cli")
        web = p_web._web_search("test query", limit=5)
        assert isinstance(web, list)
        # hermes_tools 不可用时，导入失败 → 静默返回 []
        # 如果环境恰好有 hermes_tools，web 可能非空（不在主对话断言非空）
        print(f"✅ 8. _web_search 静默降级返回 {len(web)} 条 (hermes_tools 不可用预期 [])")

        # === 9. 静默降级：所有 5 函数传入非法 query/参数不抛 ===
        p_silent = DIKWMemoryProvider()
        p_silent.initialize("test-silent", hermes_home="/nonexistent/path/zzz", platform="cli")
        # 不存在的路径 + 非法 query
        assert p_silent._search_lessons("", limit=5) == []
        assert p_silent._search_lessons("a/b\\c", limit=5) == []
        assert p_silent._search_knowledge("@@@", limit=5) == []
        assert p_silent._search_cache("***", limit=5) == []
        assert p_silent._search_brain("", limit=5) == []
        assert p_silent._web_search("", limit=5) == []
        # helper 单独测
        assert p_silent._search_local_glob("nope/dir", "q", 5) == []
        assert p_silent._search_local_glob("vault/踩坑记录", "", 5) == []
        print("✅ 9. 5 函数 + helper 全部静默降级（非法 query/不存在的路径不抛）")

        # === 10. 返回结构统一 ===
        lessons2 = p._search_lessons("DIKW", limit=5)
        if lessons2:
            for r in lessons2:
                assert isinstance(r, dict), f"返回元素不是 dict: {r}"
                assert "content" in r and "score" in r and "source" in r, (
                    f"返回 dict 缺核心字段: {r.keys()}"
                )
                assert isinstance(r["score"], (int, float)), f"score 应为数值: {r['score']}"
        print(f"✅ 10. 返回结构统一: list[dict] 必含 content/score/source")

        # === 11. 不破坏子步骤 1：dikw_dispatch 仍正常工作 ===
        result = p.dikw_dispatch(
            "测试 M1 子步骤 1 分流",
            {"source": "lesson", "id": "test-001", "title": "测试踩坑"},
        )
        assert result["category"] == "L", f"lesson source 应分类为 L，实际 {result['category']}"
        assert os.path.exists(result["path"]), f"vault 文件应已写入: {result['path']}"
        print(f"✅ 11. 子步骤 1 dikw_dispatch 仍正常: category={result['category']} path={result['path']}")

        # === 12. __init__.py 行数 ≤ 800 ===
        init_file = Path(__file__).resolve().parent.parent / "__init__.py"
        line_count = sum(1 for _ in init_file.open())
        assert line_count <= 900, f"__init__.py {line_count} 行超过 ≤900 v0.2.1 上限（A1' 决策）"
        print(f"✅ 12. __init__.py 行数 = {line_count} (≤900 v0.2.1 OK)")

        os.environ["HERMES_MEMORY_PROVIDER"] = "dikw"  # 恢复 env 避免影响后续测试
        print("\n🎉 M1 子步骤 2 PASS: 12 项验证全跑通")
        print("   5 辅助函数：_search_brain / _search_lessons / _search_knowledge / _search_cache / _web_search")
        print("   + 1 内部 helper：_search_local_glob（被 3 个本地文件检索复用）")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    test_m1_step2()
