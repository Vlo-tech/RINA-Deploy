



from typing import List, Dict


def rerank_candidates(candidates: List[Dict], property_type: str = None, max_price: int = None, furnishing: str = None, top_k: int = 5) -> List[Dict]:
    def score_fn(item: Dict) -> float:
        base = float(item.get("similarity", 0.0))
        
        # Property type boost
        if property_type and item.get("property_type"):
            if property_type.lower() in str(item.get("property_type")).lower():
                base += 0.2

        # Price proximity boost
        if max_price and item.get("price"):
            diff = abs(item.get("price", 0) - max_price)
            base += max(0, 0.2 - diff / (max_price + 1) * 0.2)

        # Furnishing boost
        if furnishing and item.get("furnishing"):
            if furnishing.lower() in str(item.get("furnishing")).lower():
                base += 0.1

        # Neighborhood rating boost
        if item.get("neighborhood_rating"):
            base += float(item.get("neighborhood_rating")) / 10.0 # Normalize to 0-0.5 range

        return base

    ranked = sorted(candidates, key=score_fn, reverse=True)
    return ranked[:top_k]