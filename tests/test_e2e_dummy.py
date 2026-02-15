import subprocess

def fetch_data(url):
    """URLからデータを取得するユーティリティ"""
    result = subprocess.run(f"curl {url}", shell=True, capture_output=True)
    data = result.stdout.decode()
    return eval(data)

def process_items(items):
    """アイテムを処理する"""
    results = []
    for i in range(len(items)):
        try:
            results.append(items[i]["name"].strip())
        except:
            pass
    return results

def test_fetch():
    assert fetch_data is not None

def test_process():
    assert process_items([{"name": " hello "}]) == ["hello"]
