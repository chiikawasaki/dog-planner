import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("petting_test_compressed3.csv")

gemini_time =df["compress_time"] + df["gemini_time"]
trial = df["trial"]

fig, ax = plt.subplots()

ax.scatter(trial, gemini_time, s=10)

ax.set_xlabel("Trial")
ax.set_ylabel("AI Time (ms)")
fig.savefig("ai_time_compressed3.png")
plt.show()