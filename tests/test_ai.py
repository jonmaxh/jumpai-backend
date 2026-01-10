import pytest
from unittest.mock import Mock, patch, MagicMock
from app.services.ai import AIService
from app.services.gmail import GmailService


class TestAIService:
    @patch('app.services.ai.openai.OpenAI')
    def test_categorize_email_returns_category_id(self, mock_openai):
        mock_client = MagicMock()
        mock_response = MagicMock()
        # AI service expects JSON response with category_id and summary
        mock_response.choices = [MagicMock(message=MagicMock(
            content='{"category_id": 1, "summary": "Weekly newsletter with updates."}'
        ))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        service = AIService()
        categories = [
            {"id": 1, "name": "Newsletters", "description": "Newsletter emails"},
            {"id": 2, "name": "Receipts", "description": "Purchase receipts"},
        ]

        result = service.categorize_email(
            subject="Weekly Newsletter",
            sender="news@example.com",
            body_text="Here's your weekly update...",
            categories=categories
        )

        assert result == 1
        mock_client.chat.completions.create.assert_called_once()

    @patch('app.services.ai.openai.OpenAI')
    def test_categorize_email_returns_none_for_no_match(self, mock_openai):
        mock_client = MagicMock()
        mock_response = MagicMock()
        # AI service expects JSON response, null for no category match
        mock_response.choices = [MagicMock(message=MagicMock(
            content='{"category_id": null, "summary": "Random email content."}'
        ))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        service = AIService()
        categories = [
            {"id": 1, "name": "Newsletters", "description": "Newsletter emails"},
        ]

        result = service.categorize_email(
            subject="Random Email",
            sender="random@example.com",
            body_text="Some random content",
            categories=categories
        )

        assert result is None

    @patch('app.services.ai.openai.OpenAI')
    def test_categorize_email_empty_categories(self, mock_openai):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(
            content='{"category_id": null, "summary": "Test email."}'
        ))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        service = AIService()

        result = service.categorize_email(
            subject="Test",
            sender="test@example.com",
            body_text="Test body",
            categories=[]
        )

        assert result is None

    @patch('app.services.ai.openai.OpenAI')
    def test_summarize_email(self, mock_openai):
        mock_client = MagicMock()
        mock_response = MagicMock()
        # AI service expects JSON response
        mock_response.choices = [MagicMock(message=MagicMock(
            content='{"category_id": null, "summary": "This is a summary of the email."}'
        ))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        service = AIService()

        result = service.summarize_email(
            subject="Important Update",
            sender="boss@company.com",
            body_text="We need to discuss the project timeline..."
        )

        assert result == "This is a summary of the email."
        mock_client.chat.completions.create.assert_called_once()


class TestGmailService:
    def test_parse_sender_with_name(self):
        service = GmailService.__new__(GmailService)
        name, email = service._parse_sender('"John Doe" <john@example.com>')
        assert name == "John Doe"
        assert email == "john@example.com"

    def test_parse_sender_without_name(self):
        service = GmailService.__new__(GmailService)
        name, email = service._parse_sender("john@example.com")
        assert name == ""
        assert email == "john@example.com"

    def test_find_unsubscribe_link_in_html(self):
        service = GmailService.__new__(GmailService)
        body_html = '''
        <html>
        <body>
            <p>Some content</p>
            <a href="https://example.com/unsubscribe?id=123">Unsubscribe</a>
        </body>
        </html>
        '''

        result = service.find_unsubscribe_link(body_html, "")
        assert "unsubscribe" in result.lower()

    def test_find_unsubscribe_link_not_found(self):
        service = GmailService.__new__(GmailService)
        body_html = "<html><body>No unsubscribe link here</body></html>"

        result = service.find_unsubscribe_link(body_html, "")
        assert result is None

    def test_decode_body_empty(self):
        service = GmailService.__new__(GmailService)
        result = service._decode_body("")
        assert result == ""

    def test_decode_body_valid(self):
        import base64
        service = GmailService.__new__(GmailService)
        encoded = base64.urlsafe_b64encode(b"Hello World").decode()
        result = service._decode_body(encoded)
        assert result == "Hello World"


class TestAIBatchProcessing:
    @patch('app.services.ai.openai.OpenAI')
    def test_batch_processing_maps_indices_correctly(self, mock_openai):
        mock_client = MagicMock()
        mock_response = MagicMock()
        # AI returns results using index numbers
        mock_response.choices = [MagicMock(message=MagicMock(
            content='''[
                {"index": 1, "category_id": 1, "summary": "First email summary"},
                {"index": 2, "category_id": 2, "summary": "Second email summary"},
                {"index": 3, "category_id": null, "summary": "Third email summary"}
            ]'''
        ))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        service = AIService()
        emails = [
            {"id": "gmail_abc123", "subject": "Email 1", "sender": "a@test.com", "body_text": "Body 1"},
            {"id": "gmail_def456", "subject": "Email 2", "sender": "b@test.com", "body_text": "Body 2"},
            {"id": "gmail_ghi789", "subject": "Email 3", "sender": "c@test.com", "body_text": "Body 3"},
        ]
        categories = [
            {"id": 1, "name": "Work", "description": "Work emails"},
            {"id": 2, "name": "Personal", "description": "Personal emails"},
        ]

        results = service.process_emails_batch(emails, categories)

        assert len(results) == 3
        # Check that original IDs are preserved
        result_map = {r["id"]: r for r in results}
        assert result_map["gmail_abc123"]["category_id"] == 1
        assert result_map["gmail_def456"]["category_id"] == 2
        assert result_map["gmail_ghi789"]["category_id"] is None

    @patch('app.services.ai.openai.OpenAI')
    def test_batch_processing_handles_missing_results(self, mock_openai):
        mock_client = MagicMock()
        mock_response = MagicMock()
        # AI only returns 2 results for 3 emails
        mock_response.choices = [MagicMock(message=MagicMock(
            content='''[
                {"index": 1, "category_id": 1, "summary": "First email"},
                {"index": 3, "category_id": 2, "summary": "Third email"}
            ]'''
        ))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        service = AIService()
        emails = [
            {"id": "id1", "subject": "Email 1", "sender": "a@test.com", "body_text": "Body 1"},
            {"id": "id2", "subject": "Email 2", "sender": "b@test.com", "body_text": "Body 2"},
            {"id": "id3", "subject": "Email 3", "sender": "c@test.com", "body_text": "Body 3"},
        ]
        categories = [{"id": 1, "name": "Cat1", "description": ""}]

        results = service.process_emails_batch(emails, categories)

        # Should still have 3 results (missing one gets default)
        assert len(results) == 3
        result_ids = {r["id"] for r in results}
        assert "id1" in result_ids
        assert "id2" in result_ids
        assert "id3" in result_ids

    @patch('app.services.ai.openai.OpenAI')
    def test_batch_processing_validates_category_ids(self, mock_openai):
        mock_client = MagicMock()
        mock_response = MagicMock()
        # AI returns invalid category ID (999 doesn't exist)
        mock_response.choices = [MagicMock(message=MagicMock(
            content='[{"index": 1, "category_id": 999, "summary": "Test"}]'
        ))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        service = AIService()
        emails = [{"id": "id1", "subject": "Test", "sender": "a@test.com", "body_text": "Body"}]
        categories = [{"id": 1, "name": "Valid", "description": ""}]

        results = service.process_emails_batch(emails, categories)

        # Invalid category ID should be set to None
        assert results[0]["category_id"] is None
