import requests
import json

url = "http://localhost:8000/api/ticker/MSFT"
print("Sending request to backend api/ticker/MSFT...")
response = requests.get(url)
print(f"Response code: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    financials = data.get("financials", {})
    print("\nKeys in financials response:")
    for key in financials.keys():
        print(f"  {key}: {len(financials[key])} items")
        # Print first few metrics
        metrics = list(financials[key].keys())[:3]
        print(f"    Sample metrics: {metrics}")
else:
    print(f"Error: {response.text}")
