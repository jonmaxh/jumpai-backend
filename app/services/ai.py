import openai
from app.config import get_settings
from typing import Optional
import json

settings = get_settings()


class AIService:
    def __init__(self):
        self.client = openai.OpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-4o"

    def process_email(
        self,
        subject: str,
        sender: str,
        body_text: str,
        categories: list[dict]
    ) -> tuple[Optional[int], str]:
        """
        Process an email: categorize and summarize in a single API call.
        Returns (category_id, summary).
        """
        truncated_body = body_text[:2000] if body_text else ""

        if categories:
            categories_text = "\n".join([
                f"- ID: {cat['id']}, Name: {cat['name']}, Description: {cat['description'] or 'No description'}"
                for cat in categories
            ])
            category_instruction = f"""
AVAILABLE CATEGORIES:
{categories_text}

Pick the best matching category ID, or "NONE" if no good fit."""
        else:
            category_instruction = "No categories available, use NONE for category_id."

        prompt = f"""Analyze this email and provide a JSON response.

EMAIL:
Subject: {subject}
From: {sender}
Body: {truncated_body}
{category_instruction}

Respond with ONLY valid JSON in this exact format:
{{"category_id": <number or null>, "summary": "<2 sentence summary>"}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}]
            )

            result = response.choices[0].message.content.strip()

            if result.startswith("```"):
                result = result.split("\n", 1)[1].rsplit("```", 1)[0]

            data = json.loads(result)

            category_id = data.get("category_id")
            if category_id == "NONE" or category_id == "null":
                category_id = None
            elif category_id is not None:
                category_id = int(category_id)
                valid_ids = [cat["id"] for cat in categories]
                if category_id not in valid_ids:
                    category_id = None

            summary = data.get("summary", f"Email from {sender}: {subject}")

            return category_id, summary

        except Exception as e:
            print(f"AI processing error: {e}")
            return None, f"Email from {sender}: {subject}"

    def categorize_email(
        self,
        subject: str,
        sender: str,
        body_text: str,
        categories: list[dict]
    ) -> Optional[int]:
        """Categorize an email (legacy method, uses process_email)."""
        category_id, _ = self.process_email(subject, sender, body_text, categories)
        return category_id

    def summarize_email(self, subject: str, sender: str, body_text: str) -> str:
        """Summarize an email (legacy method, uses process_email)."""
        _, summary = self.process_email(subject, sender, body_text, [])
        return summary

    def process_emails_batch(
        self,
        emails: list[dict],
        categories: list[dict],
        batch_size: int = 20
    ) -> list[dict]:
        """
        Process multiple emails in batches.
        Each email dict should have: id, subject, sender, body_text
        Returns list of {id, category_id, summary} for each email.
        """
        if not emails:
            return []

        # Process in batches to avoid token limits
        all_results = []
        for i in range(0, len(emails), batch_size):
            batch = emails[i:i + batch_size]
            print(f"Processing batch {i // batch_size + 1} ({len(batch)} emails)")
            batch_results = self._process_single_batch(batch, categories)
            all_results.extend(batch_results)

        return all_results

    def _process_single_batch(
        self,
        emails: list[dict],
        categories: list[dict]
    ) -> list[dict]:
        """Process a single batch of emails."""
        if not emails:
            return []

        if categories:
            categories_text = "\n".join([
                f"- ID: {cat['id']}, Name: {cat['name']}, Description: {cat['description'] or 'No description'}"
                for cat in categories
            ])
            category_instruction = f"""
AVAILABLE CATEGORIES:
{categories_text}

Pick the best matching category ID for each email, or null if no good fit."""
        else:
            category_instruction = "No categories available, use null for all category_id values."

        # Build email list with simple sequential indices (1, 2, 3...)
        # We'll map the results back using these indices
        index_to_id = {}
        emails_text = ""
        for i, email in enumerate(emails):
            idx = i + 1
            index_to_id[idx] = email['id']
            truncated_body = (email.get("body_text") or "")[:1000]
            emails_text += f"""
---EMAIL {idx}---
Subject: {email.get('subject', '')}
From: {email.get('sender', '')}
Body: {truncated_body}
"""

        prompt = f"""Analyze these {len(emails)} emails and categorize + summarize each one.
{category_instruction}

{emails_text}

IMPORTANT: Return results in the SAME ORDER as the emails above (1, 2, 3, etc).

Respond with ONLY a valid JSON array with exactly {len(emails)} items. Each item must have:
- "index": the email number (1, 2, 3, etc.)
- "category_id": matching category ID number or null
- "summary": 1-2 sentence summary

Example format:
[{{"index": 1, "category_id": 5, "summary": "Meeting invite for Friday."}}, {{"index": 2, "category_id": null, "summary": "Newsletter about tech news."}}]"""

        try:
            # Cap max_tokens to stay under model limit (16384 for gpt-4o-mini)
            max_tokens = min(100 * len(emails), 4000)
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )

            result = response.choices[0].message.content.strip()

            if result.startswith("```"):
                result = result.split("\n", 1)[1].rsplit("```", 1)[0]

            data = json.loads(result)

            valid_ids = [cat["id"] for cat in categories] if categories else []
            processed = []

            # Process results and map back to original IDs
            for item in data:
                # Get the index and map to original ID
                idx = item.get("index")
                if idx is None:
                    # Fallback: try "id" field in case AI used old format
                    idx = item.get("id")

                original_id = index_to_id.get(idx)
                if original_id is None:
                    continue

                category_id = item.get("category_id")

                if category_id == "NONE" or category_id == "null":
                    category_id = None
                elif category_id is not None:
                    try:
                        category_id = int(category_id)
                        if category_id not in valid_ids:
                            category_id = None
                    except (ValueError, TypeError):
                        category_id = None

                summary = item.get("summary", "")
                processed.append({
                    "id": original_id,
                    "category_id": category_id,
                    "summary": summary
                })

            # If we're missing some results, add defaults
            processed_ids = {p["id"] for p in processed}
            for email in emails:
                if email["id"] not in processed_ids:
                    processed.append({
                        "id": email["id"],
                        "category_id": None,
                        "summary": f"Email from {email.get('sender', 'unknown')}"
                    })

            return processed

        except Exception as e:
            print(f"AI batch processing error: {e}")
            return [
                {"id": email["id"], "category_id": None, "summary": f"Email from {email.get('sender', 'unknown')}"}
                for email in emails
            ]

    def analyze_unsubscribe_page(self, page_content: str) -> dict:
        """
        Analyze an unsubscribe page and provide instructions for unsubscribing.
        Returns a dict with actions to take.
        """
        truncated_content = page_content[:8000]

        prompt = f"""Analyze this unsubscribe page HTML and provide step-by-step instructions to complete the unsubscribe process.

PAGE CONTENT:
{truncated_content}

Respond in JSON format with the following structure:
{{
    "has_form": true/false,
    "form_selector": "CSS selector for the form if present",
    "submit_button_selector": "CSS selector for submit button",
    "email_field_selector": "CSS selector for email input if needed",
    "checkbox_selectors": ["CSS selectors for any checkboxes to check"],
    "radio_selectors": ["CSS selectors for any radio buttons to select"],
    "confirmation_needed": true/false,
    "confirmation_button_selector": "CSS selector for confirmation if needed",
    "instructions": "Brief description of the unsubscribe process"
}}

If it's a simple one-click unsubscribe with no form, just indicate that.
Respond with ONLY the JSON, no other text."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            result_text = response.choices[0].message.content.strip()
            if result_text.startswith("```"):
                result_text = result_text.split("\n", 1)[1]
                result_text = result_text.rsplit("```", 1)[0]

            return json.loads(result_text)

        except Exception as e:
            print(f"AI page analysis error: {e}")
            return {
                "has_form": False,
                "instructions": "Could not analyze page, manual unsubscribe may be required."
            }
