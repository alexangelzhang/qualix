"""Q05 结构合规补充校验（T5）：eut_missing_se / wrong_directory / mock 类启发式.

与 schema、weak_assert_gate、test_execution_gate 互补；不重复编译运行逻辑（compile_fail 见 test_execution_gate）。

新增检查（并发/幂等/锁强管控）：
- concurrent_se_no_eut：SE 描述含并发/幂等/分布式锁关键词时，必须有非占位 EUT（不允许全部为 TODO）
- lock_annotation_not_in_scope：代码仓库中 @DistributedLocked 等注解的持有类未出现在 EUT 目标中
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from dqg.constants import STRUCTURED_JSON_MAP
from dqg.core.phase_registry import PHASE_DEFS
from dqg.core.state_machine import internal_dir as _internal_dir
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.json_utils import load_json
from dqg.log import get_logger

log = get_logger(__name__)

# 常见 Mockito 方法名拼写错误（mock_wrong）
_TYPO_METHOD_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\.getSucess\s*\(",
        r"\.getSccess\s*\(",
        r"\.isSucccess\s*\(",
        r"\.isSeccess\s*\(",
    )
)

# 可疑「幽灵方法」：when(mockX.foo()) 中 foo 过短或全大写缩写（启发式，低噪音）
_PHANTOM_METHOD = re.compile(
    r"\bwhen\s*\(\s*[^)]+\)\s*\.\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
)


_TEST_FILE_SUFFIXES = frozenset((".java", ".kt", ".ts", ".tsx"))


def _collect_new_test_files_from_repos(code_repos: list[str]) -> list[Path]:
    """从业务仓库用 git status 收集新增/修改的测试文件（含 untracked）.

    SKILL.md 要求测试代码直接写到业务仓库的 src/test/java，不使用
    supplemental_tests/ 中转目录。
    """
    test_paths: list[Path] = []
    for repo_str in code_repos:
        repo = Path(repo_str).expanduser().resolve()
        if not repo.is_dir():
            continue
        try:
            r = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode != 0:
                continue
            for line in r.stdout.splitlines():
                path_str = line[3:].strip()
                p = repo / path_str
                if not p.is_file() or p.suffix not in _TEST_FILE_SUFFIXES:
                    continue
                norm = path_str.replace("\\", "/")
                name = p.name.lower()
                is_test = (
                    "src/test/" in norm
                    or name.endswith("test.java")
                    or name.endswith("test.kt")
                    or ".test." in name
                    or ".spec." in name
                )
                if is_test:
                    test_paths.append(p)
        except (subprocess.TimeoutExpired, OSError):
            continue
    return test_paths


def _collect_supplemental_files(phase_root: Path) -> list[Path]:
    """向后兼容：扫描 supplemental_tests/ 目录.

    生产环境下应通过 code_repos + git status 扫描（_collect_new_test_files_from_repos）。
    无 code_repos 时（如单元测试场景）回落到此目录。
    """
    d = phase_root / "supplemental_tests"
    if not d.is_dir():
        return []
    return sorted(p for p in d.rglob("*") if p.is_file() and p.suffix in _TEST_FILE_SUFFIXES)


# 向后兼容别名
_collect_supplemental_java = _collect_supplemental_files


def _check_eut_missing_se(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for i, eut in enumerate(data.get("eut_items") or []):
        if not isinstance(eut, dict):
            continue
        eid = eut.get("eut_id", "?")
        bs = (eut.get("bound_se") or "").strip()
        if not bs:
            errors.append(f"BLOCKED: Q05 eut_missing_se — eut_items[{i}] {eid} 缺少 bound_se")
    return errors


def _check_wrong_directory(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for i, tc in enumerate(data.get("test_cases") or []):
        if not isinstance(tc, dict):
            continue
        loc = tc.get("test_location") or {}
        if not isinstance(loc, dict):
            continue
        f = str(loc.get("file") or "").replace("\\", "/")
        fl = f.lower()
        # Java/Kotlin: 测试文件不应放在 src/main/
        if "src/main/" in fl and ("test" in fl or fl.endswith(".java") or fl.endswith(".kt")):
            errors.append(
                f"BLOCKED: Q05 wrong_directory — test_cases[{i}] test_location 指向 src/main: {loc.get('file')}"
            )
        # TypeScript: 测试文件不应放在 src/ 根目录下（应在 __tests__/ 或同文件 *.test.ts）
        # 判断：路径在 src/ 下，但既不含 __tests__ 也不是 .test.ts/.spec.ts
        elif fl.endswith((".ts", ".tsx")) and "src/" in fl:
            name = Path(f).name.lower()
            is_test_file = ".test." in name or ".spec." in name or "__tests__" in fl
            if not is_test_file:
                errors.append(
                    f"BLOCKED: Q05 wrong_directory — test_cases[{i}] test_location 指向非测试 TS 文件: {loc.get('file')}"
                )
    return errors


# P0-1: 方法级断言强度检测用到的正则
_TEST_METHOD_SPLIT = re.compile(r"(?=\s*@(?:Test|ParameterizedTest|RepeatedTest)\b)")
_STRONG_IN_METHOD = re.compile(
    r"\b(assertEquals|assertNotEquals|assertSame|assertThrows|assertThat|assertIterableEquals"
    r"|assertArrayEquals|verify\s*\(|ArgumentCaptor)\b"
)
_ANY_ASSERT_IN_METHOD = re.compile(r"\bassert\w+\s*\(|verify\s*\(")


def _check_mock_patterns(java_paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in java_paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pat in _TYPO_METHOD_PATTERNS:
            if pat.search(text):
                errors.append(
                    f"BLOCKED: Q05 mock_wrong — {path.name} 疑似错误方法名拼写（{pat.pattern}），请核对被测 API"
                )
                break
        # mock_phantom_method 启发式：when(...).X( 且 X 长度 <=2（极少为真实业务方法）
        for m in _PHANTOM_METHOD.finditer(text):
            name = m.group(1)
            if len(name) == 1 and name.isalpha():
                errors.append(
                    f"BLOCKED: Q05 mock_phantom_method — {path.name} when().{name}() 单字母方法名，"
                    "请确认是否为臆造方法名"
                )
                break

        # P0-1: 方法级断言强度检查
        errors.extend(_check_method_level_assert_strength(path, text))
    return errors


def _check_method_level_assert_strength(path: Path, text: str) -> list[str]:
    """P0-1: 逐个 @Test 方法检查断言强度，统计弱断言方法比例.

    弱断言方法 = 有 assert 调用但无强断言（assertEquals/assertThrows/verify 等）。
    比例超过阈值（>40%）时报 BLOCKED。
    """
    # 按 @Test 注解分割方法块（简单启发式）
    blocks = _TEST_METHOD_SPLIT.split(text)
    # 过滤掉没有 @Test 的开头块
    test_blocks = [b for b in blocks if re.match(r"\s*@(?:Test|ParameterizedTest|RepeatedTest)\b", b)]
    if not test_blocks:
        return []

    weak_methods: list[str] = []
    for block in test_blocks:
        has_any_assert = bool(_ANY_ASSERT_IN_METHOD.search(block))
        has_strong = bool(_STRONG_IN_METHOD.search(block))
        if has_any_assert and not has_strong:
            # 提取方法名
            m = re.search(r"(?:public|protected|void)\s+(\w+)\s*\(", block)
            name = m.group(1) if m else "?"
            weak_methods.append(name)

    total = len(test_blocks)
    weak_count = len(weak_methods)
    if total > 0 and weak_count / total > 0.4:
        return [
            f"BLOCKED: Q05 weak_assert_method — {path.name} {weak_count}/{total} 个 @Test 方法仅有弱断言"
            f"（assertNotNull 等），缺少 assertEquals/assertThrows/verify：{', '.join(weak_methods[:4])}"
        ]
    return []


# ── 并发/幂等/锁 SE 强管控 ────────────────────────────────────────────────────

# SE 描述中触发并发强检查的关键词（中英文兼顾）
_CONCURRENT_SE_KEYWORDS: frozenset[str] = frozenset(
    [
        "并发",
        "幂等",
        "分布式锁",
        "重复提交",
        "重复请求",
        "乐观锁",
        "悲观锁",
        "concurrent",
        "idempotent",
        "distributed lock",
        "race condition",
        "mutex",
        "duplicate submit",
    ]
)

# EUT then 字段被认定为"占位符/TODO"的模式
_TODO_THEN_PATTERN = re.compile(
    r"^\s*(TODO|待补充|待实现|N/?A|不适用|集成测试|integration\s+test|需要集成|暂不覆盖)\s*$",
    re.IGNORECASE,
)

# 需要在单测中明确追踪的代码注解（分布式锁/幂等/防重复提交）
# 排除 @Transactional：几乎所有 Service 方法都有，误报率极高，噪音大于价值。
_LOCK_ANNOTATIONS: tuple[str, ...] = (
    # 分布式锁
    "@DistributedLocked",
    "@RedisLock",
    "@DistributedLock",
    # Seata 分布式事务
    "@GlobalTransactional",
    # 幂等
    "@Idempotent",
    # 防重复提交（国内企业应用高频）
    "@RepeatSubmit",
    "@PreventRepeatSubmit",
    "@NoRepeatSubmit",
    # JPA/Hibernate 悲观锁
    "@Lock",
    # 自定义同步
    "@Synchronized",
)

# 代码级并发/锁模式（不依赖注解，直接识别并发原语使用）
# 每条：(pattern, label)，pattern 匹配到即认为该类含并发语义
_CONCURRENT_CODE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(p), label)
    for p, label in (
        # JUC 显式锁
        (r"\bReentrantLock\b", "ReentrantLock"),
        (r"\bReadWriteLock\b", "ReadWriteLock"),
        (r"\bStampedLock\b", "StampedLock"),
        (r"\bLockSupport\b", "LockSupport"),
        # 同步关键字（方法或块）
        (r"\bsynchronized\s*[\({]", "synchronized"),
        # 原子类
        (r"\bAtomic(?:Integer|Long|Boolean|Reference|Stamped|IntegerArray|LongArray|ReferenceArray)\b", "Atomic*"),
        # 并发集合
        (r"\bConcurrentHashMap\b", "ConcurrentHashMap"),
        (r"\bCopyOnWriteArrayList\b", "CopyOnWriteArrayList"),
        (r"\bBlockingQueue\b", "BlockingQueue"),
        (r"\bLinkedBlockingQueue\b", "LinkedBlockingQueue"),
        # 协调工具
        (r"\bCountDownLatch\b", "CountDownLatch"),
        (r"\bCyclicBarrier\b", "CyclicBarrier"),
        (r"\bSemaphore\b", "Semaphore"),
        (r"\bPhaser\b", "Phaser"),
        # 线程池 / 异步
        (r"\bExecutorService\b", "ExecutorService"),
        (r"\bThreadPoolExecutor\b", "ThreadPoolExecutor"),
        (r"\bCompletableFuture\b", "CompletableFuture"),
        (r"\b@Async\b", "@Async"),
        # volatile 字段（并发可见性）
        (r"\bvolatile\b", "volatile"),
    )
)


def _se_is_concurrent(se_desc: str) -> bool:
    """判断 SE 描述是否含并发/幂等/锁语义关键词."""
    desc_lower = se_desc.lower()
    return any(kw in desc_lower for kw in _CONCURRENT_SE_KEYWORDS)


def _check_concurrent_se_no_eut(
    q05_data: dict[str, Any],
    q01_data: dict[str, Any] | None,
) -> list[str]:
    """SE 描述含并发/幂等/锁语义时，必须有至少一个非占位 EUT.

    规则：
    - 找出所有描述含并发关键词的 SE（来自 Q01 phase_a_structured.json）
    - 对每个并发 SE，检查 phase_b_structured.json 中是否有 bound_se 匹配
      且 then 字段不是纯 TODO 占位的 EUT
    - 没有任何 EUT → BLOCKED
    - 只有 TODO 占位 EUT → BLOCKED（TODO 不算有效覆盖）

    设计原则：并发/幂等保护（@DistributedLocked 等）在 Mockito 单测中
    AOP 不生效，但注解验证（反射）可以在单测中覆盖。不允许以"需要集成测试"
    为由跳过所有单测级别的覆盖。
    """
    errors: list[str] = []

    # 从 Q01 产物识别并发 SE
    ses: list[dict[str, Any]] = []
    if q01_data and isinstance(q01_data, dict):
        ses = q01_data.get("semantic_expectations") or []

    # 构建 bound_se → EUT 列表的映射
    eut_map: dict[str, list[dict[str, Any]]] = {}
    for eut in q05_data.get("eut_items") or []:
        if not isinstance(eut, dict):
            continue
        bs = (eut.get("bound_se") or "").strip()
        if bs:
            eut_map.setdefault(bs, []).append(eut)

    for se in ses:
        if not isinstance(se, dict):
            continue
        se_id = (se.get("se_id") or "").strip()
        desc = se.get("description") or se.get("behavior") or se.get("desc") or ""
        if not se_id or not _se_is_concurrent(str(desc)):
            continue

        matched_euts = eut_map.get(se_id, [])

        if not matched_euts:
            errors.append(
                f"BLOCKED: Q05 concurrent_se_no_eut — {se_id}（描述含并发/幂等/锁语义）"
                f" 没有任何 EUT 绑定。"
                f" 即使 AOP 无法在单测中验证锁行为，也必须用反射验证注解存在性或设计注解守护测试。"
                f" SE 描述：{str(desc)[:60]}"
            )
        else:
            # 所有 EUT 的 then 都是 TODO 占位
            non_todo = [e for e in matched_euts if not _TODO_THEN_PATTERN.match(str(e.get("then") or ""))]
            if not non_todo:
                eut_ids = [e.get("eut_id", "?") for e in matched_euts]
                errors.append(
                    f"BLOCKED: Q05 concurrent_se_todo_only — {se_id}（并发/幂等/锁语义）"
                    f" 的所有 EUT {eut_ids} then 字段均为 TODO 占位，不算有效覆盖。"
                    f" 至少需要一个注解验证或防回归守护测试。"
                )

    return errors


def _detect_concurrent_signals(src: str) -> list[str]:
    """从 Java 源码中检测并发/锁信号，返回命中的信号标签列表."""
    signals: list[str] = []
    # 注解命中
    signals.extend(ann.lstrip("@") for ann in _LOCK_ANNOTATIONS if ann in src)
    # 代码级并发原语命中
    signals.extend(label for pat, label in _CONCURRENT_CODE_PATTERNS if pat.search(src))
    return signals


def _check_concurrent_scope(
    q05_data: dict[str, Any],
    code_repos: list[str],
) -> list[str]:
    """变更文件中含并发/锁注解或并发代码原语的类，若未出现在 EUT scope 中则 WARN.

    检测范围：
    - 注解：@DistributedLocked / @RedisLock / @GlobalTransactional 等（见 _LOCK_ANNOTATIONS）
    - 代码原语：ReentrantLock / synchronized / AtomicXxx / CountDownLatch /
                ThreadPoolExecutor / CompletableFuture / ConcurrentHashMap /
                volatile / Semaphore / CyclicBarrier 等（见 _CONCURRENT_CODE_PATTERNS）

    失败级别：WARNING（不阻断 finalize），但进入 soft_blocked 供 approve 判断。
    """
    warnings: list[str] = []
    if not code_repos:
        return warnings

    # 提取 EUT 和 test_cases 中已提及的简单类名
    mentioned_classes: set[str] = set()
    for eut in q05_data.get("eut_items") or []:
        if not isinstance(eut, dict):
            continue
        for field in ("given", "when", "then"):
            text = str(eut.get(field) or "")
            mentioned_classes.update(re.findall(r"\b[A-Z][a-zA-Z0-9]+\b", text))
    for tc in q05_data.get("test_cases") or []:
        if not isinstance(tc, dict):
            continue
        cut = str(tc.get("class_under_test") or "")
        if cut:
            mentioned_classes.add(cut.split(".")[-1])

    for repo in code_repos:
        repo_path = Path(repo)
        if not repo_path.is_dir():
            continue
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "origin/master...HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=15,
            )
            changed_files = [repo_path / f.strip() for f in result.stdout.splitlines() if f.strip().endswith(".java")]
        except Exception:
            continue

        for java_file in changed_files:
            if not java_file.is_file():
                continue
            try:
                src = java_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            signals = _detect_concurrent_signals(src)
            if not signals:
                continue

            # 提取类名（public/protected class/interface/enum Xxx）
            class_names = re.findall(
                r"\b(?:public|protected)\s+(?:class|interface|enum)\s+([A-Z][a-zA-Z0-9]+)",
                src,
            )
            for cls in class_names:
                if cls not in mentioned_classes:
                    signal_str = ", ".join(dict.fromkeys(signals))  # 去重保序
                    warnings.append(
                        f"WARNING: Q05 concurrent_scope — "
                        f"{java_file.name} 中 {cls} 含并发/锁信号（{signal_str}）"
                        f"，但未出现在任何 EUT 的 given/when/then 或 class_under_test 中。"
                        f" 请确认是否需要补充注解验证或并发场景测试（参考 SE-006 处理模式）。"
                    )

    return warnings


def run_q05_structure_checks(output_dir: Path, project_id: str) -> list[str]:
    """对 Q05 phase_b_structured + supplemental_tests 做结构类校验."""
    phase_def = PHASE_DEFS.get("Q05")
    if not phase_def:
        return []

    pd = _phase_dir(output_dir, project_id, phase_def)
    json_name = STRUCTURED_JSON_MAP.get("Q05")
    if not json_name:
        return []

    path = pd / json_name
    data = load_json(path)
    if not data or not isinstance(data, dict):
        return []

    # 提前加载 code_repos（同时供 mock patterns 检查和并发 scope 检查使用）
    int_dir = _internal_dir(output_dir, project_id, phase_def)
    inputs_data = load_json(int_dir / "_inputs.json") if (int_dir / "_inputs.json").is_file() else {}
    code_repos: list[str] = []
    if inputs_data and isinstance(inputs_data, dict):
        code_repos = inputs_data.get("code_repos") or []
        if not code_repos and inputs_data.get("code_repo"):
            code_repos = [inputs_data["code_repo"]]

    errors: list[str] = []
    errors.extend(_check_eut_missing_se(data))
    errors.extend(_check_wrong_directory(data))

    # mock 拼写/幽灵方法检查：有 code_repos 就扫业务仓库新增测试文件，否则 fallback 旧目录
    test_files = _collect_new_test_files_from_repos(code_repos) if code_repos else _collect_supplemental_files(pd)
    errors.extend(_check_mock_patterns(test_files))

    # ── 并发/幂等/锁强管控 ────────────────────────────────────────────────────
    # 加载 Q01 产物（获取 SE 描述，用于关键词匹配）
    q01_def = PHASE_DEFS.get("Q01")
    q01_data: dict[str, Any] | None = None
    if q01_def:
        q01_json = STRUCTURED_JSON_MAP.get("Q01")
        if q01_json:
            q01_path = _phase_dir(output_dir, project_id, q01_def) / q01_json
            q01_data = load_json(q01_path) if q01_path.is_file() else None

    errors.extend(_check_concurrent_se_no_eut(data, q01_data))

    # concurrent_scope 是 WARNING 级别（不阻断 finalize）
    # 同时检测注解（@DistributedLocked 等）和代码级并发原语（ReentrantLock/synchronized/Atomic* 等）
    concurrent_warnings = _check_concurrent_scope(data, code_repos)
    if concurrent_warnings:
        log.warning("Q05 concurrent_scope: %d warning(s)", len(concurrent_warnings))
        errors.extend(concurrent_warnings)  # WARNING 前缀，approve guardrail 会区分

    if errors:
        log.info("Q05 structure checks: %d issue(s)", len(errors))
    return errors
