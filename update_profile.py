"""Regenerate dark_mode.svg / light_mode.svg with live GitHub stats.

Runs daily via GitHub Actions. Stdlib only, no dependencies.
Adapted from github.com/DietrichGebert/DietrichGebert (neofetch-style profile).
"""
import calendar
import html
import json
import os
import urllib.request
from datetime import date, datetime, timezone

USER = "yslee4601"
BIRTHDAY = date(2001, 4, 6)
JOINED_YEAR = 2024  # account creation year, never changes
W = 56  # info column width in characters

ART = r"""
                =--:-+++===
             =---::--==+======+*
           -:--=--==--=+**++====*###***
          ==*+=+=+++++**####*++==*##****
         +=*****##*#%#######**++=+####***
        +-=++*##%@%#%@@%###**+++==+####**
        =:=*#*##%@@%#%%%##****+=+==*####*+
        -:-+***##%%%#*#%%##***+====+*###*+
        -::-==+##%%##**%%@@%#*++=*=+**#**+
         :=+**##@@@@%##%@@@@%*+*%*=+***+++
         -=#%%%%@@@@@@@@@@@@%*=**-=+++*+=
        --:+%%%#@@@@@@@@@@@%#*-=:----++==
        ::::+%%**#%@@@@@@@%##+=+===-----=
       -:::-:=++++**#%@@%%%#****+++++=====
       -:::-:::--==++#%%%#**#%%*+++++++++++++++
       -::::::::=*#%%%%*+*#%%%%*+++++++++++++++
       -::::::::::-=---=*#%%%%#++++++++++++++++
       -:::::::::::::::-+**###+++++++++++++++++
      ---::::::::::::-=-==+*#*=++++++++=+++++++
       --::::::::::::-===****+=++++++===+++++++
        --::::::::::::::-=+=++==========+===+++
        --::::::::::::::::----:---==========+++
    --- ----::::::::::::::::-::-===============
     ---------::::::::::::::--:::-===--:-----==
    -----------::::::::::::::-=::::-==--:::::-=
   ------------:::::::::::::::--:::::------:::-
   -------- ----:::::::::::::::=-::::::::--::::
    ------- --:::::::::::::::::----:::::::-::::
"""

# two tokens by design: the Actions GITHUB_TOKEN yields the contribution-style
# commit count (public + private activity), while a PAT (ACCESS_TOKEN secret)
# sees private repos for the repo list and LOC walk. Either falls back to the other.
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("ACCESS_TOKEN") or ""
PRIV_TOKEN = os.environ.get("ACCESS_TOKEN") or TOKEN


def gh(url, payload=None, token=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload else None,
        headers={"Authorization": f"Bearer {token or TOKEN}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read() or "{}")


def graphql(query, variables=None, token=None):
    _, resp = gh("https://api.github.com/graphql", {"query": query, "variables": variables or {}}, token)
    if resp.get("errors"):
        raise RuntimeError(resp["errors"])
    return resp["data"]


def age(b, t):
    years = t.year - b.year - ((t.month, t.day) < (b.month, b.day))
    months = (t.month - b.month - (t.day < b.day)) % 12
    if t.day >= b.day:
        days = t.day - b.day
    else:
        pm_year, pm = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
        days = calendar.monthrange(pm_year, pm)[1] - b.day + t.day
    return years, months, days


def fetch_stats():
    yr_aliases = "\n".join(
        f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y + 1}-01-01T00:00:00Z")'
        " { totalCommitContributions restrictedContributionsCount }"
        for y in range(JOINED_YEAR, datetime.now(timezone.utc).year + 1)
    )
    contrib = graphql(f'query {{ user(login: "{USER}") {{ {yr_aliases} }} }}')["user"]
    commits = sum(
        v["totalCommitContributions"] + v["restrictedContributionsCount"]
        for v in contrib.values()
    )
    u = graphql(f"""
    query {{
      user(login: "{USER}") {{
        id
        followers {{ totalCount }}
        repositories(first: 100, ownerAffiliations: OWNER) {{
          totalCount
          nodes {{ name stargazerCount isFork }}
        }}
        repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) {{
          totalCount
        }}
      }}
    }}""", token=PRIV_TOKEN)["user"]
    stats = {
        "followers": u["followers"]["totalCount"],
        "repos": u["repositories"]["totalCount"],
        "contributed": u["repositoriesContributedTo"]["totalCount"],
        "stars": sum(n["stargazerCount"] for n in u["repositories"]["nodes"]),
        "commits": commits,
    }
    stats.update(loc([n["name"] for n in u["repositories"]["nodes"] if not n["isFork"]], u["id"]))
    return stats


LOC_QUERY = """
query($owner: String!, $name: String!, $id: ID!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { target { ... on Commit {
      history(first: 100, author: {id: $id}, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { additions deletions }
      }
    } } }
  }
}"""


def loc(repo_names, user_id):
    # ponytail: REST stats/contributors answers 202 forever to the Actions token,
    # so walk own commits on the default branch via GraphQL instead
    add = rem = 0
    for name in repo_names:
        cursor = None
        try:
            while True:
                ref = graphql(LOC_QUERY, {"owner": USER, "name": name, "id": user_id, "cursor": cursor}, token=PRIV_TOKEN)["repository"]["defaultBranchRef"]
                if ref is None:
                    break  # empty repo
                h = ref["target"]["history"]
                add += sum(n["additions"] for n in h["nodes"])
                rem += sum(n["deletions"] for n in h["nodes"])
                if not h["pageInfo"]["hasNextPage"]:
                    break
                cursor = h["pageInfo"]["endCursor"]
        except Exception as e:
            print(f"loc {name}: {e}")
    return {"loc_add": add, "loc_del": rem, "loc": add - rem}


PALETTES = {
    "dark": {"bg": "#0d1117", "border": "#30363d", "art": "#8b949e", "h": "#58a6ff",
             "k": "#ffa657", "v": "#c9d1d9", "d": "#484f58", "g": "#3fb950", "r": "#f85149"},
    "light": {"bg": "#ffffff", "border": "#d0d7de", "art": "#57606a", "h": "#0969da",
              "k": "#953800", "v": "#24292f", "d": "#afb8c1", "g": "#1a7f37", "r": "#cf222e"},
}


def kv(key, val, width=W):
    dots = "." * max(width - len(key) - len(str(val)) - 3, 1)
    return [(f"{key}: ", "k"), (dots + " ", "d"), (str(val), "v")]


def kv2(k1, v1, k2, v2):
    left = kv(k1, v1, 30)
    return left + [(" | ", "d")] + kv(k2, v2, 23)


def rule(title=""):
    label = f"─ {title} " if title else ""
    return [(label, "h"), ("─" * (W - len(label)), "d")]


def info_lines(s):
    n = lambda x: f"{x:,}"
    uptime = []
    if BIRTHDAY:
        y, m, d = age(BIRTHDAY, date.today())
        uptime = [kv("Uptime", f"{y} years, {m} months, {d} days")]
    return [
        [(f"{USER.lower()}@github ", "h"), ("─" * (W - len(USER) - 8), "d")],
        [],
        kv("OS", "Windows, Linux (Ubuntu)"),
        *uptime,
        kv("Host", "Shinhan DS"),
        kv("Major", "Financial Engineering + CS (double)"),
        kv("Kernel", "Backend Developer (Java/Spring)"),
        kv("IDE", "IntelliJ, VS Code, Claude Code"),
        [],
        kv("Languages", "Java, SQL, Python, TypeScript, JS"),
        kv("Backend", "Spring Boot/MVC/Batch/Security, MyBatis, JPA"),
        kv("Database", "PostgreSQL, Flyway, ERD/Schema Design"),
        kv("Frontend", "Thymeleaf, JSP, JS/CSS, React + TS"),
        kv("Testing", "JUnit 5, Testcontainers, Integration Tests"),
        kv("DevOps", "Git/GitHub, GitHub Actions, Docker, K8s"),
        kv("Domain", "Finance, Fee Settlement, Batch Processing"),
        kv("Data", "Pandas, scikit-learn, Matplotlib"),
        kv("Languages.Real", "Korean, English"),
        kv("Hobbies", "Drawing, Leg Day"),
        [],
        rule("Contact"),
        kv("Email", "leeyeso9072@gmail.com"),
        [],
        rule("GitHub Stats"),
        kv2("Repos", f"{s['repos']} {{Contributed: {s['contributed']}}}", "Stars", n(s["stars"])),
        kv2("Commits", n(s["commits"]), "Followers", n(s["followers"])),
        [("Lines of Code: ", "k"), (n(s["loc"]), "v"), (" ( ", "d"),
         (n(s["loc_add"]) + "++", "g"), (", ", "d"), (n(s["loc_del"]) + "--", "r"), (" )", "d")],
    ]


def render(mode, stats):
    p = PALETTES[mode]
    art = ART.strip("\n").split("\n")
    lines = info_lines(stats)
    height = max(40 + len(art) * 15, 45 + (len(lines) - 1) * 21) + 30
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="840" height="{height}" viewBox="0 0 840 {height}" '
        'font-family="Consolas, Menlo, monospace" font-size="13px">',
        f'<rect x="0.5" y="0.5" width="839" height="{height - 1}" rx="10" fill="{p["bg"]}" stroke="{p["border"]}"/>',
    ]
    for i, line in enumerate(art):
        out.append(f'<text x="25" y="{40 + i * 15}" fill="{p["art"]}" xml:space="preserve">{html.escape(line)}</text>')
    for i, segs in enumerate(lines):
        if not segs:
            continue
        spans = "".join(f'<tspan fill="{p[c]}">{html.escape(t)}</tspan>' for t, c in segs)
        out.append(f'<text x="390" y="{45 + i * 21}" xml:space="preserve">{spans}</text>')
    out.append("</svg>")
    return "\n".join(out)


def selfcheck():
    assert age(date(1989, 1, 15), date(2026, 7, 10)) == (37, 5, 25)
    assert age(date(2000, 3, 31), date(2026, 4, 1)) == (26, 0, 1)
    assert age(date(2000, 1, 1), date(2026, 1, 1)) == (26, 0, 0)
    assert len("".join(t for t, _ in kv("OS", "Windows"))) == W
    for segs in info_lines({"repos": 0, "contributed": 0, "stars": 0, "commits": 0, "followers": 0, "loc": 0, "loc_add": 0, "loc_del": 0}):
        assert len("".join(t for t, _ in segs)) <= W, "info line too long: " + "".join(t for t, _ in segs)
    assert max(len(l) for l in ART.split("\n")) <= 50, "art too wide for the left column"


if __name__ == "__main__":
    selfcheck()
    stats = fetch_stats()
    print("stats:", stats)
    for mode in PALETTES:
        with open(f"{mode}_mode.svg", "w", encoding="utf-8") as f:
            f.write(render(mode, stats))
    print("wrote dark_mode.svg, light_mode.svg")
