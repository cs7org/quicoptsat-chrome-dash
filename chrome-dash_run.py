# pip install selenium
# pip install webdriver_manager

import argparse
import os
import socket
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

import concurrent.futures
from http.server import BaseHTTPRequestHandler, HTTPServer
import json


# This script:
#  - Starts a very simple HTTP server
#  - Runs chrome loading a website with a dash.js client, and sends some metrics to the HTTP server

# Chrome in this script has to run at least as long as it takes for the player.html/JS to send the metrics
# FIXME hard-coded value, has to match JavaScript in player.html
PLAYER_JS_SEND_METRICS_TIME = 60

# FIXME global variables in main, because I don't know how to pass them to http handler :-/
# - resultsDir
# - currentTime


# https://stackoverflow.com/questions/66514500/how-do-i-configure-a-python-server-for-post
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        #print(self.headers)
        content_length = int(self.headers['Content-Length'])
        #print(content_length)
        data = json.loads(self.rfile.read(content_length))
        #print(json.dumps(data, indent=4))
        #currentTime = datetime.now().strftime("%Y%m%d-%H%M%S") maybe use same timestamp for resource timings
        with open(f"{resultsDir}/{currentTime}.json", "w") as file:
            file.write(json.dumps(data, indent=4))
            print(f"Wrote {resultsDir}/{currentTime}.json")

        #send dummy response to make browser happy
        self.send_response(200)
        self.send_header('Content-type','text/html')
        self.end_headers()
        message = "Hello, World! Here is a POST response"
        self.wfile.write(bytes(message, "utf8"))


def runHTTPServer(iterations):
    httpIterations = 0
    with HTTPServer(('', 8000), handler) as server:
        print("Starting http server")
        #server.serve_forever()
        while httpIterations < iterations:
            server.handle_request() # Unsupported 'OPTIONS'
            server.handle_request()
            httpIterations += 1


def runChrome(dest_serverPort_without_https, dest_server_path2file, terminate_after_seconds, protocol):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    if protocol == "tcp":
        options.add_argument("--disable-quic")
    else:
        options.add_argument("--enable-quic")
        options.add_argument(f"--origin-to-force-quic-on={dest_serverPort_without_https}")
    #options.add_argument("--allow-running-insecure-content")
    #options.add_argument("--enable-logging=stderr") # log JavaScript console output in terminal

    driver = webdriver.Chrome(service=webdriver.chrome.service.Service(ChromeDriverManager().install()), options=options)
    print(f"Running driver.get() at {time.time()}")
    driver.get(f"https://{dest_serverPort_without_https}{dest_server_path2file}")

    #maybe add Chromedriver resource timing results

    #very hacky :-(
    time.sleep(terminate_after_seconds+3.14)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--quic', action='store_true')
    parser.add_argument('--tcp', action='store_true')
    parser.add_argument('destServer', type=str,
                        help='destination server (and optional port) without https, e.g., myserver.com:443')
    parser.add_argument('iterations', type=int)
    args = parser.parse_args()

    assert (args.quic and not args.tcp) or (args.tcp and not args.quic)
    protocol = "quic" if args.quic else "tcp"
    assert args.iterations > 0

    global resultsDir
    resultsDir = f"./results/{socket.gethostname()}/{protocol}/"
    print(f"Creating {resultsDir} which contains results as json files")
    try:
        os.makedirs(resultsDir)
    except OSError as error:
        print(error)

    executor = concurrent.futures.ThreadPoolExecutor()
    httpServer = executor.submit(runHTTPServer, args.iterations)

    for i in range(args.iterations):
        print(f"Running iteration {i}")
        global currentTime
        currentTime = datetime.now().strftime("%Y%m%d-%H%M%S")
        runChrome(dest_serverPort_without_https=args.destServer,
                  dest_server_path2file="/player.html",
                  terminate_after_seconds=PLAYER_JS_SEND_METRICS_TIME,
                  protocol=protocol)


    httpServer.result()


