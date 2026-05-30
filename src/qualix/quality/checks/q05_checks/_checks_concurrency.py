"""Q05 并发/幂等/锁检查."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from qualix.log import get_logger

log = get_logger(__name__)


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


_CONCURRENT_EUT_KWS = frozenset({"并发", "幂等", "CountDownLatch", "多线程", "concurren", "同时"})
_MULTITHREAD_PATTERN = re.compile(
    r"\b(CountDownLatch|CyclicBarrier|Thread\s*\(|ExecutorService|CompletableFuture"
    r"|@Async|AtomicInteger|synchronized\s*\()",
    re.IGNORECASE,
)


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
