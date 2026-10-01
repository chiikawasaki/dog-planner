import pandas as pd
import matplotlib.pyplot as plt

# ラベルのフォントサイズ
LABEL_FONTSIZE = 16
# メモリのフォントサイズ
TICK_FONTSIZE = 17

df = pd.read_csv("petting_test_compressed3.csv")

db_select_time = df["db_select_time"]
update_time = df["update_time"]

db_time = db_select_time + update_time
trial = df["trial"]

fig, ax = plt.subplots()

ax.scatter(trial, db_time, s=10, color="tab:blue")

ax.set_xlabel("Trial", fontsize=LABEL_FONTSIZE)
ax.set_ylabel("DB Processing Time (ms)", fontsize=LABEL_FONTSIZE, color="tab:blue")
ax.tick_params(axis="x", labelsize=TICK_FONTSIZE)
ax.tick_params(axis="y", labelsize=TICK_FONTSIZE, labelcolor="tab:blue")
fig.savefig("db_connect_time.png", bbox_inches="tight")
plt.show()