#!/usr/bin/env python3
"""Generate a neofetch-style terminal card SVG with live GitHub stats.

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
        "pixels": ["#0e4429", "#006d32", "#26a641", "#39d353"],
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
        "pixels": ["#9be9a8", "#40c463", "#30a14e", "#216e39"],
    },
}

EMAIL = "bramvanzwolle@sibi.nl"

SNAKE_FILES = {
    "dark": "dist/github-contribution-grid-snake-dark.svg",
    "light": "dist/github-contribution-grid-snake.svg",
}

PIXEL_B = [
    "111110",
    "100011",
    "100011",
    "111110",
    "100011",
    "100011",
    "111110",
]

FONT = "SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"


def render_pixel_avatar(palette: dict, origin_x: int, origin_y: int, cell: int = 24) -> str:
    rects = []
    for row_index, row in enumerate(PIXEL_B):
        for column_index, bit in enumerate(row):
            if bit == "1":
                color = palette["pixels"][(row_index + column_index) % len(palette["pixels"])]
                rects.append(
                    f'<rect x="{origin_x + column_index * cell}" y="{origin_y + row_index * cell}" '
                    f'width="{cell - 3}" height="{cell - 3}" rx="4" fill="{color}" />'
                )
    return "\n    ".join(rects)


def embed_snake(svg_path: str, x: int, y: int, target_width: int) -> tuple[str, int]:
    with open(svg_path, encoding="utf-8") as handle:
        content = handle.read()
    native_width, native_height = 880, 192
    target_height = round(native_height * target_width / native_width)
    content = content.replace(
        'width="880" height="192"',
        f'x="{x}" y="{y}" width="{target_width}" height="{target_height}"',
        1,
    )
    return content, target_height


def render_card(palette: dict, stats: dict, snake_path: str) -> str:
    width = 860
    info_x = 300
    line_height = 25
    lines: list[tuple[str, str, str]] = [
        ("", EMAIL, "accent"),
        ("", "─" * 34, "muted"),
        ("OS", "PHP 8.4 · Laravel 12", "text"),
        ("Role", "Full-stack developer & Product Owner", "text"),
        ("Host", "Sibi — multi-tenant SaaS for healthcare", "text"),
        ("Stack", "Livewire · Filament · Tailwind", "text"),
        ("Side quest", "smart-home-hub", "text"),
        ("Uptime", f"since {stats['since']}", "text"),
        ("", "─" * 34, "muted"),
        ("Contribs", f"{stats['contributions']:,} all-time", "text"),
        ("Streak", f"{stats['current_streak']} days · longest {stats['longest_streak']}", "text"),
        ("Repos", stats["repos_line"], "text"),
        ("Langs", stats["languages"], "text"),
    ]

    text_elements = []
    y = 96
    for key, value, tone in lines:
        if key:
            text_elements.append(
                f'<text x="{info_x}" y="{y}" font-family="{FONT}" font-size="15" '
                f'fill="{palette["key"]}">{escape(key)}:</text>'
            )
            value_x = info_x + 118
        else:
            value_x = info_x
        weight = ' font-weight="bold"' if value == EMAIL else ""
        text_elements.append(
            f'<text x="{value_x}" y="{y}" font-family="{FONT}" font-size="15"{weight} '
            f'fill="{palette[tone]}">{escape(value)}</text>'
        )
        y += line_height

    snake_prompt_y = y + 8
    snake_x, snake_width = 40, width - 80
    snake_y = snake_prompt_y + 14
    snake_block, snake_height = embed_snake(snake_path, snake_x, snake_y, snake_width)
    prompt_y = snake_y + snake_height + 30
    height = prompt_y + 34
    info_column_bottom = snake_prompt_y
    avatar_height = len(PIXEL_B) * 24
    avatar_y = 45 + (info_column_bottom - 45 - avatar_height) // 2
    info_block = "\n  ".join(text_elements)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="12" fill="{palette["background"]}" stroke="{palette["border"]}" stroke-width="2" />
  <path d="M 1 45 H {width - 1}" stroke="{palette["border"]}" stroke-width="1" />
  <rect x="1" y="1" width="{width - 2}" height="44" rx="12" fill="{palette["titlebar"]}" />
  <rect x="1" y="30" width="{width - 2}" height="15" fill="{palette["titlebar"]}" />
  <circle cx="28" cy="23" r="7" fill="#ff5f56" />
  <circle cx="52" cy="23" r="7" fill="#ffbd2e" />
  <circle cx="76" cy="23" r="7" fill="#27c93f" />
  <text x="{width / 2}" y="28" text-anchor="middle" font-family="{FONT}" font-size="13" fill="{palette["title_text"]}">bram — zsh</text>
  <g>
    {render_pixel_avatar(palette, 68, avatar_y)}
  </g>
  {info_block}
  <text x="{snake_x}" y="{snake_prompt_y}" font-family="{FONT}" font-size="15" fill="{palette["accent"]}">~ <tspan fill="{palette["text"]}">./snake --contributions</tspan></text>
  {snake_block}
  <text x="{snake_x}" y="{prompt_y}" font-family="{FONT}" font-size="15" fill="{palette["accent"]}">~ <tspan fill="{palette["text"]}">█<animate attributeName="opacity" values="1;1;0;0" dur="1.2s" repeatCount="indefinite" /></tspan></text>
</svg>
'''


def main() -> None:
    profile = fetch_profile()
    created_at = datetime.date.fromisoformat(profile["createdAt"][:10])
    contribution_days = fetch_contribution_days(created_at)
    current_streak, longest_streak = compute_streaks(contribution_days)
    languages = top_languages(profile["repositories"]["nodes"])

    stats = {
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
            handle.write(render_card(palette, stats, SNAKE_FILES[theme]))
        print("wrote", path)


if __name__ == "__main__":
    main()
