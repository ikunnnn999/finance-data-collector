import yfinance as yf
import os


def download_stock_data(
        ticker="SPY",
        start="2020-01-01",
        end="2025-01-01"):

    print("Downloading data...")

    data = yf.download(
        ticker,
        start=start,
        end=end
    )

    os.makedirs(
        "data/raw",
        exist_ok=True
    )

    file_path = f"data/raw/{ticker}.csv"

    if data.empty:
        print("No data downloaded.")
    else:
        data.to_csv(file_path)
        print(
            f"Saved to {file_path}"
        )


if __name__ == "__main__":

    download_stock_data()