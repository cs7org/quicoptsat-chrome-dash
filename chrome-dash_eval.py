import argparse
import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


# json files are expected with the file path "results/operator/protocol/timestamp.json"
#                                      e.g., "results/starlink/quic/20240622-130543.json"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('json_files', nargs='+', type=str,
                        help='List of json files to process')
    args = parser.parse_args()

    df = pd.DataFrame()

    #resIndex = []
    #resBufferLevel = []

    for file in args.json_files:
        print(file)

        with open(file) as f:
            operator = file.split("/")[1]
            protocol = file.split("/")[2]

            if operator == "netem-matthias":
                operator = "NetEm (50/5)"
            elif operator == "p700skydsl":
                operator = "SkyDSL (50/5)"
            elif operator == "op9020konnect":
                operator = "Konnect (50/5)"
            elif operator == "op9020starlink":
                operator = "Starlink"
            elif operator == "telekom5g":
                operator = "Telekom5G"
            else:
                print(f"operator {operator} not known")

            data = json.load(f)
            #print(data['bufferLevel'])

            df_temp = pd.DataFrame({"Operator": operator,
                                    "Protocol": protocol.upper(),
                                    "bufferLevel": data['bufferLevel']
                                    })
            df  = pd.concat([df, df_temp]) #concat is super slow but I don't care
            #resIndex.extend(range(len(data['bufferLevel'])))
            #resBufferLevel.extend(data['bufferLevel'])

    df.index.name = "time"
    customSort = {"NetEm (50/5)": 0,
                  "Konnect (50/5)": 1,
                  "SkyDSL (50/5)": 2,
                  "Starlink": 3,
                  "Telekom5G": 4}
    df.sort_values(by="Operator", inplace=True, key=lambda x: x.map(customSort))
    df.to_csv("eval.csv")
    print(df)

    # plot
    sns.set_theme()
    sns.lineplot(data=df, x='time', y='bufferLevel', hue='Operator', style='Protocol',
                 estimator="median", errorbar=("pi", 50))
    plt.xlabel("Duration [s]")
    plt.ylabel("Buffer Level [s]")
    plt.savefig("results.png")
