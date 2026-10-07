"""Generate a fake engineering meeting of any length (script + audio) for testing. macOS only (uses `say`).

Usage, from the project root:
    python3 scripts/make_test_meeting.py MINUTES NAME [--traps]

Writes scratch/NAME.txt (the script, i.e. the ground truth) and scratch/NAME.m4a.
With --traps, inserts items that span the meeting (a proposal accepted much later,
a decision reversed later, an owner + deadline); the correct handling is listed in
scratch/NAME_expected.txt.
"""

import random
import subprocess
import sys
from pathlib import Path

random.seed(7)
PEOPLE = ["Priya", "Arjun", "Neha", "Tom", "Meera", "Karan", "Sofia", "Daniel", "Aisha", "Rahul"]
SYSTEMS = ["the billing service", "the search API", "the mobile app", "the data pipeline", "the admin dashboard",
           "the notification service", "the payment gateway", "the analytics warehouse", "the login flow", "the CI pipeline"]
METRICS = ["error rate", "page load time", "test coverage", "crash-free rate", "query latency", "build time"]
TASKS = ["write the migration plan", "update the runbook", "fix the flaky integration tests", "review the Terraform changes",
         "set up the staging alerts", "profile the slow queries", "draft the incident report", "clean up the feature flags",
         "upgrade the Postgres driver", "document the new endpoints", "rotate the API credentials", "benchmark the cache layer"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "the end of the sprint", "next Wednesday"]
IDEAS = ["move the nightly jobs to Kubernetes cron jobs", "replace Jenkins with GitHub Actions", "add a Redis cache in front of the search API",
         "split the monolith's billing module into its own service", "switch our logging to OpenTelemetry", "try feature flags with LaunchDarkly"]
DECISIONS = ["freeze new features until the release ships", "use Grafana for all service dashboards", "keep the old API version for one more quarter",
             "run load tests before every major release", "make code review mandatory for infrastructure changes"]


def status_update() -> str:
    a, b = random.sample(PEOPLE, 2)
    s, m = random.choice(SYSTEMS), random.choice(METRICS)
    n1, n2 = random.randint(20, 60), random.randint(61, 95)
    return (f"Next, {a} gave a quick update on {s}. The {m} went from {n1} to {n2} after last week's changes. "
            f"{b} asked whether the numbers are stable, and {a} said they have been steady for about four days. "
            f"Nobody had concerns, so we moved on.")


def chatter() -> str:
    a, b = random.sample(PEOPLE, 2)
    s = random.choice(SYSTEMS)
    return (f"{a} mentioned that the on-call week was fairly quiet, apart from one alert on {s} that turned out to be a false alarm. "
            f"{b} said the alert threshold is probably too sensitive and that it has fired a few times this month. "
            f"We talked about it for a bit, but it is not urgent, and the dashboards look healthy overall.")


def assignment(used: set[str]) -> str:
    a = random.choice(PEOPLE)
    task = random.choice([t for t in TASKS if t not in used] or TASKS)
    used.add(task)
    day = random.choice(DAYS)
    return f"{a}, could you {task} by {day}? Sure, I will {task} by {day}."


def proposal() -> str:
    a = random.choice(PEOPLE)
    return f"{a} suggested that we {random.choice(IDEAS)}. People had mixed feelings, so we agreed to think about it and not decide today."


def decision() -> str:
    return f"After some discussion, we decided to {random.choice(DECISIONS)}. Everyone agreed."


def build(minutes: float, traps: bool) -> tuple[str, list[str]]:
    words_needed = int(minutes * 165)  # `say -r 175` speaks roughly 165 words a minute with pauses
    blocks, used, expected = ["Good morning everyone, let's get started with the weekly engineering sync."], set(), []
    makers = [status_update, chatter, chatter, lambda: assignment(used), proposal, decision, status_update]
    trap_at = {}
    if traps:
        trap_at = {
            0.10: ("Sofia proposed that we migrate the reporting jobs from cron to Apache Airflow. Let's park that for now and come back to it later.",
                   "PROPOSAL accepted later -> must appear as a DECISION (Airflow), not an open item"),
            0.30: ("Daniel will own the API rate limiting work, and he will have a first version ready by October 20th.",
                   "ACTION owner=Daniel deadline='by October 20th' (rate limiting)"),
            0.50: ("We decided to keep the legacy payments endpoint running until December.",
                   "DECISION later REVERSED -> must NOT appear as keep-until-December"),
            0.70: ("Going back to Sofia's idea from earlier about Apache Airflow for the reporting jobs. Okay, let's do it. We'll move the reporting jobs to Airflow.",
                   "(acceptance of the Airflow proposal)"),
            0.90: ("One correction on the legacy payments endpoint. Actually, we will shut it down at the end of this month instead of keeping it until December.",
                   "FINAL decision: shut down legacy payments endpoint at end of this month"),
        }
    pending = sorted(trap_at.items())
    while sum(len(b.split()) for b in blocks) < words_needed:
        progress = sum(len(b.split()) for b in blocks) / words_needed
        if pending and progress >= pending[0][0]:
            text, note = pending.pop(0)[1]
            blocks.append(text)
            expected.append(note)
            continue
        blocks.append(random.choice(makers)())
    for _, (text, note) in pending:  # any traps not yet placed
        blocks.append(text)
        expected.append(note)
    blocks.append("That's everything for today. Thanks, everyone.")
    return "\n".join(blocks), expected


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    minutes, name = float(sys.argv[1]), sys.argv[2]
    traps = "--traps" in sys.argv
    script, expected = build(minutes, traps)
    here = Path(__file__).resolve().parents[1] / "scratch"  # git-ignored
    here.mkdir(exist_ok=True)
    (here / f"{name}.txt").write_text(script)
    if expected:
        (here / f"{name}_expected.txt").write_text("\n".join(expected) + "\n")
    aiff = here / f"{name}.aiff"
    subprocess.run(["say", "-v", "Samantha", "-r", "175", "-o", str(aiff), "-f", str(here / f"{name}.txt")], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(aiff), "-c:a", "aac", "-b:a", "48k", str(here / f"{name}.m4a")], check=True)
    aiff.unlink()
    duration = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(here / f"{name}.m4a")],
                              capture_output=True, text=True).stdout.strip()
    size = (here / f"{name}.m4a").stat().st_size / 1024 / 1024
    print(f"{name}.m4a: {float(duration) / 60:.1f} min, {size:.1f} MB, {len(script.split())} words")


if __name__ == "__main__":
    main()
