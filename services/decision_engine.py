import numpy as np

def calculate_weighted_decision(tech_data: dict, fund_data: dict, sent_data: dict, risk_data: dict) -> dict:
    """
    Calculates the final institutional score using a weighted formula:
    Final Score = 0.4*Tech + 0.3*Fund + 0.2*Sent + 0.1*Risk
    
    Also calculates a 'Confidence Score' based on signal alignment.
    """
    t_score = tech_data.get("tech_score", 50)
    f_score = fund_data.get("fundamental_score", 50)
    
    # Sentiment usually -1 to 1, map to 0-100
    s_val = sent_data.get("sentiment_score", 0) 
    s_score = ((s_val + 1) / 2) * 100
    
    r_score = risk_data.get("risk_score", 50)
    
    # Weighted calculation
    final_score = (t_score * 0.4) + (f_score * 0.3) + (s_score * 0.2) + (r_score * 0.1)
    final_score = round(final_score, 1)
    
    # Recommendation logic
    if final_score >= 75: rec = "STRONG BUY"
    elif final_score >= 60: rec = "BUY"
    elif final_score >= 45: rec = "HOLD"
    elif final_score >= 30: rec = "SELL"
    else: rec = "STRONG SELL"
    
    # Confidence Score: Based on how many signals agree with the final recommendation
    # (Simplified internal consistency check)
    signals = [t_score, f_score, s_score, r_score]
    mean_score = np.mean(signals)
    std_dev = np.std(signals)
    
    # High disagreement (high std dev) lowers confidence
    # Low disagreement (all signals agree) raises confidence
    base_confidence = 100 - (std_dev * 1.5)
    confidence = max(50, min(95, base_confidence)) # Clamp between 50% and 95%
    
    return {
        "final_score": final_score,
        "recommendation": rec,
        "confidence_score": round(confidence, 1),
        "score_breakdown": {
            "technical": t_score,
            "fundamental": f_score,
            "sentiment": round(s_score, 1),
            "risk": r_score
        }
    }
