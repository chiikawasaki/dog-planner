import pandas as pd

df = pd.read_csv("petting_test_compressed3.csv")

before_600 = df[df["trial"] <= 599]["vibration_ms"]
after_600 = df[df["trial"] >= 600]["vibration_ms"]
all_data = df["vibration_ms"]
# describeで数値データの基本的な統計量をまとめて計算してくれる
summary = pd.DataFrame({
    "1-599": before_600.describe(),
    "600-1000": after_600.describe(),
    "All": all_data.describe(),
})

print(summary)
summary.to_csv("response-time-summary-compressed3.csv")
