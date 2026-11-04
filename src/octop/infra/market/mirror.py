"""Local mirror sources for ``market_mode=mirror_only`` catalogs."""

from __future__ import annotations

from typing import Any


def published_experts_as_hub_items(
    rows: list[Any],
    *,
    query: str = "",
    summary_of: Any | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Map published-expert rows into expert-hub card shape."""
    needle = query.strip().lower()
    items: list[dict[str, Any]] = []
    for row in rows:
        name = str(getattr(row, "name", "") or "")
        description = str(getattr(row, "description", "") or "")
        slug = str(getattr(row, "slug", "") or getattr(row, "id", "") or "")
        if (
            needle
            and needle not in name.lower()
            and needle not in description.lower()
            and needle not in slug.lower()
        ):
            continue
        card: dict[str, Any] = {
            "id": f"published-{slug}",
            "slug": slug,
            "label": {"zh": name, "en": name},
            "description": {"zh": description, "en": description},
            "scene": "local",
            "sub_scene": "",
            "icon_url": getattr(row, "icon_url", None),
            "icon_name": None,
            "color": None,
            "skill_slugs": [],
            "skill_count": 0,
            "source": "published",
            "published_expert_id": getattr(row, "id", slug),
        }
        if summary_of is not None:
            card.update(summary_of(row))
        items.append(card)
    return items, ["local"] if items else []


def skill_packages_as_hub_skills(
    rows: list[Any],
    *,
    query: str = "",
    list_skill_summaries: Any | None = None,
) -> list[dict[str, Any]]:
    """Flatten local skill packages into SkillHub-like search rows."""
    needle = query.strip().lower()
    out: list[dict[str, Any]] = []
    for row in rows:
        package_name = str(getattr(row, "name", "") or "")
        package_id = str(getattr(row, "id", "") or "")
        skills: list[dict[str, Any]] = []
        if list_skill_summaries is not None:
            try:
                skills = list(list_skill_summaries(package_id))
            except Exception:
                skills = []
        if not skills:
            if needle and needle not in package_name.lower() and needle not in package_id.lower():
                continue
            out.append(
                {
                    "slug": package_id,
                    "name": package_name or package_id,
                    "description": str(getattr(row, "description", "") or ""),
                    "source": "local_package",
                    "package_id": package_id,
                }
            )
            continue
        for skill in skills:
            slug = str(skill.get("slug") or "").strip()
            name = str(skill.get("name") or slug)
            desc = str(skill.get("description") or "")
            if (
                needle
                and needle not in slug.lower()
                and needle not in name.lower()
                and needle not in desc.lower()
                and needle not in package_name.lower()
            ):
                continue
            out.append(
                {
                    "slug": slug,
                    "name": name,
                    "description": desc,
                    "source": "local_package",
                    "package_id": package_id,
                    "package_name": package_name,
                }
            )
    return out
