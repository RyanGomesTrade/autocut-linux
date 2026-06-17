# -*- coding: utf-8 -*-
"""
uploader.py — Upload para YouTube Studio via browser automatizado.

Engine principal : Playwright  (pip install playwright && playwright install chromium)
Engine fallback  : Selenium    (pip install selenium webdriver-manager)

Anti-detecção:
  - CDP / JS patches que removem todas as flags de webdriver ANTES do primeiro request
  - User-Agent rotativo (pool de UAs reais do Chrome em Windows/Mac)
  - Mouse com trajetória Bézier (movimento humano simulado)
  - Delays com distribuição gaussiana (não-uniforme)
  - Scroll suave antes de interagir com elementos
  - Sem --disable-blink-features (flag suspeita)
  - navigator.plugins, navigator.languages, WebGL, canvas spoofing via JS
  - Sem slow_mo fixo (substituído por delays gaussianos por ação)
"""

import os
import re
import time
import math
import random
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("viral_cutter.uploader")

BASE_DIR     = Path(__file__).parent
PROFILES_DIR = BASE_DIR / "browser_profiles"
STUDIO_URL   = "https://studio.youtube.com"
UPLOADS_URL  = "https://www.youtube.com/upload"

# ─── Pool de User-Agents reais ────────────────────────────────────────────────

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# ─── JS injetado para zerar todas as flags de automação ──────────────────────

_STEALTH_JS = """
// Remove webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Plugins realistas (Chrome real tem vários)
Object.defineProperty(navigator, 'plugins', {
  get: () => {
    const plugins = [
      { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
      { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
      { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
    ];
    plugins.__proto__ = PluginArray.prototype;
    return plugins;
  }
});

// Linguagens
Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US', 'en'] });

// Hardware concurrency realista
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });

// DeviceMemory
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

// Permission query patch (Notification)
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
  parameters.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : originalQuery(parameters)
);

// Chrome runtime patch
window.chrome = {
  app: { isInstalled: false },
  webstore: { onInstallStageChanged: {}, onDownloadProgress: {} },
  runtime: {
    PlatformOs: { MAC: 'mac', WIN: 'win', ANDROID: 'android', CROS: 'cros', LINUX: 'linux', OPENBSD: 'openbsd' },
    PlatformArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
    RequestUpdateCheckStatus: { THROTTLED: 'throttled', NO_UPDATE: 'no_update', UPDATE_AVAILABLE: 'update_available' },
    OnInstalledReason: { INSTALL: 'install', UPDATE: 'update', CHROME_UPDATE: 'chrome_update', SHARED_MODULE_UPDATE: 'shared_module_update' },
    OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
    connect: () => {},
    sendMessage: () => {},
  },
};

// WebGL vendor/renderer realista
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
  if (parameter === 37445) return 'Intel Inc.';
  if (parameter === 37446) return 'Intel Iris OpenGL Engine';
  return getParameter.call(this, parameter);
};
"""

# ─── Helpers de comportamento humano ─────────────────────────────────────────

def _gauss_delay(mean: float = 0.6, sigma: float = 0.15, min_val: float = 0.15) -> float:
    """Delay gaussiano — muito mais humano que uniform()."""
    return max(min_val, random.gauss(mean, sigma))


def _bezier_mouse_path(x0, y0, x1, y1, steps=None):
    """
    Gera pontos de trajetória Bézier cúbica entre dois pontos.
    Simula o movimento natural do mouse humano.
    """
    if steps is None:
        dist = math.hypot(x1 - x0, y1 - y0)
        steps = max(8, int(dist / 12))

    # Pontos de controle aleatórios (curvatura natural)
    cx1 = x0 + random.uniform(0.1, 0.4) * (x1 - x0) + random.uniform(-40, 40)
    cy1 = y0 + random.uniform(0.1, 0.4) * (y1 - y0) + random.uniform(-40, 40)
    cx2 = x0 + random.uniform(0.6, 0.9) * (x1 - x0) + random.uniform(-40, 40)
    cy2 = y0 + random.uniform(0.6, 0.9) * (y1 - y0) + random.uniform(-40, 40)

    points = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt**3*x0 + 3*mt**2*t*cx1 + 3*mt*t**2*cx2 + t**3*x1
        y = mt**3*y0 + 3*mt**2*t*cy1 + 3*mt*t**2*cy2 + t**3*y1
        points.append((x, y))
    return points


def _profile_dir(profile: str) -> Path:
    d = PROFILES_DIR / profile
    d.mkdir(parents=True, exist_ok=True)
    return d


def _build_title(job: dict, clip_path: str) -> str:
    return (job.get("operator_title") or Path(clip_path).stem)[:100]


def _build_description(job: dict) -> str:
    parts = []
    if job.get("operator_notes"):
        parts.append(job["operator_notes"].strip())
        parts.append("")
    parts.append("#shorts")
    return "\n".join(parts)


def _build_tags(job: dict) -> list:
    raw = job.get("operator_hashtags", "")
    return [t.strip().lstrip("#") for t in raw.replace(",", " ").split() if t.strip()]


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE PLAYWRIGHT (principal)
# ══════════════════════════════════════════════════════════════════════════════

class PlaywrightUploader:
    """
    Upload via Playwright com máxima furtividade.

    Técnicas anti-detecção aplicadas:
    - JS stealth injetado via addInitScript (roda ANTES de qualquer JS da página)
    - User-Agent rotativo do pool de UAs reais
    - Mouse com trajetória Bézier
    - Delays gaussianos por ação
    - Scroll suave antes de clicar
    - Sem --disable-blink-features
    - Sem slow_mo fixo
    """

    def __init__(
        self,
        profile: str = "default",
        headless: bool = True,
        timeout: int = 60_000,
    ):
        self.profile   = profile
        self.headless  = headless
        self.timeout   = timeout
        self._pw       = None
        self._context  = None
        self._page     = None
        self._ua       = random.choice(_USER_AGENTS)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _start(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        profile_path = str(_profile_dir(self.profile))

        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir = profile_path,
            headless      = self.headless,
            # SEM slow_mo fixo — usamos delays gaussianos manualmente
            args = [
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
                "--disable-notifications",
                "--disable-popup-blocking",
                "--start-maximized",
            ],
            user_agent  = self._ua,
            viewport    = {"width": random.randint(1280, 1440), "height": random.randint(768, 900)},
            locale      = "pt-BR",
            timezone_id = "America/Sao_Paulo",
            geolocation = {"longitude": -46.63, "latitude": -23.55},  # São Paulo
            permissions = ["geolocation"],
            color_scheme = "light",
        )

        # Injeta stealth JS em TODAS as páginas antes do primeiro script
        self._context.add_init_script(_STEALTH_JS)

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
        self._pw = self._context = self._page = None

    # ── Ações humanas ─────────────────────────────────────────────────────────

    def _move_mouse_to(self, x: float, y: float):
        """Move o mouse com trajetória Bézier."""
        try:
            cur = self._page.evaluate("() => ({ x: window.__mouseX || 640, y: window.__mouseY || 400 })")
            x0, y0 = cur.get("x", 640), cur.get("y", 400)
        except Exception:
            x0, y0 = random.randint(200, 800), random.randint(200, 600)

        points = _bezier_mouse_path(x0, y0, x, y)
        for px, py in points:
            self._page.mouse.move(px, py)
            time.sleep(random.uniform(0.002, 0.008))

    def _human_click(self, locator):
        """Scroll até o elemento, move o mouse com Bézier e clica."""
        locator.scroll_into_view_if_needed()
        time.sleep(_gauss_delay(0.3, 0.1))

        box = locator.bounding_box()
        if box:
            # Clica em ponto aleatório dentro do elemento (não sempre no centro)
            tx = box["x"] + box["width"]  * random.uniform(0.3, 0.7)
            ty = box["y"] + box["height"] * random.uniform(0.3, 0.7)
            self._move_mouse_to(tx, ty)
            time.sleep(_gauss_delay(0.15, 0.05))
            self._page.mouse.click(tx, ty)
        else:
            locator.click()

        time.sleep(_gauss_delay(0.4, 0.15))

    def _human_type(self, locator, text: str):
        """Digita com delay gaussiano por caractere e pequenas pausas entre palavras."""
        locator.click()
        time.sleep(_gauss_delay(0.2, 0.08))
        locator.press("Control+a")
        time.sleep(_gauss_delay(0.1, 0.04))
        locator.press("Backspace")
        time.sleep(_gauss_delay(0.2, 0.08))

        for i, ch in enumerate(text):
            locator.type(ch, delay=random.randint(40, 140))
            # Pausa maior após espaço (fim de palavra) — comportamento humano
            if ch == " ":
                time.sleep(_gauss_delay(0.08, 0.03))
            # Micro-pausa ocasional (pensar antes de continuar)
            if i > 0 and i % random.randint(8, 20) == 0:
                time.sleep(_gauss_delay(0.3, 0.12))

    def _scroll_page(self, amount: int = None):
        """Scroll suave aleatório na página."""
        if amount is None:
            amount = random.randint(100, 400)
        self._page.evaluate(f"window.scrollBy({{top: {amount}, behavior: 'smooth'}})")
        time.sleep(_gauss_delay(0.5, 0.15))

    # ── Login guard ───────────────────────────────────────────────────────────

    def _ensure_logged_in(self):
        page = self._page
        page.goto(STUDIO_URL, wait_until="domcontentloaded")
        time.sleep(_gauss_delay(2.0, 0.4))

        if "accounts.google.com" in page.url or "signin" in page.url:
            if self.headless:
                logger.warning(f"⚠️ Perfil '{self.profile}' não logado. Reabrindo visível...")
                self._stop()
                self.headless = False
                self._start()
                page = self._page
                page.goto(STUDIO_URL, wait_until="domcontentloaded")

            logger.info("🔐 Faça login no YouTube Studio. Aguardando (até 3 min)...")
            page.wait_for_url(f"{STUDIO_URL}/**", timeout=180_000)
            logger.info(f"✅ Login concluído para '{self.profile}'.")

    def login(self):
        """Abre o browser para login manual e salva a sessão."""
        self.headless = False
        try:
            self._start()
            self._ensure_logged_in()
            logger.info("✅ Sessão salva. Pode fechar o browser.")
            time.sleep(3)
        finally:
            self._stop()

    def reset_session(self) -> bool:
        """Remove cookies salvos do perfil."""
        import shutil
        profile_path = _profile_dir(self.profile)
        try:
            shutil.rmtree(profile_path)
            profile_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Sessão do perfil '{self.profile}' limpa.")
            return True
        except Exception as e:
            logger.error(f"Erro ao limpar sessão: {e}")
            return False

    # ── Upload principal ──────────────────────────────────────────────────────

    def upload_video(
        self,
        clip_path: str,
        title: str,
        description: str = "",
        tags: Optional[list] = None,
        privacy: str = "public",
        made_for_kids: bool = False,
    ) -> Optional[str]:
        if not os.path.exists(clip_path):
            logger.error(f"Arquivo não encontrado: {clip_path}")
            return None

        size_mb = os.path.getsize(clip_path) / 1024 / 1024
        logger.info(f"📤 [Playwright] {Path(clip_path).name} ({size_mb:.1f} MB) → {title[:50]}")

        try:
            self._start()
            self._ensure_logged_in()
            page = self._page
            tags = tags or []

            # Simula navegação prévia (não vai direto para o upload)
            time.sleep(_gauss_delay(1.2, 0.3))
            self._scroll_page(random.randint(50, 200))
            time.sleep(_gauss_delay(0.8, 0.2))

            # ── 1. Abre upload ────────────────────────────────────────────────
            page.goto(STUDIO_URL, wait_until="domcontentloaded")
            time.sleep(_gauss_delay(2.0, 0.5))

            create_btn = page.locator("ytcp-button#create-icon, [aria-label='Criar'], button:has-text('Criar')")
            if create_btn.count() > 0:
                self._human_click(create_btn.first)
                time.sleep(_gauss_delay(0.6, 0.15))
                upload_opt = page.locator("tp-yt-paper-item:has-text('Enviar'), [role='menuitem']:has-text('Enviar')")
                if upload_opt.count() > 0:
                    self._human_click(upload_opt.first)
                    time.sleep(_gauss_delay(1.2, 0.3))
            else:
                page.goto(UPLOADS_URL, wait_until="domcontentloaded")
                time.sleep(_gauss_delay(2.0, 0.5))

            # ── 2. Sobe o arquivo ─────────────────────────────────────────────
            file_input = page.locator("input[type='file']")
            file_input.set_input_files(clip_path)
            logger.info("📁 Arquivo enviado. Aguardando dialog de detalhes...")
            # Aguarda o dialog abrir (tempo proporcional ao tamanho)
            wait_upload = _gauss_delay(4.0 + size_mb * 0.05, 1.0)
            time.sleep(wait_upload)
            page.wait_for_selector("ytcp-uploads-dialog, #dialog", timeout=45_000)
            time.sleep(_gauss_delay(1.5, 0.4))

            # ── 3. Título ─────────────────────────────────────────────────────
            title_input = page.locator("#title-textarea #input, ytcp-form-input-container #textbox").first
            self._human_type(title_input, title)

            # ── 4. Descrição ──────────────────────────────────────────────────
            if description:
                time.sleep(_gauss_delay(0.5, 0.15))
                desc_input = page.locator("#description-textarea #input, ytcp-form-input-container #textbox").nth(1)
                self._human_type(desc_input, description)

            # ── 5. Made for kids ──────────────────────────────────────────────
            time.sleep(_gauss_delay(0.6, 0.15))
            kids_sel = "MADE_FOR_KIDS" if made_for_kids else "NOT_MADE_FOR_KIDS"
            kids_btn = page.locator(f"tp-yt-paper-radio-button[name='{kids_sel}']")
            if kids_btn.count() > 0:
                self._human_click(kids_btn.first)

            # ── 6. Tags (Mais opções) ─────────────────────────────────────────
            if tags:
                time.sleep(_gauss_delay(0.8, 0.2))
                more_btn = page.locator("ytcp-button#toggle-button, button:has-text('Mais opções')")
                if more_btn.count() > 0:
                    self._human_click(more_btn.first)
                    time.sleep(_gauss_delay(1.0, 0.25))

                    tag_input = page.locator("input[placeholder*='tag'], ytcp-free-text-chip-bar input")
                    if tag_input.count() > 0:
                        for tag in tags[:30]:
                            tag_input.first.type(tag, delay=random.randint(50, 120))
                            tag_input.first.press("Enter")
                            time.sleep(_gauss_delay(0.2, 0.07))

            # ── 7. Avança pelas telas (3× Próximo) ───────────────────────────
            for _ in range(3):
                time.sleep(_gauss_delay(1.2, 0.3))
                next_btn = page.locator("ytcp-button#next-button")
                if next_btn.count() > 0:
                    self._human_click(next_btn.first)

            # ── 8. Visibilidade ───────────────────────────────────────────────
            time.sleep(_gauss_delay(1.0, 0.25))
            privacy_map = {"public": "PUBLIC", "unlisted": "UNLISTED", "private": "PRIVATE"}
            vis_radio = page.locator(f"tp-yt-paper-radio-button[name='{privacy_map.get(privacy, 'PUBLIC')}']")
            if vis_radio.count() > 0:
                self._human_click(vis_radio.first)

            # ── 9. Publicar ───────────────────────────────────────────────────
            time.sleep(_gauss_delay(1.0, 0.3))
            publish_btn = page.locator("ytcp-button#done-button, button:has-text('Publicar'), button:has-text('Salvar')")
            self._human_click(publish_btn.first)
            logger.info("🚀 Publicando...")
            time.sleep(_gauss_delay(5.0, 1.2))

            # ── 10. Extrai video_id ───────────────────────────────────────────
            yt_id = None
            try:
                page.wait_for_url(r".*studio\.youtube\.com/video/*/edit*", timeout=25_000)
                m = re.search(r"/video/([a-zA-Z0-9_-]{8,})/", page.url)
                if m:
                    yt_id = m.group(1)
            except Exception:
                links = page.locator("a[href*='youtube.com/watch'], a[href*='youtu.be']")
                if links.count() > 0:
                    href = links.first.get_attribute("href") or ""
                    m = re.search(r"[?&v=]([a-zA-Z0-9_-]{8,})|youtu\.be/([a-zA-Z0-9_-]{8,})", href)
                    if m:
                        yt_id = m.group(1) or m.group(2)

            if yt_id:
                logger.info(f"✅ Publicado: https://youtube.com/shorts/{yt_id}")
            else:
                logger.warning("⚠️ Upload concluído mas não extraiu o video_id.")

            return yt_id

        except Exception as e:
            logger.error(f"❌ Erro no upload: {e}", exc_info=True)
            return None
        finally:
            self._stop()

    def close(self):
        self._stop()


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE SELENIUM (fallback)
# ══════════════════════════════════════════════════════════════════════════════

class SeleniumUploader:
    """
    Fallback com Selenium + undetected-chromedriver (recomendado sobre webdriver-manager).

    pip install undetected-chromedriver
    """

    def __init__(
        self,
        profile: str = "default",
        headless: bool = False,   # headless é detectável no Selenium — use False
        timeout: int = 60,
    ):
        self.profile  = profile
        self.headless = headless
        self.timeout  = timeout
        self._driver  = None
        self._ua      = random.choice(_USER_AGENTS)

    def _start(self):
        try:
            # undetected-chromedriver é muito mais furtivo que selenium puro
            import undetected_chromedriver as uc
            profile_path = str(_profile_dir(self.profile))

            opts = uc.ChromeOptions()
            opts.add_argument(f"--user-data-dir={profile_path}")
            opts.add_argument("--no-first-run")
            opts.add_argument("--no-default-browser-check")
            opts.add_argument("--disable-notifications")
            opts.add_argument(f"--window-size={random.randint(1280,1440)},{random.randint(768,900)}")
            opts.add_argument(f"--lang=pt-BR")

            self._driver = uc.Chrome(options=opts, headless=self.headless)
            self._driver.implicitly_wait(self.timeout)

            # Injeta stealth JS logo após iniciar
            self._driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": _STEALTH_JS
            })

        except ImportError:
            # Fallback: selenium puro com patches manuais
            logger.warning("undetected-chromedriver não encontrado. Usando selenium puro (menos furtivo).")
            logger.warning("Instale com: pip install undetected-chromedriver")
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            from webdriver_manager.chrome import ChromeDriverManager

            profile_path = str(_profile_dir(self.profile))
            opts = Options()
            if self.headless:
                opts.add_argument("--headless=new")

            opts.add_argument(f"--user-data-dir={profile_path}")
            opts.add_argument("--no-first-run")
            opts.add_argument("--no-default-browser-check")
            opts.add_argument("--disable-notifications")
            opts.add_argument(f"--user-agent={self._ua}")
            opts.add_argument(f"--window-size={random.randint(1280,1440)},{random.randint(768,900)}")
            opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            opts.add_experimental_option("useAutomationExtension", False)

            service = Service(ChromeDriverManager().install())
            self._driver = webdriver.Chrome(service=service, options=opts)
            self._driver.implicitly_wait(self.timeout)

            # Patches via CDP
            self._driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": _STEALTH_JS
            })
            self._driver.execute_cdp_cmd("Network.setUserAgentOverride", {
                "userAgent": self._ua
            })

    def _stop(self):
        try:
            if self._driver:
                self._driver.quit()
        except Exception:
            pass
        self._driver = None

    def _move_mouse_to(self, element):
        """Move o mouse com ActionChains simulando trajetória humana."""
        from selenium.webdriver.common.action_chains import ActionChains
        try:
            loc = element.location
            size = element.size
            tx = loc["x"] + size["width"]  * random.uniform(0.3, 0.7)
            ty = loc["y"] + size["height"] * random.uniform(0.3, 0.7)

            # Move em etapas com offsets aleatórios
            actions = ActionChains(self._driver)
            steps = random.randint(5, 12)
            for i in range(steps):
                ox = random.randint(-8, 8)
                oy = random.randint(-8, 8)
                actions.move_by_offset(ox, oy)
            actions.move_to_element(element)
            actions.perform()
            time.sleep(_gauss_delay(0.15, 0.05))
        except Exception:
            pass

    def _human_click(self, element):
        self._scroll_to(element)
        time.sleep(_gauss_delay(0.3, 0.1))
        self._move_mouse_to(element)
        element.click()
        time.sleep(_gauss_delay(0.4, 0.15))

    def _human_type(self, element, text: str):
        from selenium.webdriver.common.keys import Keys
        self._human_click(element)
        element.send_keys(Keys.CONTROL + "a")
        time.sleep(_gauss_delay(0.1, 0.04))
        element.send_keys(Keys.BACKSPACE)
        time.sleep(_gauss_delay(0.15, 0.05))

        for i, ch in enumerate(text):
            element.send_keys(ch)
            time.sleep(random.uniform(0.04, 0.14))
            if ch == " ":
                time.sleep(_gauss_delay(0.07, 0.03))
            if i > 0 and i % random.randint(8, 20) == 0:
                time.sleep(_gauss_delay(0.25, 0.1))

    def _scroll_to(self, element):
        self._driver.execute_script(
            "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element
        )
        time.sleep(_gauss_delay(0.4, 0.12))

    def _find(self, by, sel, timeout=None):
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        t = timeout or self.timeout
        return WebDriverWait(self._driver, t).until(
            EC.presence_of_element_located((by, sel))
        )

    def _ensure_logged_in(self):
        from selenium.webdriver.support.ui import WebDriverWait
        self._driver.get(STUDIO_URL)
        time.sleep(_gauss_delay(2.5, 0.5))

        if "accounts.google.com" in self._driver.current_url or "signin" in self._driver.current_url:
            if self.headless:
                logger.warning(f"⚠️ Perfil '{self.profile}' não logado. Reabrindo visível...")
                self._stop()
                self.headless = False
                self._start()
                self._driver.get(STUDIO_URL)

            logger.info("🔐 Faça login no YouTube Studio. Aguardando (até 3 min)...")
            WebDriverWait(self._driver, 180).until(
                lambda d: STUDIO_URL in d.current_url and "accounts.google" not in d.current_url
            )
            logger.info(f"✅ Login concluído para '{self.profile}'.")

    def login(self):
        self.headless = False
        try:
            self._start()
            self._ensure_logged_in()
            time.sleep(3)
        finally:
            self._stop()

    def reset_session(self) -> bool:
        import shutil
        try:
            shutil.rmtree(_profile_dir(self.profile))
            _profile_dir(self.profile).mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Erro ao limpar sessão: {e}")
            return False

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

        size_mb = os.path.getsize(clip_path) / 1024 / 1024
        logger.info(f"📤 [Selenium] {Path(clip_path).name} ({size_mb:.1f} MB) → {title[:50]}")

        try:
            self._start()
            self._ensure_logged_in()
            tags = tags or []

            self._driver.get(STUDIO_URL)
            time.sleep(_gauss_delay(2.0, 0.5))

            # Simula leitura da página antes de clicar
            self._driver.execute_script(f"window.scrollBy({{top: {random.randint(50,200)}, behavior: 'smooth'}})")
            time.sleep(_gauss_delay(1.0, 0.3))

            # ── 1. Abre upload ────────────────────────────────────────────────
            file_input = self._find(By.CSS_SELECTOR, "input[type='file']")
            file_input.send_keys(os.path.abspath(clip_path))
            logger.info("📁 Arquivo enviado.")
            time.sleep(_gauss_delay(4.0 + size_mb * 0.05, 1.0))

            # ── 2. Título ─────────────────────────────────────────────────────
            title_el = self._find(By.CSS_SELECTOR, "#title-textarea #input")
            self._human_type(title_el, title)

            # ── 3. Descrição ──────────────────────────────────────────────────
            if description:
                time.sleep(_gauss_delay(0.5, 0.15))
                desc_els = self._driver.find_elements(By.CSS_SELECTOR, "#description-textarea #input")
                if desc_els:
                    self._human_type(desc_els[0], description)

            # ── 4. Made for kids ──────────────────────────────────────────────
            time.sleep(_gauss_delay(0.5, 0.15))
            kids_sel = "MADE_FOR_KIDS" if made_for_kids else "NOT_MADE_FOR_KIDS"
            kids_els = self._driver.find_elements(By.CSS_SELECTOR, f"tp-yt-paper-radio-button[name='{kids_sel}']")
            if kids_els:
                self._human_click(kids_els[0])

            # ── 5. Tags ───────────────────────────────────────────────────────
            if tags:
                time.sleep(_gauss_delay(0.8, 0.2))
                more_btns = self._driver.find_elements(By.CSS_SELECTOR, "ytcp-button#toggle-button")
                if more_btns:
                    self._human_click(more_btns[0])
                    time.sleep(_gauss_delay(1.0, 0.25))
                    tag_inputs = self._driver.find_elements(By.CSS_SELECTOR, "ytcp-free-text-chip-bar input")
                    if tag_inputs:
                        for tag in tags[:30]:
                            tag_inputs[0].send_keys(tag)
                            tag_inputs[0].send_keys(Keys.ENTER)
                            time.sleep(_gauss_delay(0.2, 0.07))

            # ── 6. Próximo × 3 ────────────────────────────────────────────────
            for _ in range(3):
                time.sleep(_gauss_delay(1.2, 0.3))
                next_btns = self._driver.find_elements(By.CSS_SELECTOR, "ytcp-button#next-button")
                if next_btns:
                    self._human_click(next_btns[0])

            # ── 7. Visibilidade ───────────────────────────────────────────────
            time.sleep(_gauss_delay(1.0, 0.25))
            privacy_map = {"public": "PUBLIC", "unlisted": "UNLISTED", "private": "PRIVATE"}
            vis_els = self._driver.find_elements(
                By.CSS_SELECTOR, f"tp-yt-paper-radio-button[name='{privacy_map.get(privacy, 'PUBLIC')}']"
            )
            if vis_els:
                self._human_click(vis_els[0])

            # ── 8. Publicar ───────────────────────────────────────────────────
            time.sleep(_gauss_delay(1.0, 0.3))
            done_btns = self._driver.find_elements(By.CSS_SELECTOR, "ytcp-button#done-button")
            if done_btns:
                self._human_click(done_btns[0])
            logger.info("🚀 Publicando...")
            time.sleep(_gauss_delay(5.0, 1.2))

            # ── 9. Extrai video_id ────────────────────────────────────────────
            yt_id = None
            m = re.search(r"/video/([a-zA-Z0-9_-]{8,})/", self._driver.current_url)
            if m:
                yt_id = m.group(1)
            else:
                links = self._driver.find_elements(
                    By.CSS_SELECTOR, "a[href*='youtube.com/watch'], a[href*='youtu.be']"
                )
                for link in links:
                    href = link.get_attribute("href") or ""
                    mm = re.search(r"[?&v=]([a-zA-Z0-9_-]{8,})|youtu\.be/([a-zA-Z0-9_-]{8,})", href)
                    if mm:
                        yt_id = mm.group(1) or mm.group(2)
                        break

            if yt_id:
                logger.info(f"✅ Publicado: https://youtube.com/shorts/{yt_id}")
            else:
                logger.warning("⚠️ Upload concluído mas não extraiu o video_id.")

            return yt_id

        except Exception as e:
            logger.error(f"❌ Erro no upload: {e}", exc_info=True)
            return None
        finally:
            self._stop()

    def close(self):
        self._stop()


# ══════════════════════════════════════════════════════════════════════════════
# INTERFACE UNIFICADA
# ══════════════════════════════════════════════════════════════════════════════

class VideoUploader:
    """
    Interface de alto nível para o ClipWorker.
    Tenta Playwright primeiro; cai para Selenium se não disponível.
    """

    def __init__(
        self,
        profile: str = "default",
        engine: str = "auto",
        headless: bool = True,
        privacy: str = "public",
        made_for_kids: bool = False,
        interval_seconds: float = 0.0,
    ):
        self.profile          = profile
        self.privacy          = privacy
        self.made_for_kids    = made_for_kids
        self.interval_seconds = interval_seconds
        self._last_upload_at  = 0.0
        self._engine_cls      = self._resolve_engine(engine, headless)

    def _resolve_engine(self, engine: str, headless: bool):
        if engine == "playwright":
            return lambda: PlaywrightUploader(profile=self.profile, headless=headless)
        if engine == "selenium":
            return lambda: SeleniumUploader(profile=self.profile, headless=headless)
        try:
            import playwright  # noqa
            logger.info("🎭 Engine: Playwright")
            return lambda: PlaywrightUploader(profile=self.profile, headless=headless)
        except ImportError:
            pass
        try:
            import selenium  # noqa
            logger.info("🌐 Engine: Selenium (fallback)")
            return lambda: SeleniumUploader(profile=self.profile, headless=headless)
        except ImportError:
            raise RuntimeError(
                "Nenhum engine disponível.\n"
                "Instale: pip install playwright && playwright install chromium\n"
                "      ou: pip install undetected-chromedriver"
            )

    def _respect_interval(self):
        if self.interval_seconds <= 0:
            return
        elapsed   = time.time() - self._last_upload_at
        remaining = self.interval_seconds - elapsed
        if remaining > 0:
            # Jitter de ±20% no intervalo (não esperar exatamente sempre)
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
            clip_path     = clip_path,
            title         = title,
            description   = description,
            tags          = tags,
            privacy       = self.privacy,
            made_for_kids = self.made_for_kids,
        )

        self._last_upload_at = time.time()
        return yt_id