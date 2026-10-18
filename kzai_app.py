"""Точка входа приложения «Ввоз авто в РК» (и собранного .app, и запуска из исходников).

Двойной щелчок: если сервер не запущен — поднимает его отдельным процессом (тот же исполняемый
файл с KZAI_SERVER_CHILD=1), ждёт порт, открывает браузер и завершается. Повторный щелчок
просто открывает вкладку. macOS не создаёт второй процесс запущенного бандла, поэтому
запускающий процесс не должен жить долго.
"""
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

APP_NAME = "Ввоз авто в РК"
PORT = 8790
URL = f"http://localhost:{PORT}"
FROZEN = getattr(sys, "frozen", False)
DATA_DIRS = ("sources/raw", "out")
DATA_VERSION = "1.3.0"   # поднимать, когда меняется состав данных в бандле (сценарии, таблицы)


def bundle_dir():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def data_home():
    if FROZEN:
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return bundle_dir()


def ensure_data(home):
    """Копирует базу из бандла в Application Support: при первом запуске и при новой версии данных.

    Прежние данные при смене версии не удаляются, а переносятся в backup-<версия>-<время>.
    """
    (home / "logs").mkdir(parents=True, exist_ok=True)
    if home == bundle_dir():
        return
    stamp = home / "data_version.txt"
    old = stamp.read_text().strip() if stamp.exists() else "до-1.2.0"
    if old != DATA_VERSION and any((home / sub).exists() for sub in DATA_DIRS):
        backup = home / f"backup-{old}-{time.strftime('%Y%m%d-%H%M%S')}"
        for sub in DATA_DIRS:
            if (home / sub).exists():
                (backup / sub).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(home / sub), str(backup / sub))
    for sub in DATA_DIRS:
        if not (home / sub).exists():
            shutil.copytree(bundle_dir() / sub, home / sub)
    stamp.write_text(DATA_VERSION)


def port_busy():
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def serve():
    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit", "run", str(bundle_dir() / "app.py"),
        f"--server.port={PORT}", "--server.address=127.0.0.1", "--server.headless=true",
        "--server.fileWatcherType=none", "--global.developmentMode=false",
        "--browser.gatherUsageStats=false", "--client.toolbarMode=minimal",
        "--theme.base=light", "--theme.primaryColor=#2a78d6", "--theme.backgroundColor=#ffffff",
        "--theme.secondaryBackgroundColor=#f4f5f7", "--theme.textColor=#1f2328",
    ]
    sys.exit(stcli.main())


def launch(home):
    log = open(home / "logs" / "server.log", "ab")
    cmd = [sys.executable] if FROZEN else [sys.executable, str(Path(__file__).resolve())]
    subprocess.Popen(cmd, env=dict(os.environ, KZAI_SERVER_CHILD="1"), cwd=home, stdin=subprocess.DEVNULL,
                     stdout=log, stderr=log, start_new_session=True)
    for _ in range(240):          # до 60 с: первый запуск собранного приложения долгий
        if port_busy():
            return True
        time.sleep(0.25)
    return False


def main():
    home = data_home()
    os.environ["KZAI_HOME"] = str(home)
    if os.environ.get("KZAI_SERVER_CHILD") == "1":
        serve()
        return
    ensure_data(home)
    if not port_busy() and not launch(home):
        subprocess.run(["open", str(home / "logs" / "server.log")], check=False)
        return
    subprocess.run(["open", URL], check=False)


if __name__ == "__main__":
    main()
