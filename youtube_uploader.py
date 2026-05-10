# -*- coding: utf-8 -*-
# youtube_uploader.py
import os
import pickle
import logging
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from typing import Optional, List, Dict

logger = logging.getLogger("viral_cutter.youtube")

class YouTubeUploader:
    """
    Handles authentication and uploading of videos to YouTube via Data API v3.
    Supports multiple profiles and automatic switching on quota exhaustion.
    """
    
    SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
    
    def __init__(self, profiles_file: str = "youtube_profiles.json"):
        self.profiles_file = profiles_file
        self.profiles: List[Dict] = []
        self.current_profile_index = 0
        self.youtube = None
        
        self.load_profiles()
        if self.profiles:
            self.authenticate()

    def load_profiles(self):
        """Loads profiles from the JSON file."""
        if os.path.exists(self.profiles_file):
            try:
                with open(self.profiles_file, 'r', encoding='utf-8') as f:
                    self.profiles = json.load(f)
                logger.info(f"{len(self.profiles)} perfis do YouTube carregados.")
            except Exception as e:
                logger.error(f"Erro ao carregar perfis do YouTube: {e}")
                self.profiles = []
        else:
            # Create a default profile if none exists
            self.profiles = [{
                "name": "Canal Padrão",
                "client_secrets": "client_secrets.json",
                "token": "token.pickle"
            }]
            self.save_profiles()

    def save_profiles(self):
        """Saves profiles to the JSON file."""
        try:
            with open(self.profiles_file, 'w', encoding='utf-8') as f:
                json.dump(self.profiles, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erro ao salvar perfis do YouTube: {e}")

    def add_profile(self, name: str, client_secrets: str, token: str):
        """Adds a new profile and saves it."""
        self.profiles.append({
            "name": name,
            "client_secrets": client_secrets,
            "token": token
        })
        self.save_profiles()

    def remove_profile(self, index: int):
        """Removes a profile by index."""
        if 0 <= index < len(self.profiles):
            profile = self.profiles.pop(index)
            # Tenta remover o arquivo de token associado se ele não for o padrão
            if profile["token"] != "token.pickle" and os.path.exists(profile["token"]):
                try:
                    os.remove(profile["token"])
                    logger.info(f"Arquivo de token removido: {profile['token']}")
                except Exception as e:
                    logger.warning(f"Não foi possível remover o arquivo de token: {e}")
            
            self.save_profiles()
            logger.info(f"Perfil '{profile['name']}' removido.")
            return True
        return False

    def authenticate(self, profile_index: Optional[int] = None):
        """
        Authenticates the user using OAuth2 for a specific profile.
        """
        if profile_index is not None:
            self.current_profile_index = profile_index
        
        if not self.profiles:
            logger.error("Nenhum perfil configurado para autenticação.")
            return False

        profile = self.profiles[self.current_profile_index]
        client_secrets = profile["client_secrets"]
        token_file = profile["token"]
        
        creds = None
        if os.path.exists(token_file):
            with open(token_file, 'rb') as t:
                creds = pickle.load(t)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(client_secrets):
                    logger.error(f"Arquivo '{client_secrets}' não encontrado para o perfil '{profile['name']}'.")
                    return False
                flow = InstalledAppFlow.from_client_secrets_file(client_secrets, self.SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open(token_file, 'wb') as t:
                pickle.dump(creds, t)

        self.youtube = build('youtube', 'v3', credentials=creds)
        logger.info(f"Autenticado no canal: {profile['name']}")
        return True

    def switch_to_next_profile(self) -> bool:
        """Switches to the next profile in the list."""
        if len(self.profiles) <= 1:
            logger.warning("Apenas um perfil disponível. Não há para onde trocar.")
            return False
            
        self.current_profile_index = (self.current_profile_index + 1) % len(self.profiles)
        logger.info(f"Trocando para o próximo perfil: {self.profiles[self.current_profile_index]['name']}")
        return self.authenticate()

    def upload_video(
        self, 
        file_path: str, 
        title: str, 
        description: str, 
        tags: Optional[List[str]] = None,
        category_id: str = "22",
        privacy_status: str = "private",
        publish_at: Optional[str] = None
    ) -> str:
        """
        Uploads a video to YouTube. Automatically switches profiles if quota is exceeded.
        """
        if not self.youtube:
            if not self.authenticate():
                raise RuntimeError("Falha na autenticação do YouTube.")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Vídeo não encontrado para upload: {file_path}")

        actual_privacy = "private" if publish_at else privacy_status

        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags or [],
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': actual_privacy,
                'selfDeclaredMadeForKids': False,
            }
        }
        
        if publish_at:
            body['status']['publishAt'] = publish_at

        media = MediaFileUpload(
            file_path, 
            chunksize=-1, 
            resumable=True, 
            mimetype='video/*'
        )

        try:
            request = self.youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )

            logger.info(f"Iniciando upload para YouTube ({self.profiles[self.current_profile_index]['name']}): {title}")
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"Progresso do upload: {int(status.progress() * 100)}%")
            
            video_id = response.get('id')
            logger.info(f"Upload concluído! Video ID: {video_id}")
            return video_id

        except HttpError as e:
            if e.resp.status in [403, 429] and "quotaExceeded" in str(e):
                logger.warning("Cota do Google Cloud excedida para este perfil!")
                if self.switch_to_next_profile():
                    logger.info("Tentando upload com o novo perfil...")
                    return self.upload_video(file_path, title, description, tags, category_id, privacy_status, publish_at)
                else:
                    raise RuntimeError("Cota excedida em todos os perfis disponíveis.")
            else:
                raise e
