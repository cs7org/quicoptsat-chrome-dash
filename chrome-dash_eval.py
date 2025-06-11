import argparse
import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.ticker import MaxNLocator

def load_data(dir_json_files):
    dfs_canplay, dfs_buffer, dfs_dropped, dfs_resolution = [], [], [], []

    for filename in os.listdir(dir_json_files):
        if not filename.endswith(".json"):
            continue
        if not (filename.startswith("tcp") or filename.startswith("quic-ss") or filename.startswith("quic-cr")):
            continue

        protocol = None
        if filename.startswith("tcp"):
            protocol = "TCP HTTPS/2"
        elif filename.startswith("quic-ss"):
            protocol = "picoquic HyStart"
        elif filename.startswith("quic-cr"):
            protocol = "picoquic Careful Resume"

        with open(os.path.join(dir_json_files, filename)) as f:
            data = json.load(f)

        chrome = data.get("chrome_metrics", {})
        perf = data.get("chrome_performanceTiming", {})
        fetch_start = perf.get("fetchStart")

        # 1) canPlay delay
        can_play_times = chrome.get("canPlay", [])
        if len(can_play_times) > 0 and fetch_start is not None:
            first_canplay = can_play_times[0]
            delay_s = (first_canplay - fetch_start) / 1000
            dfs_canplay.append({
                "protocol": protocol,
                "canplay_delay_s": delay_s,
                "iteration": filename
            })

        # 2) bufferLevel timeseries
        buffer_levels = chrome.get("bufferLevel", [])
        current_times = chrome.get("currentTime", [])
        if len(current_times) == len(buffer_levels) and len(buffer_levels) > 0:
            t0 = round(current_times[0] / 1000)
            for ts_raw, val in zip(current_times, buffer_levels):
                ts = round(ts_raw / 1000) - t0
                dfs_buffer.append({
                    "protocol": protocol,
                    "timestamp": ts,
                    "bufferLevel": val,
                    "iteration": filename
                })

        # 3) droppedFrames stepplot
        dropped_frames = chrome.get("droppedFrames", [])
        current_times = chrome.get("currentTime", [])
        if len(dropped_frames) == len(current_times) and len(dropped_frames) > 0:
            t0 = round(current_times[0] / 1000)
            for ts_raw, val in zip(current_times, dropped_frames):
                ts = round(ts_raw / 1000) - t0
                if val is None:
                    dropped = 0
                elif isinstance(val, dict):
                    dropped = val.get("droppedFrames", 0)
                else:
                    dropped = 0
                dfs_dropped.append({
                    "protocol": protocol,
                    "timestamp": ts,
                    "droppedFrames": dropped,
                    "iteration": filename
                })

        # 4) resolution timeseries combining resWidth and resHeight as resolution string, plot by area
        res_height = chrome.get("resHeight", [])
        res_width = chrome.get("resWidth", [])
        current_times = chrome.get("currentTime", [])
        if len(res_height) == len(res_width) == len(current_times) and len(res_height) > 0:
            t0 = round(current_times[0] / 1000)
            for ts_raw, h, w in zip(current_times, res_height, res_width):
                ts = round(ts_raw / 1000) - t0
                if h is None or w is None:
                    continue
                resolution = f"{w}x{h}"
                area = w * h
                dfs_resolution.append({
                    "protocol": protocol,
                    "timestamp": ts,
                    "resolution": resolution,
                    "area": area,
                    "iteration": filename
                })

    # Convert to DataFrames
    df_canplay = pd.DataFrame(dfs_canplay)
    df_buffer = pd.DataFrame(dfs_buffer)
    df_dropped = pd.DataFrame(dfs_dropped)
    df_resolution = pd.DataFrame(dfs_resolution)

    return df_canplay, df_buffer, df_dropped, df_resolution


def plot_all(df_canplay, df_buffer, df_dropped, df_resolution, dir_json_files):
    sns.set(style="whitegrid")

    protocol_order = ["TCP HTTPS/2", "picoquic Careful Resume", "picoquic HyStart"]
    palette = sns.color_palette(n_colors=3)
    protocol_palette = dict(zip(protocol_order, palette))

    df_canplay['protocol'] = pd.Categorical(df_canplay['protocol'], categories=protocol_order, ordered=True)
    df_buffer['protocol'] = pd.Categorical(df_buffer['protocol'], categories=protocol_order, ordered=True)
    df_dropped['protocol'] = pd.Categorical(df_dropped['protocol'], categories=protocol_order, ordered=True)
    df_resolution['protocol'] = pd.Categorical(df_resolution['protocol'], categories=protocol_order, ordered=True)

    fig, axs = plt.subplots(4, 1, figsize=(9, 15), sharex=False) # 14,18

    # 1) Boxplot of canPlay delay by protocol, use same palette as lineplots
    sns.boxplot(
        data=df_canplay,
        x="protocol",
        y="canplay_delay_s",
        hue="protocol",
        ax=axs[0],
        order=protocol_order,
        palette=protocol_palette,
        legend=False
    )
    axs[0].set_title("Time from fetchStart to CAN_PLAY")
    axs[0].set_xlabel("")
    axs[0].set_ylabel("Delay (seconds)")

    # 2) BufferLevel timeseries
    sns.lineplot(
        data=df_buffer,
        x="timestamp",
        y="bufferLevel",
        hue="protocol",
        estimator=np.median,
        errorbar=("pi", 50),
        ax=axs[1],
        hue_order=protocol_order,
        palette=protocol_palette
    )
    axs[1].set_title("Buffer Level")
    axs[1].set_xlabel("Time (seconds)")
    axs[1].set_ylabel("Buffer Level (seconds)")

    # 3) DroppedFrames step plot timeseries
    sns.lineplot(
        data=df_dropped,
        x="timestamp",
        y="droppedFrames",
        hue="protocol",
        estimator="median",
        errorbar=("pi", 50),
        drawstyle='steps-post',
        ax=axs[2],
        hue_order=protocol_order,
        palette=protocol_palette
    )
    axs[2].set_title("Dropped Frames")
    axs[2].set_xlabel("Time (seconds)")
    axs[2].set_ylabel("Dropped Frames")
    axs[2].yaxis.set_major_locator(MaxNLocator(integer=True))  # Ensures y-axis uses only integers

    # 4) Resolution timeseries as area with y-axis resolution ordered by area ascending
    unique_res = df_resolution[['resolution', 'area']].drop_duplicates().sort_values('area')
    res_order = unique_res['resolution'].tolist()
    area_order = unique_res['area'].tolist()

    df_resolution['resolution'] = pd.Categorical(df_resolution['resolution'], categories=res_order, ordered=True)

    sns.lineplot(
        data=df_resolution,
        x='timestamp',
        y='area',
        hue='protocol',
        estimator=np.median,
        errorbar=("pi", 50),
        ax=axs[3],
        hue_order=protocol_order,
        palette=protocol_palette
    )
    axs[3].set_yticks(area_order)
    axs[3].set_yticklabels(res_order)
    axs[3].set_title("Resolution")
    axs[3].set_xlabel("Time (seconds)")
    axs[3].set_ylabel("Resolution")

    plt.tight_layout()
    #plt.show()
    plt.savefig(f"{dir_json_files}/result.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('dir_json_files', type=str, help='Directory containing json files')
    args = parser.parse_args()

    df_canplay, df_buffer, df_dropped, df_resolution = load_data(args.dir_json_files)
    plot_all(df_canplay, df_buffer, df_dropped, df_resolution, args.dir_json_files)




