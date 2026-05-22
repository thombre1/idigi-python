# generate_training_data.py
# Creates a realistic synthetic KYC/account-opening dataset with 5000+ rows

import random
import string
import pandas as pd
import numpy as np

random.seed(42)
np.random.seed(42)

ROWS = 5000

# ---------- Helpers ----------

def rand_pan():
    letters = ''.join(random.choices(string.ascii_uppercase, k=5))
    nums = ''.join(random.choices(string.digits, k=4))
    last = random.choice(string.ascii_uppercase)
    return letters + nums + last

def rand_aadhaar():
    return ''.join(random.choices(string.digits, k=12))

def rand_mobile():
    first = random.choice("6789")
    rest = ''.join(random.choices(string.digits, k=9))
    return first + rest

def rand_name():
    first_names = [
        "Rohit","Amit","Priya","Sneha","Karan","Anjali","Vikas","Pooja",
        "Rahul","Simran","Arjun","Neha","Raj","Isha","Aditya","Meera"
    ]
    last_names = [
        "Sharma","Patel","Gupta","Verma","Singh","Kumar","Jain",
        "Mehta","Yadav","Reddy","Nair","Das"
    ]
    return random.choice(first_names), random.choice(last_names)

def rand_pincode():
    prefixes = ["11","12","40","56","60","70","80","90","91","92"]
    prefix = random.choice(prefixes)
    return prefix + ''.join(random.choices(string.digits, k=4))

def rand_email(fname, lname):
    domains = ["gmail.com","yahoo.com","outlook.com","hotmail.com"]
    return f"{fname.lower()}.{lname.lower()}{random.randint(1,999)}@{random.choice(domains)}"

def occupation_list():
    return [
        "Engineer","Teacher","Doctor","Student","Trader",
        "Cash","Broker","SelfEmployed","Farmer","Unknown"
    ]

# ---------- Risk Rules ----------

def occupation_risk(occ):
    risky = ["Cash","Broker","Unknown"]
    return 1 if occ in risky else 0

def pincode_risk(pin):
    return 1 if pin.startswith(("90","91","92")) else 0

def income_band_risk(income):
    if income < 12000:
        return 1
    return 0

def duplicate_flag():
    return 1 if random.random() < 0.08 else 0   # 8%

def invalid_name_match():
    return 1 if random.random() < 0.92 else 0   # 92% good match

# ---------- Label Logic ----------

def make_label(age, income, pinrisk, dup, namematch, occrisk):
    score = 0

    if age < 18:
        score += 5
    elif age < 21:
        score += 2

    if income < 12000:
        score += 2
    elif income > 80000:
        score -= 1

    score += pinrisk * 2
    score += dup * 4
    score += occrisk * 2

    if namematch == 0:
        score += 3

    # convert score into label
    # 0 = approve, 1 = risky/review/reject
    return 1 if score >= 4 else 0

# ---------- Generate ----------

rows = []

for _ in range(ROWS):
    fname, lname = rand_name()

    age = random.randint(18, 70)
    income = random.randint(8000, 150000)

    pincode = rand_pincode()
    pinrisk = pincode_risk(pincode)

    occ = random.choice(occupation_list())
    occrisk = occupation_risk(occ)

    dup = duplicate_flag()
    namematch = invalid_name_match()

    label = make_label(age, income, pinrisk, dup, namematch, occrisk)

    rows.append({
        "age": age,
        "income": income,
        "pincodeRisk": pinrisk,
        "duplicatePan": dup,
        "nameMatch": namematch,
        "occupationRisk": occrisk,
        "label": label,

        # optional extra fields
        "firstName": fname,
        "lastName": lname,
        "panNumber": rand_pan(),
        "aadhaarNumber": rand_aadhaar(),
        "mobile": rand_mobile(),
        "email": rand_email(fname, lname),
        "occupation": occ,
        "pincode": pincode
    })

df = pd.DataFrame(rows)

# Save two versions:
# 1. Full raw dataset
df.to_csv("training_full_5000.csv", index=False)

# 2. Model-only dataset
model_cols = [
    "age","income","pincodeRisk",
    "duplicatePan","nameMatch",
    "occupationRisk","label"
]
df[model_cols].to_csv("training_model_5000.csv", index=False)

print("Generated:")
print(" - training_full_5000.csv")
print(" - training_model_5000.csv")
print(df["label"].value_counts())