"""The audio player's logic, driven with a fake audio engine (the real one is Windows' MCI)."""
from harness import *


class FakeMci:
    def __init__(s): s.is_open = False; s.m = "stopped"; s.p = 0; s.L = 200000; s.vol = None
    def load(s, path):
        if path.endswith(".bad"): raise RuntimeError("Unsupported format")
        s.is_open = True; s.m = "stopped"; s.p = 0
    def play(s): s.m = "playing"
    def pause(s): s.m = "paused"
    def resume(s): s.m = "playing"
    def stop(s): s.m = "stopped"; s.p = 0
    def seek(s, ms): s.p = int(ms); s.m = "playing"
    def mode(s): return s.m
    def length(s): return s.L
    def pos(s): return s.p
    def volume(s, v): s.vol = v
    def close(s): s.is_open = False


a.AUDIO_OK = True; a.McPlayer = FakeMci
app = new_app()
check("music tab UI is built", hasattr(app, "btn_play") and hasattr(app, "music_tree"))
src = pathlib.Path(HOME) / "src"; src.mkdir()
files = []
for n in ("a.mp3", "b.wav", "c.mp3", "bad.bad", "notes.txt"):
    f = src / n; f.write_text("x" * 10); files.append(str(f))
app.copy_var.set(True); app.music_add(files)
check("only audio files are added", [pathlib.Path(x).name for x in app.music] == ["a.mp3", "b.wav", "c.mp3"], str(app.music))
check("files are copied into the launcher's library", all(str(a.MUSIC_DIR) in x for x in app.music))
app.show_tab("MUSIC"); pump(app, 3)
app.music_toggle(); check("play starts the first track", app.mus_state == "playing" and app.mus_idx == 0)
app.music_toggle(); check("pause", app.mus_state == "paused"); app.music_toggle(); check("resume", app.mus_state == "playing")
app.music_next(False); check("next track", app.mus_idx == 1)
app.music_prev(); check("previous track (history)", app.mus_idx == 0)

def end_of_track():
    app.mus_started = 0; app.mus.m = "stopped"; app.music_tick(); pump(app, 2)
end_of_track(); check("auto-advances at the end of a track", app.mus_idx == 1 and app.mus_state == "playing")
app.mus_loop = 2; end_of_track(); check("loop-one repeats the track", app.mus_idx == 1)
app.mus_loop = 0; app.music_play_index(2); end_of_track(); check("loop-off stops after the last track", app.mus_state == "stopped")
app.mus_loop = 1; app.music_play_index(2); end_of_track(); check("loop-all wraps to the first track", app.mus_idx == 0 and app.mus_state == "playing")
app.mus_loop = 0; app.music_cycle_loop(); app.music_toggle_shuffle()
check("loop and shuffle settings are remembered", app.cfg["music_loop"] == 1 and app.cfg["music_shuffle"] is True)
app.mus_state = "playing"; app.mus_len = 200000; app.seekbar.update()
class Ev: x = app.seekbar.winfo_width() // 2
app.music_seek(Ev); check("clicking the seek bar jumps to that point", abs(app.mus.p - 100000) < 3000, str(app.mus.p))
app.music_volume("40"); check("volume slider reaches the engine", app.mus.vol == 40)
(a.MUSIC_DIR / "bad.bad").write_text("x"); app.music.append(str(a.MUSIC_DIR / "bad.bad")); app.music_refresh_list()
app.music_play_index(len(app.music) - 1); check("an unplayable file reports an error instead of crashing", app.mus_state == "stopped" and not ERR)
app.music_play_index(0); app.music_suspend(); check("music pauses while a game runs", app.mus_state == "paused")
app.music_resume(); check("music resumes after the game", app.mus_state == "playing")
app.music_tree.selection_set("0"); app.music_remove(); check("remove a track", len(app.music) == 3)
app.music_clear(); check("clear the playlist", app.music == [] and app.mus_state == "stopped")
shot("music_player")
finish(app)
