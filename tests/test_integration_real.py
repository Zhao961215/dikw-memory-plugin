"""集成测试 — 验证 DIKW 插件在真实 hermes-agent 框架下行为正确

不依赖 mock，走真实父包 (plugins.memory.load_memory_provider)，
验证：
1. discover_memory_providers() 能发现 dikw
2. load_memory_provider("dikw") 能加载 DIKWMemoryProvider
3. 在真实 vault 路径下，run_information_flow 能跑通 12 步
4. vault 文件能真写入 踩坑记录/ 和 02-方法论/
5. env HERMES_MEMORY_PROVIDER=dikw 启用 is_available()=True

跑测试：venv/bin/python tests/test_integration_real.py
"""
import sys
import os
import tempfile
import shutil
from pathlib import Path

# 加 hermes-agent 根目录到 sys.path（走真实 plugins.memory 父包）
HERMES_AGENT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(HERMES_AGENT))

from plugins.memory import load_memory_provider, discover_memory_providers  # noqa: E402


def make_tmp_vault():
    """构造临时 vault 目录（避免污染主上真 vault）。"""
    tmp = tempfile.mkdtemp(prefix="dikw_integration_")
    vault = Path(tmp) / "vault"
    (vault / "踩坑记录").mkdir(parents=True, exist_ok=True)
    (vault / "02-方法论").mkdir(parents=True, exist_ok=True)
    (vault / "entities" / "general").mkdir(parents=True, exist_ok=True)
    return tmp, vault


def cleanup_tmp(tmp):
    """清理临时目录。"""
    if Path(tmp).exists():
        shutil.rmtree(tmp)


def resolve_vault_path(path_str: str, tmp: str) -> Path:
    """把 './vault/...' 形式相对路径解析成临时目录绝对路径。"""
    p = Path(path_str)
    if p.is_absolute():
        return p
    return Path(tmp) / str(p).lstrip("./")


# ----------------------------------------------------------------------------
# 测试场景
# ----------------------------------------------------------------------------
def t1_discover_finds_dikw():
    """场景 1: discover_memory_providers() 能发现 dikw 插件。"""
    providers = discover_memory_providers()
    names = [n for n, _, _ in providers]
    assert "dikw" in names, f"discover_memory_providers() 没找到 dikw, 实际: {names}"
    print(f"  [t1] discover_memory_providers() 找到 dikw, 全部插件: {names}")


def t2_load_dikw_provider():
    """场景 2: load_memory_provider('dikw') 能加载 DIKWMemoryProvider。"""
    p = load_memory_provider("dikw")
    assert p is not None, "load_memory_provider('dikw') 返回 None"
    assert p.name == "dikw"
    assert p.is_available() in (True, False)  # is_available 取决于 env/config
    print(f"  [t2] load_memory_provider('dikw') 加载成功: {type(p).__name__}, "
          f"name={p.name}, is_available={p.is_available()}")


def t3_real_vault_remember_lesson():
    """场景 3: 真实 vault 路径下，记住踩坑 → vault 写入 踩坑记录/ + 12 步全过。"""
    tmp, vault = make_tmp_vault()
    try:
        p = load_memory_provider("dikw")
        assert p is not None, "load_memory_provider('dikw') 返回 None"
        p.initialize("integration-test-1", hermes_home=tmp)  # type: ignore[union-attr]

        result = p.run_information_flow("踩坑:数据库连接超时")
        assert isinstance(result, dict)
        assert "summary" in result
        assert "iterations" in result
        assert result["summary"]["errors_count"] == 0
        assert len(result["iterations"]) >= 1
        assert result["iterations"][0]["category"] == "L"

        # 验证 vault 真实写入
        iter0 = result["iterations"][0]
        vault_path = resolve_vault_path(iter0["vault_path"], tmp)
        assert vault_path.exists(), f"vault 文件未创建: {vault_path}"

        lesson_dir = vault / "踩坑记录"
        assert vault_path.parent == lesson_dir, \
            f"应写入 踩坑记录/, 实际: {vault_path.parent}"
        assert any(lesson_dir.iterdir()), f"{lesson_dir} 应有 1 个文件"

        print(f"  [t3] 真实 vault 写入 PASS: {vault_path.name} "
              f"({vault_path.stat().st_size} B, 类别=L)")
    finally:
        cleanup_tmp(tmp)


def t4_real_vault_methodology():
    """场景 4: 真实 vault 路径下，写方法论 → vault 写入 02-方法论/。"""
    tmp, vault = make_tmp_vault()
    try:
        p = load_memory_provider("dikw")
        assert p is not None, "load_memory_provider('dikw') 返回 None"
        p.initialize("integration-test-2", hermes_home=tmp)  # type: ignore[union-attr]

        result = p.run_information_flow("方法论:先检索再决策")
        assert result["summary"]["errors_count"] == 0
        assert len(result["iterations"]) >= 1
        assert result["iterations"][0]["category"] == "W"

        iter0 = result["iterations"][0]
        vault_path = resolve_vault_path(iter0["vault_path"], tmp)
        assert vault_path.exists(), f"vault 文件未创建: {vault_path}"

        method_dir = vault / "02-方法论"
        assert vault_path.parent == method_dir, \
            f"应写入 02-方法论/, 实际: {vault_path.parent}"
        assert any(method_dir.iterdir()), f"{method_dir} 应有 1 个文件"

        print(f"  [t4] 真实 vault 方法论 PASS: {vault_path.name} "
              f"({vault_path.stat().st_size} B, 类别=W)")
    finally:
        cleanup_tmp(tmp)


def t5_env_var_enables_provider():
    """场景 5: HERMES_MEMORY_PROVIDER=dikw 环境变量能启用 is_available()=True。"""
    original = os.environ.get("HERMES_MEMORY_PROVIDER")
    try:
        os.environ["HERMES_MEMORY_PROVIDER"] = "dikw"
        p = load_memory_provider("dikw")
        assert p is not None, "load_memory_provider('dikw') 返回 None"
        avail = p.is_available()  # type: ignore[union-attr]
        assert avail is True, (
            f"env HERMES_MEMORY_PROVIDER=dikw 时 is_available() 应 True, 实际: {avail}"
        )
        print(f"  [t5] env 启用 PASS: is_available()={avail}")
    finally:
        if original is None:
            os.environ.pop("HERMES_MEMORY_PROVIDER", None)
        else:
            os.environ["HERMES_MEMORY_PROVIDER"] = original


# ----------------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------------
TESTS = [
    t1_discover_finds_dikw,
    t2_load_dikw_provider,
    t3_real_vault_remember_lesson,
    t4_real_vault_methodology,
    t5_env_var_enables_provider,
]


def main():
    print("=" * 60)
    print("DIKW 集成测试 — 真实 hermes-agent 框架（5 场景）")
    print("=" * 60)
    passed = 0
    failed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print("=" * 60)
    print(f"结果: {passed}/{passed + failed} PASS, {failed} FAILED")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
