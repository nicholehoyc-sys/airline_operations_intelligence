"""Display names for BTS reporting-carrier codes (labels only; analysis uses the codes)."""
CARRIER_NAMES = {
    "AA": "American Airlines", "AS": "Alaska Airlines", "B6": "JetBlue Airways",
    "DL": "Delta Air Lines", "F9": "Frontier Airlines", "G4": "Allegiant Air",
    "HA": "Hawaiian Airlines", "MQ": "Envoy Air", "NK": "Spirit Airlines",
    "OH": "PSA Airlines", "OO": "SkyWest Airlines", "UA": "United Airlines",
    "WN": "Southwest Airlines", "YX": "Republic Airways",
}


def label(code: str) -> str:
    """'MQ' -> 'MQ · Envoy Air'; unknown codes are returned unchanged."""
    name = CARRIER_NAMES.get(str(code))
    return f"{code} · {name}" if name else str(code)
