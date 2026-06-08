import requests

url = "http://localhost:8000/api/ticker/MSFT"
res = requests.get(url)
if res.status_code == 200:
    financials = res.json().get("financials", {})
    quarterly_income = financials.get("quarterly_income_statement", {})
    first_metric = list(quarterly_income.keys())[0] if quarterly_income else None
    print(f"First quarterly metric: {first_metric}")
    if first_metric:
        dates = sorted(list(quarterly_income[first_metric].keys()), reverse=True)
        print(f"Quarterly dates: {dates[:10]}")
        print(f"Quarterly data: {quarterly_income[first_metric]}")
