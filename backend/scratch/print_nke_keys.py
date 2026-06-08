import requests

url = "http://localhost:8000/api/ticker/NKE"
res = requests.get(url)
if res.status_code == 200:
    financials = res.json().get("financials", {})
    for statement_name in ["income_statement", "quarterly_income_statement", "balance_sheet", "quarterly_balance_sheet", "cash_flow", "quarterly_cash_flow"]:
        data = financials.get(statement_name, {})
        print(f"{statement_name}: {list(data.keys())[:5] if data else 'EMPTY'}")
else:
    print(f"Error: {res.status_code}")
