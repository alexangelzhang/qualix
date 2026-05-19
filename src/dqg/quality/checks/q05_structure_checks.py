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
    """从业务仓库收集新增/修改的测试文件.

    两路来源（取并集）：
    1. git status --porcelain：未提交的新增/修改文件（含 untracked）
    2. git diff origin/master...HEAD --name-only：已提交但相对 master 新增的文件

    SKILL.md 要求测试代码直接写到业务仓库的 src/test/java。
    """

    def _is_test_path(norm: str, name: str) -> bool:
        return (
            "src/test/" in norm
            or name.endswith("test.java")
            or name.endswith("test.kt")
            or ".test." in name
            or ".spec." in name
        )

    test_paths: list[Path] = []
    for repo_str in code_repos:
        repo = Path(repo_str).expanduser().resolve()
        if not repo.is_dir():
            continue
        candidate_paths: set[str] = set()
        try:
            # 路径 1：未提交变更（含 untracked）
            r = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    candidate_paths.add(line[3:].strip())

            # 路径 2：已提交但相对 origin/master 新增的文件
            r2 = subprocess.run(
                ["git", "diff", "origin/master...HEAD", "--name-only", "--diff-filter=AM"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r2.returncode == 0:
                for line in r2.stdout.splitlines():
                    candidate_paths.add(line.strip())
        except (subprocess.TimeoutExpired, OSError):
            continue

        for path_str in candidate_paths:
            if not path_str:
                continue
            p = repo / path_str
            if not p.is_file() or p.suffix not in _TEST_FILE_SUFFIXES:
                continue
            norm = path_str.replace("\\", "/")
            if _is_test_path(norm, p.name.lower()):
                test_paths.append(p)

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


# Step 0.5 / uncovered_reasons 相关常量
_INJECT_MOCKS_PATTERN = re.compile(r"@InjectMocks\s+(\w+)", re.IGNORECASE)
_IMPORT_CLASS_PATTERN = re.compile(r"import\s+(?:[\w.]+\.)?(\w+)\s*;")
_BACKEND_KWS: frozenset[str] = frozenset(
    {
        "接口",
        "Service",
        "数据库",
        "缓存",
        "校验",
        "验证",
        "validate",
        "domain",
        "Manager",
        "Mapper",
        "Gateway",
        "Repository",
        "save",
        "insert",
        "update",
        "delete",
        "query",
        "select",
        "事务",
        "transaction",
    }
)
_FRONTEND_EXCUSES: frozenset[str] = frozenset(
    {"前端逻辑", "前端", "UI", "BPM", "页面", "展示", "界面", "H5", "小程序", "配置项", "不在代码范围"}
)


def _check_target_modules_json(
    output_dir: Path,
    project_id: str,
    phase_def: dict,
    code_repos: list[str],
    test_files: list[Path],
    q01_data: dict | None,
) -> list[str]:
    """Step 0.5 核心 gate：三层驱动产物必须存在、完整、与测试代码交叉验证.

    三层防御：
    1. 基础：文件存在且覆盖全部 SE
    2. 中层：git_diff_files 非空（证明执行了 git diff）
    3. 深层：se_mappings 里的 impl_class 必须出现在新增测试文件中（交叉验证）
    """
    int_dir = _internal_dir(output_dir, project_id, phase_def)
    target_path = int_dir / "_q05_target_modules.json"

    if not target_path.exists():
        return [
            "BLOCKED: Q05 missing_target_modules — "
            "_internal/_q05_target_modules.json 不存在。"
            "SKILL.md Step 0.5e 要求：三层驱动（REQ/BR→类 + SE→类 + git diff）完成后"
            "必须输出此文件，否则无法证明 Step 0.5 被真正执行。"
        ]

    data = load_json(target_path)
    if not data or not isinstance(data, dict):
        return ["BLOCKED: Q05 target_modules_empty — _q05_target_modules.json 为空或格式错误"]

    errors: list[str] = []

    # ── 层 1：SE 覆盖完整性 ─────────────────────────────────────────────────
    if q01_data:
        all_se_ids = {s["se_id"] for s in q01_data.get("semantic_expectations", [])}
        se_mappings = data.get("se_mappings", [])
        mapped_se_ids = {m.get("se_id", "") for m in se_mappings if isinstance(m, dict)}
        missing_se = sorted(all_se_ids - mapped_se_ids)
        if missing_se:
            errors.append(
                f"BLOCKED: Q05 target_modules_incomplete — "
                f"_q05_target_modules.json 缺少以下 SE 的类映射: {', '.join(missing_se)}。"
                "请在 Step 0.5b 中为每条 SE 搜索对应实现类（未找到填 found=false + gap_reason）。"
            )

    # ── 层 2：git_diff_files 非空（证明执行了 git diff） ─────────────────────
    diff_files = data.get("git_diff_files", [])
    if not diff_files and code_repos:
        errors.append(
            "BLOCKED: Q05 target_modules_no_diff — "
            "_q05_target_modules.json 的 git_diff_files 为空，"
            "说明 Step 0.5c 未执行 git diff。请执行 git diff --name-only 获取变更文件列表。"
        )

    # ── 层 3：交叉验证——impl_class 必须出现在新增测试文件中 ──────────────────
    se_mappings = data.get("se_mappings", [])
    found_classes = {
        m["impl_class"] for m in se_mappings if isinstance(m, dict) and m.get("found") and m.get("impl_class")
    }
    if found_classes and test_files:
        # 收集所有新增测试文件里出现的类名（@InjectMocks + import）
        tested_classes: set[str] = set()
        for path in test_files:
            if path.suffix != ".java":
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                tested_classes.update(m.group(1) for m in _INJECT_MOCKS_PATTERN.finditer(text))
                tested_classes.update(m.group(1) for m in _IMPORT_CLASS_PATTERN.finditer(text))
            except OSError:
                continue

        # 在映射里声明了 found=true 但测试文件里完全没有用到的类
        not_tested = sorted(found_classes - tested_classes)
        if not_tested and len(not_tested) / max(len(found_classes), 1) > 0.5:
            errors.append(
                f"WARNING: Q05 target_modules_not_tested — "
                f"se_mappings 声明的 {len(not_tested)}/{len(found_classes)} 个实现类"
                f"未出现在新增测试文件的 @InjectMocks/import 中: {', '.join(not_tested[:5])}。"
                "可能是 Step 0.5 的映射表与实际生成的测试代码不一致（映射了但未写测试）。"
            )

    return errors


def _check_uncovered_br_reasons(
    output_dir: Path,
    project_id: str,
    phase_def: dict,
    q01_data: dict | None,
) -> list[str]:
    """uncovered BR 理由合理性：reason 含"前端"但 BR 描述含后端语义 → WARNING."""
    if not q01_data:
        return []

    # 查找设计矩阵
    pd = _phase_dir(output_dir, project_id, phase_def)
    int_dir = _internal_dir(output_dir, project_id, phase_def)
    matrix = None
    for candidate in [pd / "_test_design_matrix.json", int_dir / "_test_design_matrix.json"]:
        matrix = load_json(candidate) if candidate.exists() else None
        if matrix:
            break
    if not matrix:
        return []

    br_descs = {
        r["req_id"]: r.get("description", "")
        for r in q01_data.get("requirements", [])
        if str(r.get("req_id", "")).startswith("BR")
    }
    req_coverage = matrix.get("req_coverage", [])
    suspicious: list[str] = []

    for entry in req_coverage:
        if not isinstance(entry, dict):
            continue
        uncovered_brs = entry.get("uncovered_brs", []) or []
        reasons = entry.get("uncovered_reasons", []) or []
        if not uncovered_brs:
            continue
        reason_text = " ".join(str(r) for r in reasons)
        is_frontend_excuse = any(kw in reason_text for kw in _FRONTEND_EXCUSES)
        if not is_frontend_excuse:
            continue
        for br_id in uncovered_brs:
            desc = br_descs.get(br_id, "")
            if any(kw in desc for kw in _BACKEND_KWS):
                suspicious.append(f"{br_id}（reason='{reason_text[:30]}'）")

    if suspicious:
        return [
            f"WARNING: Q05 uncovered_reason_mismatch — "
            f"{len(suspicious)} 个 BR 标注为前端/配置原因，但描述含后端语义（Service/接口/数据库等），"
            f"疑似错误排除: {', '.join(suspicious[:4])}。"
            "请确认这些 BR 确实无后端实现，否则应生成对应单测。"
        ]
    return []


# Fix-3: SE/EUT 追溯标注检测
_TRACEABILITY_PATTERN = re.compile(r"(SE-\d+|EUT-\d+)", re.IGNORECASE)
# Fix-5: 并发测试多线程模式检测
_CONCURRENT_EUT_KWS = frozenset({"并发", "幂等", "CountDownLatch", "多线程", "concurren", "同时"})
_MULTITHREAD_PATTERN = re.compile(
    r"\b(CountDownLatch|CyclicBarrier|Thread\s*\(|ExecutorService|CompletableFuture"
    r"|@Async|AtomicInteger|synchronized\s*\()",
    re.IGNORECASE,
)


def _collect_git_diff_basenames(code_repos: list[str]) -> set[str]:
    """收集所有仓库 git diff 变更文件的 basename（不含路径）."""
    basenames: set[str] = set()
    for repo_str in code_repos:
        repo = Path(repo_str).expanduser().resolve()
        if not repo.is_dir():
            continue
        for cmd in [
            ["git", "diff", "--name-only", "origin/master...HEAD"],
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            ["git", "status", "--porcelain"],
        ]:
            try:
                r = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True, timeout=10)
                if r.returncode != 0 or not r.stdout.strip():
                    continue
                for line in r.stdout.splitlines():
                    name = line[3:].strip() if cmd[0] == "git" and "status" in cmd else line.strip()
                    if name.endswith(".java"):
                        basenames.add(Path(name).name)
                if basenames:
                    break
            except (subprocess.TimeoutExpired, OSError):
                continue
    return basenames


def _check_se_traceability(test_files: list[Path]) -> list[str]:
    """Fix-3: @Test 方法必须有 SE/EUT 追溯注释（检查比例）.

    SKILL.md Step 3.4：每个 @Test 方法必须标注关联的 SE/EUT ID。
    <60% 的方法有追溯标注 → WARNING。
    """
    if not test_files:
        return []
    total_methods = 0
    traced_methods = 0
    for path in test_files:
        if path.suffix != ".java":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        blocks = _TEST_METHOD_SPLIT.split(text)
        test_blocks = [b for b in blocks if re.match(r"\s*@(?:Test|ParameterizedTest|RepeatedTest)\b", b)]
        for block in test_blocks:
            total_methods += 1
            # 检查方法的前3行是否有 SE/EUT 注释，或方法名本身含 SE/EUT 编号
            first_lines = "\n".join(block.splitlines()[:6])
            if _TRACEABILITY_PATTERN.search(first_lines):
                traced_methods += 1

    if total_methods == 0:
        return []
    rate = traced_methods / total_methods
    if rate < 0.6:
        return [
            f"WARNING: Q05 traceability — {traced_methods}/{total_methods} 个 @Test 方法有 SE/EUT 追溯标注"
            f"（{rate:.0%}，要求 ≥60%）。请在方法注释或名称中加入 SE-xxx/EUT-xxx 标识。"
        ]
    return []


def _check_multi_repo_coverage(code_repos: list[str], test_files: list[Path]) -> list[str]:
    """Fix-4: 多仓库完整性 gate — 有代码变更的仓库必须有新增测试文件.

    仅对有 git diff 变更的仓库做要求：master 等基线仓库无生产代码变更，不应要求新测试。
    """
    import subprocess

    if len(code_repos) <= 1:
        return []
    errors: list[str] = []
    for repo_str in code_repos:
        repo = Path(repo_str).expanduser().resolve()
        if not repo.is_dir():
            continue

        # 检查该仓库是否有生产代码变更（git diff origin/master...HEAD）
        try:
            result = subprocess.run(
                ["git", "diff", "origin/master...HEAD", "--name-only", "--diff-filter=AM"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=10,
            )
            changed_prod = [f for f in result.stdout.splitlines() if f.endswith(".java") and "/test/" not in f]
        except Exception:
            changed_prod = []

        # 无生产代码变更（如 master 基线仓库）→ 不要求新测试
        if not changed_prod:
            continue

        # 有生产代码变更 → 必须有对应新测试文件
        repo_has_tests = any(str(f).startswith(str(repo)) for f in test_files)
        if not repo_has_tests:
            errors.append(
                f"BLOCKED: Q05 multi_repo_coverage — 仓库 {repo.name} 有 {len(changed_prod)} 个生产代码变更但无新增测试文件。"
                "SKILL.md Step 3.5：有代码变更的仓库必须有对应的测试生成，禁止静默跳过。"
            )
    return errors


def _check_concurrency_eut_multithread(
    data: dict[str, Any],
    test_files: list[Path],
    q01_data: dict[str, Any] | None,
) -> list[str]:
    """Fix-5: Concurrency EUT 必须有 CountDownLatch 等多线程验证.

    SKILL.md：并发测试必须使用 CountDownLatch 模式，仅 assertThrows 不算并发测试。
    """
    euts = data.get("eut_items", [])
    has_concurrency_eut = any(
        str(e.get("route_type", "")).lower() == "concurrency"
        or any(kw in str(e.get("then", "") or "") for kw in _CONCURRENT_EUT_KWS)
        or any(kw in str(e.get("given", "") or "") for kw in _CONCURRENT_EUT_KWS)
        for e in euts
    )

    # 也检查 Q01 中并发 SE
    if not has_concurrency_eut and q01_data:
        ses = q01_data.get("semantic_expectations", [])
        has_concurrency_eut = any(_se_is_concurrent(s.get("description", "")) for s in ses)

    if not has_concurrency_eut:
        return []

    # 有并发场景需求，检查测试文件是否有多线程模式
    java_files = [f for f in test_files if f.suffix == ".java"]
    if not java_files:
        return [
            "BLOCKED: Q05 concurrent_no_multithread — 存在并发/幂等 SE 但无新增测试文件，"
            "无法验证并发测试是否使用 CountDownLatch 多线程模式。"
        ]

    multithread_found = False
    for path in java_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            if _MULTITHREAD_PATTERN.search(text):
                multithread_found = True
                break
        except OSError:
            continue

    if not multithread_found:
        return [
            "BLOCKED: Q05 concurrent_no_multithread — 存在并发/幂等 SE，但所有新增测试文件均未使用"
            " CountDownLatch/Thread/ExecutorService 等多线程模式。"
            " SKILL.md：仅 assertThrows 验证重复提交不算并发测试，必须多线程同时触发。"
        ]
    return []


def _check_branch_file_reality(
    output_dir: Path,
    project_id: str,
    phase_def: dict[str, Any],
    code_repos: list[str],
) -> list[str]:
    """Fix-6: 设计矩阵 code_branch_coverage[].file 必须在 git diff 变更文件里.

    防止 LLM 在设计矩阵里虚构不存在的文件名。
    """
    int_dir = _internal_dir(output_dir, project_id, phase_def)
    matrix_path = (
        int_dir / "_test_design_matrix.json"
        if (int_dir / "_test_design_matrix.json").exists()
        else (_phase_dir(output_dir, project_id, phase_def) / "_test_design_matrix.json")
    )
    matrix = load_json(matrix_path) if matrix_path.exists() else None
    if not matrix:
        return []

    branch_coverage = matrix.get("code_branch_coverage", [])
    if not branch_coverage or not code_repos:
        return []

    diff_basenames = _collect_git_diff_basenames(code_repos)
    if not diff_basenames:
        return []  # git diff 失败，不误报

    ghost_files: list[str] = []
    for entry in branch_coverage:
        if not isinstance(entry, dict):
            continue
        fname = str(entry.get("file", "") or "")
        if not fname:
            continue
        basename = Path(fname).name
        if basename and basename not in diff_basenames:
            ghost_files.append(basename)

    if ghost_files:
        unique_ghosts = sorted(set(ghost_files))
        return [
            f"WARNING: Q05 ghost_branch_file — 设计矩阵 code_branch_coverage 中 {len(unique_ghosts)} 个文件"
            f"不在 git diff 变更列表里，疑似虚构：{', '.join(unique_ghosts[:5])}。"
            "请确认分支清单对应的文件是本次实际变更的文件。"
        ]
    return []


# C1+C2: EUT when/then vs actual test code
_METHOD_FROM_WHEN = re.compile(r"\b([a-z][a-zA-Z0-9]{3,})\s*\(")
# C4 / Step 0.5 共享：不应调用语义关键词
_NON_INVOCATION_KWS: frozenset[str] = frozenset(
    {"不发起", "不调用", "不生成", "不回退", "短路", "不传", "不应调用", "禁止调用"}
)
_ASSERT_FROM_THEN = re.compile(
    r"\b(assertEquals|assertThrows|assertThat|verify|assertNull|assertFalse|assertNotNull)\b",
    re.IGNORECASE,
)
# C4: never() pattern in .java files
# Mockito: verify(mock, never()).method() 或 verify(mock, times(0)).method()
# 简单匹配 ", never()" 即可覆盖嵌套括号场景（[^)]+ 无法正确处理 verify(mock, never())）
_NEVER_IN_CODE = re.compile(r",\s*never\s*\(\)|times\s*\(\s*0\s*\)", re.IGNORECASE)
# C7: test_location file existence helper
_REPO_PATH_CACHE: dict[str, Path] = {}


def _check_eut_code_alignment(
    data: dict[str, Any],
    test_files: list[Path],
    q01_data: dict[str, Any] | None,
) -> list[str]:
    """C1+C2: EUT when 字段描述的方法名 + then 字段描述的断言关键词必须出现在测试代码里.

    L1（EUT JSON）↔ L2（.java 测试代码）交叉验证：
    - C1: when="调用 identifyByPrecheckAndFulfillment" → 测试文件里有该方法调用
    - C2: then="assertEquals(LOGISTIC_EXCHANGE, ...)" → 测试文件里有 assertEquals
    """
    if not test_files:
        return []
    java_files = [f for f in test_files if f.suffix == ".java"]
    if not java_files:
        return []

    # 预读所有测试文件文本
    file_texts: list[str] = []
    for p in java_files:
        try:
            file_texts.append(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            file_texts.append("")
    all_code = "\n".join(file_texts)

    euts = data.get("eut_items", [])
    c1_mismatches: list[str] = []
    c2_mismatches: list[str] = []

    for e in euts:
        eid = e.get("eut_id", "?")
        when = str(e.get("when", "") or "")
        then = str(e.get("then", "") or "")

        # C1: 从 when 提取方法名，检查是否出现在测试文件
        method_matches = _METHOD_FROM_WHEN.findall(when)
        for method_name in method_matches:
            if len(method_name) < 5:
                continue
            if method_name not in all_code:
                c1_mismatches.append(f"{eid}(when='{method_name}')")
                break

        # C2: 从 then 提取断言关键词，检查是否出现在测试文件
        then_asserts = _ASSERT_FROM_THEN.findall(then)
        for assert_kw in then_asserts:
            if assert_kw.lower() not in all_code.lower():
                c2_mismatches.append(f"{eid}(then 含{assert_kw}但代码无)")
                break

    errors: list[str] = []
    if c1_mismatches and len(c1_mismatches) / max(len(euts), 1) > 0.3:
        errors.append(
            f"WARNING: Q05 eut_when_mismatch — {len(c1_mismatches)} 个 EUT 的 when 字段方法名"
            f"未出现在测试代码中: {', '.join(c1_mismatches[:4])}。"
            "EUT JSON 的 when 描述与实际测试调用可能不一致。"
        )
    if c2_mismatches and len(c2_mismatches) / max(len(euts), 1) > 0.3:
        errors.append(
            f"WARNING: Q05 eut_then_mismatch — {len(c2_mismatches)} 个 EUT 的 then 字段断言"
            f"未出现在测试代码中: {', '.join(c2_mismatches[:4])}。"
            "EUT then 描述的断言方法与实际测试代码可能不一致。"
        )
    return errors


def _check_never_verify_in_code(
    data: dict[str, Any],
    test_files: list[Path],
    q01_data: dict[str, Any] | None,
) -> list[str]:
    """C4: 修正版 never() 验证——直接扫描 .java 测试代码，不依赖 JSON then 字段.

    若存在"不应调用"语义的 SE，相关测试文件里必须有 verify(mock, never()) 或 times(0)。
    """
    if not q01_data:
        return []
    ses = q01_data.get("semantic_expectations", [])
    non_invoke_ses = [s for s in ses if any(kw in s.get("description", "") for kw in _NON_INVOCATION_KWS)]
    if not non_invoke_ses:
        return []

    java_files = [f for f in test_files if f.suffix == ".java"]
    if not java_files:
        return [
            "BLOCKED: Q05 never_verify_no_testfile — 存在「不应调用」语义 SE 但无新增测试文件，"
            "无法验证 verify(never()) 实际存在于代码中。"
        ]

    found_never = any(
        _NEVER_IN_CODE.search(p.read_text(encoding="utf-8", errors="replace")) for p in java_files if p.is_file()
    )
    if not found_never:
        se_ids = [s["se_id"] for s in non_invoke_ses]
        return [
            f"BLOCKED: Q05 never_verify_missing_in_code — 存在「不应调用」SE（{', '.join(se_ids[:3])}）"
            "但测试代码中未发现 verify(mock, never())/times(0)。"
            "请在对应测试方法里加入 verify(mock, never()).targetMethod() 验证。"
        ]
    return []


def _check_se_id_validity_in_traceability(
    test_files: list[Path],
    q01_data: dict[str, Any] | None,
) -> list[str]:
    """C5: @Test 方法里出现的 SE-xxx 必须是 Q01 里真实存在的 SE ID."""
    if not q01_data or not test_files:
        return []
    valid_se_ids = {s["se_id"] for s in q01_data.get("semantic_expectations", [])}
    ghost_refs: list[str] = []
    for path in test_files:
        if path.suffix != ".java":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in re.finditer(r"SE-(\d+)", text, re.IGNORECASE):
            se_id = f"SE-{m.group(1)}"
            if se_id not in valid_se_ids:
                ghost_refs.append(f"{path.name}:{se_id}")
    if ghost_refs:
        unique = sorted(set(ghost_refs))
        return [
            f"WARNING: Q05 ghost_se_ref — 测试代码中引用了 {len(unique)} 个 Q01 不存在的 SE ID: "
            f"{', '.join(unique[:5])}。请核对注释里的 SE 编号是否拼写正确。"
        ]
    return []


def _check_test_location_file_exists(
    data: dict[str, Any],
    code_repos: list[str],
) -> list[str]:
    """C7: test_cases[].test_location.file 必须在 code_repo 磁盘上真实存在."""
    if not code_repos:
        return []
    test_cases = data.get("test_cases", [])
    missing: list[str] = []
    for tc in test_cases:
        if not isinstance(tc, dict):
            continue
        loc = tc.get("test_location") or {}
        if not isinstance(loc, dict):
            continue
        file_path = str(loc.get("file", "") or "")
        if not file_path:
            continue
        # 在各 code_repo 下查找该文件
        found = False
        for repo_str in code_repos:
            repo = Path(repo_str).expanduser().resolve()
            candidate = repo / file_path.lstrip("/")
            if candidate.is_file():
                found = True
                break
            # 也尝试只用 basename 搜索
            basename = Path(file_path).name
            if basename and any((repo / "**" / basename).parent.is_dir() for _ in [1]):
                found = True
                break
        if not found:
            missing.append(Path(file_path).name)
    if missing:
        unique = sorted(set(missing))
        return [
            f"WARNING: Q05 test_location_not_found — {len(unique)} 个 test_location.file 在 code_repo 中未找到: "
            f"{', '.join(unique[:5])}。test_location 可能是虚填路径，请确认文件已写入 src/test/java。"
        ]
    return []


def _check_test_file_eut_reverse(
    data: dict[str, Any],
    test_files: list[Path],
    target_modules_data: dict[str, Any] | None,
) -> list[str]:
    """C8: 反向检查——新增测试文件里的被测类必须能在 EUT 矩阵里找到对应条目.

    防止 LLM 写了"幽灵测试"（有代码但 EUT 矩阵里没有对应记录）。
    """
    java_files = [f for f in test_files if f.suffix == ".java"]
    if not java_files:
        return []

    euts = data.get("eut_items", [])
    # 从 EUT when/given/then 提取所有提及的类名（大写开头）
    eut_text = " ".join(
        str(e.get("when", "")) + " " + str(e.get("given", "")) + " " + str(e.get("then", "")) for e in euts
    )
    eut_classes_mentioned: set[str] = set(re.findall(r"\b([A-Z][a-zA-Z0-9]{4,})\b", eut_text))

    # 也从 target_modules se_mappings 读 impl_class
    if target_modules_data:
        for m in target_modules_data.get("se_mappings", []):
            cls = str(m.get("impl_class") or "")
            if cls:
                eut_classes_mentioned.add(cls)

    orphan_tests: list[str] = []
    for path in java_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # 提取被测类（@InjectMocks 后的类名）
        for m in _INJECT_MOCKS_PATTERN.finditer(text):
            cls = m.group(1)
            if cls not in eut_classes_mentioned and len(cls) > 5:
                orphan_tests.append(f"{path.name}→{cls}")

    if orphan_tests:
        unique = sorted(set(orphan_tests))[:5]
        return [
            f"WARNING: Q05 orphan_test — {len(orphan_tests)} 个测试文件的被测类（@InjectMocks）"
            f"未出现在 EUT 矩阵 when/given 或 target_modules 中: {', '.join(unique)}。"
            "这些测试可能是无需求溯源的幽灵测试，请确认是否有对应的 EUT 条目。"
        ]
    return []


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

    # Fix-3: SE/EUT 追溯标注（WARNING）
    errors.extend(_check_se_traceability(test_files))

    # Fix-4: 多仓库完整性
    errors.extend(_check_multi_repo_coverage(code_repos, test_files))

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

    # Step 0.5 三层驱动产物验证（BLOCKED + 交叉验证）
    errors.extend(_check_target_modules_json(output_dir, project_id, phase_def, code_repos, test_files, q01_data))

    # uncovered BR 理由合理性（WARNING）
    errors.extend(_check_uncovered_br_reasons(output_dir, project_id, phase_def, q01_data))

    # Fix-5: 并发测试 CountDownLatch 多线程验证（BLOCKED）
    errors.extend(_check_concurrency_eut_multithread(data, test_files, q01_data))

    # Fix-6: 设计矩阵 branch 文件真实性（WARNING）
    errors.extend(_check_branch_file_reality(output_dir, project_id, phase_def, code_repos))

    # C1+C2: EUT when/then 与测试代码关键词交叉验证（WARNING）
    errors.extend(_check_eut_code_alignment(data, test_files, q01_data))

    # C4: never() 直接扫测试代码（补充 JSON then 字段检查的不足）
    errors.extend(_check_never_verify_in_code(data, test_files, q01_data))

    # C5: 追溯注释里的 SE ID 必须是 Q01 真实存在的（WARNING）
    errors.extend(_check_se_id_validity_in_traceability(test_files, q01_data))

    # C7: test_location.file 必须在磁盘上真实存在（WARNING）
    errors.extend(_check_test_location_file_exists(data, code_repos))

    # C8: 反向检查——@InjectMocks 类必须在 EUT 矩阵里有对应（WARNING）
    target_modules_data = (
        load_json(int_dir / "_q05_target_modules.json") if (int_dir / "_q05_target_modules.json").is_file() else None
    )
    errors.extend(_check_test_file_eut_reverse(data, test_files, target_modules_data))

    # C9: EUT 矩阵实现完整性——每条 EUT 的被测类必须有对应 @Test 文件（BLOCKED）
    errors.extend(_check_eut_implementation_completeness(data, test_files))

    # C10: git diff 变更的实现类必须有对应 EUT（WARNING）
    errors.extend(_check_q05_git_diff_coverage(data, target_modules_data))

    # concurrent_scope 是 WARNING 级别（不阻断 finalize）
    # 同时检测注解（@DistributedLocked 等）和代码级并发原语（ReentrantLock/synchronized/Atomic* 等）
    concurrent_warnings = _check_concurrent_scope(data, code_repos)
    if concurrent_warnings:
        log.warning("Q05 concurrent_scope: %d warning(s)", len(concurrent_warnings))
        errors.extend(concurrent_warnings)  # WARNING 前缀，approve guardrail 会区分

    if errors:
        log.info("Q05 structure checks: %d issue(s)", len(errors))
    return errors


def _check_eut_implementation_completeness(
    data: dict[str, Any],
    test_files: list[Path],
) -> list[str]:
    """C9: EUT 矩阵实现完整性——每条 EUT 必须有对应的 @Test 方法实现.

    两层检查：
    1. 文件级（旧逻辑）：被测类必须有 {ClassName}Test.java → 无则 BLOCKED
    2. 方法级（新增）：测试文件内的 @Test 方法数量/覆盖必须匹配 EUT 条数
       - 精确模式：@Test 方法体内有 EUT-xxx 追溯注释 → 逐条验证每个 eut_id 有对应方法
       - 代理模式：无追溯注释 → @Test 方法数 ≥ EUT 条数（下界检查）
    """
    import re as _re
    from collections import defaultdict

    euts = data.get("eut_items", [])
    if not euts:
        return []

    # 从测试文件路径建立 被测类名 → 文件路径 的映射
    test_file_by_class: dict[str, Path] = {}
    for tf in test_files:
        stem = tf.stem
        if stem.endswith("Tests"):
            test_file_by_class[stem[:-5]] = tf
        elif stem.endswith("Test"):
            test_file_by_class[stem[:-4]] = tf
        else:
            test_file_by_class[stem] = tf

    # 从 EUT when 字段提取被测类名，统计每类 EUT 条数
    _CLASS_PATTERN = _re.compile(r"\b([A-Z][a-zA-Z0-9]{3,})\.[a-z]")
    class_to_euts: dict[str, list[str]] = defaultdict(list)
    for e in euts:
        when = str(e.get("when", "") or "")
        eut_id = e.get("eut_id", "?")
        for cls in _CLASS_PATTERN.findall(when):
            class_to_euts[cls].append(eut_id)

    errors: list[str] = []
    for cls in sorted(class_to_euts):
        eut_ids = class_to_euts[cls]
        tf = test_file_by_class.get(cls)

        # 层 1：文件不存在
        if tf is None:
            sample = ", ".join(eut_ids[:3])
            suffix = "..." if len(eut_ids) > 3 else ""
            errors.append(
                f"BLOCKED: Q05 eut_not_implemented — {cls} 有 {len(eut_ids)} 条 EUT 设计"
                f"（{sample}{suffix}）但无对应测试文件（{cls}Test.java）。"
                "EUT 矩阵必须全部实现为 @Test 方法后才能 finalize。"
            )
            continue

        # 层 2：方法级检查
        try:
            src = tf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # 按 @Test/@ParameterizedTest/@RepeatedTest 边界分割，每块对应一个测试方法
        method_blocks = _TEST_METHOD_SPLIT.split(src)
        test_method_count = max(0, len(method_blocks) - 1)

        # 收集所有 @Test 方法体中出现的 EUT-xxx 追溯引用
        covered_eut_ids: set[str] = set()
        for block in method_blocks[1:]:
            for ref in _TRACEABILITY_PATTERN.findall(block):
                if ref.upper().startswith("EUT-"):
                    covered_eut_ids.add(ref.upper())

        if covered_eut_ids:
            # 精确模式：有追溯注释，逐条验证
            missing = [eid for eid in eut_ids if eid.upper() not in covered_eut_ids]
            if missing:
                sample = ", ".join(missing[:5])
                suffix = "..." if len(missing) > 5 else ""
                errors.append(
                    f"BLOCKED: Q05 eut_method_missing — {cls}Test.java 有 {test_method_count} 个"
                    f" @Test 方法，但以下 {len(missing)} 条 EUT 没有对应实现"
                    f"（按 EUT-xxx 追溯）：{sample}{suffix}。"
                    "请为每条 EUT 添加独立 @Test 方法并标注追溯注释（// EUT-xxx）。"
                )
        else:
            # 代理模式：无追溯注释，用方法数作下界
            if test_method_count < len(eut_ids):
                errors.append(
                    f"BLOCKED: Q05 eut_method_count — {cls} 有 {len(eut_ids)} 条 EUT 设计，"
                    f"但 {cls}Test.java 只有 {test_method_count} 个 @Test 方法。"
                    "每条 EUT 应有独立 @Test 方法（建议同时添加 // EUT-xxx 追溯注释）。"
                )

    return errors


# ── 实现 SKILL.md 第 44 行文档化但缺失的 gate ────────────────────────────────
# SKILL.md §Step 0.5：feature branch 每个新增/修改的 Java 实现类，
# 必须在某条 EUT 的 when/given 字段里出现。
_IMPL_SUFFIXES: frozenset[str] = frozenset(
    ("Service", "Manager", "Ext", "Consumer", "Handler", "Processor", "Executor", "Impl")
)
_SKIP_CLASS_PATTERNS: frozenset[str] = frozenset(
    (
        "Config",
        "Configuration",
        "Enum",
        "Constant",
        "VO",
        "Vo",
        "Dto",
        "DTO",
        "Entity",
        "Builder",
        "Param",
        "Request",
        "Response",
        "Abstract",
        "Base",
    )
)
# 这些模块路径里的类是接口/常量定义，不需要测试
_SKIP_MODULE_PREFIXES: tuple[str, ...] = (
    "maf-interface/",
    "maf-core/src/main/java/com/mi/maf/core/constant/",
    "maf-core/src/main/java/com/mi/maf/core/enums/",
)


def _check_q05_git_diff_coverage(
    data: dict[str, Any],
    target_modules_data: dict[str, Any] | None,
) -> list[str]:
    """C10: git diff 变更的实现类必须有对应 EUT when/given 字段引用.

    实现 SKILL.md Step 0.5 中文档化但未落地的 gate：
    'feature branch 新增/修改的每个 Java 类，必须在某条 EUT 的 when 字段里出现'

    只检查实现类（Service/Manager/Ext/Consumer/Impl 等后缀），
    排除接口定义模块、常量包、DTO/VO/Builder 等无业务逻辑类。
    级别：WARNING（允许 finalize，但标记盲区供开发者补充 EUT）
    """
    if not target_modules_data:
        return []

    diff_files: list[str] = target_modules_data.get("git_diff_files", [])
    if not diff_files:
        return []

    euts = data.get("eut_items", [])
    if not euts:
        return []

    # 从所有 EUT 的 when + given 字段提取被提及的类名
    _CLS = re.compile(r"\b([A-Z][a-zA-Z0-9]{3,})\b")
    eut_mentioned: set[str] = set()
    for e in euts:
        for field in ("when", "given"):
            text = str(e.get(field, "") or "")
            eut_mentioned.update(_CLS.findall(text))

    missing: list[tuple[str, str]] = []
    for f in diff_files:
        if not f.endswith(".java"):
            continue
        if "src/test/" in f:
            continue
        if any(f.startswith(skip) for skip in _SKIP_MODULE_PREFIXES):
            continue

        class_name = f.split("/")[-1].replace(".java", "")

        if not any(class_name.endswith(s) for s in _IMPL_SUFFIXES):
            continue
        if any(pat in class_name for pat in _SKIP_CLASS_PATTERNS):
            continue

        if class_name not in eut_mentioned:
            missing.append((class_name, f))

    if not missing:
        return []

    errors: list[str] = []
    for cls, path in missing:
        short_path = "/".join(path.split("/")[-3:])
        errors.append(
            f"BLOCKED: Q05 git_diff_not_covered — {cls} 在 git diff 中有变更"
            f"（{short_path}）但未出现在任何 EUT 的 when/given 字段。"
            "变更的实现类必须有对应 EUT，请补充到 EUT 矩阵后重新 finalize。"
        )

    return errors
