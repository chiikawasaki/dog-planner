import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("petting_test_compressed3.csv")

db_select_time = df["db_select_time"]
update_time = df["update_time"]

db_time = db_select_time + update_time
trial = df["trial"]

fig, ax = plt.subplots()

ax.scatter(trial, db_time, s=10)

ax.set_xlabel("Trial")
ax.set_ylabel("DB Processing Time (ms)")
fig.savefig("db_connect_time.png")
plt.show()