"""RetroAchievements tab (with simulated API data) and library features: filters, search, sort, favorites, menu."""
import types
from harness import *
from PIL import Image

app = new_app()
lib = lambda: app.cfg["library"]
key_for = lambda title: next(k for k, e in lib().items() if e["title"] == title)

app.show_tab("ACHIEVEMENTS"); pump(app, 3)
check("achievements tab asks for your credentials", "Enter your RetroAchievements" in app.ra_status.cget("text"))
badge = pathlib.Path(HOME) / "badge.png"; Image.new("RGB", (64, 64), (200, 60, 20)).save(badge)
app.cfg["ra"] = {"user": "tester", "key": "K"}
app.on_ra("boot", ({"User": "tester", "TotalPoints": 1234, "TotalTruePoints": 2345, "MemberSince": "2020-01-02 00:00:00"},
                   [{"id": 101, "title": "Armored Core", "console": "PS1", "ach": 3, "lb": 1, "pts": 100},
                    {"id": 201, "title": "Armored Core 2", "console": "PS2", "ach": 2, "lb": 0, "pts": 50}]), None); pump(app, 3)
check("game sets are listed", len(app.ra_games_tree.get_children()) == 2)
app.ra_cur = 101
app.on_ra("game", {"id": 101, "title": "Armored Core",
                   "ach": [{"ID": 1, "Title": "First Blood", "Description": "Destroy 10 targets", "Points": 5, "BadgeName": "001", "DisplayOrder": 1, "DateEarned": "2024-01-02 03:04:05"},
                           {"ID": 2, "Title": "Collector", "Description": "Buy every part", "Points": 25, "BadgeName": "002", "DisplayOrder": 2}],
                   "lb": [{"ID": 9, "Title": "Arena Time Trial", "Description": "Fastest clear", "TopEntry": {"User": "ace", "FormattedScore": "1:02.55"}}],
                   "earned": 1, "total": 2, "pts_earned": 5, "pts_total": 30}, None); pump(app, 3)
check("achievements and leaderboards are listed", len(app.ra_ach.get_children()) == 2 and len(app.ra_lb.get_children()) == 1)
app.on_ra("badge", ("1", str(badge)), None); pump(app, 2)
check("badge images are applied", bool(app.ra_ach.item("1", "image")))
shot("achievements"); app.ra_set_view("lb"); pump(app, 2); shot("leaderboards")
app.on_ra("entries", {"title": "Arena Time Trial", "rows": [{"Rank": 1, "User": "ace", "Score": 62550, "FormattedScore": "1:02.55", "DateSubmitted": "2024-05-01T00:00:00Z"}]}, None); pump(app, 2)
check("leaderboard entries window opens", bool(toplevels(app))); close_all(app)
app.on_ra("boot", None, "RetroAchievements answered HTTP 401: check your username and Web API key"); pump(app, 1)
check("a wrong key shows a clear error", "Could not connect" in app.ra_status.cget("text"))
app.ra_disconnect(); check("disconnect removes the saved key", "ra" not in app.cfg)
app.show_tab("LIBRARY"); pump(app, 2)

for _ in range(4): app.cycle_sort()
check("sort button cycles back to release order", app.cfg["sort"] == "RELEASE")
app.set_filter("PS3"); pump(app, 2); check("PS3 filter", len(app.tree.get_children()) == 2)
app.set_filter("FAV"); pump(app, 2); check("favorites filter", len(app.tree.get_children()) == 1)
app.set_filter("ALL"); app.q.set("nexus"); pump(app, 2); check("search", len(app.tree.get_children()) == 1); app.q.set(""); pump(app, 1)
fa = key_for("Armored Core: For Answer"); app.tree.selection_set(fa); pump(app, 2)
app.toggle_fav(); check("favorite toggles on", lib()[fa].get("fav") is True); app.toggle_fav(); check("and off", not lib()[fa].get("fav"))
app.tree_menu(types.SimpleNamespace(y=app.tree.bbox(fa)[1] + 5, x_root=10, y_root=10)); check("right-click menu builds", not ERR)
finish(app)
