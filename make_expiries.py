#!/usr/bin/env python3

import json
import sys
import pandas as pd
from datetime import datetime
from pathlib import Path
import requests
import re

URL = "https://api.kite.trade/instruments"

def unique_expiries_with_tokens(
        df: pd.DataFrame, *, symbol: str, exchange: str, segment: str
    ) -> pd.DataFrame:

    # Basic filter to the instruments of interest
    mask = (
        (df["exchange"] == exchange)
        & (df["segment"] == segment)
        & (df["instrument_type"].isin(["CE", "PE"]))
        & (df["name"] == symbol)
        & (df["expiry"].notna())
        & (df["tradingsymbol"].notna())
    )
    dfx = df.loc[mask, ["expiry", "tradingsymbol"]].copy()

    pat = re.compile(r"^([A-Z]+)[A-Z0-9]*?(\d{2}[A-Z0-9]{3})(\d{2})?\d*(CE|PE)$")

    # Extract pieces from tradingsymbol
    extracted = dfx["tradingsymbol"].astype(str).str.extract(pat)
    extracted.columns = ["underlying", "YYMDD", "opt", "cp"]
    dfx = dfx.join(extracted)

    # Keep rows where regex matched
    dfx = dfx.dropna(subset=["YYMDD"])

    # Normalize to uppercase just in case
    dfx["YYMDD"] = dfx["YYMDD"].str.upper()

    dfx["expiry"] = pd.to_datetime(dfx["expiry"])
    dfx["token_short"] = dfx["YYMDD"]

    dfx.sort_values(["expiry", "tradingsymbol"], inplace=True)
    out = (
        dfx.groupby("expiry", as_index=False)
        .agg(token_short=("token_short", "first"))
        .sort_values("expiry")
        .reset_index(drop=True)
    )
    out["symbol"] = symbol
    return out


def main():
    data_path = Path(__file__).resolve().parent 
    print(f"data_path: {data_path}")
    out_path = data_path / "data/kiteInstruments.csv"

    try:
        resp = requests.get(URL, timeout=60)
        resp.raise_for_status()
        out_path.write_text(resp.text, encoding="utf-8")
        print("Successfully downloaded kiteInstruments")
        print(f"Saved to: {out_path}")
    except requests.RequestException as e:
        print("Failed to download instruments CSV:", e, file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print("Failed to write the CSV file:", e, file=sys.stderr)
        sys.exit(1)


    df = pd.read_csv(out_path, parse_dates=["expiry"])
    df.columns = [c.strip() for c in df.columns]

    nifty_exps = unique_expiries_with_tokens(df, symbol="NIFTY", exchange="NFO", segment="NFO-OPT")
    sensex_exps = unique_expiries_with_tokens(df, symbol="SENSEX", exchange="BFO", segment="BFO-OPT")
        

    combined = pd.concat([nifty_exps, sensex_exps], axis=0).reset_index(drop=True)
    combined.rename(columns={"token_short": "zerodha_token"}, inplace=True)

    # Order columns nicely
    combined = combined[["symbol", "expiry", "zerodha_token"]]

    csv_path = data_path / "data/expiries.csv"
    combined.to_csv(csv_path, index=False)
    
    print("\nWrote:")
    print(f"- CSV:     {csv_path}")

    print("\nNIFTY Option Expiries:")
    print(nifty_exps)
    print("\nSENSEX Option Expiries:")
    print(sensex_exps)

if __name__ == "__main__":
    main()
