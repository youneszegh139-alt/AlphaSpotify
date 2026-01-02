#!/usr/bin/env python3
import os
import sys
import time
from core.config import AppConfig
from core.search import Searcher
from core.settings import SettingsStore
from core.playlist import Playlist, PlaylistStore
from core.info import estimate_mp3_size_bytes, human_size
from player.controller import MpvController
from player.download import Downloader
from utils.ui import (
    set_console_title,
    clear_screen,
    get_terminal_size,
    render_center_block,
    render_footer_right,
    prompt,
    select_from_list,
    wait_keypress,
    read_key_nonblocking,
    theme,
    color,
    progress_bar,
    set_theme,
)

# ANSI colors for theme
WHITE = "\033[97m"
GREEN = "\033[92m"
ORANGE = "\033[38;5;208m"  # fallback terminal may map to 256-color; otherwise use "\033[33m"
RESET = "\033[0m"

# Global controller reference for close handling
CURRENT_CONTROLLER = None

# Windows console close handler to stop mpv when the window is closed
if os.name == "nt":
    import ctypes
    import ctypes.wintypes

    def _console_ctrl_handler(ctrl_type):
        # 0=CTRL_C_EVENT, 1=CTRL_BREAK_EVENT, 2=CTRL_CLOSE_EVENT
        if ctrl_type in (0, 1, 2):
            try:
                global CURRENT_CONTROLLER
                if CURRENT_CONTROLLER is not None:
                    CURRENT_CONTROLLER.stop()
                    time.sleep(0.2)
                if CURRENT_CONTROLLER and CURRENT_CONTROLLER.proc:
                    CURRENT_CONTROLLER.proc.terminate()
                    CURRENT_CONTROLLER.proc.wait()
            except Exception:
                pass
            return True
        return False

    _HANDLER_REF = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.DWORD)(_console_ctrl_handler)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(_HANDLER_REF, True)

LOGO = r"""
MMP"""""""MM dP        dP MP""""""`MM dP        oo        .8888b
M' .mmmm  MM 88        88 M  mmmmm..M 88                    "
M  `M     88 88d888b.  88 88d888b.   .d8888b.  M.` YM  88d888b.  .d8888b. d8888P dP  88aaa  dP  dP
M   MMMMM MM 88'  `88  88 88'  `88   88'  `88 MMMMMMM. M 88'  `88 88'  `88  88   88  88     88  88
M  .MMMM' MM 88.  .88  88 88.  .88   88.  .88 M. .MMM' M 88.  .88 88.  .88  88   88  88     88  88
M  MMMMM  MM 88Y888P'  dP 88Y888P'   `88888P8 Mb.  .dM  88Y888P'  `88888P'  dP   dP  dP     dP  dP
MMMMMMMMMMMM 88             MMMMMMMMMMM                              88                       .88
             dP             dP      dP d8888P
"""


SUBTITLE = "Minimal • No Ads • Fast"
FOOTER = f"developed by {ORANGE}strength{RESET}"
TITLE = "AlphaSpotifyV0.1/str9ngth"


def render_header():
    set_console_title(TITLE)
    clear_screen()
    width, height = get_terminal_size()
    pad_lines = max(0, (height // 8))
    print("\n" * pad_lines)
    # Render logo with first half white (Alpha) and second half green (Spotify)
    lines = LOGO.strip("\n").splitlines()
    max_w = max(len(l) for l in lines) if lines else 0
    pad = max(0, (width - max_w) // 2)
    for l in lines:
        s = l.ljust(max_w)
        half = max_w // 2
        first, second = s[:half], s[half:]
        print(" " * pad + f"{WHITE}{first}{theme.ACCENT}{second}{theme.RESET}")
    print()
    render_center_block([f"{ORANGE}{SUBTITLE}{theme.RESET}"])
    print("\n")


def main_menu() -> int | None:
    items = [
        "Play a song",
        "Search a song (info, play or download)",
        "Settings",
        "Support / Account",
        "Playlist",
        "Search singer",
        "Themes",
        "Exit",
    ]
    idx = select_from_list(items, header="Main Menu:")
    return idx


def play_now_flow(searcher: Searcher, ctrl: MpvController, settings: Settings, playlist: Playlist | None = None):
    query = prompt("Search query: ").strip()
    if not query:
        return
    results = searcher.search(query, limit=10)
    if not results:
        print("No results.")
        wait_keypress()
        return
    sel = select_from_list([f"{r['title']} - {r.get('uploader','?')} [{r.get('duration','?')}]" for r in results], header="Select track:")
    if sel is None:
        return
    track = results[sel]
    url = track["webpage_url"]
    print("\nResolving stream URL...")
    stream_url = searcher.resolve_stream_url(url)
    if not stream_url:
        print("Failed to resolve stream.")
        wait_keypress()
        return
    # Play with live controls
    global CURRENT_CONTROLLER
    CURRENT_CONTROLLER = ctrl
    if ctrl.start(stream_url) != 0:
        CURRENT_CONTROLLER = None
        wait_keypress()
        return
    kb = settings.keybinds
    controls_text = f"Controls: [ ]=Pause  [9]=Vol-  [0]=Vol+  [,]=Seek-  [.]=Seek+  [q]=Quit"
    print("\n" + color(controls_text, theme.ACCENT))
    last_draw = 0
    while ctrl.is_running():
        # Draw progress bar at ~5 FPS for low memory
        now = time.time()
        if now - last_draw > 0.2:
            cur, dur = ctrl.get_progress()
            bar = progress_bar(cur, dur, width=max(20, min(60, get_terminal_size()[0]-20)))
            print("\r" + color(bar, theme.PRIMARY), end="", flush=True)
            last_draw = now
        time.sleep(0.02)
    print("\r" + " " * 100 + "\r", end="")
    CURRENT_CONTROLLER = None
    wait_keypress("Playback ended. Press any key to continue...")


def search_info_flow(searcher: Searcher, downloader: Downloader, settings: Settings):
    query = prompt("Search query: ").strip()
    if not query:
        return
    results = searcher.search(query, limit=10)
    if not results:
        print("No results.")
        wait_keypress()
        return
    sel = select_from_list([f"{r['title']} - {r.get('uploader','?')} [{r.get('duration','?')}]" for r in results], header="Select track:")
    if sel is None:
        return
    track = results[sel]
    duration_txt = track.get('duration','?')
    print("\nInfo:")
    print(f"Title: {track.get('title')}")
    print(f"Uploader: {track.get('uploader')}")
    print(f"Duration: {duration_txt}")
    print(f"URL: {track.get('webpage_url')}")

    # Download options
    # Estimate sizes from bitrate and duration seconds if available
    # Try to parse duration like m:ss or h:mm:ss to seconds
    def parse_dur(d: str | None):
        if not d:
            return None
        try:
            parts = [int(x) for x in str(d).split(":")]
            if len(parts) == 3:
                h,m,s = parts
                return h*3600 + m*60 + s
            if len(parts) == 2:
                m,s = parts
                return m*60 + s
            return int(d)
        except Exception:
            return None

    dur_sec = parse_dur(track.get('duration'))
    opts = [(128, estimate_mp3_size_bytes(dur_sec, 128)),
            (192, estimate_mp3_size_bytes(dur_sec, 192)),
            (320, estimate_mp3_size_bytes(dur_sec, 320))]

    print("\nOptions:")
    print("1) Play")
    print("2) Download MP3")
    choice = prompt("Select: ").strip()
    if choice == "1":
        ctrl = MpvController(AppConfig())
        url = track["webpage_url"]
        print("\nResolving stream URL...")
        su = searcher.resolve_stream_url(url)
        if not su:
            print("Failed to resolve stream.")
            wait_keypress()
            return
        global CURRENT_CONTROLLER
        CURRENT_CONTROLLER = ctrl
        if ctrl.start(su) != 0:
            CURRENT_CONTROLLER = None
            wait_keypress()
            return
        kb = settings.keybinds
        controls_text = f"Controls: [ ]=Pause  [9]=Vol-  [0]=Vol+  [,]=Seek-  [.]=Seek+  [q]=Quit"
        print("\n" + color(controls_text, theme.ACCENT))
        last_draw = 0
        while ctrl.is_running():
            now = time.time()
            if now - last_draw > 0.2:
                cur, dur = ctrl.get_progress()
                bar = progress_bar(cur, dur, width=max(20, min(60, get_terminal_size()[0]-20)))
                print("\r" + color(bar, theme.PRIMARY), end="", flush=True)
                last_draw = now
            time.sleep(0.02)
        print("\r" + " " * 100 + "\r", end="")
        CURRENT_CONTROLLER = None
        wait_keypress()
        return
    elif choice == "2":
        print("\nQuality:")
        for i,(kb, size) in enumerate(opts, start=1):
            print(f"{i}) {kb} kbps  ~ {human_size(size)}")
        which = prompt("Choose quality (1-3): ").strip()
        if which not in {"1","2","3"}:
            return
        kbps = opts[int(which)-1][0]
        out_dir = prompt("Output dir (default: ./downloads): ").strip() or "./downloads"
        os.makedirs(out_dir, exist_ok=True)
        base_name = track.get('title','audio').replace('/', '_').replace('\\', '_')
        out_path = os.path.join(out_dir, base_name + ".mp3")
        print(f"Downloading {kbps}kbps to {out_path} ...")
        rc = downloader.audio_mp3_bitrate(track['webpage_url'], out_path, kbps)
        print("Done." if rc == 0 else f"Failed with code {rc}")
        wait_keypress()
        return


def settings_flow(settings_store: SettingsStore):
    s = settings_store.load()
    while True:
        clear_screen()
        print("Settings:")
        print(f"Cache dir: {s.cache_dir}")
        print("Keybinds:")
        for k,v in s.keybinds.items():
            print(f"  {k}: {repr(v)}")
        print("\n1) Change cache dir  2) Change keybind  0) Back")
        ch = prompt("Select: ").strip()
        if ch == "1":
            newd = prompt("New cache dir: ").strip()
            if newd:
                s.cache_dir = newd
                settings_store.save(s)
        elif ch == "2":
            action = prompt("Action name (pause_toggle, vol_up, vol_down, seek_forward, seek_backward, next_track, prev_track, stop, quit_player): ").strip()
            if action in s.keybinds:
                val = prompt(f"New key for {action}: ").strip()
                if val:
                    s.keybinds[action] = val[0]
                    settings_store.save(s)
        else:
            break


def support_flow(settings_store: SettingsStore):
    s = settings_store.load()
    print("\nSupport / Account")
    print(s.support_text)
    wait_keypress()


def playlist_flow(searcher: Searcher, pl_store: PlaylistStore, settings: Settings):
    playlists = pl_store.list_playlists()
    if playlists:
        print("Existing playlists:")
        for i, name in enumerate(playlists, 1):
            pl_temp = pl_store.load(name)
            print(f"{i}) {name} ({len(pl_temp.items)} songs)")
        print()
    pl_name = prompt("Playlist name (default: default): ").strip() or "default"
    pl = pl_store.load(pl_name)
    while True:
        clear_screen()
        print(f"Playlist: {pl.name}")
        for i, item in enumerate(pl.items, 1):
            print(f"{i}) {item.get('title')} - {item.get('uploader','?')}")
        print("\n1) Add song  2) Remove song  3) Play all  0) Back")
        ch = prompt("Select: ").strip()
        if ch == "1":
            q = prompt("Search query: ").strip()
            if not q:
                continue
            results = searcher.search(q, limit=10)
            if not results:
                print("No results.")
                wait_keypress()
                continue
            sel = select_from_list([f"{r['title']} - {r.get('uploader','?')}" for r in results], header="Select:")
            if sel is None:
                continue
            pl.add(results[sel])
            pl_store.save(pl)
        elif ch == "2":
            idx = prompt("Index to remove: ").strip()
            if idx.isdigit():
                pl.remove(int(idx)-1)
                pl_store.save(pl)
        elif ch == "3":
            ctrl = MpvController(AppConfig())
            for it in pl.items[pl.index:]:
                print(f"\nResolving: {it.get('title')}")
                su = searcher.resolve_stream_url(it['webpage_url'])
                if not su:
                    continue
                if ctrl.start(su) != 0:
                    break
                global CURRENT_CONTROLLER
                CURRENT_CONTROLLER = ctrl
                kb = settings.keybinds
                controls_text = f"Controls: [ ]=Pause  [9]=Vol-  [0]=Vol+  [,]=Seek-  [.]=Seek+  [q]=Quit"
                print("\n" + color(controls_text, theme.ACCENT))
                last_draw = 0
                while ctrl.is_running():
                    now = time.time()
                    if now - last_draw > 0.2:
                        cur, dur = ctrl.get_progress()
                        bar = progress_bar(cur, dur, width=max(20, min(60, get_terminal_size()[0]-20)))
                        print("\r" + color(bar, theme.PRIMARY), end="", flush=True)
                        last_draw = now
                    time.sleep(0.02)
                print("\r" + " " * 100 + "\r", end="")
                CURRENT_CONTROLLER = None
            wait_keypress()
        else:
            break


def singer_info_flow(searcher: Searcher):
    artist = prompt("Singer/Artist name: ").strip()
    if not artist:
        return
    # Lightweight: show top results and basic info from metadata
    results = searcher.search(artist, limit=5)
    if not results:
        print("No info found.")
        wait_keypress()
        return
    print(f"Info for {artist}:")
    print("Birth date: Unknown")
    print("Status: Unknown (Alive/Deceased)")
    print("Family name: Unknown")
    print("Nickname/Real name: Unknown")
    print("\nTop results:")
    for r in results:
        print(f"- {r.get('title')} ({r.get('uploader','?')}) [{r.get('duration','?')}]")
    wait_keypress()


def themes_flow(settings_store: SettingsStore):
    from utils.ui import Theme
    themes = list(Theme.THEMES.keys())
    print("Available themes:")
    for i, t in enumerate(themes, 1):
        print(f"{i}) {t}")
    print("0) Cancel")
    choice = prompt("Select theme: ").strip()
    if not choice.isdigit():
        return
    idx = int(choice)
    if idx == 0:
        return
    if 1 <= idx <= len(themes):
        selected = themes[idx - 1]
        s = settings_store.load()
        s.theme = selected
        settings_store.save(s)
        set_theme(selected)
        print(f"Theme set to {selected}.")
        wait_keypress()


def run():
    cfg = AppConfig()
    searcher = Searcher(cfg)
    ctrl = MpvController(cfg)
    downloader = Downloader(cfg)
    settings_store = SettingsStore()
    s = settings_store.load()
    set_theme(s.theme)
    pl_store = PlaylistStore(os.path.join(os.path.expanduser("~"), ".alphaspotify"))

    while True:
        render_header()
        render_footer_right("developed by strength")
        idx = main_menu()
        clear_screen()
        if idx == 0:
            play_now_flow(searcher, ctrl, s)
        elif idx == 1:
            search_info_flow(searcher, downloader, s)
        elif idx == 2:
            settings_flow(settings_store)
        elif idx == 3:
            support_flow(settings_store)
        elif idx == 4:
            playlist_flow(searcher, pl_store, s)
        elif idx == 5:
            singer_info_flow(searcher)
        elif idx == 6:
            themes_flow(settings_store)
        elif idx == 7:
            print("Goodbye.")
            break
        else:
            continue


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        sys.exit(0)
