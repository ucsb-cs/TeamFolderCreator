import requests
import json


# Read credentials from credentials.json
with open('token_chat.json') as f:
    credentials = json.load(f)
    access_token = credentials['token']
    

url = 'https://chat.googleapis.com/v1/spaces'

headers = {
    'Authorization': f'Bearer {access_token}'
}

response = requests.get(url, headers=headers)
print(response.status_code, response.text)
