import argparse
import json
import os

from dqg.log import get_logger

log = get_logger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Generate strict EUT Matrix fulfilling ut-audit-zh guidelines.")
    parser.add_argument(
        "--input", "-i", type=str, default="ingest.json", help="Path to parsing output containing REQ/BR/SE."
    )
    parser.add_argument("--output", "-o", type=str, default="eut_matrix.md", help="Output matrix file path.")
    return parser.parse_args()


def generate_eut_matrix(input_path, output_path):
    # Retrieve SEs
    se_list = []
    if os.path.exists(input_path):
        try:
            with open(input_path, encoding="utf-8") as f:
                data = json.load(f)
                se_list = data.get("semantic_expectations", [])
        except Exception:
            log.debug("Failed to load semantic expectations from %s", input_path, exc_info=True)

    # Dummy fallback to demonstrate required constraints
    if not se_list:
        se_list = [
            {
                "id": "SEM-001",
                "req": "BR-01",
                "desc": "订单状态机从INIT推进为PROCESSING并持久化",
                "verify": "status == PROCESSING",
            },
            {
                "id": "SEM-002",
                "req": "BR-02",
                "desc": "若库存扣减Ability抛出超时异常，须挂起并重试",
                "verify": "Throws RetryException & rollback() called",
            },
        ]

    md = ["# EUT (Expected Unit Test) 严控审计大纲\n"]
    md.append("> **审计警告**：以下生成的 EUT 矩阵须被单测 100% 覆盖。未来 `/ut-audit-zh` 将逐一校验下表。\n")
    md.append(
        "| EUT编号 | 绑定语义(SEM) | 路线类型 | Given (外部装载Mock) | When (触发行为) | Then (必须满足 ut-audit-zh 的强断言约束) |"
    )
    md.append("|---|---|---|---|---|---|")

    counter = 1
    for se in se_list:
        s_id = se.get("id", "SEM-UNKNOWN")
        desc = se.get("desc", "N/A")
        verify = se.get("verify", "N/A")

        # Happy
        md.append(
            f"| EUT-{counter:03d} | `{s_id}` | Happy Path | 正常DTO与无报错RPC拦截 | {desc} | ✅ 务必断言副产物与强状态: `{verify}` |"
        )
        counter += 1

        # Exception - Forcing ut-audit-zh compliance
        md.append(
            f"| EUT-{counter:03d} | `{s_id}` | Exception | 强制 Mock 下游依赖抛出 Timeout/5xx | 异常环境进入 | 🛑 禁止含糊断言。务必断言特定错误码 `assertThrows(BizExe)` |"
        )
        counter += 1

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))


def main() -> int:
    args = parse_args()
    generate_eut_matrix(args.input, args.output)
    print(f"Strict EUT matrix generated at {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
