"""Offline behaviour: a failed lore/art lookup must not retry in a loop (it used to hammer the network)."""
from harness import *

app = new_app()
calls = []
def failing(game, wiki_title, system): calls.append(game); raise RuntimeError("offline")
a.fetch_all = failing
app.show_tab("ARCHIVE"); pump(app, 3)
fa = "Armored Core: For Answer"; app.lore_tree.selection_set(fa)
for _ in range(25): pump(app, 2)
check("only one lookup per title while offline", calls.count(fa) == 1, str(calls))
for _ in range(4): app.lore_tree.selection_set("__overview"); pump(app, 2); app.lore_tree.selection_set(fa); pump(app, 3)
check("re-selecting the game does not hammer the network", calls.count(fa) == 1, str(calls.count(fa)))
check("the archive explains it could not load", "Could not load" in app.lore_text.get("1.0", "end"))
app.wiki_try[fa] = 0; app.lore_tree.selection_set("__overview"); pump(app, 2); app.lore_tree.selection_set(fa); pump(app, 6)
check("it retries once the cooldown has passed", calls.count(fa) == 2, str(calls.count(fa)))
a.fetch_all = lambda g, w, s: {"extract": "Hello world", "url": "", "img": None, "extra": []}
app.wiki_try[fa] = 0; app.lore_tree.selection_set("__overview"); pump(app, 2); app.lore_tree.selection_set(fa)
for _ in range(10): pump(app, 2)
check("it recovers when the internet returns", "Hello world" in app.lore_text.get("1.0", "end"))
finish(app)
