# -*- coding: utf-8 -*-
# youtube_uploader.py
import os
import pickle
import logging
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from typing import Optional, List

logger = logging.getLogger("viral_cutter.youtube")

class YouTubeUploader:
    """
    Handles authentication and uploading of videos to YouTube via Data API v3.
    """
    
    SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
    
    def __init__(self, client_secrets_file: str = "client_secrets.json", token_file: str = "token.pickle"):
        self.client_secrets_file = client_secrets_file
        self.token_file = token_file
        self.youtube = None
        self.authenticate()

    def authenticate(self):
        """
        Authenticates the user using OAuth2. 
        Uses a local token file if available, otherwise triggers the browser flow.
        """
        creds = None
        if os.path.exists(self.token_file):
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)
        
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.client_secrets_file):
                    raise FileNotFoundError(
                        f"Arquivo '{self.client_secrets_file}' não encontrado. "
                        "Obtenha-o no Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_file, self.SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)

        self.youtube = build('youtube', 'v3', credentials=creds)
        logger.info("Autenticação com YouTube concluída com sucesso.")

    def upload_video(
        self, 
        file_path: str, 
        title: str, 
        description: str, 
        tags: Optional[List[str]] = None,
        category_id: str = "22",  # 22 = People & Blogs
        privacy_status: str = "private", # private, public, unlisted
        publish_at: Optional[str] = None # ISO 8601 string (YYYY-MM-DDTHH:MM:SSZ)
    ) -> str:
        """
        Uploads a video to YouTube.
        Returns the video ID.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Vídeo não encontrado para upload: {file_path}")

        # Para agendamento, o status precisa ser 'private' e ter o 'publishAt'
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

        # Call the API's videos.insert method to create and upload the video.
        media = MediaFileUpload(
            file_path, 
            chunksize=-1, 
            resumable=True, 
            mimetype='video/*'
        )

        request = self.youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )

        logger.info(f"Iniciando upload para YouTube: {title}")
        
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"Upload progress: {int(status.progress() * 100)}%")
        
        video_id = response.get('id')
        logger.info(f"Upload concluído! Video ID: {video_id}")
        return video_id
