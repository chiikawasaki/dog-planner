import pandas as pd
import matplotlib.pyplot as plt
# 箱ひげ図
# dfにcsvファイルのデータを渡す
df = pd.read_csv("petting_test_compressed.csv")

before_600 = df[df["trial"] <= 599]["vibration_ms"]
after_600 = df[df["trial"] >= 600]["vibration_ms"]
all_data = df["vibration_ms"]

fig, ax = plt.subplots()

ax.boxplot(
    [before_600, after_600, all_data],
    tick_labels=["1-599", "600-1000", "All"]
)

ax.set_xlabel("Trial Range")
ax.set_ylabel("Response Time (ms)")
ax.set_title("Comparison of Response Time")
fig.savefig("boxplot-compressed.png")

plt.show()
