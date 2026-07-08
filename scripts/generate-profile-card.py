#!/usr/bin/env python3
"""Generate a terminal-session card SVG with live GitHub stats.

Runs in CI with GITHUB_TOKEN set; writes dist/profile-card-dark.svg
and dist/profile-card-light.svg.
"""
import datetime
import json
import os
import urllib.request
from xml.sax.saxutils import escape

TOKEN = os.environ["GITHUB_TOKEN"]
USER = "Bramvzw"
EMAIL = "bram@vanzwolle.net"
API = "https://api.github.com/graphql"


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
            repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC) {{
              totalCount
              nodes {{
                stargazerCount
                languages(first: 5) {{ edges {{ size node {{ name }} }} }}
              }}
            }}
            pullRequests(states: MERGED) {{ totalCount }}
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


def compute_streaks(days: list[tuple[datetime.date, int]]) -> tuple[int, int]:
    longest = run = 0
    previous_active: datetime.date | None = None
    for date, count in days:
        if count > 0:
            run = run + 1 if previous_active == date - datetime.timedelta(days=1) else 1
            previous_active = date
            longest = max(longest, run)
    # Current streak: walk backwards from today (today itself may still be 0).
    by_date = dict(days)
    cursor = datetime.date.today()
    if by_date.get(cursor, 0) == 0:
        cursor -= datetime.timedelta(days=1)
    current = 0
    while by_date.get(cursor, 0) > 0:
        current += 1
        cursor -= datetime.timedelta(days=1)
    return current, longest


def top_languages(repositories: list[dict], limit: int = 3) -> list[tuple[str, float]]:
    totals: dict[str, int] = {}
    for repository in repositories:
        for edge in repository["languages"]["edges"]:
            totals[edge["node"]["name"]] = totals.get(edge["node"]["name"], 0) + edge["size"]
    grand_total = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [(name, size / grand_total * 100) for name, size in ranked]


PALETTES = {
    "dark": {
        "background": "#0d1117",
        "border": "#30363d",
        "titlebar": "#161b22",
        "title_text": "#8b949e",
        "text": "#c9d1d9",
        "key": "#f97316",
        "accent": "#22c55e",
        "muted": "#8b949e",
        "banner": ["#39d353", "#33c94d", "#2dbf47", "#26a641", "#1f9a3c", "#188c36", "#117e30"],
    },
    "light": {
        "background": "#ffffff",
        "border": "#d0d7de",
        "titlebar": "#f6f8fa",
        "title_text": "#57606a",
        "text": "#24292f",
        "key": "#ea580c",
        "accent": "#16a34a",
        "muted": "#57606a",
        "banner": ["#216e39", "#25793e", "#298443", "#2d8f48", "#30a14e", "#3ab357", "#45c05f"],
    },
}

# Pixel wordmark "BRAM", rendered as rects so it stays crisp in every font environment.
BANNER_LETTERS = {
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
}
BANNER_WORD = "BRAM"

FONT = "SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
LEFT = 40


def render_pixel_banner(palette: dict, origin_x: int, origin_y: int, cell: int = 13) -> tuple[str, int]:
    rects = []
    column_offset = 0
    for letter in BANNER_WORD:
        rows = BANNER_LETTERS[letter]
        for row_index, row in enumerate(rows):
            for column_index, bit in enumerate(row):
                if bit == "#":
                    rects.append(
                        f'<rect x="{origin_x + (column_offset + column_index) * cell}" '
                        f'y="{origin_y + row_index * cell}" width="{cell - 2}" height="{cell - 2}" '
                        f'rx="2" fill="{palette["banner"][row_index]}" />'
                    )
        column_offset += len(rows[0]) + 2
    banner_height = len(BANNER_LETTERS[BANNER_WORD[0]]) * cell
    return "\n  ".join(rects), banner_height


def render_card(palette: dict, stats: dict) -> str:
    width = 860
    elements: list[str] = []
    y = 78

    def add_text(value: str, color: str, size: int = 15, x: int = LEFT, bold: bool = False) -> None:
        weight = ' font-weight="bold"' if bold else ""
        elements.append(
            f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}"{weight} '
            f'fill="{color}" xml:space="preserve">{escape(value)}</text>'
        )

    def add_prompt(command: str) -> None:
        elements.append(
            f'<text x="{LEFT}" y="{y}" font-family="{FONT}" font-size="15" fill="{palette["accent"]}" '
            f'xml:space="preserve">~ <tspan fill="{palette["text"]}">{escape(command)}</tspan></text>'
        )

    add_text(f"Last login: {stats['generated_at']} on ttys001", palette["muted"], size=13)
    y += 32

    add_prompt("figlet bram")
    y += 18
    banner_block, banner_height = render_pixel_banner(palette, LEFT, y)
    elements.append(banner_block)
    y += banner_height + 40

    add_prompt("neofetch")
    y += 28

    add_text(EMAIL, palette["accent"], bold=True)
    y += 25
    add_text("─" * 42, palette["muted"])
    y += 25

    info_lines: list[tuple[str, str]] = [
        ("OS", "PHP 8.4 · Laravel 12"),
        ("Role", "Full-stack developer & Product Owner"),
        ("Host", "Sibi — multi-tenant SaaS for healthcare"),
        ("Stack", "Livewire · Filament · Tailwind"),
        ("Side quest", "smart-home-hub"),
        ("Uptime", f"since {stats['since']}"),
        ("Contribs", f"{stats['contributions']:,} all-time"),
        ("Streak", f"{stats['current_streak']} days · longest {stats['longest_streak']}"),
        ("Repos", stats["repos_line"]),
        ("Langs", stats["languages"]),
    ]
    for key, value in info_lines:
        add_text(f"{key}:", palette["key"])
        add_text(value, palette["text"], x=LEFT + 130)
        y += 25
    y += 8

    elements.append(
        f'<text x="{LEFT}" y="{y}" font-family="{FONT}" font-size="15" fill="{palette["accent"]}">~ '
        f'<tspan fill="{palette["text"]}">█<animate attributeName="opacity" values="1;1;0;0" dur="1.2s" '
        f'repeatCount="indefinite" /></tspan></text>'
    )
    height = y + 34

    body = "\n  ".join(elements)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="12" fill="{palette["background"]}" stroke="{palette["border"]}" stroke-width="2" />
  <path d="M 1 45 H {width - 1}" stroke="{palette["border"]}" stroke-width="1" />
  <rect x="1" y="1" width="{width - 2}" height="44" rx="12" fill="{palette["titlebar"]}" />
  <rect x="1" y="30" width="{width - 2}" height="15" fill="{palette["titlebar"]}" />
  <circle cx="28" cy="23" r="7" fill="#ff5f56" />
  <circle cx="52" cy="23" r="7" fill="#ffbd2e" />
  <circle cx="76" cy="23" r="7" fill="#27c93f" />
  <text x="{width / 2}" y="28" text-anchor="middle" font-family="{FONT}" font-size="13" fill="{palette["title_text"]}">bram — zsh</text>
  {body}
</svg>
'''


def main() -> None:
    profile = fetch_profile()
    created_at = datetime.date.fromisoformat(profile["createdAt"][:10])
    contribution_days = fetch_contribution_days(created_at)
    current_streak, longest_streak = compute_streaks(contribution_days)
    languages = top_languages(profile["repositories"]["nodes"])

    stats = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%a %b %d %H:%M:%S UTC"),
        "since": created_at.strftime("%b %Y"),
        "contributions": sum(count for _, count in contribution_days),
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "repos": profile["repositories"]["totalCount"],
        "stars": sum(repo["stargazerCount"] for repo in profile["repositories"]["nodes"]),
        "merged_prs": profile["pullRequests"]["totalCount"],
        "languages": " · ".join(f"{name} {percentage:.0f}%" for name, percentage in languages),
    }
    star_part = f" · {stats['stars']} stars" if stats["stars"] > 0 else ""
    stats["repos_line"] = f"{stats['repos']} public{star_part} · {stats['merged_prs']} merged PRs"
    print("stats:", json.dumps(stats, indent=2))

    os.makedirs("dist", exist_ok=True)
    for theme, palette in PALETTES.items():
        path = f"dist/profile-card-{theme}.svg"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(render_card(palette, stats))
        print("wrote", path)


if __name__ == "__main__":
    main()
