import requests

url = "https://data-api.polymarket.com/v1/leaderboard"
params = {
    "timePeriod": "month",
    "orderBy": "PNL",
    "limit": 20,
    "offset": 0,
    "category": "overall"
}

try:
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    print("Status Code:", response.status_code)
    print("Number of records:", len(data))
    if len(data) > 0:
        print("First user:", data[0])
except Exception as e:
    print("Error:", e)


