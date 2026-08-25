#!/usr/bin/env python3
"""Validate and render enforced Vercel Firewall rate-limit commands without publishing."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "vercel_firewall.v1.json"
PUBLIC_ROUTE_METHODS = frozenset(
    {
        ("/api/v1/ask", "POST"),
        ("/api/v1/feedback", "POST"),
        ("/api/v1/live/map", "GET"),
        ("/api/v1/live/nearby", "POST"),
    }
)


def load_plan(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("firewall plan must be a JSON object")
    payload: dict[str, Any] = loaded
    if payload.get("schema_version") != "firelens.vercel_firewall.v1":
        raise ValueError("unsupported firewall plan schema")
    observation_hours = payload.get("observation_period_hours")
    if not isinstance(observation_hours, int) or observation_hours < 1:
        raise ValueError("observation_period_hours must be a positive integer")
    rules = payload.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("firewall plan requires at least one rule")

    names: set[str] = set()
    routes: set[tuple[str, str]] = set()
    for rule in rules:
        name, path_value, method = _validate_rule(rule, names=names, routes=routes)
        names.add(name)
        routes.add((path_value, method))
    if routes != PUBLIC_ROUTE_METHODS:
        raise ValueError("firewall plan must cover every guarded public route and method")
    return payload


def _validate_rule(
    rule: object,
    *,
    names: set[str],
    routes: set[tuple[str, str]],
) -> tuple[str, str, str]:
    if not isinstance(rule, dict):
        raise ValueError("each firewall rule must be an object")
    required = {
        "name",
        "path",
        "method",
        "window_seconds",
        "requests",
        "keys",
        "rate_limit_action",
    }
    if set(rule) != required:
        raise ValueError("firewall rules must use the exact v1 fields")
    name, path_value, method = rule["name"], rule["path"], rule["method"]
    if not isinstance(name, str) or not name.strip() or name in names:
        raise ValueError("firewall rule names must be unique and non-empty")
    if not isinstance(path_value, str) or path_value not in {
        path for path, _ in PUBLIC_ROUTE_METHODS
    }:
        raise ValueError("firewall rules may target only public FireLens data routes")
    if not isinstance(method, str) or method not in {"GET", "POST"}:
        raise ValueError("firewall rule methods must be GET or POST")
    if (path_value, method) in routes:
        raise ValueError("firewall path and method pairs must be unique")
    if not isinstance(rule["window_seconds"], int) or not 10 <= rule["window_seconds"] <= 300:
        raise ValueError("rate-limit windows must be between 10 and 300 seconds")
    if not isinstance(rule["requests"], int) or not 30 <= rule["requests"] <= 10_000:
        raise ValueError("rate-limit request thresholds must be between 30 and 10000")
    if rule["keys"] != ["ip"]:
        raise ValueError("V1.5 anonymous rate limits must use only the IP key")
    if rule["rate_limit_action"] != "deny":
        raise ValueError("public V1.5 firewall rules must use an enforced deny action")
    return name, path_value, method


def render_command(rule: dict[str, Any]) -> list[str]:
    path_condition = json.dumps(
        {"type": "path", "op": "eq", "value": rule["path"]}, separators=(",", ":")
    )
    method_condition = json.dumps(
        {"type": "method", "op": "eq", "value": rule["method"]}, separators=(",", ":")
    )
    return [
        "npx",
        "vercel@58.1.0",
        "firewall",
        "rules",
        "add",
        rule["name"],
        "--condition",
        path_condition,
        "--condition",
        method_condition,
        "--action",
        "rate_limit",
        "--rate-limit-window",
        str(rule["window_seconds"]),
        "--rate-limit-requests",
        str(rule["requests"]),
        "--rate-limit-keys",
        "ip",
        "--rate-limit-action",
        rule["rate_limit_action"],
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable plan")
    args = parser.parse_args()
    plan = load_plan(args.config)
    commands = [render_command(rule) for rule in plan["rules"]]
    if args.json:
        print(
            json.dumps(
                {
                    "schema_version": plan["schema_version"],
                    "observation_period_hours": plan["observation_period_hours"],
                    "publish_authorized": False,
                    "commands": commands,
                },
                indent=2,
            )
        )
        return
    print("Validated enforced firewall plan. No external state was changed.\n")
    for command in commands:
        print(shlex.join(command))
    print(
        "\nThe rendered rules deny excess requests when published. Review thresholds for at least "
        f"{plan['observation_period_hours']} hours in an owner-approved preview. "
        "This tool never publishes rules; the owner must authorize every external change."
    )


if __name__ == "__main__":
    main()
