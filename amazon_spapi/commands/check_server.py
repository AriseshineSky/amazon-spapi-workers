# -*- coding: utf-8 -*-
"""Server-side smoke test without starting Celery workers."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse

from amazon_spapi.config.env import get_broker_url
from amazon_spapi.config.paths import CONFIG_ENV_VAR, DEFAULT_CONFIG_PATH


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    results: List[CheckResult] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append(CheckResult(name=name, ok=ok, detail=detail))

    @property
    def passed(self) -> bool:
        return all(r.ok for r in self.results)


def _config_path() -> str:
    return os.getenv(
        CONFIG_ENV_VAR,
        os.getenv(
            "MWS_COLLECTOR_CONFIGURATION_PATH",
            DEFAULT_CONFIG_PATH,
        ),
    )


def check_python_version(report: Report) -> None:
    major, minor = sys.version_info[:2]
    ok = (major, minor) in ((3, 11), (3, 12))
    report.add(
        "python",
        ok,
        f"{major}.{minor}" if ok else f"{major}.{minor} (need 3.11 or 3.12)",
    )


def check_imports(report: Report) -> None:
    try:
        from amazon_spapi.worker import app  # noqa: F401

        report.add("imports", True, "amazon_spapi.worker loads")
    except Exception as exc:
        report.add("imports", False, str(exc))


def check_config(report: Report) -> None:
    path = _config_path()
    if not os.path.isfile(path):
        report.add("config_file", False, f"missing: {path}")
        return

    report.add("config_file", True, path)
    try:
        from amazon_spapi.platform.config_loader import IniConfigLoader

        cfg = IniConfigLoader(path, False).load()
    except Exception as exc:
        report.add("config_parse", False, str(exc))
        return

    report.add("config_parse", True, f"{len(cfg)} sections")
    for section in ("spapi", "offer_service", "product_service"):
        if section not in cfg:
            report.add(f"config:{section}", False, "section missing")
            continue
        keys = cfg[section]
        empty = [k for k, v in keys.items() if not str(v).strip()]
        if empty:
            report.add(
                f"config:{section}",
                False,
                f"empty keys: {', '.join(empty[:5])}",
            )
        else:
            report.add(f"config:{section}", True, f"{len(keys)} keys")


def check_broker(report: Report) -> None:
    try:
        broker_url = get_broker_url()
    except Exception as exc:
        report.add("broker_env", False, str(exc))
        return

    if not broker_url:
        report.add("broker_env", False, "BROKER_URL not set")
        return

    parsed = urlparse(broker_url)
    report.add(
        "broker_env",
        True,
        f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 'default'}",
    )

    try:
        import redis

        client = redis.from_url(broker_url, socket_connect_timeout=5)
        client.ping()
        report.add("redis_ping", True, "PONG")
    except Exception as exc:
        report.add("redis_ping", False, str(exc))


def check_elasticsearch(report: Report, section: str) -> None:
    try:
        from amazon_spapi.platform import get_config

        cfg = get_config()[section]
        from elasticsearch import Elasticsearch

        es = Elasticsearch(
            hosts=cfg["host"],
            port=int(cfg["port"]),
            http_auth=(cfg["user"], cfg["password"]),
            timeout=10,
        )
        if not es.ping():
            report.add(f"es:{section}", False, "ping failed")
            return
        report.add(f"es:{section}", True, f"{cfg['host']}:{cfg['port']}")
    except KeyError as exc:
        report.add(f"es:{section}", False, f"missing key {exc}")
    except Exception as exc:
        report.add(f"es:{section}", False, str(exc))


def check_celery_tasks(report: Report) -> None:
    try:
        from amazon_spapi.worker import app

        expected = {
            "amazon_spapi.jobs.refresh_offers.refresh_offers",
            "amazon_spapi.jobs.refresh_catalog.refresh_catalog",
            "amazon_spapi.jobs.fetch_products.fetch_products",
        }
        registered = set(app.tasks.keys())
        missing = sorted(expected - registered)
        if missing:
            report.add("celery_tasks", False, f"missing: {', '.join(missing)}")
        else:
            report.add("celery_tasks", True, f"{len(expected)} tasks registered")
    except Exception as exc:
        report.add("celery_tasks", False, str(exc))


def check_running_workers(report: Report, timeout: float) -> None:
    try:
        from amazon_spapi.worker import app

        inspector = app.control.inspect(timeout=timeout)
        ping = inspector.ping() if inspector else None
        if not ping:
            report.add(
                "celery_workers",
                False,
                "no worker replied (optional if not started yet)",
            )
            return
        names = ", ".join(sorted(ping.keys()))
        report.add("celery_workers", True, names)
    except Exception as exc:
        report.add("celery_workers", False, str(exc))


def check_systemd_units(report: Report, units: List[str]) -> None:
    import subprocess

    for unit in units:
        try:
            proc = subprocess.run(
                ["systemctl", "is-active", unit],
                capture_output=True,
                text=True,
                check=False,
            )
            state = (proc.stdout or proc.stderr or "").strip()
            report.add(f"systemd:{unit}", proc.returncode == 0, state)
        except FileNotFoundError:
            report.add("systemd", False, "systemctl not found")
            return
        except Exception as exc:
            report.add(f"systemd:{unit}", False, str(exc))


def print_report(report: Report) -> None:
    print("")
    print("Amazon SP-API workers — server check")
    print("=" * 50)
    for item in report.results:
        mark = "OK" if item.ok else "FAIL"
        line = f"[{mark}] {item.name}"
        if item.detail:
            line = f"{line}: {item.detail}"
        print(line)
    print("=" * 50)
    if report.passed:
        print("Result: all checks passed")
    else:
        failed = [r.name for r in report.results if not r.ok]
        print(f"Result: failed ({len(failed)}): {', '.join(failed)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check server readiness without running Celery tasks.",
    )
    parser.add_argument(
        "--with-workers",
        action="store_true",
        help="Also ping running Celery workers (needs broker + workers up).",
    )
    parser.add_argument(
        "--worker-timeout",
        type=float,
        default=3.0,
        help="Seconds to wait for worker ping (default: 3).",
    )
    parser.add_argument(
        "--systemd",
        nargs="*",
        metavar="UNIT",
        help="Check systemd units, e.g. amazon-spapi-offers-us.service",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = Report()

    check_python_version(report)
    check_imports(report)
    check_config(report)
    check_broker(report)

    if any(r.name == "config_parse" and r.ok for r in report.results):
        check_elasticsearch(report, "offer_service")
        check_elasticsearch(report, "product_service")

    check_celery_tasks(report)

    if args.with_workers:
        check_running_workers(report, args.worker_timeout)

    if args.systemd is not None:
        units = args.systemd or [
            "amazon-spapi-offers-us.service",
            "amazon-spapi-catalog-us.service",
        ]
        check_systemd_units(report, units)

    print_report(report)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
