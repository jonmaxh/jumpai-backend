from playwright.async_api import async_playwright, Page, Browser
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

            try:
                await page.goto(url, timeout=30000)
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(2)

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

    async def _check_already_unsubscribed(self, page: Page) -> bool:
        """Check if page indicates user is already unsubscribed."""
        content = await page.content()
        content_lower = content.lower()

        success_indicators = [
            "successfully unsubscribed",
            "you have been unsubscribed",
            "unsubscribe successful",
            "you've been removed",
            "removed from our list",
            "no longer receive",
        ]

        return any(indicator in content_lower for indicator in success_indicators)

    async def _handle_form(
        self,
        page: Page,
        analysis: dict,
        user_email: Optional[str]
    ) -> dict:
        """Handle form-based unsubscribe pages."""
        try:
            if analysis.get("email_field_selector") and user_email:
                try:
                    await page.fill(analysis["email_field_selector"], user_email)
                except Exception:
                    pass

            for checkbox in analysis.get("checkbox_selectors", []):
                try:
                    await page.check(checkbox)
                except Exception:
                    pass

            for radio in analysis.get("radio_selectors", []):
                try:
                    await page.click(radio)
                except Exception:
                    pass

            submit_selector = analysis.get("submit_button_selector")
            if submit_selector:
                try:
                    await page.click(submit_selector)
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(2)
                except Exception:
                    pass

            if analysis.get("confirmation_needed"):
                confirm_selector = analysis.get("confirmation_button_selector")
                if confirm_selector:
                    try:
                        await page.click(confirm_selector)
                        await page.wait_for_load_state("domcontentloaded")
                        await asyncio.sleep(2)
                    except Exception:
                        pass

            if await self._check_already_unsubscribed(page):
                return {
                    "success": True,
                    "message": "Successfully unsubscribed via form."
                }

            return {
                "success": True,
                "message": "Unsubscribe form submitted. Please verify manually if needed."
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to complete form: {str(e)}"
            }

    async def _handle_simple_page(self, page: Page) -> dict:
        """Handle pages without forms, looking for unsubscribe buttons/links."""
        try:
            button_selectors = [
                'button:has-text("unsubscribe")',
                'a:has-text("unsubscribe")',
                'input[type="submit"][value*="unsubscribe" i]',
                'button:has-text("confirm")',
                'a:has-text("confirm")',
                'button:has-text("opt out")',
                'a:has-text("opt out")',
            ]

            for selector in button_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        await element.click()
                        await page.wait_for_load_state("domcontentloaded")
                        await asyncio.sleep(2)

                        if await self._check_already_unsubscribed(page):
                            return {
                                "success": True,
                                "message": "Successfully unsubscribed."
                            }
                        break
                except Exception:
                    continue

            return {
                "success": True,
                "message": "Unsubscribe page loaded. Manual verification may be required."
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
