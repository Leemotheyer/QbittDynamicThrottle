import datetime
import os
import threading
import time

import dateutil
import requests
import schedule
import yaml
from flask import Flask, jsonify, render_template, request
from mcstatus import JavaServer

app = Flask(__name__)
CONFIG_FILE = "config.yaml"

# Default configuration
DEFAULT_CONFIG = {
    "qbittorrent": {
        "host": "http://qbittorrent:8080",
        "username": "admin",
        "password": "adminadmin",
        "enabled": True,
    },
    "jellyfin": {
        "host": "http://jellyfin:8096",
        "api_key": "",
        "active_stream_threshold": 1,
        "enabled": False,
    },
    "minecraft": {
        "host": "minecraft-server",
        "port": 25565,
        "active_player_threshold": 1,
        "enabled": False,
    },
    "wireguard": {
        "host": "http://wireguard:51821",
        "username": "admin",
        "password": "adminadmin",
        "session_time_threshold": 300,
        "active_session_threshold": 1,
        "enabled": False,
    },
    "throttle_settings": {
        "normal_upload": 0,  # 0 means unlimited
        "normal_download": 0,  # 0 means unlimited
        "throttled_upload": 100,  # KB/s
        "throttled_download": 100,  # KB/s
        "check_interval": 60,  # seconds
        "current_state": "unthrottled",
    },
}


def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            yaml.dump(DEFAULT_CONFIG, f)
        return DEFAULT_CONFIG.copy()

    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f)
        for key, default_value in DEFAULT_CONFIG.items():
            if key not in config:
                config[key] = default_value
            elif isinstance(default_value, dict):
                for sub_key, sub_default in default_value.items():
                    if sub_key not in config[key]:
                        config[key][sub_key] = sub_default
        return config


def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f)


def qbittorrent_login():
    config = load_config()
    if not config["qbittorrent"]["enabled"]:
        return None

    try:
        s = requests.Session()
        login_url = f"{config['qbittorrent']['host']}/api/v2/auth/login"
        response = s.post(
            login_url,
            data={
                "username": config["qbittorrent"]["username"],
                "password": config["qbittorrent"]["password"],
            },
        )
        response.raise_for_status()
        return s
    except Exception as e:
        print(f"QBitTorrent login failed: {e}")
        return None


def set_limits(session, upload_kbps, download_kbps):
    config = load_config()
    if not config["qbittorrent"]["enabled"]:
        return

    try:
        # Convert KB/s to bytes (1 KB = 1024 bytes)
        upload_bytes = int(upload_kbps) * 1024
        download_bytes = int(download_kbps) * 1024

        # Set limits
        upload_url = f"{config['qbittorrent']['host']}/api/v2/transfer/setUploadLimit"
        download_url = f"{config['qbittorrent']['host']}/api/v2/transfer/setDownloadLimit"

        session.post(upload_url, data={"limit": upload_bytes})
        session.post(download_url, data={"limit": download_bytes})

        print(f"Set limits: ↑{upload_kbps}KB/s, ↓{download_kbps}KB/s")
    except Exception as e:
        print(f"Failed to set limits: {e}")


def check_jellyfin_activity():
    config = load_config()
    if not config["jellyfin"]["enabled"]:
        return False

    try:
        url = f"{config['jellyfin']['host']}/Sessions"
        headers = {"X-Emby-Token": config["jellyfin"]["api_key"]}
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        sessions = response.json()
        active_streams = sum(1 for s in sessions if s.get("NowPlayingItem"))

        return active_streams >= config["jellyfin"]["active_stream_threshold"]
    except Exception as e:
        print(f"Jellyfin check failed: {e}")
        return False


def check_minecraft_players():
    config = load_config()
    if not config["minecraft"]["enabled"]:
        return False

    try:
        server = JavaServer.lookup(f"{config['minecraft']['host']}:{config['minecraft']['port']}")
        status = server.status()
        return status.players.online >= config["minecraft"]["active_player_threshold"]
    except Exception as e:
        print(f"Minecraft check failed: {e}")
        return False


def check_wireguard_sessions():
    config = load_config()
    if not config["wireguard"]["enabled"]:
        return False

    try:
        url = f"{config['wireguard']['host']}/api/client"
        response = requests.get(
            url,
            auth=(
                config["wireguard"]["username"],
                config["wireguard"]["password"],
            ),
        )
        response.raise_for_status()

        active_sessions = 0

        for client in response.json():
            if client["latestHandshakeAt"] is None:
                continue
            last_handshake = dateutil.parser.parse(client["latestHandshakeAt"])

            if (datetime.datetime.now(datetime.timezone.utc) - last_handshake).seconds < config["wireguard"]["session_time_threshold"]:
                active_sessions += 1

        return active_sessions >= config["wireguard"]["active_session_threshold"]

    except requests.RequestException as e:
        print(f"Failed to communicate with wg-easy: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error occured: {e}")
        return False


def check_and_adjust_throttle():
    config = load_config()
    if not config["qbittorrent"]["enabled"]:
        return

    session = qbittorrent_login()
    if not session:
        return

    throttle_needed = False

    if config["jellyfin"]["enabled"] and check_jellyfin_activity():
        print("Jellyfin activity detected - throttling needed")
        throttle_needed = True

    if config["minecraft"]["enabled"] and check_minecraft_players():
        print("Minecraft players detected - throttling needed")
        throttle_needed = True

    if config["wireguard"]["enabled"] and check_wireguard_sessions():
        print("Wireguard sessions detected - throttling needed")
        throttle_needed = True

    if throttle_needed:
        set_limits(
            session,
            config["throttle_settings"]["throttled_upload"],
            config["throttle_settings"]["throttled_download"],
        )
        config["throttle_settings"]["current_state"] = "throttled"
    else:
        set_limits(
            session,
            config["throttle_settings"]["normal_upload"],
            config["throttle_settings"]["normal_download"],
        )
        config["throttle_settings"]["current_state"] = "unthrottled"

    save_config(config)


def schedule_checks():
    config = load_config()
    schedule.every(config["throttle_settings"]["check_interval"]).seconds.do(check_and_adjust_throttle)

    while True:
        schedule.run_pending()
        time.sleep(1)


# Start the scheduler in a background thread
threading.Thread(target=schedule_checks, daemon=True).start()


@app.route("/")
def index():
    config = load_config()
    return render_template("index.html", config=config)


@app.route("/update_config", methods=["POST"])
def update_config():
    config = load_config()

    # Update QBitTorrent settings
    config["qbittorrent"]["enabled"] = request.form.get("qb_enabled") == "on"
    config["qbittorrent"]["host"] = request.form["qb_host"]
    config["qbittorrent"]["username"] = request.form["qb_username"]
    config["qbittorrent"]["password"] = request.form["qb_password"]

    # Update Jellyfin settings
    config["jellyfin"]["enabled"] = request.form.get("jf_enabled") == "on"
    config["jellyfin"]["host"] = request.form["jf_host"]
    config["jellyfin"]["api_key"] = request.form["jf_api_key"]
    config["jellyfin"]["active_stream_threshold"] = int(request.form["jf_threshold"])

    # Update Minecraft settings
    config["minecraft"]["enabled"] = request.form.get("mc_enabled") == "on"
    config["minecraft"]["host"] = request.form["mc_host"]
    config["minecraft"]["port"] = int(request.form["mc_port"])
    config["minecraft"]["active_player_threshold"] = int(request.form["mc_threshold"])

    # Update Wireguard settings
    config["wireguard"]["enabled"] = request.form.get("wireguard_enabled") == "on"
    config["wireguard"]["host"] = request.form.get("wireguard_host")
    config["wireguard"]["username"] = request.form.get("wireguard_username")
    config["wireguard"]["password"] = request.form.get("wireguard_password")
    config["wireguard"]["session_time_threshold"] = int(request.form.get("wireguard_session_time_threshold"))
    config["wireguard"]["active_session_threshold"] = int(request.form.get("wireguard_active_session_threshold"))

    # Update throttle settings
    config["throttle_settings"]["normal_upload"] = int(request.form["normal_upload"])
    config["throttle_settings"]["normal_download"] = int(request.form["normal_download"])
    config["throttle_settings"]["throttled_upload"] = int(request.form["throttled_upload"])
    config["throttle_settings"]["throttled_download"] = int(request.form["throttled_download"])
    config["throttle_settings"]["check_interval"] = int(request.form["check_interval"])

    save_config(config)
    check_and_adjust_throttle()

    return jsonify({"status": "success", "message": "Configuration updated"})


@app.route("/get_status")
def get_status():
    config = load_config()
    status = {
        "current_state": config["throttle_settings"]["current_state"],
        "last_check": time.strftime("%Y-%m-%d %H:%M:%S"),
        "triggered_criteria": [],
        "current_upload": config["throttle_settings"]["normal_upload"],
        "current_download": config["throttle_settings"]["normal_download"],
    }

    if config["throttle_settings"]["current_state"] == "throttled":
        if config["jellyfin"]["enabled"] and check_jellyfin_activity():
            status["triggered_criteria"].append("Jellyfin activity")
        if config["minecraft"]["enabled"] and check_minecraft_players():
            status["triggered_criteria"].append("Minecraft players")
        if config["wireguard"]["enabled"] and check_wireguard_sessions():
            status["triggered_criteria"].append("Wireguard sessions")

        status["current_upload"] = config["throttle_settings"]["throttled_upload"]
        status["current_download"] = config["throttle_settings"]["throttled_download"]

    return jsonify(status)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
