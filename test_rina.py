import unittest
from unittest.mock import patch, MagicMock

from src.chat_service import get_bot_response

class TestRinaBot(unittest.TestCase):

    @patch('src.chat_service.detect_language')
    @patch('src.chat_service.INTENT.predict')
    def test_greeting(self, mock_intent_predict, mock_lang_detect):
        """Test that the bot responds with a greeting."""
        mock_lang_detect.return_value = 'en'
        mock_intent_predict.return_value = ('greeting', 0.9)

        response = get_bot_response('hello')
        self.assertIn('Hi! I can help you find student housing', response)

    @patch('src.chat_service.detect_language')
    @patch('src.chat_service.INTENT.predict')
    @patch('src.chat_service.retrieve_listings')
    def test_search_intent(self, mock_retrieve_listings, mock_intent_predict, mock_lang_detect):
        """Test that the bot correctly identifies a search intent."""
        mock_lang_detect.return_value = 'en'
        mock_intent_predict.return_value = ('search_listings', 0.9)
        mock_retrieve_listings.return_value = [
            {
                'id': '123',
                'title': 'Test Listing',
                'location': 'Test Location',
                'price': '10000',
                'room_type': 'Bedsitter',
                'landlord_contact': '1234567890'
            }
        ]

        response = get_bot_response('find me a room')
        self.assertIn('Here are some of the listings I found:', response)
        self.assertIn('Test Listing', response)

    @patch('src.chat_service.detect_language')
    @patch('src.chat_service.INTENT.predict')
    @patch('src.chat_service.sb.save_listing_to_favorites')
    def test_save_listing_intent(self, mock_save_listing, mock_intent_predict, mock_lang_detect):
        """Test that the bot correctly identifies a save listing intent."""
        mock_lang_detect.return_value = 'en'
        mock_intent_predict.return_value = ('save_listing', 0.9)
        mock_save_listing.return_value = None

        response = get_bot_response('save 12345678')
        self.assertIn('Saved listing 12345678 to your favorites', response)

if __name__ == '__main__':
    unittest.main()