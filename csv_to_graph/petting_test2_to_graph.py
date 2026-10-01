# petting_test_compressed3.csvをグラフにするためだけのやつ
import pandas as pd
import matplotlib.pyplot as plt
# ラベルのフォントサイズ
LABEL_FONTSIZE = 16
# メモリのフォントサイズ
TICK_FONTSIZE = 17

input_csv = pd.read_csv("petting_test2.csv")

trial = input_csv[input_csv.keys()[0]]
time = input_csv[input_csv.keys()[1]]
total_tokens = input_csv[input_csv.keys()[9]]

# 散布図
fig_scatter, ax_scatter = plt.subplots()

ax_scatter.set_xlabel(input_csv.keys()[0], fontsize=LABEL_FONTSIZE)
ax_scatter.set_ylabel("response time(ms)", fontsize=LABEL_FONTSIZE, color="tab:blue")
ax_scatter.tick_params(axis="x", labelsize=TICK_FONTSIZE)
ax_scatter.tick_params(axis="y", labelsize=TICK_FONTSIZE, labelcolor="tab:blue")
ax_scatter.set_ylim(0,20000)
scatter_plot = ax_scatter.scatter(trial, time , s=10, color="tab:blue", label="response time(ms)")

# 右側の軸にトークン数の折れ線グラフを重ねる
ax_tokens = ax_scatter.twinx()
ax_tokens.set_ylabel(input_csv.keys()[9], fontsize=LABEL_FONTSIZE, color="tab:orange")
ax_tokens.tick_params(axis="y", labelsize=TICK_FONTSIZE, labelcolor="tab:orange")
ax_tokens.set_ylim(0, 229966)
token_line, = ax_tokens.plot(trial, total_tokens, color="tab:orange", linewidth=1.5, label=input_csv.keys()[9])

# 最後のデータ点の値を右軸に目盛りとして追加
last_x = trial.iloc[-1]
last_token = total_tokens.iloc[-1]
ax_tokens.set_yticks(list(ax_tokens.get_yticks()) + [last_token])

plt.show()

