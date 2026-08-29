"""Project registry ImageEntry into user/admin card DTOs."""

from __future__ import annotations

from typing import Any


class CardViewProjector:
    @staticmethod
    def for_user(card: dict[str, Any]) -> dict[str, Any]:
        return {
            "framework": card.get("framework") or "",
            "framework_version": card.get("framework_version") or "",
            "is_default": bool(card.get("is_default")),
        }

    @staticmethod
    def for_admin(
        card: dict[str, Any],
        *,
        total_count: int = 0,
        running_count: int = 0,
        include_paths: bool = False,
    ) -> dict[str, Any]:
        dto = {
            **CardViewProjector.for_user(card),
            "total_instances": total_count,
            "running_instances": running_count,
        }
        if include_paths:
            dto["package_path"] = card.get("package_path") or ""
        return dto
