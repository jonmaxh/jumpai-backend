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

                if analysis.get("has_form"):
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
        ]

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
