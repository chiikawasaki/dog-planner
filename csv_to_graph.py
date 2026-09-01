import pandas as pd
import matplotlib.pyplot as plt
# 目盛りを打つ位置を、指定した数の倍数にするためのクラス
from matplotlib.ticker import MultipleLocator
# ラベルのフォントサイズ
LABEL_FONTSIZE = 16
# メモリのフォントサイズ
TICK_FONTSIZE = 17
# # 散布図の軸の範囲と目盛り間隔（データを変えても固定したいのでここで指定）
# TIME_YMAX = 20000
# TIME_YSTEP = 2500
# TOKENS_YMAX = 16000
# 2000の倍数をメモリにする
# TOKENS_YSTEP = 2000

input_csv = pd.read_csv("petting_test_compressed3.csv")

trial = input_csv[input_csv.keys()[0]]
time = input_csv[input_csv.keys()[1]]
total_tokens = input_csv[input_csv.keys()[9]]

# 折れ線グラフ
fig_line, ax_line = plt.subplots()

ax_line.set_xlabel(input_csv.keys()[0], fontsize=LABEL_FONTSIZE)
ax_line.set_ylabel("response time(ms)", fontsize=LABEL_FONTSIZE)
ax_line.tick_params(axis="both", labelsize=TICK_FONTSIZE)
ax_line.plot(trial, time, linestyle="solid", marker="o")

fig_line.savefig("petting_test2.png")

# 散布図
fig_scatter, ax_scatter = plt.subplots()

ax_scatter.set_xlabel(input_csv.keys()[0], fontsize=LABEL_FONTSIZE)
ax_scatter.set_ylabel("response time(ms)", fontsize=LABEL_FONTSIZE)
ax_scatter.tick_params(axis="both", labelsize=TICK_FONTSIZE)
ax_scatter.set_ylim(0, TIME_YMAX)
ax_scatter.yaxis.set_major_locator(MultipleLocator(TIME_YSTEP))
scatter_plot = ax_scatter.scatter(trial, time , s=10, label="response time(ms)")

# 右側の軸にトークン数の折れ線グラフを重ねる
ax_tokens = ax_scatter.twinx()
ax_tokens.set_ylabel(input_csv.keys()[9], fontsize=LABEL_FONTSIZE)
ax_tokens.tick_params(axis="y", labelsize=TICK_FONTSIZE)
ax_tokens.set_ylim(0, TOKENS_YMAX)
ax_tokens.yaxis.set_major_locator(MultipleLocator(TOKENS_YSTEP))
token_line, = ax_tokens.plot(trial, total_tokens, color="tab:orange", linewidth=1.5, label=input_csv.keys()[9])

# 最後のデータ点の値を右軸に目盛りとして追加
# last_x = trial.iloc[-1]
# last_token = total_tokens.iloc[-1]
# ax_tokens.set_yticks(list(ax_tokens.get_yticks()) + [last_token])

ax_scatter.legend(handles=[scatter_plot, token_line], loc="upper left")

fig_scatter.savefig("petting_test2.png")


moving_average = time.rolling(window=50).mean()

fig, ax = plt.subplots()

ax.plot(trial, moving_average, linewidth=2, label="50-trial moving average")

ax.set_xlabel("Trial", fontsize=LABEL_FONTSIZE)
ax.set_ylabel("Response time (ms)", fontsize=LABEL_FONTSIZE)
ax.tick_params(axis="both", labelsize=TICK_FONTSIZE)
ax.legend()

fig.savefig("trial-responsetime-compressed3.png", bbox_inches="tight")

# 折れ線グラフ
figtokens, axtokens = plt.subplots()

axtokens.set_xlabel(input_csv.keys()[0], fontsize=LABEL_FONTSIZE)
axtokens.set_ylabel(input_csv.keys()[9], fontsize=LABEL_FONTSIZE)
axtokens.tick_params(axis="both", labelsize=TICK_FONTSIZE)
axtokens.plot(trial, total_tokens, linewidth=2)

figtokens.savefig("petting_test2.png")



plt.show()

