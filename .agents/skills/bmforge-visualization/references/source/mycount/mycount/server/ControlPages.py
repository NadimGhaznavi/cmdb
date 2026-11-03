"""Render the control server's presentation assets."""

from pathlib import Path
from datetime import datetime, timezone

import pycountry
from uuid import uuid4

from mycount.entity.Report import Report
from mycount.interface.ReportQuery import ReportQuery

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from mycount.constants.DMarketing import DMarketing
from mycount.constants.DVisitors import DVisitors
from mycount.interface.VisitorsQuery import VisitorsQuery


class ControlPages:
    @staticmethod
    def favicon() -> bytes:
        return Path(__file__).with_name("assets").joinpath("mycount.png").read_bytes()

    def __init__(self) -> None:
        self._templates = Environment(
            loader=FileSystemLoader(Path(__file__).with_name("templates")),
            autoescape=select_autoescape(["html"]),
            undefined=StrictUndefined,
        )
        self._templates.filters["country_flag"] = self._country_flag
        self._templates.filters["utc_iso"] = lambda value: value.replace(tzinfo=timezone.utc).isoformat()

    def render(self, report: Report, *, error: str | None = None) -> bytes:
        pages_by_site = {}
        for page in report.pages:
            pages_by_site.setdefault(page["site"], []).append(page)
        return self._templates.get_template("control.html").render(
            sites=report.sites, pages_by_site=pages_by_site, locations=report.locations,
            recent=report.recent, referrers=report.referrers,
            country_slices=self._country_slices(report.locations),
            language_slices=[{"name": self._language_label(row["language_tag"]), "visits": row["page_views"]}
                             for row in report.languages],
            error=error, active_page="metrics", **self._report_context(report, "/metrics"),
        ).encode("utf-8")

    @staticmethod
    def _report_context(report: Report, path: str) -> dict[str, object]:
        return dict(options=report.options, daily=report.daily, available_sites=report.available_sites,
                    first_visit_at=report.first_visit_at, exclude_bots=report.options.exclude_bots,
                    refreshed_at=datetime.now(timezone.utc),
                    newest_url=ReportQuery.link(path, report.options),
                    older_url=ReportQuery.link(path, report.options, report.older) if report.older else None)

    @staticmethod
    def _country_slices(locations: list[dict[str, object]]) -> list[dict[str, object]]:
        countries = {}
        for location in locations:
            code = (location["country_code"] or "").upper()
            country = countries.setdefault(code, {
                "name": location["country_name"] or code or "Unknown", "visits": 0,
            })
            country["visits"] += location["page_views"]
        ordered = sorted(countries.values(), key=lambda country: (-country["visits"], country["name"]))
        total = sum(country["visits"] for country in ordered)
        slices = []
        for country in ordered:
            slices.append({
                **country,
                "percent": country["visits"] / total * 100,
            })
        return slices

    @staticmethod
    def _language_label(tag: str | None) -> str:
        """Name known language, script, and country codes; retain unfamiliar tags."""
        if not tag:
            return "Unknown"
        parts = tag.split("-")
        code = parts[0].lower()
        if len(code) == 2:
            language = pycountry.languages.get(alpha_2=code)
        elif len(code) == 3:
            language = pycountry.languages.get(alpha_3=code)
        else:
            return tag
        if language is None:
            return tag
        qualifiers = []
        for part in parts[1:]:
            if len(part) == 4:
                qualifier = pycountry.scripts.get(alpha_4=part.title())
            elif len(part) == 2:
                qualifier = pycountry.countries.get(alpha_2=part.upper())
            else:
                return tag
            if qualifier is None:
                return tag
            qualifiers.append(qualifier.name)
        return language.name + (f" ({', '.join(qualifiers)})" if qualifiers else "")

    def visitor_map(self, report: Report, *, error: str | None = None) -> bytes:
        mapped = report.map_locations
        return self._templates.get_template("visitor_map.html").render(
            locations=report.locations, mapped_locations=mapped,
            mapped_views=sum(row["page_views"] for row in mapped),
            total_views=sum(row["page_views"] for row in report.locations),
            error=error, active_page="visitor_map", **self._report_context(report, "/"),
        ).encode("utf-8")

    def visitors(self, report: Report, filters: dict[str, str], *, error: str | None = None) -> bytes:
        return self._templates.get_template("visitors.html").render(
            active_page="visitors", columns=DVisitors.COLUMNS, rows=report.recent,
            filters=filters, error=error, first_visit_at=report.first_visit_at,
            exclude_bots=report.options.exclude_bots, refreshed_at=datetime.now(timezone.utc),
            newest_url=VisitorsQuery.link(filters, exclude_bots=report.options.exclude_bots),
            older_url=VisitorsQuery.link(filters, report.older, exclude_bots=report.options.exclude_bots)
            if report.older else None,
        ).encode("utf-8")

    def reference(self, first_visit_at: datetime | None = None) -> bytes:
        return self._templates.get_template("reference.html").render(
            refreshed_at=datetime.now(timezone.utc), active_page="reference", first_visit_at=first_visit_at,
        ).encode("utf-8")

    def marketing(self, report: Report, *, error: str | None = None,
                  fields: dict[str, list[str]] | None = None, saved: bool = False) -> bytes:
        return self._templates.get_template("marketing.html").render(
            active_page="marketing", platforms=DMarketing.PLATFORMS, posts=report.posts,
            error=error, fields=fields or {}, saved=saved, submission_id=uuid4().hex,
            posting_times=[{"posted_at": post["posted_at"].replace(tzinfo=timezone.utc).isoformat(),
                            "platform": post["platform"], "id": post["id"]} for post in report.posts],
            **self._report_context(report, "/marketing"),
        ).encode("utf-8")

    @staticmethod
    def _country_flag(code: str | None) -> str:
        code = (code or "").upper()
        if pycountry.countries.get(alpha_2=code) is None:
            return ""
        return "".join(chr(ord(character) - ord("A") + 0x1F1E6) for character in code)
