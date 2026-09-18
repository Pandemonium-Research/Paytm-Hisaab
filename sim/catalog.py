"""Static knobs for the synthetic world: labels, items, shop archetypes, people and places.

Everything here is fictional or public reference data. Behaviour (how these are combined into a
year of payments) lives in world.py.
"""

from __future__ import annotations

from datetime import date

# ---------------------------------------------------------------- labels

SUPPLY_LABELS = ("taxable_supply", "exempt_supply")
LABELS = SUPPLY_LABELS + (
    "personal_transfer",  # from household family: spouse, sibling, parent, in-law
    "inter_account",      # from an account in the owner's own name
    "non_business",       # loan, chit payout, gift from friends, hand loan repaid, deposit, insurance
    "refund_reversal",    # supplier sending money back, or a failed payout reversed
    "duplicate",          # the refunded twin of a double payment (or the later twin if none refunded)
)
PREDICTION_LABELS = LABELS + ("unclassified",)  # unclassified is an allowed answer, never a truth

# What a merchant can tap when asked, and the ledger labels each answer is consistent with.
ANSWER_CHOICES = {
    "sale": SUPPLY_LABELS,
    "family": ("personal_transfer",),
    "own_money": ("inter_account",),
    "loan_or_gift": ("non_business",),
    "refund": ("refund_reversal",),
    "double_payment": ("duplicate",),
    "not_sure": (),
}
LABEL_TO_ANSWER = {label: answer for answer, labels in ANSWER_CHOICES.items() for label in labels}

# Registration thresholds on aggregate turnover (taxable + exempt), CGST s.22 as summarised for
# engineering. Crossing means the running total goes strictly above the threshold.
THRESHOLDS = {"goods": 4_000_000, "services": 2_000_000}

FY_START = date(2025, 4, 1)
FY_END = date(2026, 3, 31)

# ---------------------------------------------------------------- items

_FRESH = "fresh / loose / unbranded - nil-rated or exempt"
_PACKED = "pre-packaged, labelled or branded - taxable"
_GOODS = "taxable goods"
_REST = "restaurant service (SAC 996331) - taxable service"

# item, hsn, exempt, basis, group, unit, unit price range (Rs), quantity choices
ITEMS = [
    ("Tomato", "0702", True, _FRESH, "veg", "kg", (20, 60), (0.5, 1, 1, 2, 3)),
    ("Onion", "0703", True, _FRESH, "veg", "kg", (25, 55), (0.5, 1, 1, 2, 3)),
    ("Potato", "0701", True, _FRESH, "veg", "kg", (20, 40), (0.5, 1, 2, 3)),
    ("Beans", "0708", True, _FRESH, "veg", "kg", (40, 100), (0.25, 0.5, 1)),
    ("Carrot", "0706", True, _FRESH, "veg", "kg", (30, 80), (0.25, 0.5, 1)),
    ("Cabbage", "0704", True, _FRESH, "veg", "pc", (20, 50), (1, 1, 2)),
    ("Coriander & greens", "0709", True, _FRESH, "veg", "bunch", (5, 20), (1, 2, 3)),
    ("Banana", "0803", True, _FRESH, "fruit", "dozen", (40, 80), (0.5, 1, 1, 2)),
    ("Tender coconut", "0801", True, _FRESH, "fruit", "pc", (40, 60), (1, 1, 2)),
    ("Lemon", "0805", True, _FRESH, "fruit", "pc", (5, 10), (2, 4, 6)),
    ("Loose milk", "0401", True, _FRESH, "dairy", "litre", (50, 60), (0.5, 1, 1, 2)),
    ("Eggs", "0407", True, _FRESH, "dairy", "pc", (6, 8), (6, 12, 30)),
    ("Fresh flowers", "0603", True, _FRESH, "pooja", "molla", (20, 80), (1, 1, 2)),
    ("Loose rice", "1006", True, _FRESH, "staples", "kg", (45, 70), (1, 2, 5, 10)),
    ("Biscuits", "1905", False, _PACKED, "packaged", "pkt", (10, 40), (1, 2, 3)),
    ("Namkeen", "2106", False, _PACKED, "packaged", "pkt", (20, 60), (1, 2)),
    ("Packaged atta", "1101", False, _PACKED, "staples_packed", "bag", (220, 320), (1,)),
    ("Branded rice", "1006", False, _PACKED, "staples_packed", "bag", (350, 600), (1,)),
    ("Cooking oil", "1512", False, _PACKED, "staples_packed", "litre", (140, 210), (1, 1, 2)),
    ("Sugar", "1701", False, _PACKED, "staples_packed", "kg", (45, 55), (1, 2)),
    ("Tea powder", "0902", False, _PACKED, "packaged", "pkt", (60, 250), (1,)),
    ("Instant noodles", "1902", False, _PACKED, "packaged", "pkt", (14, 60), (1, 2, 4)),
    ("Chocolate", "1806", False, _PACKED, "packaged", "pc", (10, 100), (1, 2)),
    ("Soft drink", "2202", False, _PACKED, "packaged", "bottle", (20, 95), (1, 2)),
    ("Bath soap", "3401", False, _PACKED, "personal_care", "pc", (35, 60), (1, 2, 4)),
    ("Detergent", "3402", False, _PACKED, "personal_care", "pkt", (90, 220), (1,)),
    ("Toothpaste", "3306", False, _PACKED, "personal_care", "pc", (50, 110), (1, 2)),
    ("Shampoo", "3305", False, _PACKED, "personal_care", "bottle", (80, 180), (1,)),
    ("Agarbatti", "3307", False, _PACKED, "pooja_packed", "pkt", (10, 60), (1, 2)),
    ("Phone cover", "3926", False, _GOODS, "mobile", "pc", (149, 499), (1,)),
    ("Charger", "8504", False, _GOODS, "mobile", "pc", (299, 999), (1,)),
    ("Earphones", "8518", False, _GOODS, "mobile", "pc", (199, 1499), (1,)),
    ("Screen guard", "3919", False, _GOODS, "mobile", "pc", (99, 399), (1, 2)),
    ("Memory card", "8523", False, _GOODS, "mobile", "pc", (299, 899), (1,)),
    ("USB cable", "8544", False, _GOODS, "mobile", "pc", (99, 399), (1, 2)),
    ("Power bank", "8507", False, _GOODS, "mobile", "pc", (699, 1999), (1,)),
    ("Coffee", "996331", False, _REST, "restaurant", "cup", (15, 30), (1, 2, 3)),
    ("Idli-vada", "996331", False, _REST, "restaurant", "plate", (40, 70), (1, 2, 3)),
    ("Masala dosa", "996331", False, _REST, "restaurant", "plate", (60, 110), (1, 2)),
    ("Meals", "996331", False, _REST, "restaurant", "plate", (90, 160), (1, 2, 3)),
    ("Parcel order", "996331", False, _REST, "restaurant", "order", (150, 900), (1,)),
]
ITEM_BY_NAME = {row[0]: row for row in ITEMS}

EXEMPT_GROUPS = {"veg": 6, "fruit": 2, "dairy": 3, "pooja": 1, "staples": 2}
TAXABLE_GROUPS_KIRANA = {"packaged": 5, "staples_packed": 3, "personal_care": 2, "pooja_packed": 1}

# ---------------------------------------------------------------- time shape

# relative sales intensity by hour of day (0..23)
HOUR_CURVES = {
    "kirana": [0, 0, 0, 0, 0, 1, 4, 8, 9, 7, 5, 4, 4, 4, 3, 3, 5, 8, 10, 10, 8, 4, 1, 0],
    "veg": [0, 0, 0, 0, 0, 3, 8, 10, 9, 6, 4, 3, 2, 2, 2, 3, 6, 9, 10, 9, 6, 3, 0, 0],
    "meals": [0, 0, 0, 0, 0, 0, 3, 9, 10, 6, 3, 5, 10, 9, 4, 3, 4, 6, 7, 9, 8, 5, 1, 0],
    "mobile": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 5, 6, 6, 6, 5, 5, 6, 7, 8, 8, 6, 2, 0],
}
DOW_FACTOR = [0.95, 0.95, 0.95, 1.0, 1.05, 1.2, 1.25]  # Monday..Sunday

# Approximate FY 2025-26 festival dates (a few days' bump either side is what matters).
FESTIVALS = {
    date(2025, 4, 6): ("Ram Navami", 1.25),
    date(2025, 4, 30): ("Akshaya Tritiya", 1.2),
    date(2025, 8, 8): ("Varamahalakshmi", 1.35),
    date(2025, 8, 9): ("Raksha Bandhan", 1.2),
    date(2025, 8, 27): ("Ganesh Chaturthi", 1.5),
    date(2025, 9, 5): ("Onam", 1.2),
    date(2025, 10, 1): ("Ayudha Puja", 1.4),
    date(2025, 10, 2): ("Dussehra", 1.35),
    date(2025, 10, 20): ("Deepavali", 1.6),
    date(2025, 10, 21): ("Deepavali", 1.4),
    date(2025, 12, 25): ("Christmas", 1.1),
    date(2026, 1, 14): ("Sankranti", 1.4),
    date(2026, 2, 15): ("Maha Shivaratri", 1.2),
    date(2026, 3, 4): ("Holi", 1.25),
    date(2026, 3, 19): ("Ugadi", 1.5),
    date(2026, 3, 20): ("Eid al-Fitr", 1.2),
    date(2026, 3, 26): ("Ram Navami", 1.2),
}
GIFT_FESTIVALS = [date(2025, 8, 27), date(2025, 10, 20), date(2026, 1, 14), date(2026, 3, 19)]

# ---------------------------------------------------------------- shop archetypes

_BASE = dict(
    avg_daily=50,          # sales on an ordinary weekday at the start of the window
    growth=0.01,           # compounding monthly growth in sales volume
    closed_p=0.01,         # chance the shop is shut on a given day
    hour_curve="kirana",
    exempt_share=0.5,      # chance a basket line is drawn from the exempt groups
    exempt_groups=EXEMPT_GROUPS,
    taxable_groups=TAXABLE_GROUPS_KIRANA,
    basket=(1, 6),         # lines per basket
    bulk_p=0.01,           # chance of a bulk order (quantities x4..x15)
    pos_share=0.30,        # share of sales billed on the POS (itemised bill is visible)
    card_share=0.10,       # share of POS sales paid by card
    p2p_sale_share=0.015,  # share of sales paid straight to the VPA instead of scanning
    regulars=260,          # size of the regular-customer pool
    regular_share=0.55,    # share of sales from regulars (rest are walk-ins)
    dup_rate=0.008,        # share of QR sales that get paid twice
    repeat_rate=0.004,     # genuine same-amount repeat purchases minutes apart (hard negatives)
    family=1.0,            # multiplier on household transfers
    own_topups=1.0,        # multiplier on month-start top-ups from own accounts
    nonbiz=1.0,            # multiplier on loans, chit, gifts, hand loans, deposits, insurance
    suppliers=(2, 4),
    supplier_ratio=(0.55, 0.75),  # share of recent sales paid out to suppliers
    supplier_gap=(2, 4),          # days between supplier payments
    stock_up_p=0.15,              # chance a supplier payment is a bigger stock-up (x1.8..x3)
    vendor_refund_rate=0.035,
    payout_fail_rate=0.007,
    sweep_p=0.7,           # chance of a Sunday-night sweep to savings
    sweep_share=(0.6, 0.9),  # share of the balance above the buffer that gets swept
    opening_balance=(15_000, 60_000),
    buffer=(2_000, 5_000),
    supply_kind="goods",
    gst_status="unregistered",
    mcc="5411",
    category="Grocery & provisions",
    supplier_kind="kirana",
)

ARCHETYPES = {
    "veg_vendor": {**_BASE, "avg_daily": 55, "exempt_share": 1.0, "hour_curve": "veg",
                   "exempt_groups": {"veg": 8, "fruit": 3, "pooja": 1}, "pos_share": 0.0,
                   "card_share": 0.0, "basket": (1, 4), "mcc": "5499",
                   "category": "Fruits & vegetables", "supplier_kind": "veg"},
    "mixed_kirana": {**_BASE, "avg_daily": 35, "exempt_share": 0.5, "pos_share": 0.5},
    "family_kirana": {**_BASE, "avg_daily": 32, "exempt_share": 0.6, "family": 1.8,
                      "own_topups": 0.6, "nonbiz": 1.5},
    "mobile_accessories": {**_BASE, "avg_daily": 12, "exempt_share": 0.0, "hour_curve": "mobile",
                           "taxable_groups": {"mobile": 1}, "basket": (1, 3), "pos_share": 0.6,
                           "card_share": 0.2, "growth": 0.04, "regulars": 90, "regular_share": 0.2,
                           "bulk_p": 0.004, "mcc": "5732", "category": "Mobile accessories",
                           "supplier_kind": "mobile"},
    "darshini": {**_BASE, "avg_daily": 45, "exempt_share": 0.0, "hour_curve": "meals",
                 "taxable_groups": {"restaurant": 1}, "basket": (1, 4), "pos_share": 0.2,
                 "supply_kind": "services", "mcc": "5814", "category": "Darshini restaurant",
                 "supplier_kind": "darshini"},
    "composition_kirana": {**_BASE, "exempt_share": 0.45, "pos_share": 0.6,
                           "gst_status": "composition"},
    "demo_sahana": {**_BASE, "avg_daily": 29, "exempt_share": 0.85, "pos_share": 0.35,
                    "growth": 0.025, "family": 1.8, "nonbiz": 2.0,
                    "category": "Fruits, vegetables & provisions", "supplier_kind": "veg"},
    "demo_lucknow_veg": {**_BASE, "avg_daily": 60, "exempt_share": 1.0, "hour_curve": "veg",
                         "exempt_groups": {"veg": 8, "fruit": 3}, "pos_share": 0.0,
                         "card_share": 0.0, "p2p_sale_share": 0.03, "basket": (1, 4),
                         "growth": 0.015, "mcc": "5499", "category": "Fruits & vegetables",
                         "supplier_kind": "veg"},
}

# ---------------------------------------------------------------- regions, people, places

REGIONS = {
    "ka": dict(
        language="kn", state="Karnataka",
        first=["Sahana", "Manjunath", "Raghu", "Sunitha", "Lakshmi", "Kavya", "Deepak", "Ravi",
               "Suresh", "Anitha", "Prakash", "Shwetha", "Naveen", "Pooja", "Harish", "Divya",
               "Girish", "Asha", "Mahesh", "Rekha", "Vinay", "Nandini", "Kiran", "Chaitra",
               "Santosh", "Bhavya", "Umesh", "Shilpa", "Arun", "Meena"],
        surnames=["Gowda", "Shetty", "Murthy", "Rao", "Hegde", "Kamath", "Naik", "Reddy", "Bhat",
                  "Patil", "Kulkarni", "Shenoy", "Poojary", "Acharya", "Nayak"],
        family_notes=["mane kharchu", "school fees", "gas", "amma", "for you", "rent",
                      "hospital", "ration"],
        places=[("Bengaluru", "Jayanagar", "560041", 12.9250, 77.5938),
                ("Bengaluru", "Malleshwaram", "560003", 13.0035, 77.5647),
                ("Mysuru", "Devaraja Mohalla", "570001", 12.3086, 76.6550)],
    ),
    "up": dict(
        language="hi", state="Uttar Pradesh",
        first=["Rakesh", "Sunita", "Amit", "Pooja", "Rajesh", "Neha", "Vikas", "Anjali", "Sanjay",
               "Priya", "Manoj", "Kavita", "Ashok", "Rekha", "Deepak", "Suman", "Rahul", "Seema",
               "Arvind", "Geeta"],
        surnames=["Maurya", "Yadav", "Verma", "Gupta", "Srivastava", "Mishra", "Tiwari", "Pandey",
                  "Singh", "Shukla", "Kushwaha", "Saxena", "Rastogi", "Awasthi"],
        family_notes=["ghar kharch", "school fees", "rashan", "maa ke liye", "bijli bill",
                      "dawai", "kiraya"],
        places=[("Lucknow", "Aminabad", "226018", 26.8467, 80.9310),
                ("Lucknow", "Chowk", "226003", 26.8691, 80.9097)],
    ),
    "tn": dict(
        language="ta", state="Tamil Nadu",
        first=["Karthik", "Priya", "Senthil", "Lakshmi", "Murugan", "Divya", "Arun", "Kavitha",
               "Suresh", "Meena", "Ramesh", "Anitha", "Vignesh", "Revathi", "Bala"],
        surnames=["Kumar", "Subramanian", "Rajan", "Natarajan", "Pillai", "Sundaram", "Krishnan",
                  "Raman", "Selvam", "Murugesan"],
        family_notes=["veetu selavu", "school fees", "gas", "amma", "for you", "rent"],
        places=[("Chennai", "Mylapore", "600004", 13.0368, 80.2676)],
    ),
    "ts": dict(
        language="te", state="Telangana",
        first=["Srinivas", "Lakshmi", "Venkat", "Padma", "Ravi", "Swathi", "Kiran", "Sravani",
               "Naresh", "Madhavi", "Suresh", "Anusha", "Prasad", "Sirisha"],
        surnames=["Reddy", "Rao", "Naidu", "Chowdary", "Varma", "Goud", "Yadav", "Raju", "Sharma"],
        family_notes=["intiki", "school fees", "gas", "amma", "for you", "rent"],
        places=[("Hyderabad", "Kukatpally", "500072", 17.4948, 78.3996)],
    ),
    "mh": dict(
        language="mr", state="Maharashtra",
        first=["Sachin", "Snehal", "Prashant", "Pooja", "Rahul", "Madhuri", "Nilesh", "Swati",
               "Amol", "Vaishali", "Sagar", "Ashwini"],
        surnames=["Patil", "Deshmukh", "Joshi", "Kulkarni", "Pawar", "Shinde", "Jadhav", "Kale",
                  "Gaikwad"],
        family_notes=["ghar kharch", "school fees", "gas", "aai", "for you", "bhade"],
        places=[("Pune", "Kothrud", "411038", 18.5074, 73.8077)],
    ),
    "wb": dict(
        language="bn", state="West Bengal",
        first=["Sourav", "Rimi", "Abhijit", "Moumita", "Subrata", "Payel", "Arindam", "Sutapa",
               "Debashis", "Tanushree"],
        surnames=["Das", "Ghosh", "Mukherjee", "Chatterjee", "Sen", "Roy", "Banerjee", "Saha",
                  "Paul", "Mondal"],
        family_notes=["songsar khoroch", "school fees", "gas", "maa", "for you", "bhara"],
        places=[("Kolkata", "Gariahat", "700019", 22.5184, 88.3663)],
    ),
}

PSP_SUFFIXES = ["okaxis", "okhdfcbank", "oksbi", "okicici", "ybl", "paytm", "ptyes", "pthdfc",
                "ibl", "axl"]

BUSINESS_WORDS = ["TRADERS", "WHOLESALE", "AGENCIES", "DISTRIBUTORS", "SUPPLIES"]
SUPPLIER_TEMPLATES = {
    "veg": ["SRI {deity} VEGETABLE TRADERS", "{place} FRUITS WHOLESALE", "{surname} AGRO TRADERS",
            "{deity} EGGS AND DAIRY SUPPLIES"],
    "kirana": ["{surname} AGENCIES", "SRI {deity} DISTRIBUTORS", "{place} WHOLESALE TRADERS",
               "{surname} FMCG SUPPLIES"],
    "mobile": ["TECHWORLD ACCESSORIES WHOLESALE", "{surname} MOBILE DISTRIBUTORS",
               "{place} ELECTRONICS TRADERS"],
    "darshini": ["{deity} DAIRY SUPPLIES", "{place} PROVISIONS WHOLESALE", "{surname} GAS AGENCIES",
                 "SRI {deity} VEGETABLE TRADERS"],
}
DEITIES = ["LAKSHMI", "GANESHA", "VENKATESHWARA", "DURGA", "MANJUNATHA", "SAI", "BALAJI",
           "ANNAPURNA"]

# fictional lenders and institutions
LENDERS = ["ANANTHA MICROCREDIT PVT LTD", "TRIVIKRAM FINANCE LTD", "SAHYADRI GRAMEEN CREDIT LTD"]
CHIT_FUNDS = ["KAVERI NIDHI CHITS PVT LTD", "SRI SUBHADRA CHIT FUNDS PVT LTD"]
INSURERS = ["STHIRA GENERAL INSURANCE LTD", "NIRBHAYA HEALTH INSURANCE LTD"]

TAX_OFFICES = {
    "Karnataka": ("Commercial Taxes Department",
                  "Office of the Assistant Commissioner of Commercial Taxes (SYN), LGSTO-120"),
    "Uttar Pradesh": ("State Tax Department",
                      "Office of the Deputy Commissioner, State Tax (SYN), Sector-9"),
    "Tamil Nadu": ("Commercial Taxes Department",
                   "Office of the Assistant Commissioner (ST) (SYN), Mylapore Assessment Circle"),
    "Telangana": ("Commercial Taxes Department",
                  "Office of the Assistant Commissioner (ST) (SYN), Kukatpally Circle"),
    "Maharashtra": ("Department of Goods and Services Tax",
                    "Office of the State Tax Officer (SYN), Pune Division"),
    "West Bengal": ("Directorate of Commercial Taxes",
                    "Office of the Commercial Tax Officer (SYN), Gariahat Charge"),
}

LEA_UNITS = [
    ("Cyber Crime Police Station, Hyderabad", "Telangana", "Hyderabad"),
    ("Cyber Crime Police Station, Jaipur", "Rajasthan", "Jaipur"),
    ("Cyber Crime Police Station, Lucknow", "Uttar Pradesh", "Lucknow"),
    ("Cyber Crime Police Station, Ahmedabad", "Gujarat", "Ahmedabad"),
]
FRAUD_SCHEMES = ["fake investment app", "courier customs scam", "part-time job task scam",
                 "electricity disconnection scam"]
