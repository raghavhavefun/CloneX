import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright
from modules.platform_adapter import kill_browser_processes


class MeetingJoiner:
    def __init__(self, headless=False, close_chrome_before_launch=True, user_data_dir=None):
        self.headless = headless
        self.close_chrome_before_launch = close_chrome_before_launch
        self.user_data_dir = user_data_dir or os.getenv("ARIA_CHROME_USER_DATA_DIR", "").strip()
        self.profile_directory = os.getenv("ARIA_CHROME_PROFILE_DIR", "").strip()
        self._playwright = None
        self.browser = None
        self.page = None
        self.context = None
        self.current_platform = "unknown"
        self.dashboard_url = os.getenv("ARIA_DASHBOARD_URL", "http://localhost:5173").strip()

    def _close_running_chrome(self):
        if not self.close_chrome_before_launch:
            return
        # Force-close Chrome to avoid user-profile lock conflicts.
        kill_browser_processes()

    def _normalize_url(self, meeting_url: str) -> str:
        target_url = (meeting_url or "").strip()
        if not target_url:
            raise ValueError("Meeting URL is empty.")
        if not target_url.startswith(("http://", "https://")):
            target_url = f"https://{target_url}"
        return target_url

    async def _ensure_browser_context(self):
        print("[MeetingJoiner] Initializing Playwright automation...")
        self._playwright = await async_playwright().start()
        self._close_running_chrome()
        print("[MeetingJoiner] Launching Chrome Browser...")
        args = [
            "--use-fake-ui-for-media-stream",
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
        ]
        if self.profile_directory:
            args.append(f"--profile-directory={self.profile_directory}")
        if self.user_data_dir:
            profile_path = Path(self.user_data_dir)
            profile_path.mkdir(parents=True, exist_ok=True)
            print(f"[MeetingJoiner] Using user data dir: {profile_path}")
            if self.profile_directory:
                print(f"[MeetingJoiner] Using profile directory: {self.profile_directory}")
            self.context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_path),
                channel="chrome",
                headless=self.headless,
                permissions=["microphone", "camera"],
                args=args,
                timeout=45000,
            )
            print("[MeetingJoiner] Persistent context launched.")
            self.page = await self.context.new_page()
            print("[MeetingJoiner] Fresh page created.")
        else:
            self.browser = await self._playwright.chromium.launch(headless=self.headless, args=args)
            self.context = await self.browser.new_context(permissions=["microphone", "camera"])
            self.page = await self.context.new_page()

    async def join_meeting(self, meeting_url, assistant_name="Aria"):
        target_url = self._normalize_url(meeting_url)
        lower = target_url.lower()
        if "zoom.us" in lower or "zoomgov.com" in lower:
            self.current_platform = "zoom"
            meeting_page = await self.join_zoom_meeting(target_url, assistant_name=assistant_name)
            await self._open_dashboard_then_return_to_meeting()
            return meeting_page
        self.current_platform = "gmeet"
        meeting_page = await self.join_google_meet(target_url, assistant_name=assistant_name)
        await self._open_dashboard_then_return_to_meeting()
        return meeting_page

    async def _open_dashboard_then_return_to_meeting(self):
        if not self.context or not self.page:
            return
        dashboard_url = (self.dashboard_url or "").strip()
        if not dashboard_url:
            return
        try:
            meeting_page = self.page
            dashboard_tab = await self.context.new_page()
            await dashboard_tab.goto(dashboard_url, wait_until="domcontentloaded", timeout=15000)
            print(f"[MeetingJoiner] Dashboard opened in new tab: {dashboard_url}")
            await meeting_page.bring_to_front()
            self.page = meeting_page
            print("[MeetingJoiner] Switched back to meeting tab.")
        except Exception as e:
            print(f"[MeetingJoiner] Dashboard open/switch-back skipped: {e}")

    async def join_google_meet(self, meeting_url, assistant_name="Aria"):
        await self._ensure_browser_context()
        target_url = self._normalize_url(meeting_url)

        print(f"[MeetingJoiner] Navigating to Google Meet: {target_url}")
        nav_ok = False
        last_err = None
        for attempt in range(1, 3):
            try:
                if attempt == 2:
                    # Fallback: open a fresh tab in case first page is extension/about:blank locked.
                    self.page = await self.context.new_page()  # type: ignore
                self.page.set_default_timeout(20000)  # type: ignore
                await self.page.goto(target_url, wait_until="domcontentloaded", timeout=20000)  # type: ignore
                await self.page.wait_for_timeout(2500)  # type: ignore
                print(f"[MeetingJoiner] Current URL after navigation: {self.page.url}")  # type: ignore
                nav_ok = True
                break
            except Exception as e:
                last_err = e
                print(f"[MeetingJoiner] Navigation attempt {attempt} failed: {e}")
        if not nav_ok:
            raise RuntimeError(f"Could not navigate to meeting URL. Last error: {last_err}")

        # Dismiss any "Continue without signing in" / guest name prompt if present
        try:
            name_input = await self.page.query_selector('input[placeholder*="name"], input[aria-label*="name"]')  # type: ignore
            if name_input:
                print(f"[MeetingJoiner] Entering name: {assistant_name}")
                await name_input.fill(assistant_name)
                await self.page.wait_for_timeout(500)  # type: ignore
        except Exception:
            pass

        # Try to click join button (Google Meet variants)
        join_selectors = [
            'button:has-text("Join now")',
            'button:has-text("Ask to join")',
            'button:has-text("Join")',
            '[data-id="join-button"]',
            'button[jsname="Qx7uuf"]',
        ]
        joined = False
        for selector in join_selectors:
            try:
                btn = await self.page.wait_for_selector(selector, timeout=6000)  # type: ignore
                if btn:
                    await btn.click()
                    joined = True
                    print("[MeetingJoiner] Joined meeting successfully.")
                    break
            except Exception:
                continue

        if not joined:
            print("[MeetingJoiner] Could not find join button — you may need to join manually.")

        await self.page.wait_for_timeout(2000)  # type: ignore
        return self.page

    async def execute_agentic_steps(self, steps: list[dict]):
        if not self.page or not steps:
            return
        for step in steps:
            op = str(step.get("op", "")).strip().lower()
            args = step.get("args", {}) or {}
            try:
                if op == "stop_share":
                    await self._stop_share()
                elif op == "stop_video":
                    await self._stop_video()
                elif op == "open_url":
                    url = str(args.get("url", "")).strip()
                    if url:
                        target = url if url.startswith(("http://", "https://")) else f"https://{url}"
                        await self.page.goto(target, wait_until="domcontentloaded")
                elif op == "search_youtube":
                    q = str(args.get("query", "")).strip()
                    if q:
                        target = f"https://www.youtube.com/results?search_query={q.replace(' ', '+')}"
                        await self.page.goto(target, wait_until="domcontentloaded")
                elif op == "switch_tab":
                    await self._switch_tab(str(args.get("to", "next")).strip().lower())
                elif op == "scroll":
                    direction = str(args.get("direction", "down")).strip().lower()
                    amount = int(args.get("amount", 800) or 800)
                    signed = amount if direction != "up" else -abs(amount)
                    await self.page.evaluate("(d) => window.scrollBy(0, d)", signed)
                elif op == "play":
                    await self.page.keyboard.press("k")
                elif op == "pause":
                    await self.page.keyboard.press("k")
                elif op == "close_tab":
                    await self.page.close()
                    pages = self.context.pages if self.context else []
                    if pages:
                        self.page = pages[-1]
            except Exception as e:
                print(f"[MeetingJoiner] Agentic step failed ({op}): {e}")

    async def _switch_tab(self, target: str):
        pages = self.context.pages if self.context else []
        if not pages:
            return
        current_idx = pages.index(self.page) if self.page in pages else len(pages) - 1
        next_idx = current_idx
        if target == "latest":
            next_idx = len(pages) - 1
        elif target == "previous":
            next_idx = max(0, current_idx - 1)
        else:
            next_idx = min(len(pages) - 1, current_idx + 1)
        self.page = pages[next_idx]
        await self.page.bring_to_front()

    async def _stop_share(self):
        selectors = [
            'button:has-text("Stop sharing")',
            'button:has-text("Stop Sharing")',
            'button[aria-label*="Stop sharing"]',
            'button[aria-label*="Stop presenting"]',
            'button[aria-label*="Stop share"]',
        ]
        for sel in selectors:
            try:
                btn = await self.page.query_selector(sel)  # type: ignore
                if btn and await btn.is_visible():
                    await btn.click()
                    print(f"[MeetingJoiner] Stop share clicked via {sel}")
                    return
            except Exception:
                continue

    async def _stop_video(self):
        selectors = [
            'button:has-text("Stop Video")',
            'button:has-text("Turn off camera")',
            'button[aria-label*="Stop Video"]',
            'button[aria-label*="Turn off camera"]',
            'button[aria-label*="camera off"]',
        ]
        for sel in selectors:
            try:
                btn = await self.page.query_selector(sel)  # type: ignore
                if btn and await btn.is_visible():
                    await btn.click()
                    print(f"[MeetingJoiner] Stop video clicked via {sel}")
                    return
            except Exception:
                continue

    async def join_zoom_meeting(self, meeting_url, assistant_name="Aria"):
        await self._ensure_browser_context()
        target_url = self._normalize_url(meeting_url)
        print(f"[MeetingJoiner] Navigating to Zoom: {target_url}")
        await self.page.goto(target_url, wait_until="domcontentloaded", timeout=30000)  # type: ignore
        await self.page.wait_for_timeout(3000)  # type: ignore

        # Step 1: click "Join from browser".
        join_browser_clicked = False
        for selector in [
            'button:has-text("Join from browser")',
            'button:has-text("Join from Browser")',
            'a:has-text("Join from browser")',
            'a:has-text("Join from Browser")',
            'a:has-text("Join from Your Browser")',
            'button:has-text("Join from Your Browser")',
        ]:
            try:
                btn = await self.page.wait_for_selector(selector, timeout=4000)  # type: ignore
                if btn:
                    await btn.click()
                    join_browser_clicked = True
                    print(f"[MeetingJoiner] Clicked browser join option: {selector}")
                    await self.page.wait_for_timeout(1800)  # type: ignore
                    break
            except Exception:
                continue
        if not join_browser_clicked:
            print("[MeetingJoiner] Browser join option not found immediately; continuing with fallback flow.")

        # Zoom can take several seconds after "Join from browser" before rendering the name form.
        # Wait explicitly for URL/state transition and name input visibility.
        try:
            await self.page.wait_for_timeout(1200)  # type: ignore
            for _ in range(12):
                ready = await self.page.evaluate(  # type: ignore
                    """() => {
                        const inputs = Array.from(document.querySelectorAll('input[type="text"], input'));
                        return inputs.some(i => {
                            const ph = (i.getAttribute('placeholder') || '').toLowerCase();
                            const ar = (i.getAttribute('aria-label') || '').toLowerCase();
                            const nm = (i.getAttribute('name') || '').toLowerCase();
                            const visible = !!(i.offsetWidth || i.offsetHeight || i.getClientRects().length);
                            return visible && (ph.includes('name') || ar.includes('name') || nm.includes('name'));
                        });
                    }"""
                )
                if ready:
                    print("[MeetingJoiner] Zoom name form is ready.")
                    break
                await self.page.wait_for_timeout(1000)  # type: ignore
        except Exception:
            pass

        # Step 2: fill display name robustly (keystrokes + events to enable Join button).
        name_filled = False
        async def _fill_name_in_frame(frame):
            selectors = [
                'input#input-for-name',
                'input[name="name"]',
                'input[placeholder*="Name"]',
                'input[placeholder*="name"]',
                'input[aria-label*="name"]',
                'input[aria-label*="Name"]',
                'input[type="text"]',
            ]
            for sel in selectors:
                try:
                    el = await frame.query_selector(sel)
                    if not el:
                        continue
                    visible = await el.is_visible()
                    if not visible:
                        continue
                    await el.click()
                    await el.fill("")
                    await frame.page.keyboard.type(assistant_name, delay=30)
                    await frame.page.keyboard.press("Tab")
                    await frame.wait_for_timeout(200)
                    val = ""
                    try:
                        val = await el.input_value()
                    except Exception:
                        pass
                    if not (val or "").strip():
                        await el.fill(assistant_name)
                    return True
                except Exception:
                    continue
            return False

        for fr in self.page.frames:  # type: ignore
            try:
                if await _fill_name_in_frame(fr):
                    name_filled = True
                    print(f"[MeetingJoiner] Filled Zoom display name in frame: {fr.url[:120]}")
                    break
            except Exception:
                continue

        if not name_filled:
            # JS fallback for variants where selector text/case differs.
            try:
                ok = await self.page.evaluate(  # type: ignore
                    """(displayName) => {
                        const candidates = Array.from(document.querySelectorAll('input[type="text"], input'));
                        const target = candidates.find(i => {
                            const ph = (i.getAttribute('placeholder') || '').toLowerCase();
                            const ar = (i.getAttribute('aria-label') || '').toLowerCase();
                            const nm = (i.getAttribute('name') || '').toLowerCase();
                            return ph.includes('name') || ar.includes('name') || nm.includes('name');
                        }) || candidates[0];
                        if (!target) return false;
                        target.focus();
                        target.value = '';
                        target.dispatchEvent(new InputEvent('input', { bubbles: true, data: '' }));
                        target.value = displayName;
                        target.dispatchEvent(new InputEvent('input', { bubbles: true, data: displayName }));
                        target.dispatchEvent(new Event('keyup', { bubbles: true }));
                        target.dispatchEvent(new Event('change', { bubbles: true }));
                        target.blur();
                        return true;
                    }""",
                    assistant_name,
                )
                if ok:
                    name_filled = True
                    print("[MeetingJoiner] Filled Zoom display name via JS fallback.")
                    await self.page.wait_for_timeout(400)  # type: ignore
            except Exception:
                pass
        if not name_filled:
            print("[MeetingJoiner] Name input not found; Zoom may already have a prefilled identity.")

        # Step 2b: deterministic form fill for Zoom "Enter Meeting Info" page.
        # This path uses label->input resolution and native-style events.
        try:
            forced = await self.page.evaluate(  # type: ignore
                """(displayName) => {
                    const norm = (s) => (s || '').trim().toLowerCase();
                    const labels = Array.from(document.querySelectorAll('label, div, span, p'));
                    let input = null;
                    for (const node of labels) {
                        if (norm(node.textContent) === 'your name') {
                            // Search close siblings/container first.
                            const box = node.closest('div, form, section') || document;
                            input = box.querySelector('input[type="text"], input[name="name"], input');
                            if (input) break;
                        }
                    }
                    if (!input) {
                        const candidates = Array.from(document.querySelectorAll('input[type="text"], input[name="name"], input'));
                        input = candidates.find(i => {
                            const ph = norm(i.getAttribute('placeholder'));
                            const ar = norm(i.getAttribute('aria-label'));
                            const nm = norm(i.getAttribute('name'));
                            return ph.includes('name') || ar.includes('name') || nm.includes('name');
                        }) || candidates[0];
                    }
                    if (!input) return { ok: false, reason: 'no_input' };
                    input.focus();
                    input.value = '';
                    input.dispatchEvent(new Event('focus', { bubbles: true }));
                    input.dispatchEvent(new InputEvent('input', { bubbles: true, data: '' }));
                    input.value = displayName;
                    input.dispatchEvent(new InputEvent('input', { bubbles: true, data: displayName }));
                    input.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'a' }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    input.blur();

                    // Resolve join button near the form area first.
                    const formRoot = (input.closest('form') || input.closest('div') || document);
                    let joinBtn = formRoot.querySelector('button[type="submit"]');
                    if (!joinBtn) {
                        const btns = Array.from(formRoot.querySelectorAll('button'));
                        joinBtn = btns.find(b => {
                            const t = norm(b.textContent);
                            return t === 'join' || t === 'join now' || t.startsWith('join');
                        }) || null;
                    }
                    const disabled = joinBtn ? (joinBtn.disabled || joinBtn.getAttribute('aria-disabled') === 'true') : null;
                    return { ok: true, hasJoin: !!joinBtn, joinDisabled: !!disabled };
                }""",
                assistant_name,
            )
            print(f"[MeetingJoiner] Zoom deterministic form fill: {forced}")
        except Exception as e:
            print(f"[MeetingJoiner] Deterministic form fill warning: {e}")

        # Step 3: click final Join button.
        joined = False
        async def _click_join_in_frame(frame):
            join_selectors = [
                'button[type="submit"]',
                'button:has-text("Join now")',
                'button:has-text("Join Now")',
                'button:has-text("Join")',
                'button:has-text("Join Meeting")',
            ]
            for sel in join_selectors:
                try:
                    btn = await frame.query_selector(sel)
                    if not btn:
                        continue
                    if not await btn.is_visible():
                        continue
                    disabled = await btn.get_attribute("disabled")
                    aria_dis = await btn.get_attribute("aria-disabled")
                    if disabled is not None or (aria_dis or "").lower() == "true":
                        continue
                    await btn.click()
                    return True, sel
                except Exception:
                    continue
            return False, ""
        # Wait briefly for Join button to become enabled after input propagation.
        for _ in range(10):
            try:
                state = await self.page.evaluate(  # type: ignore
                    """() => {
                        const norm = (s) => (s || '').trim().toLowerCase();
                        const btn = Array.from(document.querySelectorAll('button')).find(
                            b => norm(b.textContent) === 'join' || norm(b.textContent) === 'join now'
                        );
                        if (!btn) return { exists: false, enabled: false };
                        const disabled = btn.disabled || btn.getAttribute('aria-disabled') === 'true';
                        return { exists: true, enabled: !disabled };
                    }"""
                )
                if state.get("exists") and state.get("enabled"):
                    print("[MeetingJoiner] Zoom Join button is enabled.")
                    break
            except Exception:
                pass
            await self.page.wait_for_timeout(300)  # type: ignore

        # Try deterministic form submit first (most reliable for Zoom variants).
        try:
            submitted = await self.page.evaluate(  # type: ignore
                """() => {
                    const norm = (s) => (s || '').trim().toLowerCase();
                    const nameInput = Array.from(document.querySelectorAll('input[type="text"], input[name="name"], input'))
                        .find(i => {
                            const ph = norm(i.getAttribute('placeholder'));
                            const ar = norm(i.getAttribute('aria-label'));
                            const nm = norm(i.getAttribute('name'));
                            return ph.includes('name') || ar.includes('name') || nm.includes('name');
                        });
                    if (!nameInput) return { ok: false, reason: 'no_name_input' };
                    const root = nameInput.closest('form') || nameInput.closest('div') || document;
                    let btn = root.querySelector('button[type="submit"]');
                    if (!btn) {
                        btn = Array.from(root.querySelectorAll('button')).find(b => {
                            const t = norm(b.textContent);
                            return t === 'join' || t === 'join now' || t.startsWith('join');
                        }) || null;
                    }
                    if (!btn) return { ok: false, reason: 'no_join_button' };
                    const disabled = btn.disabled || btn.getAttribute('aria-disabled') === 'true';
                    if (disabled) return { ok: false, reason: 'join_disabled' };
                    btn.click();
                    return { ok: true };
                }"""
            )
            if submitted.get("ok"):
                joined = True
                print("[MeetingJoiner] Zoom join action triggered via deterministic form submit.")
                await self.page.wait_for_timeout(1200)  # type: ignore
        except Exception:
            pass

        for fr in self.page.frames:  # type: ignore
            ok, used_sel = await _click_join_in_frame(fr)
            if ok:
                joined = True
                print(f"[MeetingJoiner] Zoom join action triggered via {used_sel} in frame: {fr.url[:120]}")
                await self.page.wait_for_timeout(1500)  # type: ignore
                break

        if not joined:
            for selector in [
                'button:has-text("Join Audio by Computer")',
                'button:has-text("Join with Computer Audio")',
            ]:
                try:
                    btn = await self.page.query_selector(selector)  # type: ignore
                    if btn and await btn.is_visible():
                        await btn.click()
                        joined = True
                        print(f"[MeetingJoiner] Zoom join action triggered via {selector}.")
                        break
                except Exception:
                    continue

        if not joined:
            # Final fallback: submit form with Enter.
            try:
                await self.page.keyboard.press("Enter")  # type: ignore
                await self.page.wait_for_timeout(1200)  # type: ignore
                joined = True
                print("[MeetingJoiner] Zoom join fallback triggered via Enter key.")
            except Exception:
                pass
        if not joined:
            print("[MeetingJoiner] Could not complete Zoom web join automatically; you may need one manual click.")
        await self.page.wait_for_timeout(2000)  # type: ignore
        return self.page

    async def perform_web_action(self, action_type, query):
        if not self.page:
            return

        print(f"[MeetingJoiner] Executing Web Action: {action_type} -> {query}")

        # 1. Open the content tab first
        new_page = await self.page.context.new_page()
        
        target_url = ""
        if action_type == "search":
            if "youtube" in query.lower() or "video" in query.lower():
                clean_query = query.replace("youtube", "").replace("video", "").strip()
                target_url = f"https://www.youtube.com/results?search_query={clean_query.replace(' ', '+')}"
            else:
                target_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        else: # open
            target_url = query if query.startswith("http") else f"https://{query}"

        print(f"[MeetingJoiner] Navigating to: {target_url}")
        await new_page.goto(target_url, wait_until="domcontentloaded")
        await new_page.wait_for_timeout(2000) # Wait for results to render

        # 2. AUTO-CLICKER: If we are on a search results page, click the first major link
        try:
            is_youtube_search = "youtube.com/results" in target_url
            is_google_search = "google.com/search" in target_url

            if is_youtube_search:
                print("[MeetingJoiner] YouTube Results detected. Searching for first video...")
                video_selectors = ['ytd-video-renderer a#video-title', 'ytd-video-renderer a#thumbnail', 'a#video-title']
                for s in video_selectors:
                    video_btn = await new_page.query_selector(s)
                    if video_btn:
                        print(f"[MeetingJoiner] CLICKING VIDEO: {s}")
                        await video_btn.click()
                        await new_page.wait_for_url("**/watch?v=*", timeout=8000)
                        await new_page.wait_for_timeout(2000)
                        break
            elif is_google_search:
                print("[MeetingJoiner] Google Results detected. Clicking first organic link...")
                first_link = await new_page.query_selector('h3, .g a')
                if first_link:
                    await first_link.click()
                    await new_page.wait_for_load_state("networkidle")
        except Exception as e:
            print(f"[MeetingJoiner] Auto-click warning: {e}")

        # 3. Go back to Meet and trigger sharing
        try:
            await self.page.bring_to_front()
            await self.page.wait_for_timeout(2000)
            
            # Ultra-wide search for the sharing button
            share_selectors = [
                # Zoom variants
                'button:has-text("Share Screen")',
                'button:has-text("Share screen")',
                'button[aria-label*="Share Screen"]',
                'button[aria-label*="share screen"]',
                '[data-testid*="share"]',
                '[id*="share"]',
                'button[aria-label*="Present"]',
                'button[aria-label*="present"]',
                'button[aria-label*="Share"]',
                'button[aria-label*="share"]',
                '[data-id="sharing-button"]',
                'button[jsname="V67SHe"]'
            ]
            
            sharing_btn = None
            for _ in range(8):
                for selector in share_selectors:
                    sharing_btn = await self.page.query_selector(selector)
                    if sharing_btn:
                        print(f"[MeetingJoiner] Found sharing button with selector: {selector}")
                        break
                if sharing_btn:
                    break
                await self.page.wait_for_timeout(500)
            
            if sharing_btn:
                await sharing_btn.click()
                await self.page.wait_for_timeout(1500)
                # Select "A tab" specifically
                tab_option = await self.page.query_selector(
                    'text="A tab", [aria-label*="A tab"], [aria-label*="tab"], '
                    'button:has-text("Window"), button:has-text("Chrome Tab"), button:has-text("Tab")'
                )
                if tab_option:
                    await tab_option.click()
                    print("[MeetingJoiner] SUCCESS: Sharing dialog triggered.")
            else:
                print("[MeetingJoiner] ERROR: Could not find any sharing button.")
        except Exception as e:
            print(f"[MeetingJoiner] Screen share error: {e}")
        
        # Finally, focus the content
        await new_page.bring_to_front()

    async def leave_meeting(self):
        try:
            leave_selectors = [
                'button[aria-label*="Leave"]',
                'button[aria-label*="leave"]',
                '[data-id="hangup-button"]',
                'button:has-text("Leave Meeting")',
                'button:has-text("End")',
            ]
            for selector in leave_selectors:
                btn = await self.page.query_selector(selector)  # type: ignore
                if btn:
                    await btn.click()
                    break
        except Exception:
            pass
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
