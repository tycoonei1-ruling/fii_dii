import requests
import pandas as pd
import gspread
import urllib3

from sqlalchemy import create_engine, text
from oauth2client.service_account import ServiceAccountCredentials
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# -----------------------------------
# Disable SSL warnings
# -----------------------------------
urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)

print("Starting Daily Update...")

# -----------------------------------
# PostgreSQL Connection
# -----------------------------------
engine = create_engine(
    "postgresql://postgres:1508@localhost:5432/finance_db"
)

# -----------------------------------
# NSE API URL
# -----------------------------------
url = "https://www.nseindia.com/api/fiidiiTradeReact"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive"
}

# -----------------------------------
# Create NSE Session
# -----------------------------------
session = requests.Session()

retry_strategy = Retry(
    total=5,
    connect=5,
    read=5,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504]
)

adapter = HTTPAdapter(max_retries=retry_strategy)

session.mount("https://", adapter)
session.mount("http://", adapter)

session.headers.update(headers)

try:

    print("Connecting to NSE...")

    home_response = session.get(
        "https://www.nseindia.com",
        timeout=30
    )

    print(
        f"NSE Home Status: {home_response.status_code}"
    )

    response = session.get(
        url,
        timeout=30
    )

    print(
        f"API Status: {response.status_code}"
    )

    response.raise_for_status()

    data = response.json()

except Exception as e:

    print("\nERROR CONNECTING TO NSE")
    print(str(e))
    raise SystemExit()

# -----------------------------------
# Extract FII & DII Data
# -----------------------------------
try:

    fii = next(
        item for item in data
        if item["category"] == "FII/FPI"
    )

    dii = next(
        item for item in data
        if item["category"] == "DII"
    )

except Exception as e:

    print("Unable to find FII/DII data")
    print(str(e))
    raise SystemExit()

# -----------------------------------
# Create DataFrame
# -----------------------------------
df = pd.DataFrame([{

    "trade_date": pd.to_datetime(
        fii["date"],
        dayfirst=True
    ),

    "fii_gross_purchase": float(
        str(fii["buyValue"]).replace(",", "")
    ),

    "fii_gross_sale": float(
        str(fii["sellValue"]).replace(",", "")
    ),

    "fii_net_purchase_sale": float(
        str(fii["netValue"]).replace(",", "")
    ),

    "dii_gross_purchase": float(
        str(dii["buyValue"]).replace(",", "")
    ),

    "dii_gross_sale": float(
        str(dii["sellValue"]).replace(",", "")
    ),

    "dii_net_purchase_sale": float(
        str(dii["netValue"]).replace(",", "")
    )

}])

print("\nLatest Data:")
print(df)

# -----------------------------------
# Insert Into PostgreSQL
# -----------------------------------
try:

    with engine.begin() as conn:

        query = text("""

        INSERT INTO fii_dii_activity (

            trade_date,

            fii_gross_purchase,
            fii_gross_sale,
            fii_net_purchase_sale,

            dii_gross_purchase,
            dii_gross_sale,
            dii_net_purchase_sale

        )

        VALUES (

            :trade_date,

            :fii_gross_purchase,
            :fii_gross_sale,
            :fii_net_purchase_sale,

            :dii_gross_purchase,
            :dii_gross_sale,
            :dii_net_purchase_sale

        )

        ON CONFLICT (trade_date)

        DO UPDATE SET

            fii_gross_purchase =
                EXCLUDED.fii_gross_purchase,

            fii_gross_sale =
                EXCLUDED.fii_gross_sale,

            fii_net_purchase_sale =
                EXCLUDED.fii_net_purchase_sale,

            dii_gross_purchase =
                EXCLUDED.dii_gross_purchase,

            dii_gross_sale =
                EXCLUDED.dii_gross_sale,

            dii_net_purchase_sale =
                EXCLUDED.dii_net_purchase_sale

        """)

        conn.execute(
            query,
            df.iloc[0].to_dict()
        )

    print(
        "\nPostgreSQL Updated Successfully"
    )

except Exception as e:

    print(
        "\nPostgreSQL Update Failed"
    )
    print(str(e))
    raise SystemExit()

# -----------------------------------
# Read Full Database
# -----------------------------------
full_df = pd.read_sql("""

SELECT

    trade_date,

    fii_gross_purchase,
    fii_gross_sale,
    fii_net_purchase_sale,

    dii_gross_purchase,
    dii_gross_sale,
    dii_net_purchase_sale

FROM fii_dii_activity

ORDER BY trade_date DESC

""", engine)

full_df["trade_date"] = (
    full_df["trade_date"].astype(str)
)

# -----------------------------------
# Google Sheets Authentication
# -----------------------------------
try:

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = (
        ServiceAccountCredentials
        .from_json_keyfile_name(
            "credentials.json",
            scope
        )
    )

    client = gspread.authorize(
        creds
    )

    print(
        "Google Authentication Successful"
    )

except Exception as e:

    print(
        "\nGoogle Authentication Failed"
    )
    print(str(e))
    raise SystemExit()

# -----------------------------------
# Open Sheet
# -----------------------------------
try:

    sheet = client.open_by_url(
        "https://docs.google.com/spreadsheets/d/1YaBS6wqb5uPBEgmBMTjyPgDWpyeuZZkHUoTfIhxQgN0/edit?gid=0#gid=0"
    ).sheet1

    print("Google Sheet Opened")

except Exception as e:

    print(
        "\nUnable To Open Google Sheet"
    )
    print(str(e))
    raise SystemExit()

# -----------------------------------
# Clear Existing Data
# -----------------------------------
sheet.clear()

# -----------------------------------
# Upload Data
# -----------------------------------
sheet.update([

    [
        "Date",
        "FII Gross Purchase",
        "FII Gross Sale",
        "FII Net Purchase/Sale",
        "DII Gross Purchase",
        "DII Gross Sale",
        "DII Net Purchase/Sale"
    ]

] + full_df.values.tolist())

print(
    "\nGoogle Sheet Updated Successfully"
)

print(
    "\nDaily Update Completed Successfully"
)