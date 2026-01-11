import pytest

from app.services.unsubscribe import UnsubscribeAgent


class FakePage:
    def __init__(self):
        self.filled = []
        self.checked = []
        self.clicked = []

    async def fill(self, selector, value):
        self.filled.append((selector, value))

    async def check(self, selector):
        self.checked.append(selector)

    async def click(self, selector):
        self.clicked.append(selector)

    async def wait_for_load_state(self, state):
        return None

    async def content(self):
        return "You have been successfully unsubscribed."


@pytest.mark.asyncio
async def test_unsubscribe_form_flow():
    agent = UnsubscribeAgent()
    page = FakePage()
    analysis = {
        "has_form": True,
        "email_field_selector": "#email",
        "checkbox_selectors": ["#optout"],
        "radio_selectors": ["#all"],
        "submit_button_selector": "#submit",
        "confirmation_needed": False,
    }

    result = await agent._handle_form(page, analysis, user_email="test@example.com")

    assert result["success"] is True
    assert ("#email", "test@example.com") in page.filled
    assert "#optout" in page.checked
    assert "#submit" in page.clicked
