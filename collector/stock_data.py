import akshare as ak
import pandas as pd
import os
import time


def download_stock_data(stocks):

    save_dir = "data/raw"

    os.makedirs(
        save_dir,
        exist_ok=True
    )


    for stock in stocks:

        print(f"Downloading {stock}...")

        try:

            df = ak.stock_us_daily(
                symbol=stock,
                adjust="qfq"
            )


            # 删除异常价格
            df = df[
                df["close"] > 0
            ]


            if df.empty:

                print(
                    f"{stock}: No data"
                )

                continue


            df = df.reset_index()


            file_path = f"{save_dir}/{stock}.csv"


            df.to_csv(
                file_path,
                index=False
            )


            print(
                f"Saved: {file_path}"
            )


        except Exception as e:

            print(
                f"{stock} failed: {e}"
            )


        time.sleep(5)



if __name__ == "__main__":


    stocks = [
        "AAPL",
        "MSFT",
        "SPY"
    ]


    download_stock_data(stocks)