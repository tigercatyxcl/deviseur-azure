#!/usr/bin/env python3
"""
Step 1 of the deviseur-azure workflow.

Given a hardware spec (vCPU + RAM), propose several candidate Azure VM
flavors across families (Burstable / General / Memory / Compute) and show
their live price in a region, so the user can pick one.

Usage:
    python3 scripts/propose_flavors.py --vcpu 4 --ram 8 --region francecentral
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from azure_lib import (  # noqa: E402
    load_catalog, query_vm_prices, organize_vm_prices,
    currency_symbol, HOURS_PER_MONTH,
)


def rank_candidates(catalog, vcpu, ram, max_results):
    """Pick flavors near the spec.

    Priority: exact vCPU match, then smallest RAM gap. If too few exact-vCPU
    matches exist, widen to +/- 1 vCPU.
    """
    exact = [s for s in catalog if s["vcpu"] == vcpu]
    pool = exact if len(exact) >= 3 else [s for s in catalog if abs(s["vcpu"] - vcpu) <= 1]
    pool.sort(key=lambda s: (abs(s["ram_gib"] - ram), abs(s["vcpu"] - vcpu), s["sku"]))
    # De-duplicate by (family, vcpu, ram) keeping newest naming first
    seen = set()
    out = []
    for s in pool:
        key = (s["family"], s["vcpu"], s["ram_gib"])
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= max_results:
            break
    return out


def fmt(price, sym):
    return "N/A" if price is None else f"{sym}{price:.4f}"


def fmt_month(price, sym):
    return "N/A" if price is None else f"{sym}{price * HOURS_PER_MONTH:,.2f}"


def main():
    p = argparse.ArgumentParser(description="Propose Azure VM flavors for a hardware spec")
    p.add_argument("--vcpu", "-v", type=int, required=True, help="Number of vCPUs (e.g. 4)")
    p.add_argument("--ram", "-m", type=float, required=True, help="RAM in GiB (e.g. 8)")
    p.add_argument("--region", "-r", default="francecentral", help="Azure region (default: francecentral)")
    p.add_argument("--currency", "-c", default="EUR", help="Currency code (default: EUR)")
    p.add_argument("--max", type=int, default=6, help="Max candidates to show (default: 6)")
    args = p.parse_args()

    sym = currency_symbol(args.currency)
    catalog = load_catalog()
    candidates = rank_candidates(catalog, args.vcpu, args.ram, args.max)

    if not candidates:
        print(f"No catalog flavors found near {args.vcpu} vCPU / {args.ram} GiB.")
        return

    print(f"Proposing flavors for ~{args.vcpu} vCPU / {args.ram:g} GiB in {args.region} "
          f"({args.currency})...\n")

    rows = []
    for c in candidates:
        prices = organize_vm_prices(query_vm_prices(c["sku"], args.region, args.currency))
        rows.append((c, prices))

    fam_label = {"B": "Burstable", "D": "General", "E": "Memory", "F": "Compute"}

    print(f"## Flavor proposals — {args.vcpu} vCPU / {args.ram:g} GiB @ {args.region}\n")
    print("| # | Flavor | Type | vCPU | RAM | Linux/hr | Linux/mo | 1yr Res/mo |")
    print("|---|--------|------|------|-----|----------|----------|------------|")
    for i, (c, pr) in enumerate(rows, 1):
        res_mo = pr["reserved_1yr"]
        res_mo_val = "N/A" if res_mo is None else f"{sym}{res_mo * HOURS_PER_MONTH:,.2f}"
        print(f"| {i} | {c['sku']} | {fam_label.get(c['family'], c['family'])} "
              f"| {c['vcpu']} | {c['ram_gib']} GiB "
              f"| {fmt(pr['linux'], sym)} | {fmt_month(pr['linux'], sym)} | {res_mo_val} |")

    print("\n> Exact spec match is listed first (closest RAM). "
          "Burstable (B) is cheapest for low steady load; Memory (E) gives more RAM/vCPU.")
    print(f"\n**Next:** pick a flavor, then run the quote:\n"
          f"`python3 scripts/query_quote.py --sku <Flavor> --region {args.region} "
          f"--disk-size <GiB> --disk-type premium-ssd`")


if __name__ == "__main__":
    main()
