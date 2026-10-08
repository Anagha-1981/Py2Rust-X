"""Command-line interface (CLI) for Py2SafeRust-X.

Enables local command-line transpilation, adaptive repair, semantic verification,
and report generation without starting the web server.

Usage:
    python -m cli.main input.py --out output.rs --report report.md
"""
import argparse
import json
import sys
from pathlib import Path
from pipeline import run_pipeline, PipelineConfig


def main():
    parser = argparse.ArgumentParser(
        prog="Py2SafeRust-X CLI",
        description="Transpile Python code to safe, verified, compilable Rust."
    )
    parser.add_argument("input", help="Path to Python source file (.py)")
    parser.add_argument("--out", "-o", help="Path to output generated Rust file (.rs)")
    parser.add_argument("--report", "-r", help="Path to save generated Markdown explanation report (.md)")
    parser.add_argument("--json", action="store_true", help="Print full output dictionary as JSON")
    parser.add_argument("--max-repair", type=int, default=5, help="Maximum repair loop iterations (default: 5)")
    parser.add_argument("--timeout", type=int, default=5, help="Execution timeout in seconds (default: 5)")

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file '{args.input}' does not exist.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            python_source = f.read()
    except Exception as e:
        print(f"Error reading file '{args.input}': {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Transpiling and verifying '{args.input}' through Py2SafeRust-X pipeline...")

    config = PipelineConfig(
        max_repair_iterations=args.max_repair,
        execution_timeout_secs=args.timeout
    )

    try:
        result = run_pipeline(python_source, config=config)
    except Exception as e:
        print(f"[!] Pipeline execution error: {e}", file=sys.stderr)
        sys.exit(1)

    # Print summary to terminal
    print("\n" + "=" * 55)
    print("           Py2SafeRust-X Pipeline Summary")
    print("=" * 55)
    print(f"Compiled:             {'YES (Clean)' if result.compiled else 'NO (Failed)'}")
    if not result.compiled:
        print("Semantic Equivalence: SKIPPED (Compilation Failed)")
    else:
        print(f"Semantic Equivalence: {'YES (Verified)' if result.semantic_match else 'NO (Mismatch)'}")
    print(f"Confidence Score:     {result.confidence_score} / 100")
    print(f"Repair Iterations:    {len(result.repair_log)}")
    if result.warnings:
        print(f"Transpiler Warnings:  {len(result.warnings)}")
        for w in result.warnings:
            print(f"  - {w}")
    print("=" * 55 + "\n")

    # Write output Rust file
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(result.rust_code)
        print(f"[+] Output Rust code written to: {args.out}")
    else:
        print("--- Generated Rust Code ---")
        print(result.rust_code)
        print("---------------------------")

    # Write Markdown explanation report
    if args.report:
        rep_path = Path(args.report)
        rep_path.parent.mkdir(parents=True, exist_ok=True)
        with open(rep_path, "w", encoding="utf-8") as f:
            f.write(result.explanation_report_markdown)
        print(f"[+] Explanation report saved to: {args.report}")

    # Output JSON if requested
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))

    sys.exit(0 if (result.compiled and result.semantic_match) else 2)


if __name__ == "__main__":
    main()
