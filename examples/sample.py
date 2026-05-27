"""Kitchen sink Python sample.

Purpose: compile supported constructs and expose unsupported constructs as warnings.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MAX_POINTS = 1000
PREMIUM_THRESHOLD = 100000
audit_counter = 0


@dataclass(frozen=True)
class Purchase:
    price: int
    category: str = "general"


@dataclass(frozen=True)
class BenefitResult:
    points: int
    message: str
    level: str
    tags: tuple[str, ...] = field(default_factory=tuple)


class AuditLog:
    """Plain class sample with methods."""

    def __init__(self) -> None:
        self.entries: list[str] = []

    def add(self, message: str) -> None:
        self.entries.append(message)


def calculate_user_benefit(
    user: dict[str, Any],
    purchases: list[Purchase],
    dry_run: bool = False,
    *tags: str,
) -> dict[str, Any]:
    """Supported-heavy function: guards, loops, data transforms, try/except/finally and condition chains."""
    if user["status"] != "ACTIVE":
        raise ValueError("inactive user")

    total_amount = 0
    for purchase in purchases:
        total_amount += purchase.price

    try:
        config_text = Path("config.json").read_text(encoding="utf-8")
        print(config_text)
    except OSError as error:
        print(error)
        raise error
    finally:
        print("benefit calculation finished")

    if dry_run:
        return {"points": 0, "message": "dry run", "level": "basic", "tags": tags}
    elif total_amount >= PREMIUM_THRESHOLD and user["rank"] == "Gold":
        return {"points": MAX_POINTS, "message": "premium benefit", "level": "premium", "tags": tags}
    elif total_amount >= 50000:
        return {"points": 500, "message": "standard benefit", "level": "standard", "tags": tags}
    else:
        return {"points": 100, "message": "basic benefit", "level": "basic", "tags": tags}


def inspect_unsupported_flow(user: dict[str, Any], values: list[int]) -> int:
    """Unsupported-heavy function: these constructs should be visible as extraction warnings today."""
    index = 0
    total = 0

    while index < len(values):
        total += values[index]
        index += 1

    match user.get("status"):
        case "ACTIVE":
            total += 10
        case "BANNED":
            total -= 100
        case _:
            total += 0

    with open("audit.log", "a", encoding="utf-8") as file:
        file.write("checked\n")

    first, *rest = values
    normalized = [value * 2 for value in rest if value > first]
    label = f"rank:{user.get('rank', 'None')}" if total > 0 else "none"
    callback = lambda value: value + 1
    print(label)

    return sum(callback(value) for value in normalized) + total


async def fetch_remote_points(user_id: str) -> int:
    await asyncio.sleep(0)
    return len(user_id)


def stream_points(values: list[int]):
    for value in values:
        yield value

