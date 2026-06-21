"""
Shared helpers for the deviseur-azure skill.

Wraps the Azure Retail Prices API and loads the local reference catalogs.
Used by propose_flavors.py and query_quote.py.
"""

import json
import os
import sys
import requests
from typing import Dict, List, Optional, Any

API_URL = "https://prices.azure.com/api/retail/prices"
HOURS_PER_MONTH = 730
HOURS_PER_YEAR = 8760

REFERENCES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "references")

CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "AUD": "A$", "CAD": "C$",
}


def currency_symbol(currency: str) -> str:
    return CURRENCY_SYMBOLS.get(currency.upper(), currency.upper() + " ")


def load_catalog() -> List[Dict[str, Any]]:
    """Load the curated VM SKU catalog (sku, family, vcpu, ram_gib)."""
    with open(os.path.join(REFERENCES_DIR, "vm-catalog.json"), encoding="utf-8") as f:
        return json.load(f)["skus"]


def load_disk_tiers() -> Dict[str, Any]:
    """Load managed-disk tier definitions."""
    with open(os.path.join(REFERENCES_DIR, "disk-tiers.json"), encoding="utf-8") as f:
        return json.load(f)


# Preference order when several flavors fit equally well. General-purpose (D)
# is the "Standard" default for unknown lift-and-shift workloads, then Compute
# (F), Memory (E), Burstable (B) last (B throttles under steady load).
FAMILY_PREFERENCE = {"D": 0, "F": 1, "E": 2, "B": 3}


def target_vcpu(catalog: List[Dict[str, Any]], vcpu: int) -> int:
    """The Azure vCPU count to aim for: the largest standard size <= the source.

    Azure VMs come in a fixed vCPU grid (1, 2, 4, 8, 16, 32 ...). When a source
    spec lands between two sizes (e.g. 3 vCPU), the sizing rule allows the target
    to sit *just below* the source rather than rounding up — so 3 vCPU floors to
    2. If the source is smaller than every catalog size, use the smallest size.
    """
    grid = sorted({s["vcpu"] for s in catalog})
    below = [g for g in grid if g <= vcpu]
    return max(below) if below else min(grid)


def pick_flavor(catalog: List[Dict[str, Any]], vcpu: int, ram_gib: float) -> Optional[Dict[str, Any]]:
    """Pick the best catalog flavor for a source spec under the sizing rule.

    The rule (azure目标vm sizing): **RAM must meet-or-exceed** the source, but
    **vCPU may sit just below** it — Azure has no odd-core sizes, so a 3 vCPU /
    4 GiB source maps to a 2 vCPU target with RAM >= 4 (e.g. ``D2s_v5``), and we
    **prefer the D family** (general-purpose "Standard") on ties.

    Selection: among flavors with ``ram_gib >= source`` (the hard floor), rank by
      1. fewest vCPUs *above* the source (don't over-provision cores),
      2. fewest vCPUs *below* the floored target (don't needlessly under-provision),
      3. family preference (D first),
      4. least RAM over-provision, then SKU name.
    If nothing satisfies the RAM floor, fall back to the single largest flavor.
    """
    if not catalog:
        return None
    fits = [s for s in catalog if s["ram_gib"] >= ram_gib]
    if not fits:
        # RAM floor unmet — return the biggest available so the caller can flag it.
        return max(catalog, key=lambda s: (s["ram_gib"], s["vcpu"]))
    target = target_vcpu(catalog, vcpu)

    def key(s):
        over = max(0, s["vcpu"] - vcpu)       # cores above the source (discouraged)
        under = max(0, target - s["vcpu"])    # cores below the floored target (discouraged)
        return (over, under, FAMILY_PREFERENCE.get(s["family"], 9), s["ram_gib"], s["sku"])

    fits.sort(key=key)
    return fits[0]


def normalize_sku(sku: str) -> str:
    """Ensure a SKU name has the Standard_ prefix."""
    sku = sku.strip()
    if not sku.lower().startswith("standard_"):
        sku = "Standard_" + sku
    # Fix casing of the prefix only
    return "Standard_" + sku[len("Standard_"):]


def _get_all(url: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    while url:
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            print(f"Error querying Azure API: {e}", file=sys.stderr)
            break
        items.extend(data.get("Items", []))
        url = data.get("NextPageLink")
    return items


def query_vm_prices(sku: str, region: str, currency: str = "EUR") -> List[Dict[str, Any]]:
    """All price records (Consumption / Reservation / Spot) for one VM SKU in one region."""
    flt = (
        f"serviceName eq 'Virtual Machines' "
        f"and armSkuName eq '{sku}' "
        f"and armRegionName eq '{region}'"
    )
    url = f"{API_URL}?$filter={requests.utils.quote(flt)}&currencyCode={currency}"
    return _get_all(url)


def organize_vm_prices(items: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Reduce raw records into effective HOURLY rates per price type (cheapest of each).

    The Azure API is messy here:
      * Spot is tagged type='Consumption' with 'Spot' in meterName (NOT type='Spot').
      * 'Low Priority' meters are legacy and ignored.
      * 'Cloud Services' productName variants are not plain VMs and are ignored.
      * Reservation retailPrice is the TOTAL price for the whole term, so we
        convert it to an effective hourly rate (total / term hours).
    """
    out: Dict[str, Optional[float]] = {
        "linux": None, "windows": None, "spot": None,
        "reserved_1yr": None, "reserved_3yr": None,
    }
    for item in items:
        price = item.get("retailPrice")
        if price is None:
            continue
        product = item.get("productName", "").lower()
        meter = item.get("meterName", "").lower()
        ptype = item.get("type", "").lower()

        if "cloud services" in product:
            continue
        is_windows = "windows" in product

        if ptype == "reservation":
            if is_windows:
                continue  # Linux/base reservation only
            term = item.get("reservationTerm")
            if term == "1 Year":
                _min(out, "reserved_1yr", price / HOURS_PER_YEAR)
            elif term == "3 Years":
                _min(out, "reserved_3yr", price / (3 * HOURS_PER_YEAR))
        elif ptype == "consumption":
            if "low priority" in meter:
                continue
            if "spot" in meter:
                if not is_windows:
                    _min(out, "spot", price)
            else:
                _min(out, "windows" if is_windows else "linux", price)
        # DevTestConsumption and other types are ignored
    return out


def _min(d: Dict[str, Optional[float]], key: str, price: float) -> None:
    if d[key] is None or price < d[key]:
        d[key] = price


def disk_tier_for_size(size_gib: float, disk_type: str, tiers_data: Dict[str, Any]) -> Dict[str, Any]:
    """Round a requested disk size up to the next managed-disk tier.

    Returns {sku_name, product_name, tier_size_gib, label}.
    """
    dtype = tiers_data["disk_types"].get(disk_type)
    if dtype is None:
        raise ValueError(f"Unknown disk type '{disk_type}'. Options: {list(tiers_data['disk_types'])}")
    chosen = None
    for tier in tiers_data["tiers"]:
        if tier["size_gib"] >= size_gib:
            chosen = tier
            break
    if chosen is None:
        chosen = tiers_data["tiers"][-1]
    sku_name = f"{dtype['tier_prefix']}{chosen['index']} LRS"
    return {
        "sku_name": sku_name,
        "product_name": dtype["product_name"],
        "tier_size_gib": chosen["size_gib"],
        "label": dtype["label"],
    }


def query_disk_price(sku_name: str, product_name: str, region: str, currency: str = "EUR") -> Optional[float]:
    """Flat per-disk monthly price for a managed-disk tier (e.g. 'P4 LRS') in a region."""
    flt = (
        f"serviceName eq 'Storage' "
        f"and armRegionName eq '{region}' "
        f"and skuName eq '{sku_name}'"
    )
    url = f"{API_URL}?$filter={requests.utils.quote(flt)}&currencyCode={currency}"
    items = _get_all(url)
    best = None
    for item in items:
        if item.get("type", "").lower() != "consumption":
            continue
        if product_name.lower() not in item.get("productName", "").lower():
            continue
        # The per-disk monthly charge, not per-GB or transactions
        if "1/month" not in item.get("unitOfMeasure", "").lower():
            continue
        meter = item.get("meterName", "").lower()
        if "disk" not in meter:
            continue
        price = item.get("retailPrice")
        if price is not None and (best is None or price < best):
            best = price
    return best
