# pip install selenium
# pip install webdriver_manager

import argparse
import os
import time
import json
import subprocess
from enum import Enum, auto
from multiprocessing import Process, Queue
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


# picoquic server configuration
# FIXME picoquicdemo (with CR) must be compiled and executable
server_picoquic         = "your-server.de"
server_picoquic_user    = "your-user"  # used for remote access to start picoquic and transfer qlog files
server_picoquic_port    = 44321 # required for picoquic (bind to this port) and chrome (send request to this port)
server_picoquic_dir     = "~/picoquic_cr"
server_picoquic_cert    = "~/path-to-your/cert.pem"
server_picoquic_key     = "~/path-to-your/privkey.pem"
server_picoquic_wwwdir  = "~/path-to/data/1080_360_480_720_bbd.mpd"
server_picoquic_qlogdir = "~/dash-qlog-files"
server_picoquic_cr_para = "PREVIOUS_RTT=600000 PREVIOUS_CWND_BYTES=3750000"

# chrome destination URL (h2 and h3 could be running on different servers)
chrome_h2_url = "https://your-server.de/player.html"
chrome_h3_url = f"https://{server_picoquic}:{server_picoquic_port}/player.html"


class Protocol(Enum):
    TCP = auto()
    QUIC = auto()


def run_picoquic_server(cr_parameters: str, iteration: int):
    """Starts Picoquic server via SSH and renames qlog files."""
    print("Preparing and starting picoquic server")
    cmd = ["ssh", f"{server_picoquic_user}@{server_picoquic}",
           f"mkdir -p {server_picoquic_qlogdir}/temp"]
    print("\033[90m" + " ".join(cmd) + "\033[0m")
    subprocess.run(cmd, check=True)

    cmd = [
        "ssh", f"{server_picoquic_user}@{server_picoquic}",
        f"sudo {cr_parameters} {server_picoquic_dir}/picoquicdemo "
        f"-c {server_picoquic_cert} "
        f"-k {server_picoquic_key} "
        f"-w {server_picoquic_wwwdir} "
        f"-q {server_picoquic_qlogdir}/temp "
        f"-p {server_picoquic_port} -G cubic -a h3 -n {server_picoquic} -1"
    ]
    print("\033[90m" + " ".join(cmd) + "\033[0m")
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    # print(res.stdout)
    # print(res.stderr)

    q.put({"picoquic_stdout": res.stdout, "picoquic_stderr": res.stderr})

    protocol = "quic-cr" if cr_parameters else "quic-ss"
    cmd = ["ssh", f"{server_picoquic_user}@{server_picoquic}",
           f"cd {server_picoquic_qlogdir}/temp; "
           f"for i in *.qlog; do mv $i ../{protocol}_{iteration:03}_$i; done"]
    print("\033[90m" + " ".join(cmd) + "\033[0m")
    subprocess.run(cmd, check=True)

    # FIXME optional: copy files, might also 'collect em all' later manually
    cmd = ["scp", f"{server_picoquic_user}@{server_picoquic}:{server_picoquic_qlogdir}/*.qlog", "results"]
    print("\033[90m" + " ".join(cmd) + "\033[0m")
    subprocess.run(cmd, check=True)
    cmd = ["ssh", f"{server_picoquic_user}@{server_picoquic}", f"rm -f {server_picoquic_qlogdir}/*.qlog"]
    print("\033[90m" + " ".join(cmd) + "\033[0m")
    subprocess.run(cmd, check=True)


def run_chrome(dest_server: str, protocol: Protocol):
    """Launches Chrome headlessly to fetch a webpage with QUIC/TCP."""
    assert dest_server.startswith('https://'), "URL must start with https://"

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")

    if protocol == Protocol.TCP:
        options.add_argument("--disable-quic")
        info = f"Running Chrome to server {dest_server} with options --disable-quic"
    else:
        hostname = urlparse(dest_server).hostname
        port = urlparse(dest_server).port or 443
        options.add_argument("--enable-quic")
        options.add_argument(f"--origin-to-force-quic-on={hostname}:{port}")
        info = f"Running Chrome to server {dest_server} with options --enable-quic --origin-to-force-quic-on={hostname}:{port}"

    driver = webdriver.Chrome(service=webdriver.chrome.service.Service(ChromeDriverManager().install()),
                              options=options)
    driver_get_time = int(time.time() * 1000)

    try:
        print(info)
        driver.get(dest_server)

        # let video play and collect metrics
        time.sleep(15)

        metrics = driver.execute_script("return metrics")
        # in case of "javascript error: metrics is not defined" try to wait longer until picoquic server has started
        # and/or check driver.page_source

        perf_timing = driver.execute_script("return window.performance.timing")
    except Exception as e:
        driver.quit()
        raise RuntimeError(f"Chrome error: {e}")

    driver.close()
    res = {
        "chrome_driver.get()": driver_get_time,
        "chrome_performanceTiming": perf_timing,
        "chrome_metrics": metrics
    }
    # print(json.dumps(res, indent=2))
    q.put(res)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--configDone', action='store_true', default=False,
                        help="Confirm that you checked the hardcoded values used in the script")
    parser.add_argument('--iterations', type=int, default=1,
                        help="Number of iterations")
    args = parser.parse_args()

    assert args.configDone, "Confirm that you checked the hardcoded values used in the script with --configDone"
    assert args.iterations > 0, "Please specify number of iterations > 0"
    os.makedirs("results", exist_ok=True)

    for iteration in range(args.iterations):
        print(f"\n=== Iteration {iteration} ===")
        q = Queue()

        # tcp
        run_chrome(chrome_h2_url, Protocol.TCP)
        result = q.get()
        # print(json.dumps(result, indent=2))
        with open(f"results/tcp_{iteration:03}_dash.json", "w") as file:
            json.dump(result, file, indent=2)
        print(f"Finished tcp iteration {iteration}\n\n")

        # quic
        for cr in ["quic-ss", "quic-cr"]:
            cr_parameters = server_picoquic_cr_para if cr == "quic-cr" else ""
            p_server = Process(target=run_picoquic_server, args=(cr_parameters, iteration))
            p_chrome = Process(target=run_chrome,
                               args=(chrome_h3_url, Protocol.QUIC))

            p_server.start()
            time.sleep(10)  # picoquic server needs some time to start
            p_chrome.start()

            p_server.join()
            print("Picoquic server returned")
            p_chrome.join()
            print("Chromium client returned")

            result = q.get() | q.get()
            # print(json.dumps(result, indent=2))
            with open(f"results/{cr}_{iteration:03}_dash.json", "w") as file:
                json.dump(result, file, indent=2)
            print(f"Finished {cr} iteration {iteration}\n\n")
