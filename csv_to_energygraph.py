import pandas as pd
import matplotlib.pyplot as plt

input_csv = pd.read_csv("petting_test.csv")

trial = input_csv[input_csv.keys()[0]]
energy = input_csv[input_csv.keys()[4]]

fig, ax = plt.subplots()

ax.plot(trial, energy, linewidth=1.5)

ax.set_xlabel("Trial")
ax.set_ylabel("Energy")
ax.set_xlim(0,100)
fig.savefig("energy.png")
plt.show()

