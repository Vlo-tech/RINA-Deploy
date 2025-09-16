
import csv
from src.intent_classifier import IntentClassifier

# Path to your training data
TRAINING_DATA_PATH = "src/intent_training_examples.csv"

def train_model():
    """
    Reads training data and trains the intent classifier model.
    """
    print("Reading training data...")
    texts = []
    labels = []
    try:
        with open(TRAINING_DATA_PATH, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header row
            for row in reader:
                if len(row) == 2:
                    texts.append(row[0])
                    labels.append(row[1])
    except FileNotFoundError:
        print(f"Error: Training data file not found at {TRAINING_DATA_PATH}")
        print("Please ensure the file exists and the path is correct.")
        return

    if not texts or not labels:
        print("No training data found. Aborting.")
        return

    print(f"Found {len(texts)} training examples.")
    print("Training intent classifier...")

    # Initialize and train the classifier
    classifier = IntentClassifier()
    classifier.train(texts, labels)

    print("\nTraining complete!")
    print("The trained model has been saved to models/intent_clf.pkl")
    print("The application will now use the local model for intent classification.")

if __name__ == "__main__":
    train_model()
