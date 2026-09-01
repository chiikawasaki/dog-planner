import csv
import time
import requests

PET_ID = "791330b5-c8b2-4fca-96dd-195746286c3b"
BASE_URL = "http://127.0.0.1:8000"
        

with open("petting_test_compressed3.csv", "w", newline="", encoding="utf-8") as f, \
     open("error_log3.csv", "w", newline="", encoding="utf-8") as error_file:
    writer = csv.writer(f)
    writer.writerow([
        "trial",
        "vibration_ms",
        "petting_ms",
        "vibration_pattern",
        "energy",
        "intimacy",
        "input_tokens",
        "output_tokens",
        "thinking_tokens",
        "total_tokens",
        "vibration_compressed",
        "petting_compressed",
        "db_select_time",
        "gemini_time",
        "compress_time",
        "update_time",
        "total_time",
        "client_elapsed_ms",
        "network_overhead_ms",
    ])

    # エラー記録用CSV
    error_writer = csv.writer(error_file)
    error_writer.writerow([
        "trial",
        "phase",         # vibration か petting か
        "status_code",
        "response_text",
    ])

    trial = 1
    while trial <= 1000:
        start = time.perf_counter()
        vibration = requests.post(
            f"{BASE_URL}/pet/vibration",
            json={"pet_id": PET_ID},
        )
        vibration_ms = (time.perf_counter() - start) * 1000

        if vibration.status_code != 200:
            error_writer.writerow([
                trial,
                "vibration",
                vibration.status_code,
                vibration.text,
            ])
            error_file.flush()

            print(f"{trial}/1000 振動APIでエラー。やり直します")
            time.sleep(2)
            continue

        time.sleep(5)

        start = time.perf_counter()
        petting = requests.post(
            f"{BASE_URL}/pet/petting",
            json={
                "pet_id": PET_ID,
                "petting_duration": 5,
            },
        )
        
        petting_ms = (time.perf_counter() - start) * 1000
        
        if petting.status_code != 200:
            error_writer.writerow([
                trial,
                "petting",
                petting.status_code,
                petting.text,
            ])
            error_file.flush()
            print(f"{trial}/1000 撫で終了APIでエラー。やり直します")
            time.sleep(2)
            continue
        
        vibration_data = vibration.json()
        
        pattern = vibration_data["vibration_pattern"]
        usage = vibration_data["usage"]
        input_tokens = usage["input_tokens"]
        output_tokens = usage["output_tokens"]
        thinking_tokens = usage["thinking_tokens"]
        total_tokens = usage["total_tokens"]

        petting_data = petting.json()
        energy = petting_data["energy"]
        intimacy = petting_data["intimacy"]

        time_data = vibration_data["time"]
        db_select_time = time_data["db_select_time"]
        gemini_time = time_data["gemini_time"]
        compress_time = time_data["compress_time"]
        update_time = time_data["update_time"]
        total_time = time_data["total_time"]

        # クライアント接続の時間
        # response.elapsed: リクエスト送信〜レスポンスヘッダ受信まで(requests計測)
        client_elapsed_ms = vibration.elapsed.total_seconds() * 1000
        # ネットワーク/接続オーバーヘッド: クライアント往復 - サーバー処理時間
        network_overhead_ms = vibration_ms - total_time

        # 圧縮が起きたか（振動時・撫で時それぞれ）
        vibration_compressed = bool(vibration_data.get("compressed"))
        petting_compressed = bool(petting_data.get("compressed"))
        if vibration_compressed or petting_compressed:
            print(f"{trial}/1000 圧縮が発生 (振動:{vibration_compressed} 撫で:{petting_compressed})")

        writer.writerow([
            trial,
            round(vibration_ms, 3),
            round(petting_ms, 3),
            pattern,
            energy,
            intimacy,
            input_tokens,
            output_tokens,
            thinking_tokens,
            total_tokens,
            vibration_compressed,
            petting_compressed,
            db_select_time,
            gemini_time,
            compress_time,
            update_time,
            total_time,
            round(client_elapsed_ms, 3),
            round(network_overhead_ms, 3),
        ])
        f.flush()

        print(
            f"{trial}/1000 "
            f"振動:{vibration_ms:.1f}ms "
            f"撫で終了:{petting_ms:.1f}ms"
            f"total_tokens:{total_tokens}"
            f"input_tokens:{input_tokens}"
            f"output_tokens:{output_tokens}"
        )

        # 成功したときだけ次の試行へ進む(エラー時はcontinueで同じtrialをやり直す)
        trial += 1
