"""Print one clear line when the graph and cache tests were skipped because Neo4j or Redis is down.

The tests skip themselves (see service_or_skip in test_smoke.py), and pytest still reports success.
This makes the skip visible at the end of `make smoke`.
"""


def pytest_terminal_summary(terminalreporter):
    skipped = terminalreporter.stats.get("skipped", [])
    services = set()
    count = 0
    for report in skipped:
        reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
        for name in ("Neo4j", "Redis"):
            if f"{name} not reachable" in reason:
                services.add(name)
                count += 1
                break
    if count:
        names = " and ".join(sorted(services))
        verb = "was" if len(services) == 1 else "were"
        tests = "test" if count == 1 else "tests"
        terminalreporter.write_line(
            f"NOTE: {count} graph and cache {tests} SKIPPED because {names} {verb} not reachable. "
            "Start Neo4j and Redis (make services, or the docker run commands in the README) "
            "and run make smoke again to test everything.",
            yellow=True, bold=True,
        )
