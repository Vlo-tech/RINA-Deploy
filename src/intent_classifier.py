import os
from typing import Tuple
from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI

# Initialize OpenAI client with a timeout
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""), timeout=10.0)


class IntentClassifier:
    def __init__(self):
        """
        This classifier now uses OpenAI's API for intent detection.
        The local model training and prediction logic has been removed for faster deployment.
        The code is structured to allow re-integration of a local model in the future.
        """
        pass

    def predict(self, text: str) -> Tuple[str, float]:
        """
        Predicts intent using a few-shot prompt to the OpenAI API.
        Returns (intent, confidence).
        """
        return self._few_shot_openai(text)

    def _few_shot_openai(self, text: str) -> Tuple[str, float]:
        """
        Performs few-shot classification using the OpenAI API.
        """
        prompt = (
            "You are a classifier that labels user intents into one of: "
            "search_listings, save_listing, create_inquiry, greeting, fallback.\n\n"
            "Examples:\n"
            "User: 'Find me a bedsitter near Kenyatta University under 8k'\nIntent: search_listings\n"
            "User: 'Save listing 5e3f...'\nIntent: save_listing\n"
            "User: 'Hey, hi'\nIntent: greeting\n\n"
            f"User: '{text}'\nIntent:"
        )
        try:
            resp = openai_client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"),
                messages=[{"role": "system", "content": "You are a classifier. Reply with only one word from the list of intents."}, 
                          {"role": "user", "content": prompt}],
                max_tokens=8,
                temperature=0.0,
            )
            raw = resp.choices[0].message.content.strip().split()[0]
            # Remove potential punctuation from the model's response
            intent = ''.join(filter(str.isalnum, raw))
            
            # List of valid intents
            valid_intents = ["search_listings", "save_listing", "create_inquiry", "greeting", "fallback"]

            if intent in valid_intents:
                # no real confidence score from this simple approach; set a default
                return intent, 0.9 # High confidence as it's from a powerful LLM
            else:
                return "fallback", 0.5

        except Exception as e:
            print(f"Error in OpenAI intent classification: {e}")
            return "fallback", 0.0