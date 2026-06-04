# -*- coding: utf-8 -*-
"""
uploader.py — Upload para o YouTube Studio via browser automatizado.

Engine principal : Playwright  (pip install playwright && playwright install chromium)
Engine fallback  : Selenium    (pip install selenium webdriver-manager)

Estratégia:
  - Usa um perfil de browser persistente (cookies/sessão salvos por canal).
  - Na primeira execução, abre o browser visível para você fazer login manualmente.
  - Nas execuções seguintes, reutiliza a sessão salva — sem precisar logar de novo.
  - Preenche todos os campos do YouTube Studio (título, descrição, tags, categoria,
    público, made for kids) como um humano faria.
  - Delays com jitter entre ações para não parecer automação.
  - Suporte a múltiplos canais via perfis separados.
"""

import os
import re
import time
import random
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("viral_cutter.uploader")

# ─── Config de paths ──────────────────────────────────────────────────────────

BASE_DIR      = Path(__file__).parent
PROFILES_DIR  = BASE_DIR / "browser_profiles"   # sessões salvas por canal
UPLOADS_URL   = "https://www.youtube.com/upload"
STUDIO_URL    = "https://studio.youtube.com"

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _jitter(lo: float = 0.4, hi: float = 1.2) -> float:
    """Retorna um delay aleatório entre lo e hi segundos."""
    return random.uniform(lo, hi)

def _human_type(element, text: str, delay_lo=0.04, delay_hi=0.12):
    """
    Digita texto caractere por caractere com delay variável.
    Só disponível no contexto Playwright — ver uso abaixo.
    """
    for ch in text:
        element.type(ch, delay=random.randint(int(delay_lo * 1000), int(delay_hi * 1000)))

def _build_description(job: dict) -> str:
    """Monta descrição a partir dos campos do operador."""
    parts = []
    if job.get("operator_notes"):
        parts.append(job["operator_notes"].strip())
        parts.append("")
    parts.append("#shorts")
    return "\n".join(parts)

def _build_tags(job: dict) -> list[str]:
    """Extrai tags/hashtags do campo operator_hashtags."""
    raw = job.get("operator_hashtags", "")
    return [t.strip().lstrip("#") for t in raw.replace(",", " ").split() if t.strip()]

def _build_title(job: dict, clip_path: str) -> str:
    return (
        job.get("operator_title")
        or Path(clip_path).stem
    )[:100]

def _profile_dir(profile: str) -> Path:
    d = PROFILES_DIR / profile
    d.mkdir(parents=True, exist_ok=True)
    return d


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE PLAYWRIGHT
# ══════════════════════════════════════════════════════════════════════════════

class PlaywrightUploader:
    """
    Faz upload via Playwright usando um perfil de browser persistente.

    Setup inicial (uma vez por máquina):
        pip install playwright
        playwright install chromium

    Primeiro uso por canal:
        Chame upload_video() com headless=False — o browser abre, você faz
        login normalmente no YouTube/Google, e a sessão é salva para sempre.
    """

    def __init__(
        self,
        profile: str = "default",
        headless: bool = True,
        slow_mo: int = 80,          # ms entre ações (simula humano)
        timeout: int = 60_000,      # ms timeout geral
    ):
        self.profile    = profile
        self.headless   = headless
        self.slow_mo    = slow_mo
        self.timeout    = timeout
        self._pw        = None
        self._browser   = None
        self._context   = None
        self._page      = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _start(self):
        from playwright.sync_api import sync_playwright
        self._pw      = sync_playwright().start()
        profile_path  = str(_profile_dir(self.profile))

        # persistent_context mantém cookies/localStorage entre sessões
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir = profile_path,
            headless      = self.headless,
            slow_mo       = self.slow_mo,
            args          = [
                "--disable-blink-features=AutomationControlled",  # oculta webdriver flag
                "--no-first-run",
                "--no-default-browser-check",
            ],
            viewport      = {"width": 1280, "height": 800},
            locale        = "pt-BR",
            timezone_id   = "America/Sao_Paulo",
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._page.set_default_timeout(self.timeout)

    def _stop(self):
        try:
            if self._context:
                self._context.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._pw = self._browser = self._context = self._page = None

    # ── Login guard ───────────────────────────────────────────────────────────

    def _ensure_logged_in(self):
        """
        Navega para o Studio. Se não estiver logado, abre visível
        e espera o usuário fazer login manualmente (até 3 minutos).
        """
        page = self._page
        page.goto(STUDIO_URL, wait_until="domcontentloaded")
        time.sleep(_jitter(1.5, 2.5))

        # Se redirecionou para accounts.google.com, não está logado
        if "accounts.google.com" in page.url or "signin" in page.url:
            if self.headless:
                # Reinicia visível para o usuário logar
                logger.warning(
                    f"⚠️  Perfil '{self.profile}' não está logado. "
                    "Reiniciando em modo visível para autenticação manual..."
                )
                self._stop()
                self.headless = False
                self._start()
                page = self._page
                page.goto(STUDIO_URL, wait_until="domcontentloaded")

            logger.info("🔐 Faça login no YouTube Studio. Aguardando (até 3 min)...")
            # Espera o Studio carregar após login
            page.wait_for_url(f"{STUDIO_URL}/**", timeout=180_000)
            logger.info(f"✅ Login concluído para perfil '{self.profile}'. Sessão salva.")

    # ── Upload ────────────────────────────────────────────────────────────────

    def upload_video(
        self,
        clip_path: str,
        title: str,
        description: str = "",
        tags: Optional[list] = None,
        privacy: str = "public",        # "public" | "unlisted" | "private"
        made_for_kids: bool = False,
    ) -> Optional[str]:
        """
        Faz o upload completo de um vídeo no YouTube Studio.
        Retorna o video_id do YouTube ou None em caso de falha.
        """
        if not os.path.exists(clip_path):
            logger.error(f"Arquivo não encontrado: {clip_path}")
            return None

        file_size_mb = os.path.getsize(clip_path) / 1024 / 1024
        logger.info(f"📤 [Playwright] Upload: {Path(clip_path).name} ({file_size_mb:.1f} MB)")

        try:
            self._start()
            self._ensure_logged_in()

            page  = self._page
            tags  = tags or []

            # ── 1. Abre o dialog de upload ────────────────────────────────────
            page.goto(STUDIO_URL, wait_until="domcontentloaded")
            time.sleep(_jitter(1.0, 2.0))

            # Clica no botão "Criar" ou vai direto para /upload
            upload_btn = page.locator("ytcp-button#create-icon, [aria-label='Criar'], button:has-text('Criar')")
            if upload_btn.count() > 0:
                upload_btn.first.click()
                time.sleep(_jitter(0.5, 1.0))
                # Seleciona "Enviar vídeos" no menu dropdown
                upload_option = page.locator("tp-yt-paper-item:has-text('Enviar'), [role='menuitem']:has-text('Enviar')")
                if upload_option.count() > 0:
                    upload_option.first.click()
                    time.sleep(_jitter(1.0, 1.5))
            else:
                page.goto(UPLOADS_URL, wait_until="domcontentloaded")
                time.sleep(_jitter(1.5, 2.5))

            # ── 2. Sobe o arquivo ─────────────────────────────────────────────
            file_input = page.locator("input[type='file']")
            file_input.set_input_files(clip_path)
            logger.info("📁 Arquivo selecionado. Aguardando processamento inicial...")
            time.sleep(_jitter(3.0, 5.0))

            # Aguarda o dialog de detalhes abrir
            page.wait_for_selector("ytcp-uploads-dialog, #dialog", timeout=30_000)
            time.sleep(_jitter(1.0, 2.0))

            # ── 3. Título ─────────────────────────────────────────────────────
            title_input = page.locator("#title-textarea #input, ytcp-form-input-container #textbox").first
            title_input.click()
            time.sleep(_jitter(0.3, 0.6))
            # Seleciona tudo e apaga (o YouTube pré-preenche com o nome do arquivo)
            title_input.press("Control+a")
            title_input.press("Backspace")
            time.sleep(_jitter(0.2, 0.4))
            _human_type(title_input, title)
            time.sleep(_jitter(0.4, 0.8))

            # ── 4. Descrição ──────────────────────────────────────────────────
            if description:
                desc_input = page.locator("#description-textarea #input, ytcp-form-input-container #textbox").nth(1)
                desc_input.click()
                time.sleep(_jitter(0.3, 0.6))
                _human_type(desc_input, description)
                time.sleep(_jitter(0.4, 0.8))

            # ── 5. Made for kids ──────────────────────────────────────────────
            if made_for_kids:
                kids_yes = page.locator("#made-for-kids-group tp-yt-paper-radio-button[name='MADE_FOR_KIDS']")
                if kids_yes.count() > 0:
                    kids_yes.click()
            else:
                kids_no = page.locator("#made-for-kids-group tp-yt-paper-radio-button[name='NOT_MADE_FOR_KIDS']")
                if kids_no.count() > 0:
                    kids_no.click()
            time.sleep(_jitter(0.3, 0.6))

            # ── 6. Mais opções (tags) ─────────────────────────────────────────
            if tags:
                more_options = page.locator("ytcp-button#toggle-button, button:has-text('Mais opções')")
                if more_options.count() > 0:
                    more_options.first.click()
                    time.sleep(_jitter(0.8, 1.5))

                    tags_input = page.locator("input[placeholder*='tag'], ytcp-free-text-chip-bar input")
                    if tags_input.count() > 0:
                        for tag in tags[:30]:   # YouTube suporta até 500 chars de tags totais
                            tags_input.first.type(tag, delay=50)
                            tags_input.first.press("Enter")
                            time.sleep(_jitter(0.1, 0.3))

            time.sleep(_jitter(0.5, 1.0))

            # ── 7. Avança para tela de visibilidade (2 cliques em "Próximo") ──
            for step_label in ["Próximo", "Próximo", "Próximo"]:
                next_btn = page.locator(f"ytcp-button#next-button, button:has-text('{step_label}')")
                if next_btn.count() > 0:
                    next_btn.first.click()
                    time.sleep(_jitter(1.0, 2.0))

            # ── 8. Visibilidade ───────────────────────────────────────────────
            privacy_map = {
                "public":   "PUBLIC",
                "unlisted": "UNLISTED",
                "private":  "PRIVATE",
            }
            privacy_val = privacy_map.get(privacy, "PUBLIC")
            visibility_radio = page.locator(f"tp-yt-paper-radio-button[name='{privacy_val}']")
            if visibility_radio.count() > 0:
                visibility_radio.click()
                time.sleep(_jitter(0.5, 1.0))

            # ── 9. Publicar ───────────────────────────────────────────────────
            publish_btn = page.locator("ytcp-button#done-button, button:has-text('Publicar'), button:has-text('Salvar')")
            publish_btn.first.click()
            logger.info("🚀 Botão Publicar clicado. Aguardando confirmação...")
            time.sleep(_jitter(3.0, 6.0))

            # ── 10. Extrai o video_id da URL de confirmação ───────────────────
            yt_video_id = None
            try:
                page.wait_for_url(r".*studio\.youtube\.com/video/*/edit*", timeout=20_000)
                match = re.search(r"/video/([a-zA-Z0-9_-]{8,})/", page.url)
                if match:
                    yt_video_id = match.group(1)
            except Exception:
                # Tenta extrair de links de confirmação no dialog
                links = page.locator("a[href*='youtube.com/watch'], a[href*='youtu.be']")
                if links.count() > 0:
                    href = links.first.get_attribute("href") or ""
                    match = re.search(r"[?&v=]([a-zA-Z0-9_-]{8,})|youtu\.be/([a-zA-Z0-9_-]{8,})", href)
                    if match:
                        yt_video_id = match.group(1) or match.group(2)

            if yt_video_id:
                logger.info(f"✅ Publicado! https://youtube.com/shorts/{yt_video_id}")
            else:
                logger.warning("⚠️ Upload concluído mas não conseguiu extrair o video_id.")

            return yt_video_id

        except Exception as e:
            logger.error(f"❌ Erro no upload via Playwright: {e}", exc_info=True)
            return None
        finally:
            self._stop()


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE SELENIUM (fallback)
# ══════════════════════════════════════════════════════════════════════════════

class SeleniumUploader:
    """
    Fallback para Playwright — mesma lógica, usando Selenium + ChromeDriver.

    Setup:
        pip install selenium webdriver-manager

    Usa um user-data-dir persistente (igual ao Playwright), então o login
    também é feito só uma vez por perfil.
    """

    def __init__(
        self,
        profile: str = "default",
        headless: bool = True,
        timeout: int = 60,
    ):
        self.profile  = profile
        self.headless = headless
        self.timeout  = timeout
        self._driver  = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _start(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager

        profile_path = str(_profile_dir(self.profile))
        opts = Options()

        if self.headless:
            opts.add_argument("--headless=new")

        opts.add_argument(f"--user-data-dir={profile_path}")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_argument("--window-size=1280,800")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)

        service = Service(ChromeDriverManager().install())
        self._driver = webdriver.Chrome(service=service, options=opts)
        self._driver.implicitly_wait(self.timeout)
        # Remove a flag navigator.webdriver
        self._driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

    def _stop(self):
        try:
            if self._driver:
                self._driver.quit()
        except Exception:
            pass
        self._driver = None

    def _wait_for(self, by, selector, timeout=None):
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        t = timeout or self.timeout
        return WebDriverWait(self._driver, t).until(
            EC.presence_of_element_located((by, selector))
        )

    def _slow_type(self, element, text: str):
        """Digita com delay humano."""
        for ch in text:
            element.send_keys(ch)
            time.sleep(random.uniform(0.04, 0.12))

    # ── Login guard ───────────────────────────────────────────────────────────

    def _ensure_logged_in(self):
        self._driver.get(STUDIO_URL)
        time.sleep(_jitter(2.0, 3.0))

        if "accounts.google.com" in self._driver.current_url or "signin" in self._driver.current_url:
            if self.headless:
                logger.warning(
                    f"⚠️  Perfil '{self.profile}' não logado. "
                    "Reiniciando em modo visível para autenticação manual..."
                )
                self._stop()
                self.headless = False
                self._start()
                self._driver.get(STUDIO_URL)

            logger.info("🔐 Faça login no YouTube Studio. Aguardando (até 3 min)...")
            from selenium.webdriver.support.ui import WebDriverWait
            WebDriverWait(self._driver, 180).until(
                lambda d: STUDIO_URL in d.current_url and "accounts.google" not in d.current_url
            )
            logger.info(f"✅ Login concluído para perfil '{self.profile}'. Sessão salva.")

    # ── Upload ────────────────────────────────────────────────────────────────

    def upload_video(
        self,
        clip_path: str,
        title: str,
        description: str = "",
        tags: Optional[list] = None,
        privacy: str = "public",
        made_for_kids: bool = False,
    ) -> Optional[str]:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys

        if not os.path.exists(clip_path):
            logger.error(f"Arquivo não encontrado: {clip_path}")
            return None

        file_size_mb = os.path.getsize(clip_path) / 1024 / 1024
        logger.info(f"📤 [Selenium] Upload: {Path(clip_path).name} ({file_size_mb:.1f} MB)")

        try:
            self._start()
            self._ensure_logged_in()

            tags = tags or []
            driver = self._driver

            # ── 1. Abre upload ────────────────────────────────────────────────
            driver.get(STUDIO_URL)
            time.sleep(_jitter(1.5, 2.5))

            # Seleciona o input de arquivo (pode estar oculto)
            file_input = self._wait_for(By.CSS_SELECTOR, "input[type='file']")
            file_input.send_keys(os.path.abspath(clip_path))
            logger.info("📁 Arquivo selecionado.")
            time.sleep(_jitter(3.0, 5.0))

            # ── 2. Título ─────────────────────────────────────────────────────
            title_el = self._wait_for(By.CSS_SELECTOR, "#title-textarea #input")
            title_el.click()
            title_el.send_keys(Keys.CONTROL + "a")
            title_el.send_keys(Keys.BACKSPACE)
            time.sleep(_jitter(0.2, 0.4))
            self._slow_type(title_el, title)
            time.sleep(_jitter(0.4, 0.8))

            # ── 3. Descrição ──────────────────────────────────────────────────
            if description:
                desc_els = driver.find_elements(By.CSS_SELECTOR, "#description-textarea #input")
                if desc_els:
                    desc_els[0].click()
                    self._slow_type(desc_els[0], description)
                    time.sleep(_jitter(0.4, 0.8))

            # ── 4. Made for kids ──────────────────────────────────────────────
            kids_selector = (
                "tp-yt-paper-radio-button[name='MADE_FOR_KIDS']"
                if made_for_kids else
                "tp-yt-paper-radio-button[name='NOT_MADE_FOR_KIDS']"
            )
            kids_els = driver.find_elements(By.CSS_SELECTOR, kids_selector)
            if kids_els:
                kids_els[0].click()
            time.sleep(_jitter(0.3, 0.6))

            # ── 5. Mais opções / Tags ─────────────────────────────────────────
            if tags:
                more_btns = driver.find_elements(By.CSS_SELECTOR, "ytcp-button#toggle-button")
                if more_btns:
                    more_btns[0].click()
                    time.sleep(_jitter(0.8, 1.5))

                    tag_inputs = driver.find_elements(By.CSS_SELECTOR, "ytcp-free-text-chip-bar input")
                    if tag_inputs:
                        for tag in tags[:30]:
                            tag_inputs[0].send_keys(tag)
                            tag_inputs[0].send_keys(Keys.ENTER)
                            time.sleep(_jitter(0.1, 0.3))

            time.sleep(_jitter(0.5, 1.0))

            # ── 6. Avança pelas telas ─────────────────────────────────────────
            for _ in range(3):
                next_btns = driver.find_elements(By.CSS_SELECTOR, "ytcp-button#next-button")
                if next_btns:
                    next_btns[0].click()
                    time.sleep(_jitter(1.0, 2.0))

            # ── 7. Visibilidade ───────────────────────────────────────────────
            privacy_map = {"public": "PUBLIC", "unlisted": "UNLISTED", "private": "PRIVATE"}
            privacy_val = privacy_map.get(privacy, "PUBLIC")
            radio_els = driver.find_elements(By.CSS_SELECTOR, f"tp-yt-paper-radio-button[name='{privacy_val}']")
            if radio_els:
                radio_els[0].click()
            time.sleep(_jitter(0.5, 1.0))

            # ── 8. Publicar ───────────────────────────────────────────────────
            done_btns = driver.find_elements(By.CSS_SELECTOR, "ytcp-button#done-button")
            if done_btns:
                done_btns[0].click()
            logger.info("🚀 Botão Publicar clicado.")
            time.sleep(_jitter(4.0, 7.0))

            # ── 9. Extrai video_id ────────────────────────────────────────────
            yt_video_id = None
            match = re.search(r"/video/([a-zA-Z0-9_-]{8,})/", driver.current_url)
            if match:
                yt_video_id = match.group(1)
            else:
                links = driver.find_elements(By.CSS_SELECTOR, "a[href*='youtube.com/watch'], a[href*='youtu.be']")
                for link in links:
                    href = link.get_attribute("href") or ""
                    m = re.search(r"[?&v=]([a-zA-Z0-9_-]{8,})|youtu\.be/([a-zA-Z0-9_-]{8,})", href)
                    if m:
                        yt_video_id = m.group(1) or m.group(2)
                        break

            if yt_video_id:
                logger.info(f"✅ Publicado! https://youtube.com/shorts/{yt_video_id}")
            else:
                logger.warning("⚠️ Upload concluído mas não conseguiu extrair o video_id.")

            return yt_video_id

        except Exception as e:
            logger.error(f"❌ Erro no upload via Selenium: {e}", exc_info=True)
            return None
        finally:
            self._stop()


# ══════════════════════════════════════════════════════════════════════════════
# INTERFACE UNIFICADA (usada pelo ClipWorker)
# ══════════════════════════════════════════════════════════════════════════════

class VideoUploader:
    """
    Interface de alto nível para o ClipWorker.
    Tenta Playwright primeiro; cai para Selenium se não disponível.

    Uso no ClipWorker:
        self.uploader = VideoUploader(profile="meu_canal", interval_seconds=300)
        yt_id = self.uploader.upload_after_render(job, final_clip_path)
    """

    def __init__(
        self,
        profile: str = "default",
        engine: str = "auto",           # "playwright" | "selenium" | "auto"
        headless: bool = True,
        privacy: str = "public",
        made_for_kids: bool = False,
        interval_seconds: float = 0.0,  # delay entre uploads (0 = sem espera)
    ):
        self.profile           = profile
        self.privacy           = privacy
        self.made_for_kids     = made_for_kids
        self.interval_seconds  = interval_seconds
        self._last_upload_at   = 0.0
        self._engine_cls       = self._resolve_engine(engine, headless)

    def _resolve_engine(self, engine: str, headless: bool):
        if engine == "playwright":
            return lambda: PlaywrightUploader(profile=self.profile, headless=headless)
        if engine == "selenium":
            return lambda: SeleniumUploader(profile=self.profile, headless=headless)

        # auto: tenta Playwright, cai para Selenium
        try:
            import playwright  # noqa: F401
            logger.info("🎭 Engine: Playwright")
            return lambda: PlaywrightUploader(profile=self.profile, headless=headless)
        except ImportError:
            pass
        try:
            import selenium  # noqa: F401
            logger.info("🌐 Engine: Selenium (fallback)")
            return lambda: SeleniumUploader(profile=self.profile, headless=headless)
        except ImportError:
            raise RuntimeError(
                "Nenhum engine de browser disponível.\n"
                "Instale: pip install playwright && playwright install chromium\n"
                "      ou: pip install selenium webdriver-manager"
            )

    def _respect_interval(self):
        if self.interval_seconds <= 0:
            return
        elapsed   = time.time() - self._last_upload_at
        remaining = self.interval_seconds - elapsed
        if remaining > 0:
            wait = remaining + random.uniform(-remaining * 0.2, remaining * 0.2)
            wait = max(1.0, wait)
            logger.info(f"⏳ Aguardando {wait:.0f}s antes do próximo upload...")
            time.sleep(wait)

    def upload_after_render(
        self,
        job: dict,
        clip_path: str,
        extra_metadata: Optional[dict] = None,
    ) -> Optional[str]:
        """
        Ponto de entrada principal — chamado pelo ClipWorker após render concluído.

        Parâmetros:
            job           : dict do job (campos: operator_title, operator_notes,
                            operator_hashtags, video_id, start_time, end_time)
            clip_path     : caminho absoluto do .mp4 renderizado
            extra_metadata: override opcional de title/description/tags

        Retorna o youtube_video_id ou None.
        """
        if not clip_path or not os.path.exists(clip_path):
            logger.error(f"upload_after_render: arquivo não existe: {clip_path}")
            return None

        title       = _build_title(job, clip_path)
        description = _build_description(job)
        tags        = _build_tags(job)

        if extra_metadata:
            title       = extra_metadata.get("title", title)
            description = extra_metadata.get("description", description)
            tags        = extra_metadata.get("tags", tags)

        self._respect_interval()

        uploader = self._engine_cls()
        yt_id = uploader.upload_video(
            clip_path   = clip_path,
            title       = title,
            description = description,
            tags        = tags,
            privacy     = self.privacy,
            made_for_kids = self.made_for_kids,
        )

        self._last_upload_at = time.time()
        return yt_id


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRAÇÃO NO ClipWorker  (copiar para clip_worker.py)
# ══════════════════════════════════════════════════════════════════════════════
#
# from uploader import VideoUploader
#
# class ClipWorker:
#     def __init__(self, ..., upload_enabled=False, upload_profile="default",
#                  upload_engine="auto", upload_headless=True, interval_seconds=300):
#         ...
#         self.upload_enabled = upload_enabled
#         self.uploader = VideoUploader(
#             profile          = upload_profile,
#             engine           = upload_engine,   # "playwright" | "selenium" | "auto"
#             headless         = upload_headless,
#             privacy          = "public",
#             interval_seconds = interval_seconds,
#         )
#
#     def process_job(self, job):
#         ...
#         if os.path.exists(final_clip_path):
#             database.update_job_status(job_id, "DONE", output_path=final_clip_path, metrics=metrics)
#
#             if self.upload_enabled or job.get("upload_after_render"):
#                 database.update_job_status(job_id, "UPLOADING")
#                 yt_id = self.uploader.upload_after_render(job, final_clip_path)
#                 if yt_id:
#                     database.update_job_youtube_id(job_id, yt_id)
#                     database.update_job_status(job_id, "PUBLISHED")
#                     logger.info(f"🎬 https://youtube.com/shorts/{yt_id}")
#                 else:
#                     logger.warning(f"⚠️ Upload falhou (job {job_id})")