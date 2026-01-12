from playwright.async_api import async_playwright, Page
from app.services.ai import AIService
from typing import Optional
import asyncio


class UnsubscribeAgent:
    def __init__(self):
        self.ai_service = AIService()

    async def unsubscribe(self, url: str, user_email: Optional[str] = None) -> dict:
        """
        Navigate to an unsubscribe URL and attempt to complete the unsubscribe process.
        Returns a dict with success status and message.
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
            page = await context.new_page()
            page.set_default_timeout(5000)

            try:
                await page.goto(url, timeout=30000)
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(1)
                await self._wait_for_interactive(page)

                page_content = await page.content()

                if await self._check_already_unsubscribed(page):
                    await browser.close()
                    return {
                        "success": True,
                        "message": "Already unsubscribed or unsubscribe was automatic."
                    }

                analysis = self.ai_service.analyze_unsubscribe_page(page_content)
                has_form = bool(analysis.get("has_form"))

                if not has_form:
                    for context in self._collect_contexts(page):
                        query_selector = getattr(context, "query_selector", None)
                        if not query_selector:
                            continue
                        try:
                            if await query_selector("form"):
                                has_form = True
                                break
                        except Exception:
                            continue

                if has_form:
                    result = await self._handle_form(page, analysis, user_email)
                else:
                    result = await self._handle_simple_page(page)

                await browser.close()
                return result

            except Exception as e:
                await browser.close()
                return {
                    "success": False,
                    "message": f"Error during unsubscribe: {str(e)}"
                }

    def _collect_contexts(self, page: Page):
        contexts = [page]
        frames = getattr(page, "frames", None)
        if frames:
            for frame in frames:
                if frame not in contexts:
                    contexts.append(frame)
        return contexts

    async def _safe_fill(self, context, selector: str, value: str) -> bool:
        try:
            await context.fill(selector, value, timeout=2000)
            return True
        except TypeError:
            await context.fill(selector, value)
            return True
        except Exception:
            return False

    async def _safe_click(self, context, selector: str) -> bool:
        try:
            await context.click(selector, timeout=2000)
            return True
        except TypeError:
            await context.click(selector)
            return True
        except Exception:
            return False

    async def _safe_check(self, context, selector: str) -> bool:
        try:
            await context.check(selector, timeout=2000)
            return True
        except TypeError:
            await context.check(selector)
            return True
        except Exception:
            return False

    async def _wait_for_interactive(self, page: Page) -> None:
        selectors = "form, input, button, a"
        for context in self._collect_contexts(page):
            wait_for_selector = getattr(context, "wait_for_selector", None)
            if not wait_for_selector:
                continue
            try:
                await wait_for_selector(selectors, timeout=4000, state="visible")
                return
            except Exception:
                continue

    async def _context_has_visible_success(self, context, indicators) -> bool:
        evaluate = getattr(context, "evaluate", None)
        if not evaluate:
            return False
        try:
            return await evaluate(
                """
                (indicators) => {
                  const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    if (!style || style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                      return false;
                    }
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                  };
                  const nodes = Array.from(document.querySelectorAll('body *'));
                  return nodes.some((el) => {
                    const text = (el.textContent || '').toLowerCase();
                    if (!text) return false;
                    if (!indicators.some((indicator) => text.includes(indicator))) return false;
                    return isVisible(el);
                  });
                }
                """,
                indicators,
            )
        except Exception:
            return False

    async def _check_success_in_contexts(self, contexts) -> bool:
        success_indicators = [
            "successfully unsubscribed",
            "you have been unsubscribed",
            "unsubscribe successful",
            "you've been removed",
            "removed from our list",
            "no longer receive",
            "unsubscribe complete",
            "you are unsubscribed",
            "preferences have been updated successfully",
            "updated successfully",
        ]

        had_visible_check = False
        for context in contexts:
            if getattr(context, "evaluate", None):
                had_visible_check = True
                if await self._context_has_visible_success(context, success_indicators):
                    return True

        if had_visible_check:
            return False

        for context in contexts:
            content = ""
            try:
                content = await context.content()
            except Exception:
                continue
            content_lower = content.lower()
            if any(indicator in content_lower for indicator in success_indicators):
                return True

        return False

    async def _fill_required_fields(self, contexts, user_email: Optional[str]) -> bool:
        email_value = user_email or "user@example.com"
        text_value = "Please unsubscribe me."
        filled_any = False

        for context in contexts:
            query_selector_all = getattr(context, "query_selector_all", None)
            if not query_selector_all:
                continue

            try:
                inputs = await query_selector_all("input[required]")
            except Exception:
                inputs = []

            for input_el in inputs:
                try:
                    input_type = (await input_el.get_attribute("type") or "").lower()
                    name = (await input_el.get_attribute("name") or "").lower()
                    element_id = (await input_el.get_attribute("id") or "").lower()

                    if input_type in ["checkbox", "radio"]:
                        await input_el.check()
                        filled_any = True
                        continue

                    if input_type == "email" or "email" in name or "email" in element_id:
                        await input_el.fill(email_value)
                        filled_any = True
                        continue

                    if input_type == "url":
                        await input_el.fill("https://example.com")
                        filled_any = True
                        continue

                    if input_type == "tel":
                        await input_el.fill("0000000000")
                        filled_any = True
                        continue

                    if input_type == "number":
                        await input_el.fill("1")
                        filled_any = True
                        continue

                    await input_el.fill("unsubscribe")
                    filled_any = True
                except Exception:
                    continue

            try:
                selects = await query_selector_all("select[required]")
            except Exception:
                selects = []

            for select in selects:
                try:
                    options = await select.query_selector_all("option")
                    selected_value = None
                    for option in options:
                        value = await option.get_attribute("value")
                        if value and value.strip():
                            selected_value = value
                            break
                    if selected_value:
                        await select.select_option(value=selected_value)
                        filled_any = True
                except Exception:
                    continue

            try:
                textareas = await query_selector_all("textarea[required]")
            except Exception:
                textareas = []

            for textarea in textareas:
                try:
                    await textarea.fill(text_value)
                    filled_any = True
                except Exception:
                    continue

        return filled_any

    async def _check_already_unsubscribed(self, page: Page) -> bool:
        """Check if page indicates user is already unsubscribed."""
        return await self._check_success_in_contexts(self._collect_contexts(page))

    async def _handle_form(
        self,
        page: Page,
        analysis: dict,
        user_email: Optional[str]
    ) -> dict:
        """Handle form-based unsubscribe pages."""
        try:
            contexts = self._collect_contexts(page)
            submitted = False
            filled = False

            if analysis.get("email_field_selector") and user_email:
                for context in contexts:
                    if await self._safe_fill(context, analysis["email_field_selector"], user_email):
                        filled = True
                        break

            if not filled and user_email:
                fallback_email_selectors = [
                    'input[type="email"]',
                    'input[name*="email" i]',
                    'input[id*="email" i]',
                    'input[placeholder*="email" i]',
                ]
                for selector in fallback_email_selectors:
                    for context in contexts:
                        if await self._safe_fill(context, selector, user_email):
                            filled = True
                            break
                    if filled:
                        break

            await self._fill_required_fields(contexts, user_email)

            for checkbox in analysis.get("checkbox_selectors", []):
                for context in contexts:
                    if await self._safe_check(context, checkbox):
                        break

            for radio in analysis.get("radio_selectors", []):
                for context in contexts:
                    if await self._safe_click(context, radio):
                        break

            submit_selector = analysis.get("submit_button_selector")
            if submit_selector:
                for context in contexts:
                    if await self._safe_click(context, submit_selector):
                        submitted = True
                        break

            if not submitted:
                fallback_submit_selectors = [
                    'button:has-text("unsubscribe")',
                    'input[type="submit"]',
                    'button[type="submit"]',
                    'button:has-text("confirm")',
                    'button:has-text("opt out")',
                ]
                for selector in fallback_submit_selectors:
                    for context in contexts:
                        if await self._safe_click(context, selector):
                            submitted = True
                            break
                    if submitted:
                        break

            if submitted:
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(1)

            if analysis.get("confirmation_needed"):
                confirm_selector = analysis.get("confirmation_button_selector")
                if confirm_selector:
                    for context in contexts:
                        if await self._safe_click(context, confirm_selector):
                            submitted = True
                            break
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(1)

            if await self._check_success_in_contexts(contexts):
                return {
                    "success": True,
                    "message": "Successfully unsubscribed via form."
                }

            if submitted:
                return {
                    "success": True,
                    "message": "Unsubscribe form submitted. Please verify manually if needed."
                }

            return {
                "success": False,
                "message": "Unable to locate an unsubscribe form to submit."
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to complete form: {str(e)}"
            }

    async def _handle_simple_page(self, page: Page) -> dict:
        """Handle pages without forms, looking for unsubscribe buttons/links."""
        try:
            contexts = self._collect_contexts(page)
            clicked = False
            button_selectors = [
                'button:has-text("unsubscribe")',
                'a:has-text("unsubscribe")',
                'input[type="submit"][value*="unsubscribe" i]',
                'button:has-text("confirm")',
                'a:has-text("confirm")',
                'button:has-text("opt out")',
                'a:has-text("opt out")',
                'button[type="submit"]',
            ]

            for selector in button_selectors:
                for context in contexts:
                    if await self._safe_click(context, selector):
                        clicked = True
                        break
                if clicked:
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(1)

                    if await self._check_success_in_contexts(contexts):
                        return {
                            "success": True,
                            "message": "Successfully unsubscribed."
                        }
                    break

            if clicked:
                return {
                    "success": True,
                    "message": "Unsubscribe action submitted. Please verify manually if needed."
                }

            return {
                "success": False,
                "message": "No unsubscribe action found on the page."
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Error on unsubscribe page: {str(e)}"
            }


def run_unsubscribe(url: str, user_email: Optional[str] = None) -> dict:
    """Synchronous wrapper for the unsubscribe agent."""
    agent = UnsubscribeAgent()
    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(agent.unsubscribe(url, user_email))
    finally:
        loop.close()


async def async_unsubscribe(url: str, user_email: Optional[str] = None) -> dict:
    """Async wrapper for the unsubscribe agent."""
    agent = UnsubscribeAgent()
    return await agent.unsubscribe(url, user_email)
