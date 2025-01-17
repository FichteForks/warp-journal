import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError, HTTPError


def get_data_path():
    if sys.platform == 'win32':
        path = Path(os.environ['APPDATA']) / 'warp-journal'
    elif sys.platform == 'linux':
        if 'XDG_DATA_HOME' in os.environ:
            path = Path(os.environ['XDG_DATA_HOME']) / 'warp-journal'
        else:
            path = Path('~/.local/share/warp-journal').expanduser()
    elif sys.platform == 'darwin':
        if 'XDG_DATA_HOME' in os.environ:
            path = Path(os.environ['XDG_DATA_HOME']) / 'warp-journal'
        else:
            path = Path('~/Library/Application Support/warp-journal').expanduser()
    else:
        panic('Warp Journal is only designed to run on Windows or Linux-based systems.')

    # ensure dir exists
    try:
        path.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        panic(f'{path} already exists, but is a file.')

    return path

def get_cache_path():
    if not (game_path := get_game_path()):
        return None

    web_cache_path = get_web_cache_path(game_path)
    if not web_cache_path:
        logging.debug('could not find latest webCaches subfolder')
        return None

    path = web_cache_path / 'Cache/Cache_Data/data_2'
    logging.debug('cache path is: ' + str(path))
    if not path.exists():
        logging.debug('cache file does not exist')
        return None

    if sys.platform == 'win32':
        # create a copy of the file so we can also access it while star rail is running.
        # python cannot do this without raising an error, and neither can the default
        # windows copy command, so we instead delegate this task to powershell's Copy-Item
        try:
            copy_path = get_data_path() / 'data_2'
            subprocess.check_output(f'powershell.exe -Command "Copy-Item \'{path}\' \'{copy_path}\'"', shell=True)
            return copy_path
        except (FileNotFoundError, subprocess.CalledProcessError, OSError):
            logging.error('Could not create copy of cache file')
            return None
    else:
        return path

def get_game_path():
    """Retrieve the "game path".

    The "game path" is the one where the game data is put
    and not the folder of the launcher,
    which is the 'Games' subfolder on Windows.
    Since a custom launcher is generally used on Linux,
    the outer launcher folder doesn't exist there.
    """
    if 'GAME_PATH' in os.environ:
        # Allow some leeway for the envvar override
        game_path = Path(os.environ['GAME_PATH'])
        sub_path = game_path / 'Games'
        return sub_path if sub_path.exists() else game_path
    elif sys.platform == 'win32':
        return get_game_path_windows()
    elif sys.platform == 'linux':
        return get_game_path_linux()
    else:
        return None

def get_game_path_windows():
    if 'USERPROFILE' not in os.environ:
        logging.debug('USERPROFILE environment variable does not exist')
        return None

    log_path = Path(os.environ['USERPROFILE']) / 'AppData/LocalLow/Cognosphere/Star Rail/Player.log'
    if not log_path.exists():
        logging.debug('Player.log not found')
        return None

    regex = re.compile('Loading player data from (.+)/StarRail_Data/data.unity3d')
    with log_path.open() as fp:
        for line in fp:
            match = regex.search(line)
            if match is not None:
                return match.group(1)

    logging.debug('game path not found in output_log')
    return None

def get_game_path_linux():
    """Try to determine game folder from launcher configuration."""
    hsr_config_path = Path('~/.local/share/honkers-railway-launcher/config.json').expanduser()
    if not hsr_config_path.exists():
        logging.debug('launcher configuration not found')
        return None

    with hsr_config_path.open() as fp:
        config = json.load(fp)

    try:
        global_path = Path(config['game']['path']['global'])
        if global_path.exists():
            return global_path
        china_path = Path(config['game']['path']['china'])
        if china_path.exists():
            return china_path
    except KeyError:
        pass

    logging.debug('game folder configuration in launcher could not be found')
    return None

def get_web_cache_path(game_path):
    web_caches = game_path / 'StarRail_Data/webCaches/'
    versions = [p for p in web_caches.iterdir() if p.is_dir() and '.' in p.name]
    if not versions:
        return None
    versions.sort(key=lambda p: p.name.split('.'))
    return versions[-1]


def set_up_logging():
    log_level = logging.DEBUG if 'DEBUG' in os.environ else logging.INFO
    log_format = '%(asctime)s %(levelname)s: %(message)s'
    logging.basicConfig(filename=(get_data_path() / 'warp-journal.log'), format=log_format, level=log_level)

    # add a stream handler for log output to stdout
    root_logger = logging.getLogger()
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(log_level)
    formatter = logging.Formatter(log_format)
    stdout_handler.setFormatter(formatter)
    root_logger.addHandler(stdout_handler)

    logging.info('Starting Warp Journal')

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('localhost', port))
            return False
        except OSError:
            return True

def get_usable_port():
    for port in range(6193, 6193 + 10):
        if not is_port_in_use(port):
            return port
        # check if warp journal is already running on this port
        try:
            with urlopen(f'http://localhost:{port}/warp-journal', timeout=0.1) as _:
                return port
            panic('Warp Journal is already running.')
        except (URLError, HTTPError):
            continue

    panic('No suitable port found.')

def panic(message):
    logging.error(message)
    show_error_dialog(message)
    logging.info('Quitting')
    sys.exit(1)

def show_error_dialog(message):
    try:
        import tkinter
        from tkinter import ttk
    except ImportError:
        return

    root = tkinter.Tk()
    root.title('Warp Journal')
    root.minsize(300, 0)
    root.resizable(False, False)
    root.iconphoto(False, tkinter.PhotoImage(file=Path(sys.path[0]) / 'icon.png'))

    frame = ttk.Frame(root, padding=10)
    frame.pack()
    ttk.Label(frame, text=message).pack()
    ttk.Frame(frame, height=5).pack()
    ttk.Button(frame, text='Okay', command=root.destroy).pack()

    # center the window
    window_width = root.winfo_reqwidth()
    window_height = root.winfo_reqheight()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    root.geometry('+{}+{}'.format(int(screen_width / 2 - window_width / 2), int(screen_height / 2 - window_height / 2)))

    root.mainloop()
