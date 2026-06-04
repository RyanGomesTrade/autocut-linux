# -*- coding: utf-8 -*-
import sys
import os
import time
import json
from playwright.sync_api import sync_playwright

# Garante que a pasta de sessões existe
os.makedirs("sessions", exist_ok=True)

def save_session(platform_name):
    """
    Abre o navegador para o usuário fazer login manualmente e salva os cookies.
    """
    print(f"\n--- Login Manual: {platform_name} ---")
    print("1. O navegador vai abrir.")
    print("2. Faça o login na sua conta manualmente.")
    print("3. Quando terminar de logar e estiver na página inicial, feche o navegador ou pressione Enter aqui.")
    
    with sync_playwright() as p:
        # Abre o navegador (Chrome/Chromium)
        browser = p.chromium.launch(headless=False) # Precisa ser visível para o login
        context = browser.new_context()
        page = context.new_page()
        
        if platform_name.lower() == "youtube":
            page.goto("https://studio.youtube.com")
        elif platform_name.lower() == "tiktok":
            page.goto("https://www.tiktok.com/login")
            
        print("\nAguardando login... (pressione Enter no terminal quando terminar)")
        input()
        
        # Salva o estado da sessão (cookies e localStorage)
        session_path = f"sessions/{platform_name.lower()}_session.json"
        context.storage_state(path=session_path)
        print(f"Sessão salva com sucesso em: {session_path}")
        
        browser.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 session_manager.py [youtube|tiktok]")
    else:
        save_session(sys.argv[1])
