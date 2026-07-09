#!/usr/bin/env python3
"""Generate a terminal-session card SVG with live GitHub stats.

Runs in CI with GITHUB_TOKEN set; writes dist/intro-{theme}.svg and
dist/profile-card-{theme}.svg. The look follows the "Terminal Profile"
design: blue-accent zsh window, JetBrains Mono, ANSI figlet banner and
right-aligned dotted-leader rows.
"""
import datetime
import json
import os
import urllib.request
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Europe/Amsterdam")

# PROFILE_TOKEN is a personal access token so private activity is counted too;
# without it the default Actions token sees public data only.
TOKEN = os.environ.get("PROFILE_TOKEN") or os.environ["GITHUB_TOKEN"]
USER = "Bramvzw"
EMAIL = "bram@vanzwolle.net"
API = "https://api.github.com/graphql"

FONT = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"


def graphql(query: str) -> dict:
    request = urllib.request.Request(
        API,
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        payload = json.loads(response.read())
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]


def fetch_profile() -> dict:
    return graphql(
        f'''
        query {{
          user(login: "{USER}") {{
            createdAt
          }}
        }}
        '''
    )["user"]


def fetch_contribution_days(created_at: datetime.date) -> list[tuple[datetime.date, int]]:
    days: list[tuple[datetime.date, int]] = []
    today = datetime.date.today()
    year_start = created_at
    while year_start <= today:
        year_end = min(year_start + datetime.timedelta(days=364), today)
        data = graphql(
            f'''
            query {{
              user(login: "{USER}") {{
                contributionsCollection(
                  from: "{year_start.isoformat()}T00:00:00Z",
                  to: "{year_end.isoformat()}T23:59:59Z"
                ) {{
                  contributionCalendar {{
                    weeks {{ contributionDays {{ date contributionCount }} }}
                  }}
                }}
              }}
            }}
            '''
        )
        weeks = data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        for week in weeks:
            for day in week["contributionDays"]:
                date = datetime.date.fromisoformat(day["date"])
                if year_start <= date <= year_end:
                    days.append((date, day["contributionCount"]))
        year_start = year_end + datetime.timedelta(days=1)
    days.sort()
    return days


def compute_streak(days: list[tuple[datetime.date, int]]) -> int:
    by_date = dict(days)
    cursor = datetime.date.today()
    if by_date.get(cursor, 0) == 0:
        cursor -= datetime.timedelta(days=1)
    current = 0
    while by_date.get(cursor, 0) > 0:
        current += 1
        cursor -= datetime.timedelta(days=1)
    return current


# Terminal window palette (always dark — a terminal is dark regardless of the
# page it sits on). Variable names mirror the source design.
TERM = {
    "term_top": "#0d1117",
    "term_bottom": "#0b0f15",
    "bar": "#161b22",
    "bar_line": "#20262e",
    "ink": "#cdd3dc",
    "ink_soft": "#aab1bd",
    "dim": "#5b6673",
    "dots": "#2b333d",
    "accent": "#4090ff",
    "accent_br": "#64a7ff",
    "amber": "#e3a44a",
    "rule": "#222932",
    "light_r": "#ff5f57",
    "light_y": "#febc2e",
    "light_g": "#28c840",
}

# Intro sits on a transparent background, so its text must adapt to the page.
INTRO_PALETTES = {
    "dark": {"text": "#cdd3dc", "accent": "#64a7ff", "dim": "#5b6673"},
    "light": {"text": "#24292f", "accent": "#2f6fed", "dim": "#57606a"},
}

FIGLET = [
    "██████╗ ██████╗  █████╗ ███╗   ███╗██╗   ██╗███████╗██╗    ██╗",
    "██╔══██╗██╔══██╗██╔══██╗████╗ ████║██║   ██║╚══███╔╝██║    ██║",
    "██████╔╝██████╔╝███████║██╔████╔██║██║   ██║  ███╔╝ ██║ █╗ ██║",
    "██╔══██╗██╔══██╗██╔══██║██║╚██╔╝██║╚██╗ ██╔╝ ███╔╝  ██║███╗██║",
    "██████╔╝██║  ██║██║  ██║██║ ╚═╝ ██║ ╚████╔╝ ███████╗╚███╔███╔╝",
    "╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═══╝  ╚══════╝ ╚══╝╚══╝ ",
]

WIDTH = 760
PAD = 24
SIZE = 13
CW = SIZE * 0.6  # monospace advance width


def render_intro(palette: dict) -> str:
    height = 104
    center = WIDTH / 2

    def span(text: str, color: str) -> str:
        return f'<tspan fill="{color}">{escape(text)}</tspan>'

    def line(y: int, size: int, bold: bool, spans: list[str]) -> str:
        weight = ' font-weight="700"' if bold else ""
        return (
            f'<text x="{center}" y="{y}" text-anchor="middle" font-family="{FONT}" '
            f'font-size="{size}"{weight} xml:space="preserve">{"".join(spans)}</text>'
        )

    lines = [
        line(30, 15, True, [span("Full-stack developer & Product Owner building", palette["text"])]),
        line(54, 15, True, [
            span("multi-tenant healthcare SaaS", palette["accent"]),
            span(" at Sibi.", palette["text"]),
        ]),
        line(88, 13, False, [
            span("I care about clean architecture, static analysis and shipping.", palette["dim"]),
        ]),
    ]
    body = "\n  ".join(lines)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}">\n  {body}\n</svg>\n'
    )


def render_card(stats: dict) -> str:
    elements: list[str] = []
    right = WIDTH - PAD
    y = 0

    def add_text(value: str, color: str, size: int = SIZE, x: int = PAD, bold: bool = False) -> None:
        weight = ' font-weight="700"' if bold else ""
        elements.append(
            f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}"{weight} '
            f'fill="{color}" xml:space="preserve">{escape(value)}</text>'
        )

    def add_cmd(command: str) -> None:
        elements.append(
            f'<text x="{PAD}" y="{y}" font-family="{FONT}" font-size="{SIZE}" xml:space="preserve">'
            f'<tspan fill="{TERM["accent"]}" font-weight="700">~ </tspan>'
            f'<tspan fill="{TERM["ink"]}">{escape(command)}</tspan></text>'
        )

    def add_row(key: str, key_color: str, segments: list[tuple[str, str]]) -> None:
        elements.append(
            f'<text x="{PAD}" y="{y}" font-family="{FONT}" font-size="{SIZE}" '
            f'font-weight="500" fill="{key_color}" xml:space="preserve">{escape(key)}</text>'
        )
        tspans = "".join(f'<tspan fill="{color}">{escape(text)}</tspan>' for text, color in segments)
        elements.append(
            f'<text x="{right}" y="{y}" text-anchor="end" font-family="{FONT}" '
            f'font-size="{SIZE}" fill="{TERM["ink"]}" xml:space="preserve">{tspans}</text>'
        )
        value_len = sum(len(text) for text, _ in segments)
        x1 = PAD + len(key) * CW + 10
        x2 = right - value_len * CW - 10
        if x2 > x1 + 8:
            elements.append(
                f'<line x1="{x1:.0f}" y1="{y - 4}" x2="{x2:.0f}" y2="{y - 4}" '
                f'stroke="{TERM["dots"]}" stroke-width="2" stroke-dasharray="1 4" stroke-linecap="round" />'
            )

    sep = ("·", TERM["dim"])

    def joined(parts: list[str], accent_arrow: bool = False) -> list[tuple[str, str]]:
        segments: list[tuple[str, str]] = []
        for index, part in enumerate(parts):
            if index:
                segments.append((" ", TERM["ink"]))
                segments.append(sep)
                segments.append((" ", TERM["ink"]))
            segments.append((part, TERM["ink"]))
        return segments

    y = 62
    add_text(f"Last login: {stats['generated_at']} on ttys001", TERM["dim"], size=12)

    y += 26
    add_cmd("figlet bramvzw")
    y += 20
    for index, line in enumerate(FIGLET):
        elements.append(
            f'<text x="{PAD}" y="{y + index * 11}" font-family="{FONT}" font-size="12" '
            f'fill="{TERM["accent_br"]}" filter="url(#glow)" xml:space="preserve">{escape(line)}</text>'
        )
    y += len(FIGLET) * 11 + 18

    add_cmd("neofetch")
    y += 20
    add_text("bram@vanzwolle", TERM["accent_br"], bold=True)
    y += 12
    elements.append(
        f'<line x1="{PAD}" y1="{y}" x2="{right}" y2="{y}" stroke="{TERM["rule"]}" stroke-width="1" />'
    )
    y += 18

    add_row("Role", TERM["amber"], [("Full-stack Developer & Product Owner", TERM["ink"])])
    y += 19
    add_row("Company", TERM["amber"], joined(["Sibi", "Healthcare SaaS"]))
    y += 19
    add_row("Platform", TERM["amber"], joined(["Multi-tenant", "isolated DB per tenant"]))
    y += 19
    add_row("Languages", TERM["amber"], joined(["PHP", "Rust", "TypeScript", "JavaScript", "Python", "C#"]))
    y += 19
    add_row("Backend", TERM["amber"], joined(["Laravel 12", "MySQL", "Redis", "Horizon", "Scout"]))
    y += 19
    add_row("Frontend", TERM["amber"], joined(["Livewire", "Filament", "Alpine", "Tailwind"]))
    y += 19
    add_row("Tooling", TERM["amber"], joined(["Docker", "PHPUnit", "PHPStan", "Pint", "GitHub Actions"]))
    y += 28

    add_cmd("ls ~/projects")
    y += 20
    add_row("sooth", TERM["accent"], joined(["Rust CLI", "flaky-test detector", "no AI, no keys"]))
    y += 19
    add_row("smart-home-hub", TERM["accent"], joined(["Laravel", "modular self-hosted dashboard"]))
    y += 28

    add_cmd("uptime")
    y += 20
    elements.append(
        f'<text x="{PAD}" y="{y}" font-family="{FONT}" font-size="{SIZE}" '
        f'fill="{TERM["ink_soft"]}" xml:space="preserve">'
        f'active since {escape(stats["since"])} '
        f'<tspan fill="{TERM["dim"]}">·</tspan> '
        f'<tspan fill="{TERM["accent"]}">{stats["contributions"]:,}</tspan> contributions '
        f'<tspan fill="{TERM["dim"]}">·</tspan> '
        f'{stats["current_streak"]}-day streak</text>'
    )
    y += 28

    add_cmd("cat contact.txt")
    y += 20
    add_row("web", TERM["amber"], [("bramvzw.nl", TERM["accent"])])
    y += 19
    add_row("email", TERM["amber"], [(EMAIL, TERM["accent"])])
    y += 19
    add_row("linkedin", TERM["amber"], [("in/bram-van-zwolle-239ba7198", TERM["accent"])])
    y += 26

    elements.append(
        f'<text x="{PAD}" y="{y}" font-family="{FONT}" font-size="{SIZE}" fill="{TERM["accent"]}" '
        f'font-weight="700">~ <tspan fill="{TERM["ink"]}">█<animate attributeName="opacity" '
        f'values="1;1;0;0" dur="1.05s" repeatCount="indefinite" /></tspan></text>'
    )
    height = y + 20

    body = "\n  ".join(elements)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}">
  <defs>
    <linearGradient id="term" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{TERM["term_top"]}" />
      <stop offset="1" stop-color="{TERM["term_bottom"]}" />
    </linearGradient>
    <filter id="glow" x="-10%" y="-40%" width="120%" height="180%">
      <feGaussianBlur stdDeviation="1.3" result="blur" />
      <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
    </filter>
  </defs>
  <rect x="1" y="1" width="{WIDTH - 2}" height="{height - 2}" rx="12" fill="url(#term)" stroke="{TERM["bar_line"]}" stroke-width="1" />
  <rect x="1" y="1" width="{WIDTH - 2}" height="38" rx="12" fill="{TERM["bar"]}" />
  <rect x="1" y="25" width="{WIDTH - 2}" height="13" fill="{TERM["bar"]}" />
  <line x1="1" y1="38" x2="{WIDTH - 1}" y2="38" stroke="{TERM["bar_line"]}" stroke-width="1" />
  <circle cx="24" cy="19" r="6" fill="{TERM["light_r"]}" />
  <circle cx="44" cy="19" r="6" fill="{TERM["light_y"]}" />
  <circle cx="64" cy="19" r="6" fill="{TERM["light_g"]}" />
  <text x="{WIDTH / 2}" y="23" text-anchor="middle" font-family="{FONT}" font-size="12" fill="{TERM["dim"]}">bram — zsh</text>
  {body}
</svg>
'''


def main() -> None:
    profile = fetch_profile()
    created_at = datetime.date.fromisoformat(profile["createdAt"][:10])
    contribution_days = fetch_contribution_days(created_at)

    stats = {
        "generated_at": datetime.datetime.now(TIMEZONE).strftime("%a %b %d %H:%M:%S %Z"),
        "since": created_at.strftime("%b %Y"),
        "contributions": sum(count for _, count in contribution_days),
        "current_streak": compute_streak(contribution_days),
    }
    print("stats:", json.dumps(stats, indent=2))

    os.makedirs("dist", exist_ok=True)
    card = render_card(stats)
    for theme in ("dark", "light"):
        for name, svg in (
            (f"intro-{theme}.svg", render_intro(INTRO_PALETTES[theme])),
            (f"profile-card-{theme}.svg", card),
        ):
            path = f"dist/{name}"
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(svg)
            print("wrote", path)


if __name__ == "__main__":
    main()
