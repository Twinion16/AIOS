"""Test wrapper standing in for an agent executable in BUILD->REVIEW->FIX tests.

Invoked as:  <wrapper> run <prompt>
  - REVIEW prompts -> FAIL on first call, PASS afterwards (counter file)
  - FIX prompts    -> record that a fix happened (marker file)
  - BUILD prompts  -> delegate to the real `opencode run`

Markers live in the current working directory (= project state dir when
the project has no repository, which is the case for these tests).
"""
import subprocess
import sys
from pathlib import Path


def main() -> int:
    prompt = sys.argv[2] if len(sys.argv) > 2 else ""
    cwd = Path.cwd()

    if "REVIEW AGENT" in prompt:
        counter = cwd / ".stub_review_count"
        n = int(counter.read_text()) if counter.exists() else 0
        n += 1
        counter.write_text(str(n))
        verdict = "FAIL" if n == 1 else "PASS"
        (cwd / "REVIEW.md").write_text(
            "# REVIEW\n\n"
            f"## Summary\nStub reviewer call {n}: verdict {verdict}.\n\n"
            "## Findings\n"
            "- (stub)\n\n"
            "## Final Status\n"
            f"{verdict}\n",
            encoding="utf-8",
        )
        print(f"[stub] review call {n} -> {verdict}")
        return 0

    if "FIX AGENT" in prompt:
        (cwd / ".stub_fixed").write_text("1")
        print("[stub] fix recorded")
        return 0

    # BUILD: delegate to the real opencode
    return subprocess.run(["opencode", "run", prompt], cwd=str(cwd)).returncode


if __name__ == "__main__":
    sys.exit(main())
