"""
Run: python data_generation/generate_fake_data.py
Output: data_generation/fake_data.csv
"""

import csv
import random
import os
from datetime import date, timedelta

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "fake_data.csv")
NUM_ROWS = 800
RANDOM_SEED = 42

random.seed(RANDOM_SEED)

GENDERS = ["Male", "Female", "Non-binary"]
GENDER_WEIGHTS = [0.46, 0.48, 0.06]

PAYMENT_METHODS = ["Credit Card", "Debit Card", "PayPal", "TWINT", "Invoice"]
PAYMENT_WEIGHTS = [0.35, 0.25, 0.20, 0.15, 0.05]

# Product categories with realistic price ranges (CHF) and return rates
CATEGORIES = {
    "Hiking Footwear":      {"price": (80, 280),  "return_rate": 0.18},
    "Trail Running Shoes":  {"price": (100, 240),  "return_rate": 0.15},
    "Ski Equipment":        {"price": (150, 900),  "return_rate": 0.08},
    "Ski Apparel":          {"price": (60, 400),   "return_rate": 0.12},
    "Hiking Apparel":       {"price": (40, 220),   "return_rate": 0.10},
    "Climbing Gear":        {"price": (30, 500),   "return_rate": 0.06},
    "Backpacks":            {"price": (50, 350),   "return_rate": 0.09},
    "Tents & Sleeping":     {"price": (80, 600),   "return_rate": 0.07},
    "Base Layers":          {"price": (30, 150),   "return_rate": 0.14},
    "Accessories":          {"price": (10, 80),    "return_rate": 0.11},
    "Navigation & Safety":  {"price": (20, 300),   "return_rate": 0.05},
    "Bike & MTB":           {"price": (40, 800),   "return_rate": 0.09},
}

CATEGORY_WEIGHTS = [1.5, 1.2, 1.3, 1.0, 1.4, 0.8, 1.3, 0.7, 1.6, 2.0, 0.5, 0.7]


def weighted_choice(options, weights):
    total = sum(weights)
    r = random.uniform(0, total)
    cumulative = 0
    for option, weight in zip(options, weights):
        cumulative += weight
        if r <= cumulative:
            return option
    return options[-1]


def random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def churn_probability(age: int, category: str, returns: int) -> float:
    base = 0.18
    if age > 55:
        base -= 0.05
    if age < 25:
        base += 0.08
    if returns == 1:
        base += 0.12
    if category in ("Accessories", "Base Layers"):
        base += 0.04
    if category in ("Ski Equipment", "Climbing Gear"):
        base -= 0.06
    return max(0.02, min(0.65, base))


def generate_row(customer_id: int) -> dict:
    age = int(random.gauss(38, 12))
    age = max(16, min(75, age))

    gender = weighted_choice(GENDERS, GENDER_WEIGHTS)
    category = weighted_choice(list(CATEGORIES.keys()), CATEGORY_WEIGHTS)
    cat_info = CATEGORIES[category]

    price = round(random.uniform(*cat_info["price"]), 2)
    quantity = random.choices([1, 2, 3, 4], weights=[0.65, 0.22, 0.09, 0.04])[0]
    total = round(price * quantity, 2)

    purchase_date = random_date(date(2023, 1, 1), date(2025, 12, 31))
    payment = weighted_choice(PAYMENT_METHODS, PAYMENT_WEIGHTS)

    returns = 1 if random.random() < cat_info["return_rate"] else 0
    churn = 1 if random.random() < churn_probability(age, category, returns) else 0

    return {
        "Customer ID": f"CUST{customer_id:05d}",
        "Customer Age": age,
        "Gender": gender,
        "Purchase Date": purchase_date.isoformat(),
        "Product Category": category,
        "Product Price": price,
        "Quantity": quantity,
        "Total Purchase Amount": total,
        "Payment Method": payment,
        "Returns": returns,
        "Churn": churn,
    }


def main():
    rows = [generate_row(i + 1) for i in range(NUM_ROWS)]

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {NUM_ROWS} rows -> {OUTPUT_PATH}")

    # Quick summary
    churned = sum(r["Churn"] for r in rows)
    returned = sum(r["Returns"] for r in rows)
    avg_spend = sum(r["Total Purchase Amount"] for r in rows) / NUM_ROWS
    print(f"Churn rate:   {churned / NUM_ROWS:.1%}")
    print(f"Return rate:  {returned / NUM_ROWS:.1%}")
    print(f"Avg spend:    CHF {avg_spend:.2f}")


if __name__ == "__main__":
    main()
