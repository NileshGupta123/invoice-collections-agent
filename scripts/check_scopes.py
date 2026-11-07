import os
import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
BASE_URL = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")

response = requests.post(
    f"{BASE_URL}/v1/oauth2/token",
    auth=(CLIENT_ID, CLIENT_SECRET),
    headers={"Accept": "application/json"},
    data={"grant_type": "client_credentials"},
    timeout=30,
)
response.raise_for_status()
data = response.json()

scopes = sorted(data.get("scope", "").split())
print("Total scopes:", len(scopes))
print("Invoicing scope mila:", any("invoicing" in s for s in scopes))
print()
for s in scopes:
    print(s)