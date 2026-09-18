"""Static inputs to the simulator: item/HSN catalog, name pools, calendars, archetypes.

Only the HSN catalog is visible to the system under test (as public reference data).
Everything else here is part of the hidden generating process.
"""
from datetime import date

# (item, hsn, exempt, line_value_lo, line_value_hi)
# `exempt` reflects the fresh / loose / unbranded condition described in `basis` below.
# GST rates are deliberately omitted: they changed on 22 Sep 2025 and belong to the
# map_hsn_exemption skill, not to the data.
ITEMS = {
    "veg": [
        ("Tomato", "0702", True, 20, 120),
        ("Onion", "0703", True, 25, 150),
        ("Potato", "0701", True, 20, 120),
        ("Beans", "0708", True, 20, 90),
        ("Carrot", "0706", True, 15, 80),
        ("Cabbage", "0704", True, 15, 60),
        ("Coriander & greens", "0709", True, 10, 40),
        ("Banana", "0803", True, 30, 120),
        ("Tender coconut", "0801", True, 40, 120),
        ("Lemon", "0805", True, 10, 50),
        ("Loose milk", "0401", True, 28, 120),
        ("Eggs", "0407", True, 42, 180),
        ("Fresh flowers", "0603", True, 20, 150),
        ("Loose rice", "1006", True, 60, 600),
    ],
    "packaged": [
        ("Biscuits", "1905", False, 10, 80),
        ("Namkeen", "2106", False, 10, 120),
        ("Packaged atta", "1101", False, 60, 480),
        ("Branded rice", "1006", False, 90, 900),
        ("Cooking oil", "1512", False, 140, 950),
        ("Bath soap", "3401", False, 30, 220),
        ("Detergent", "3402", False, 40, 400),
        ("Toothpaste", "3306", False, 30, 160),
        ("Shampoo", "3305", False, 2, 250),
        ("Chocolate", "1806", False, 10, 120),
        ("Soft drink", "2202", False, 20, 110),
        ("Instant noodles", "1902", False, 14, 120),
        ("Tea powder", "0902", False, 50, 350),
        ("Sugar", "1701", False, 45, 250),
        ("Agarbatti", "3307", False, 10, 90),
    ],
    "mobile": [
        ("Phone cover", "3926", False, 120, 600),
        ("Charger", "8504", False, 250, 1500),
        ("Earphones", "8518", False, 200, 2500),
        ("Screen guard", "3919", False, 80, 400),
        ("Memory card", "8523", False, 350, 1200),
        ("USB cable", "8544", False, 100, 450),
        ("Power bank", "8507", False, 700, 2500),
    ],
    "darshini": [
        ("Coffee", "996331", False, 20, 40),
        ("Idli-vada", "996331", False, 40, 70),
        ("Masala dosa", "996331", False, 60, 110),
        ("Meals", "996331", False, 80, 150),
        ("Parcel order", "996331", False, 150, 600),
    ],
}

BASIS = {
    "veg": "fresh / loose / unbranded - nil-rated or exempt",
    "packaged": "pre-packaged, labelled or branded - taxable",
    "mobile": "taxable goods",
    "darshini": "restaurant service (SAC 996331) - taxable service",
}

# Hour-of-day weights, index 0..23.
HOURLY = {
    "shop":     [0, 0, 0, 0, 0, 0.2, 2, 4, 6, 6.5, 6, 5.5, 5, 4, 3.5, 3.5, 4.5, 6.5, 8.5, 9, 7.5, 4, 1, 0.2],
    "retail":   [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 5, 6, 6, 5, 5, 6, 7, 8, 8, 6, 1, 0.2, 0],
    "darshini": [0, 0, 0, 0, 0, 0.5, 5, 9, 10, 7, 4, 4, 8, 9, 5, 3, 4, 6, 7, 6, 4, 2, 0.5, 0],
}
DOW = [0.95, 0.90, 0.92, 0.95, 1.05, 1.20, 1.25]  # Mon..Sun
MONTH = {4: 1.0, 5: 0.96, 6: 0.98, 7: 0.97, 8: 1.04, 9: 1.0, 10: 1.10, 11: 1.03, 12: 1.0, 1: 1.0, 2: 0.97, 3: 1.03}

# Karnataka festival calendar, FY 2025-26. Sales rise on the day and the two days before.
FESTIVALS = {
    date(2025, 8, 8): 1.3,    # Varamahalakshmi
    date(2025, 8, 27): 1.35,  # Ganesha Chaturthi
    date(2025, 10, 1): 1.3,   # Ayudha Puja
    date(2025, 10, 2): 1.2,   # Vijayadashami
    date(2025, 10, 20): 1.5,  # Deepavali
    date(2025, 10, 21): 1.3,
    date(2026, 1, 14): 1.3,   # Sankranti
    date(2026, 3, 19): 1.4,   # Ugadi
}
GIFT_FESTIVALS = [date(2025, 10, 20), date(2026, 1, 14), date(2026, 3, 19)]


def festival_mult(d):
    best = 1.0
    for f, m in FESTIVALS.items():
        lead = (f - d).days
        if 0 <= lead <= 2:
            best = max(best, 1 + (m - 1) * (1.0, 0.6, 0.3)[lead])
    return best


MALE = ["Ravi", "Suresh", "Manjunath", "Kiran", "Prakash", "Naveen", "Raghu", "Santosh", "Mahesh",
        "Harish", "Vinay", "Arjun", "Abdul", "Imran", "Joseph", "Venkatesh", "Srinivas", "Anil",
        "Deepak", "Karthik", "Shivakumar", "Nagaraj", "Basavaraj", "Mohan", "Girish", "Ramesh"]
FEMALE = ["Lakshmi", "Kavya", "Deepa", "Shwetha", "Pooja", "Anitha", "Sunitha", "Rekha", "Divya",
          "Priya", "Ayesha", "Fathima", "Mary", "Bhavya", "Nandini", "Asha", "Geetha", "Roopa",
          "Sowmya", "Meghana", "Sahana", "Vidya"]
SURNAMES = ["Gowda", "Reddy", "Shetty", "Rao", "Naik", "Kumar", "Hegde", "Patil", "Murthy", "Iyer",
            "Nair", "Khan", "Sharma", "Prasad", "Bhat", "Kulkarni", "Swamy", "Raju", "DSouza",
            "Achar", "Poojary", "Pasha"]
HANDLES = ["okaxis", "oksbi", "okicici", "okhdfcbank", "ybl", "ibl", "axl", "ptyes", "ptaxis", "pthdfc", "ptsbi"]
BANKS = ["SBIN", "CNRB", "HDFC", "ICIC", "UTIB", "KARB", "BARB"]
LOCALITIES = ["Jayanagar", "Malleshwaram", "Basavanagudi", "Rajajinagar", "Indiranagar", "Yelahanka",
              "BTM Layout", "Vijayanagar", "Banashankari", "RT Nagar"]
DEITIES = ["Vinayaka", "Lakshmi", "Manjunatha", "Venkateshwara", "Raghavendra", "Chamundeshwari", "Annapoorneshwari"]

SUPPLIERS = {
    "grocery": ["Sri Vinayaka Vegetable Traders", "Annapoorna Wholesale", "Maruthi Agencies",
                "SLV Distributors", "Ganesh Provision Wholesale", "Nandi FMCG Distributors",
                "KRM Onion Commission Agents"],
    "mobile": ["Techline Mobile Distributors", "SP Road Accessories Hub", "Galaxy Telecom Traders"],
    "darshini": ["Sri Lakshmi Rice Traders", "Hotel Supplies Bengaluru", "Balaji Gas Agency", "Annapoorna Wholesale"],
}
LENDERS = ["Swiftcash Finance Pvt Ltd", "Laghu Udyog Finance Ltd", "Sahyog Microcredit Pvt Ltd"]
CHITS = ["Sri Chamundeshwari Chits Pvt Ltd", "Kaveri Chit Funds", "Sri Rama Chits"]
INSURERS = ["Suraksha General Insurance", "Abhaya General Insurance"]

PERSONAL_NOTES = ["mane kharchu", "for home", "amma medicine", "school fees", "rent share", "gas cylinder", "EMI share", "for you"]
GIFT_NOTES = ["Happy Deepavali", "shagun", "blessings", "gift", "Ugadi wishes"]

# Knobs for the hidden process. exempt_p = probability a basket line comes from the exempt pool.
_BASE = dict(kind="goods", pools=("veg", "packaged"), exempt_p=0.5, avg_daily=50, basket=(1, 5),
             pos_share=0.3, card_share=0.08, bulk_p=0.01, dup_p=0.008, repeat_p=0.004, growth=0.01,
             walkin_p=0.3, hours="shop", family=0.6, own_topup=0.3, supplier_days=4,
             supplier_hours=(6, 7, 14, 15), supplier_kind="grocery", sweep_p=0.5, nonbiz=1.0,
             gst="unregistered", mcc="5411", category="Grocery / provision store")

ARCHETYPES = {
    # Exclusively exempt: turnover can exceed Rs 40L with no registration liability (s.23).
    "veg_vendor": dict(_BASE, pools=("veg", None), exempt_p=1.0, avg_daily=55, basket=(1, 4),
                       pos_share=0.0, card_share=0.0, bulk_p=0.015, growth=0.005, walkin_p=0.35,
                       family=0.4, own_topup=0.25, supplier_days=6, supplier_hours=(5, 6),
                       nonbiz=0.7, mcc="5499", category="Fruits & vegetables"),
    "mixed_kirana": dict(_BASE, exempt_p=0.5, avg_daily=35, basket=(1, 6), pos_share=0.5, growth=0.01),
    "family_kirana": dict(_BASE, exempt_p=0.6, avg_daily=32, pos_share=0.25, growth=0.015,
                          family=1.8, own_topup=0.6, nonbiz=1.5),
    "mobile_accessories": dict(_BASE, pools=(None, "mobile"), exempt_p=0.0, avg_daily=12, basket=(1, 2),
                               pos_share=0.6, card_share=0.2, growth=0.04, walkin_p=0.7, hours="retail",
                               supplier_days=1, supplier_hours=(11, 12, 16), supplier_kind="mobile",
                               repeat_p=0.001, mcc="4812", category="Mobile phone accessories"),
    "darshini": dict(_BASE, kind="services", pools=(None, "darshini"), exempt_p=0.0, avg_daily=45,
                     basket=(1, 3), pos_share=0.2, card_share=0.05, walkin_p=0.5, hours="darshini",
                     family=0.4, own_topup=0.2, supplier_kind="darshini", repeat_p=0.01, nonbiz=0.7,
                     mcc="5814", category="Restaurant (darshini)"),
    "composition_kirana": dict(_BASE, exempt_p=0.45, avg_daily=45, pos_share=0.6, growth=0.01,
                               gst="composition"),
    # The demo hero. Calibrated in generate.py so aggregate turnover crosses Rs 40L on 14 Mar 2026.
    "demo_sahana": dict(_BASE, exempt_p=0.85, avg_daily=29, pos_share=0.35, card_share=0.04,
                        bulk_p=0.012, growth=0.025, family=1.8, own_topup=0.22, supplier_days=5,
                        supplier_hours=(5, 6, 7), nonbiz=2.0, mcc="5411",
                        category="Fruits, vegetables & provisions"),
}

for _k, _v in HOURLY.items():
    assert len(_v) == 24, _k


def vpa(rng, first, surname):
    f = "".join(c for c in first.lower() if c.isalpha())
    s = "".join(c for c in surname.lower() if c.isalpha())
    h = rng.choice(HANDLES)
    style = rng.random()
    if style < 0.45:
        return f"{f}.{s}{rng.randint(1, 99)}@{h}"
    if style < 0.8:
        return f"{rng.choice('6789')}{rng.randint(0, 9)}XXXXXX{rng.randint(10, 99)}@{h}"
    return f"{f}{rng.randint(100, 9999)}@{h}"


def bank_handle(rng):
    return f"A/C XXXXXX{rng.randint(1000, 9999)} {rng.choice(BANKS)}0{rng.randint(10000, 99999)}"


def business_name(rng, owner_first, arch):
    suffix = {
        "5499": ["Fruits & Vegetables", "Tarakari Angadi"],
        "5411": ["Provision Stores", "General Stores", "Super Market"],
        "4812": ["Mobile World", "Mobile Point", "Telecom"],
        "5814": ["Darshini", "Upahara", "Tiffin Centre"],
    }[arch["mcc"]]
    lead = owner_first if rng.random() < 0.5 else f"Sri {rng.choice(DEITIES)}"
    return f"{lead} {rng.choice(suffix)}"
