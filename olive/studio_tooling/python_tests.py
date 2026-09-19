"""Structured unittest runner executed inside the workspace interpreter.

Invoked as `python -m olive.studio_tooling.python_tests <root> [--json path] [--list] [names...]`;
the process writes a JSON report so Studio never regex-parses console text.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
import unittest


def _location(test) -> tuple[str, int | None]:
    try:
        import inspect
        method = getattr(test, test._testMethodName)
        file = inspect.getsourcefile(method) or ""
        _, line = inspect.getsourcelines(method)
        return file, line
    except Exception:
        return "", None


class Result(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.records = []
        self._started = {}

    def startTest(self, test):
        super().startTest(test)
        self._started[test.id()] = time.perf_counter()

    def _record(self, test, state, error=None, message=""):
        file, line = _location(test)
        stack = "".join(traceback.format_exception(*error)) if error else ""
        if error and not message:
            message = "".join(traceback.format_exception_only(error[0], error[1])).strip()
        self.records.append({"name": test._testMethodName, "full_name": test.id(), "state": state,
                             "duration_seconds": round(time.perf_counter() - self._started.get(test.id(), time.perf_counter()), 4),
                             "message": message[:4000], "stack_trace": stack[:12000], "file": file, "line": line})

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record(test, "passed")

    def addFailure(self, test, error):
        super().addFailure(test, error)
        self._record(test, "failed", error)

    def addError(self, test, error):
        super().addError(test, error)
        self._record(test, "failed", error)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record(test, "skipped", message=str(reason))

    def addExpectedFailure(self, test, error):
        super().addExpectedFailure(test, error)
        self._record(test, "passed", message="expected failure")

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._record(test, "failed", message="unexpected success")


def _flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--json", default="")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--start", default="tests")
    parser.add_argument("names", nargs="*")
    args = parser.parse_args(argv)
    sys.path.insert(0, args.root)
    loader = unittest.TestLoader()
    import os
    start = os.path.join(args.root, args.start) if args.start else args.root
    if not os.path.isdir(start):
        start = args.root
    try:
        # Mirrors `python -m unittest discover -s tests` run from the workspace root:
        # the start directory need not be a package; the root stays importable.
        suite = loader.discover(start)
    except Exception as error:
        report = {"summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "duration_seconds": 0.0}, "results": [],
                  "error": f"Discovery failed: {error}"[:400]}
        _write(args.json, report)
        return 2
    tests = list(_flatten(suite))
    if args.names:
        wanted = set(args.names)
        tests = [t for t in tests if t.id() in wanted or any(t.id().endswith("." + name) for name in wanted)]
    if args.list:
        names = [{"full_name": t.id(), "name": getattr(t, "_testMethodName", t.id()), **dict(zip(("file", "line"), _location(t)))} for t in tests]
        _write(args.json, {"tests": names, "error": "" if not loader.errors else str(loader.errors[0])[:400]})
        return 0
    result = Result()
    started = time.perf_counter()
    unittest.TestSuite(tests).run(result)
    summary = {"total": len(result.records), "passed": sum(r["state"] == "passed" for r in result.records),
               "failed": sum(r["state"] == "failed" for r in result.records), "skipped": sum(r["state"] == "skipped" for r in result.records),
               "duration_seconds": round(time.perf_counter() - started, 3)}
    _write(args.json, {"summary": summary, "results": result.records, "error": ""})
    return 0 if summary["failed"] == 0 else 1


def _write(path, report):
    text = json.dumps(report, ensure_ascii=False)
    if path:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    sys.exit(main())
