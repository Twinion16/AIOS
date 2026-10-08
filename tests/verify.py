"""Final verification battery for AIOS (no network, no agent runs).

Portable: runs from a fresh clone as a new user. Checks that depend on
this machine's optional data (opencode history DB) are SKIPped, not failed.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aios import config
from aios.task_types import classify_task, select_workflow, TaskType
from aios.agents.registry import AgentRegistry
from aios.history.opencode_history import OpenCodeHistoryProvider
from aios.projects import ProjectRegistry
from aios.context.engine import ContextEngine
from aios.reporting import CONTRACT_TEXT, REPORT_FILENAME
from aios.orchestrator import Orchestrator

failures = []


def check(name, cond, detail=""):
    tag = "OK  " if cond else "FAIL"
    print(f"[{tag}] {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def skip(name, reason):
    print(f"[SKIP] {name} -- {reason}")


# 1. classification
cases = [
    ("Build a wallpaper fitting tool", ["BUILD_LOOP"]),
    ("Find ideas discussed in previous OpenCode sessions", ["HISTORY"]),
    ("Review the greeter.py code and write REVIEW.md", ["REVIEW"]),
    ("Research argparse best practices and summarize", ["KNOWLEDGE"]),
    ("Please flag this for human review", ["HUMAN"]),
]
for text, expect in cases:
    types = classify_task(text)
    wf = select_workflow(types).value
    check(f"classify: {text[:40]!r} -> {wf}", wf in expect, f"got {wf}")

multi = classify_task("research X and then build a demo")
mwf = select_workflow(multi).value
check("multi-intent build+research -> BUILD_LOOP (code loop outranks knowledge)",
      TaskType.BUILD in multi and TaskType.RESEARCH in multi and mwf == "BUILD_LOOP",
      f"types={multi} wf={mwf}")

# 2. config + registry (defaults must keep runtime data outside the repo)
cfg = config.load_config()
pr_path = Path(cfg["projects_root"])
check("projects_root is absolute", pr_path.is_absolute(), str(pr_path))
check("projects_root lives outside the source repo (privacy boundary)",
      ".aios" in pr_path.parts, str(pr_path))
check("_aios_root set for {root} placeholders", bool(cfg.get("_aios_root")))

reg = AgentRegistry.from_config(cfg)
check("hermes disabled by default", not any(a.name == "hermes" for a in reg.all()))
check("kilo disabled by default", not any(a.name == "kilo" for a in reg.all()))
for cap in ["build", "review", "fix", "research", "history"]:
    s = reg.resolve(cap, None)
    check(f"resolve({cap}) -> opencode", s and s.name == "opencode")
check("review prompt is review template",
      reg.resolve("review").prompt_for("REVIEW").name == "hermes_review.md")

# 3. phase-aware prompts in build loop
s = reg.resolve("build")
check("phase build/build/review/fix prompts",
      [s.prompt_for("BUILD_LOOP", p).name for p in (None, "build", "review", "fix")]
      == ["opencode_build.md", "opencode_build.md", "hermes_review.md", "kilo_fix.md"])

# 4. history provider (read-only) - skips when no opencode.db on this machine
try:
    hp = OpenCodeHistoryProvider(
        config=cfg, db_path=cfg["history"]["opencode"].get("db_path", ""))
    if hp.db_path and hp.db_path.exists():
        check("history db found", True)
        sessions = hp.list_sessions(limit=5)
        check("history sessions > 0", len(sessions) > 0, str(len(sessions)))
    else:
        skip("history db found", f"no opencode.db at {hp.db_path}")
except Exception as exc:  # provider must degrade, not crash
    check("history provider degrades gracefully", False, str(exc))

# 5. project registry (no config.yaml rewrite) - scratch project, cleaned up
pr = ProjectRegistry(cfg)
check("registry path is projects.yaml",
      str(pr.registry_path).endswith("projects.yaml"))
scratch_dir = None
try:
    proj = pr.create("verify-scratch")
    scratch_dir = proj.state_dir
    check("scratch project resolvable", pr.exists("verify-scratch"))
    check("scratch state dir under projects_root",
          Path(proj.state_dir).is_relative_to(Path(cfg["projects_root"])))
except Exception as exc:
    check("scratch project creation", False, str(exc))
    proj = None

# 6. context engine renders a bundle
if proj is not None:
    eng = ContextEngine(cfg, reg)
    bundle = eng.build("test task", [TaskType.BUILD],
                       select_workflow([TaskType.BUILD]), proj, phase="review")
    check("bundle has agent", bundle.agent is not None)
    check("bundle prompt non-empty", len(bundle.prompt) > 100)
    from aios.agents.opencode import OpenCodeAgent
    final_prompt = OpenCodeAgent(cfg).prompt_for({"prompt": bundle.prompt})
    check("final prompt has contract", CONTRACT_TEXT.strip() in final_prompt)
    check("review prompt uses review template", "REVIEW AGENT" in bundle.prompt)

# 7. orchestrator wiring
o = Orchestrator(cfg)
check("orchestrator has registry", o.registry is not None)
check("report filename", REPORT_FILENAME == "AIOS_REPORT.json")

# 8. cleanup scratch project (never touch pre-existing user data)
if scratch_dir:
    shutil.rmtree(scratch_dir, ignore_errors=True)

print()
if failures:
    print(f"FAILURES ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL VERIFICATION CHECKS PASSED")
