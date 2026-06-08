import requests

url = "http://localhost:8000/api/ticker/MSFT"
res = requests.get(url)
if res.status_code == 200:
    financials = res.json().get("financials", {})
    income = financials.get("income_statement", {})
    first_metric = list(income.keys())[0] if income else None
    print(f"First metric: {first_metric}")
    if first_metric:
        print(f"Dates for first metric: {list(income[first_metric].keys())}")
        print(f"Data for first metric: {income[first_metric]}")
