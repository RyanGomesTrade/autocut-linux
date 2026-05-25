
import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

client_secrets = "jacare-cortes.json"
token_file = "token_jacare-cortes_.pickle"
SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']

def test():
    print(f"Checking for {token_file}...")
    creds = None
    if os.path.exists(token_file):
        print("Token file found.")
        with open(token_file, 'rb') as t:
            creds = pickle.load(t)
    else:
        print("Token file NOT found.")
    
    if not creds:
        print("No credentials loaded.")
        return

    print(f"Creds valid: {creds.valid}")
    if not creds.valid:
        if creds.expired:
            print("Creds expired.")
        if creds.refresh_token:
            print("Refresh token available.")
            try:
                print("Tentando renovar token...")
                creds.refresh(Request())
                print("Token renovado!")
            except Exception as e:
                print(f"Erro ao renovar: {e}")
        else:
            print("No refresh token available.")

test()
