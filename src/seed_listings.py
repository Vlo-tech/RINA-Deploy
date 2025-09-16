import json
from .supabase_client import _get_or_create_landlord, create_listing, _get_or_create

def seed_listings():
    with open('listings.json', 'r') as f:
        listings_data = json.load(f)

    for item in listings_data:
        landlord_data = item['landlord']
        complex_data = item['complex']
        listing_data = item['listing']

        try:
            # Create or get landlord
            landlord_id = _get_or_create(
                'landlords',
                {'contact_number': f"eq.{landlord_data['contact_number']}"},
                landlord_data
            )

            # Create or get complex
            complex_id = None
            if complex_data:
                complex_id = _get_or_create(
                    'complexes',
                    {'name': f"eq.{complex_data['name']}"},
                    {**complex_data, 'landlord_id': landlord_id}
                )

            # Create listing
            listing_data['landlord_id'] = landlord_id
            if complex_id:
                listing_data['complex_id'] = complex_id

            res = create_listing(listing_data)
            print("Inserted listing:", res)

        except Exception as e:
            print(f"Error inserting listing: {e}")

if __name__ == "__main__":
    seed_listings()
    print("Seeding complete.")