import requests

headers = {
    "User-Agent": "financialresearchagent rohan@example.com",
    "Accept-Encoding": "gzip, deflate"
}

ticker = "MSFT"
cik = "0000789019"
url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

response = requests.get(url, headers=headers)
if response.status_code == 200:
    us_gaap = response.json().get("facts", {}).get("us-gaap", {})
    
    # Check SalesRevenueNet
    if "SalesRevenueNet" in us_gaap:
        entries = us_gaap["SalesRevenueNet"].get("units", {}).get("USD", [])
        print("Checking entries for 2009-09-30:")
        for e in entries:
            if e.get("end") == "2009-09-30":
                print(f"  form: {e.get('form')} | fp: {e.get('fp')} | start: {e.get('start')} | val: {e.get('val')}")
                
        print("\nChecking first 10 entries of SalesRevenueNet:")
        for e in entries[:15]:
             print(f"  form: {e.get('form')} | fp: {e.get('fp')} | end: {e.get('end')} | start: {e.get('start')} | val: {e.get('val')}")
