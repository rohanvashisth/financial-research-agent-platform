import requests
import json

url = "http://localhost:8000/api/ticker/MSFT"
res = requests.get(url)
if res.status_code == 200:
    financials = res.json().get("financials", {})
    with open("backend/scratch/msft_api_financials.json", "w") as f:
        json.dump(financials, f, indent=2)
    print("Saved financials JSON to backend/scratch/msft_api_financials.json")
else:
    print(f"Error: {res.status_code}")
