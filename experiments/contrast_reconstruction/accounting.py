"""OFox balance accounting, separate from the reconstruction tools."""
from datetime import datetime, timezone
from decimal import Decimal


def balance(session, base_url, key):
    response = session.get(base_url.rstrip("/") + "/user/balance",
        headers={"Authorization": "Bearer " + key}, timeout=(10, 20), allow_redirects=False)
    response.raise_for_status()
    data = response.json(parse_float=str)
    return {"time_utc": datetime.now(timezone.utc).isoformat(),
            **{name: data[name] for name in ("balance", "used", "currency", "is_active")}}


def charge(before, after):
    if before["currency"] != "USD" or after["currency"] != "USD":
        raise ValueError("Budget is denominated in USD")
    return max(Decimal(0), Decimal(str(after["used"])) - Decimal(str(before["used"])))
