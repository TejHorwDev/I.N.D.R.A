import os
import string
import winreg
import subprocess

# System directories to exclude from game lists
_STEAM_EXCLUDE = {
    "steamworks shared", "directx", "steam controller configs", "proton",
    "proton experimental", "__temp", "redistributables", "steam linux runtime",
    "steam linux runtime - soldier", "steam linux runtime - sniper",
}
_EPIC_EXCLUDE = {"directxredist", "vcredist", "prerequisites", "launcher"}
_GENERIC_EXCLUDE = {
    "windows", "system32", "syswow64", "program files", "program files (x86)",
    "programdata", "users", "appdata", "temp", "$recycle.bin", "recovery",
    "system volume information", "boot", "perflogs",
}
_MS_SYSTEM_PACKAGES = {
    "microsoft.xboxidentityprovider", "microsoft.xboxapp", "microsoft.xboxgamingoverlay",
    "microsoft.xboxgamespeech", "microsoft.xboxspeech", "microsoft.desktopappinstaller",
    "microsoft.windowscalculator", "microsoft.webpimaextension", "microsoft.vp9videoextensions",
    "microsoft.storepurchaseapp", "microsoft.heifimaextension", "microsoftwindows.client.webexperience",
    "microsoft.windowsstore", "microsoft.screenSketch", "microsoft.windowsnotepad",
    "microsoft.winget.source", "microsoft.vclibs", "microsoft.net", "microsoft.ui.xaml",
    "microsoft.windows", "e046963f.lenovocompanion", "appup.intelarcsoftware",
    "nvidiacorp.nvidiacontrolpanel", "12030rocksdanister",
}

# Folders with these names on any drive are treated as game libraries
_GAME_FOLDER_NAMES = {
    "games", "mygames", "my games", "gaming", "installed games", "pc games", "videogames",
}

# Known Xbox/MS Game Pass game identifiers (partial name matching)
_XBOX_GAME_KEYWORDS = [
    "halo", "forza", "gears", "sea of thieves", "starfield", "fable", "age of empires",
    "doom", "fallout", "elderscrolls", "bethesda", "mojang", "minecraft", "flight simulator",
    "psychonauts", "grounded", "as dusk falls", "pentiment", "hi-fi rush",
]

# Paths that should always be treated as specific platform launchers
_RIOT_SUBFOLDER_NAMES = {
    "valorant": "VALORANT",
    "league of legends": "League of Legends",
    "teamfight tactics": "Teamfight Tactics",
    "legends of runeterra": "Legends of Runeterra",
    "wild rift": "Wild Rift",
}
_BNET_GAME_NAMES = {
    "world of warcraft": "World of Warcraft",
    "overwatch": "Overwatch 2",
    "starcraft ii": "StarCraft II",
    "hearthstone": "Hearthstone",
    "diablo iv": "Diablo IV",
    "call of duty": "Call of Duty",
    "warzone": "Warzone",
    "diablo iii": "Diablo III",
}


def _get_all_drives() -> list:
    """Returns all available drive letters on the system."""
    drives = []
    for letter in string.ascii_uppercase:
        path = f"{letter}:\\"
        if os.path.exists(path):
            drives.append(path)
    return drives


def _scan_steam(games: dict):
    """Scan all Steam libraries by following libraryfolders.vdf across all drives."""
    # Find Steam base dir (try C and D drive)
    steam_candidates = [
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
        r"D:\Steam",
    ]
    # Also find Steam via registry
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SOFTWARE\WOW6432Node\Valve\Steam")
        steam_path, _ = winreg.QueryValueEx(key, "InstallPath")
        winreg.CloseKey(key)
        if steam_path and steam_path not in steam_candidates:
            steam_candidates.insert(0, steam_path)
    except Exception:
        pass

    steam_libraries = []
    for steam_base in steam_candidates:
        if not os.path.exists(steam_base):
            continue
        if steam_base not in steam_libraries:
            steam_libraries.append(steam_base)
        vdf_path = os.path.join(steam_base, r"steamapps\libraryfolders.vdf")
        if os.path.exists(vdf_path):
            try:
                with open(vdf_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if '"path"' in line:
                            parts = line.split('"')
                            if len(parts) >= 4:
                                lib_path = parts[3].replace('\\\\', '\\')
                                if lib_path and lib_path not in steam_libraries:
                                    steam_libraries.append(lib_path)
            except Exception:
                pass

    for lib in steam_libraries:
        common_path = os.path.join(lib, r"steamapps\common")
        if os.path.exists(common_path):
            try:
                for item in os.listdir(common_path):
                    if os.path.isdir(os.path.join(common_path, item)):
                        if item.lower() not in _STEAM_EXCLUDE:
                            games["Steam"].add(item)
            except Exception:
                pass


def _scan_epic(games: dict):
    """Scan Epic Games across multiple drives."""
    drives = _get_all_drives()
    for drive in drives:
        epic_paths = [
            os.path.join(drive, "Program Files", "Epic Games"),
            os.path.join(drive, "Epic Games"),
        ]
        for epic_path in epic_paths:
            if os.path.exists(epic_path):
                try:
                    for item in os.listdir(epic_path):
                        full = os.path.join(epic_path, item)
                        if os.path.isdir(full) and item.lower() not in _EPIC_EXCLUDE:
                            games["Epic Games"].add(item)
                except Exception:
                    pass

    # Also check Epic Manifests for installed games
    try:
        manifest_dir = os.path.join(
            os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
            "Epic", "EpicGamesLauncher", "Data", "Manifests"
        )
        if os.path.exists(manifest_dir):
            import json
            for fname in os.listdir(manifest_dir):
                if fname.endswith(".item"):
                    try:
                        with open(os.path.join(manifest_dir, fname), 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            display_name = data.get("DisplayName", "")
                            if display_name:
                                games["Epic Games"].add(display_name)
                    except Exception:
                        pass
    except Exception:
        pass


def _scan_riot(games: dict):
    """Scan Riot Games across all drives and common subfolder names."""
    drives = _get_all_drives()
    riot_folder_names = {"riot games", "riotgames"}

    for drive in drives:
        try:
            for folder in os.listdir(drive):
                full = os.path.join(drive, folder)
                if not os.path.isdir(full):
                    continue
                if folder.lower() in riot_folder_names:
                    # Direct Riot folder found
                    _scan_riot_subfolder(full, games)
                elif folder.lower() in _GAME_FOLDER_NAMES:
                    # A "GAMES" folder – check inside for "Riot Games"
                    try:
                        for sub in os.listdir(full):
                            if sub.lower() in riot_folder_names:
                                _scan_riot_subfolder(os.path.join(full, sub), games)
                    except Exception:
                        pass
        except Exception:
            pass


def _scan_riot_subfolder(riot_path: str, games: dict):
    try:
        for item in os.listdir(riot_path):
            matched = _RIOT_SUBFOLDER_NAMES.get(item.lower())
            if matched:
                games["Riot Games"].add(matched)
            elif os.path.isdir(os.path.join(riot_path, item)) and item.lower() != "riot client":
                # Add it as-is if it's not the launcher
                games["Riot Games"].add(item)
    except Exception:
        pass


def _scan_xbox(games: dict):
    """Scan Xbox / Game Pass installs."""
    drives = _get_all_drives()
    xbox_names = {"xboxgames", "xbox games", "windowsgames"}

    for drive in drives:
        try:
            for folder in os.listdir(drive):
                if folder.lower() in xbox_names:
                    full = os.path.join(drive, folder)
                    try:
                        for item in os.listdir(full):
                            if os.path.isdir(os.path.join(full, item)):
                                # Strip "  Content" suffix common in Xbox installs
                                name = item.replace("  Content", "").strip()
                                games["Xbox / Game Pass"].add(name)
                    except Exception:
                        pass
        except Exception:
            pass

    # Appx packages
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-AppxPackage | Where-Object { $_.IsFramework -eq $false } | "
             "Select-Object -ExpandProperty Name | ConvertTo-Json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            import json
            try:
                names = json.loads(result.stdout)
                if isinstance(names, str):
                    names = [names]
                for name in names:
                    pkg_lower = name.lower()
                    if any(sys_pkg in pkg_lower for sys_pkg in _MS_SYSTEM_PACKAGES):
                        continue
                    if any(kw in pkg_lower for kw in _XBOX_GAME_KEYWORDS):
                        display = name.replace("Microsoft.", "").replace("Xbox.", "")
                        # Insert spaces before capital letters
                        clean = ""
                        for i, c in enumerate(display):
                            if c.isupper() and i > 0 and display[i-1].islower():
                                clean += " " + c
                            else:
                                clean += c
                        games["Xbox / Game Pass"].add(clean.strip())
            except Exception:
                pass
    except Exception:
        pass


def _scan_gog(games: dict):
    """Scan GOG games via registry."""
    for hive, prefix in [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\GOG.com\Games"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\GOG.com\Games"),
    ]:
        try:
            key = winreg.OpenKey(hive, prefix)
            i = 0
            while True:
                try:
                    sub_name = winreg.EnumKey(key, i)
                    sub_key = winreg.OpenKey(key, sub_name)
                    try:
                        game_name, _ = winreg.QueryValueEx(sub_key, "GAMENAME")
                        if game_name:
                            games["GOG"].add(game_name)
                    except FileNotFoundError:
                        pass
                    winreg.CloseKey(sub_key)
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except Exception:
            pass


def _scan_battlenet(games: dict):
    """Scan Battle.net installed games."""
    drives = _get_all_drives()
    bnet_names = {"battle.net", "battlenet", "blizzard entertainment"}

    for drive in drives:
        candidate_parents = [
            os.path.join(drive, "Program Files (x86)"),
            os.path.join(drive, "Program Files"),
            drive,
        ]
        for parent in candidate_parents:
            try:
                for folder in os.listdir(parent):
                    if folder.lower() in bnet_names and os.path.isdir(os.path.join(parent, folder)):
                        # Found Battle.net, scan siblings for games
                        try:
                            for sibling in os.listdir(parent):
                                matched = _BNET_GAME_NAMES.get(sibling.lower())
                                if matched:
                                    games["Battle.net"].add(matched)
                                    continue
                                for kw, display in _BNET_GAME_NAMES.items():
                                    if kw in sibling.lower() and os.path.isdir(os.path.join(parent, sibling)):
                                        games["Battle.net"].add(display)
                        except Exception:
                            pass
            except Exception:
                pass


def _scan_ea(games: dict):
    """Scan EA App games."""
    drives = _get_all_drives()
    ea_folder_names = {"ea games", "ea desktop", "ea app", "origin games"}
    ea_exclude = {"eadesktop", "ea app", "origin"}

    for drive in drives:
        for parent in [os.path.join(drive, "Program Files"),
                       os.path.join(drive, "Program Files (x86)"),
                       drive]:
            try:
                for folder in os.listdir(parent):
                    if folder.lower() in ea_folder_names:
                        full = os.path.join(parent, folder)
                        try:
                            for item in os.listdir(full):
                                if os.path.isdir(os.path.join(full, item)) and item.lower() not in ea_exclude:
                                    games["EA App"].add(item)
                        except Exception:
                            pass
            except Exception:
                pass


def _scan_generic_game_folders(games: dict):
    """
    Scan common 'Games' folders on all drives (e.g. D:\\GAMES) that are not
    already covered by a known platform. Games found here go into 'Other'.
    """
    already_known: set = set()
    for v in games.values():
        already_known.update(vv.lower() for vv in v)

    drives = _get_all_drives()
    for drive in drives:
        try:
            for folder in os.listdir(drive):
                if folder.lower() in _GAME_FOLDER_NAMES:
                    full = os.path.join(drive, folder)
                    try:
                        for item in os.listdir(full):
                            item_full = os.path.join(full, item)
                            if not os.path.isdir(item_full):
                                continue
                            item_lower = item.lower()
                            # Skip if it's a known platform sub-folder
                            if item_lower in {"riot games", "steam", "epic games", "xbox games",
                                              "gog", "battle.net", "ea games", "bluestack",
                                              "bluestacks"}:
                                continue
                            # Skip if already discovered under a known platform
                            if item_lower in already_known:
                                continue
                            games.setdefault("Other", set()).add(item)
                    except Exception:
                        pass
        except Exception:
            pass


def get_game_list() -> dict:
    """Scans ALL drives on the system for installed games, grouped by platform."""
    games = {
        "Steam": set(),
        "Epic Games": set(),
        "Xbox / Game Pass": set(),
        "Riot Games": set(),
        "GOG": set(),
        "Battle.net": set(),
        "EA App": set(),
    }

    _scan_steam(games)
    _scan_epic(games)
    _scan_riot(games)
    _scan_xbox(games)
    _scan_gog(games)
    _scan_battlenet(games)
    _scan_ea(games)
    _scan_generic_game_folders(games)

    # Remove empty platforms and sort
    return {k: sorted(list(v)) for k, v in games.items() if v}


def scan_games() -> str:
    """Returns a formatted string of installed games."""
    games = get_game_list()
    if not games:
        return "No specific games detected automatically. The user might have them installed in custom drives."

    result = "Detected installed games/apps:\n"
    for platform, game_list in games.items():
        result += f"\n[{platform}]\n"
        result += "\n".join(f"- {g}" for g in game_list)
        result += "\n"
    return result.strip()


if __name__ == "__main__":
    print(scan_games())
