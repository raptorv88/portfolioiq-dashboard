from isin_master import resolve_scrip, stats

tests = [
    'GARDEN REACH SHIP&ENG LTD',
    'GARDEN REACH SHIPBUILDERS & EN',
    'XPRO INDIA LTD',
    'XPRO INDIA LIMITED',
    'SHRIRAMFIN',
    'ANANT RAJ',
    'ANANTRAJ',
    'KILBURN ENGINEERING LTD.'
]

for t in tests:
    r = resolve_scrip(t)
    print(f"{t:40} -> ISIN={r['isin']} | {r['canonical_name']}")

print()
print("Stats:", stats())