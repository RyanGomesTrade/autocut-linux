# -*- coding: utf-8 -*-
import os
import time
import logging
from playwright.sync_api import sync_playwright, TimeoutError
from typing import Optional, List

logger = logging.getLogger("viral_cutter.playwright_uploader")

class PlaywrightUploader:
    """
    Handles YouTube video uploads using Playwright (Browser Automation).
    This bypasses API quota limits by simulating a real user upload.
    """
    
    def __init__(self, profile_name: str = "default"):
        # Cada perfil do YouTube tem sua própria pasta de sessão do navegador
        safe_name = "".join([c if c.isalnum() else "_" for c in profile_name])
        self.user_data_dir = os.path.abspath(f"playwright_sessions/{safe_name}")
        self.browser_context = None
        self.playwright = None

    def reset_session(self):
        """Remove a pasta de sessão para forçar um novo login."""
        import shutil
        self.close()
        if os.path.exists(self.user_data_dir):
            shutil.rmtree(self.user_data_dir)
            logger.info(f"Sessão resetada para o perfil: {self.user_data_dir}")
            return True
        return False

    def _setup_browser(self, headless: bool = False):
        if not self.playwright:
            self.playwright = sync_playwright().start()
            self.browser_context = self.playwright.chromium.launch_persistent_context(
                self.user_data_dir,
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox"
                ],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

    def is_logged_in(self) -> bool:
        """Checks if the user is already logged into YouTube Studio."""
        self._setup_browser(headless=True)
        page = self.browser_context.new_page()
        try:
            page.goto("https://studio.youtube.com", timeout=30000)
            # Se encontrar o avatar ou o botão de criar, está logado
            if page.query_selector("#avatar-btn") or page.query_selector("#create-icon"):
                return True
            return False
        except:
            return False
        finally:
            page.close()

    def login(self):
        """Opens YouTube for the user to login manually and save session."""
        self._setup_browser(headless=False)
        page = self.browser_context.new_page()
        page.goto("https://studio.youtube.com")
        
        print("\n[INFO] Por favor, faça login na sua conta do YouTube no navegador aberto.")
        print("[INFO] Assim que o Studio carregar e você vir seu painel, você pode fechar o navegador.")
        
        try:
            # Espera até 10 minutos pelo login bem-sucedido
            page.wait_for_selector("#avatar-btn", timeout=600000)
            logger.info("Login detectado com sucesso.")
            time.sleep(5) # Garante que os cookies sejam salvos
        except Exception as e:
            logger.warning(f"Tempo limite de login excedido ou erro: {e}")
        finally:
            page.close()

    def upload_video(
        self, 
        file_path: str, 
        title: str, 
        description: str, 
        tags: Optional[List[str]] = None,
        publish_at: Optional[str] = None
    ) -> bool:
        """Uploads a video via YouTube Studio web interface."""
        if not os.path.exists(file_path):
            logger.error(f"Arquivo não encontrado: {file_path}")
            return False

        self._setup_browser(headless=False) # YouTube costuma bloquear headless total no upload
        page = self.browser_context.new_page()
        
        try:
            logger.info(f"Iniciando upload via Playwright: {title}")
            page.goto("https://studio.youtube.com")
            
            # Verifica se está logado
            try:
                page.wait_for_selector("#create-icon", timeout=15000)
            except TimeoutError:
                logger.error("Não logado no YouTube Studio. Por favor, faça login primeiro.")
                return False

            # 1. Clique em Criar -> Enviar Vídeos
            page.click("#create-icon")
            # O seletor do item de menu pode variar, vamos tentar pelo texto se falhar
            try:
                page.click("tp-yt-paper-item:has-text('Enviar vídeos')")
            except:
                page.click("#text-item-0") 
            
            # 2. Upload do arquivo
            page.wait_for_selector("input[type='file']")
            file_input = page.query_selector("input[type='file']")
            file_input.set_input_files(file_path)
            
            # 3. Preencher Detalhes (esperar carregar campos de texto)
            logger.info("Aguardando carregamento dos campos de detalhes...")
            page.wait_for_selector("#title-textarea", timeout=60000)
            
            # Título (YouTube às vezes coloca o nome do arquivo, limpamos primeiro)
            title_field = page.locator("#title-textarea #textbox")
            title_field.click()
            # Ctrl+A e Backspace para limpar
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            title_field.fill(title[:100])
            
            # Descrição
            desc_field = page.locator("#description-textarea #textbox")
            desc_field.fill(description[:5000])
            
            # Tags (Opcional - precisa clicar em 'MOSTRAR MAIS')
            if tags:
                try:
                    page.click("text=MOSTRAR MAIS")
                    page.wait_for_selector("input[aria-label='Tags']")
                    tags_field = page.locator("input[aria-label='Tags']")
                    tags_text = ",".join(tags)
                    tags_field.fill(tags_text)
                except:
                    logger.warning("Não foi possível preencher as tags.")

            # 'Não é conteúdo para crianças' (obrigatório)
            # Tenta múltiplos seletores pois o YouTube muda as vezes
            try:
                page.click("tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MADE_FOR_KIDS']")
            except:
                page.click("text=Não, não é conteúdo para crianças")
            
            # Avançar (Elementos de vídeo)
            page.click("#next-button")
            time.sleep(1)
            
            # Avançar (Verificações)
            page.click("#next-button")
            time.sleep(1)
            
            # Avançar (Visibilidade)
            page.click("#next-button")
            time.sleep(1)
            
            # 4. Visibilidade / Agendamento
            if publish_at:
                # O agendamento via Playwright é complexo (calendário/relógio).
                # Definimos como PRIVADO para que o usuário não poste algo fora de hora por engano,
                # mas avisamos claramente no log.
                logger.info(f"⚠️ Vídeo agendado para {publish_at}. Definindo como PRIVADO para ajuste manual no Studio.")
                try:
                    page.click("tp-yt-paper-radio-button[name='PRIVACY_PRIVATE']")
                except:
                    page.click("text=Privado")
            else:
                logger.info("Definindo vídeo como PÚBLICO para visibilidade imediata.")
                try:
                    # Rola a página para garantir que os botões estão visíveis
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1)
                    
                    # Tenta múltiplos seletores para garantir o 'Público'
                    public_selectors = [
                        "tp-yt-paper-radio-button[name='PRIVACY_PUBLIC']",
                        "text='Público'",
                        "text='Public'",
                        "#public-radio-button"
                    ]
                    
                    success_click = False
                    for selector in public_selectors:
                        try:
                            if page.is_visible(selector):
                                page.click(selector)
                                success_click = True
                                break
                        except:
                            continue
                            
                    if not success_click:
                        logger.warning("Não foi possível encontrar o botão 'Público' via seletores. Tentando clique forçado no rádio.")
                        page.locator("tp-yt-paper-radio-button").nth(2).click() # Geralmente o terceiro é o Público
                except Exception as e:
                    logger.warning(f"Erro ao selecionar visibilidade: {e}")
            
            # 5. Salvar / Publicar
            logger.info("Finalizando upload...")
            page.click("#done-button")
            
            # Esperar o modal fechar ou confirmação de upload
            # O YouTube mostra um modal de "Upload concluído" ou similar
            time.sleep(10) 
            
            logger.info(f"Upload via Playwright concluído com sucesso: {title}")
            return True
            
        except Exception as e:
            logger.error(f"Erro no upload via Playwright: {e}")
            try:
                page.screenshot(path=f"upload_error_{int(time.time())}.png")
            except:
                pass
            return False
        finally:
            page.close()

    def close(self):
        if self.browser_context:
            self.browser_context.close()
            self.browser_context = None
        if self.playwright:
            self.playwright.stop()
            self.playwright = None
