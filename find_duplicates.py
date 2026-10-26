#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重複ファイル検索ツール
======================

指定したフォルダの中（サブフォルダも含む）を調べて、
「中身がまったく同じファイル」を見つけて一覧表示します。
結果は画面に表示するだけでなく、CSV ファイルにも保存します。

※ このツールはファイルを「削除しません」。レポートを作るだけなので安心して使えます。

使い方（ターミナル / コマンドプロンプトで実行します）:
    python find_duplicates.py 調べたいフォルダ
    python find_duplicates.py 調べたいフォルダ --csv 結果.csv

例:
    python find_duplicates.py C:\\Users\\taro\\Pictures
    python find_duplicates.py ~/Documents --csv report.csv

しくみ（どうやって同じ内容だと判断しているか）:
    1. まずファイルサイズでグループ分けします。
       サイズが違うファイル同士は、中身が同じになることはありません。
       この段階で比較する数を大きく減らせるので、処理が速くなります。
    2. サイズが同じファイルだけ「ハッシュ値」を計算します。
       ハッシュ値とは、ファイルの中身から作る「指紋」のような文字列です。
       中身が同じなら必ず同じハッシュ値になり、
       1バイトでも違えばまったく別のハッシュ値になります。
    3. ハッシュ値が同じファイルを「重複」として報告します。
"""

# ---------------------------------------------------------------
# 必要な部品（モジュール）を読み込みます。どれも Python に最初から入っています。
# ---------------------------------------------------------------
import argparse  # コマンドラインの引数（フォルダ名など）を受け取るため
import csv  # CSV ファイルを書き出すため
import hashlib  # ハッシュ値（ファイルの指紋）を計算するため
import os  # フォルダの中を順番に調べるため
import sys  # エラー時にプログラムを終了するため
from collections import defaultdict  # 「グループ分け」を簡単に書くための便利な辞書
from datetime import datetime  # CSV のファイル名に日時を入れるため

# ファイルを読み込むときの1回あたりの大きさ（1MB）。
# 大きなファイルを一度に全部読むとメモリを大量に使うので、少しずつ読みます。
CHUNK_SIZE = 1024 * 1024


def format_size(size_in_bytes):
    """バイト数を「1.5 MB」のような人間が読みやすい形に変換します。"""
    size = float(size_in_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        # 1024 未満になったら、その単位で表示します
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024


def collect_files(folder):
    """
    フォルダの中のファイルを、サブフォルダも含めてすべて集めます。
    戻り値は {ファイルサイズ: [ファイルパスのリスト]} という辞書です。
    """
    # defaultdict(list) は、まだ無いキーを使ったときに自動で空のリストを作ってくれる辞書です
    files_by_size = defaultdict(list)

    # os.walk はフォルダの中を「再帰的に」（サブフォルダの奥まで）たどってくれます。
    # ループのたびに (今いるフォルダ, その中のフォルダ一覧, その中のファイル一覧) が返ってきます。
    # onerror を指定すると、開けないフォルダがあっても止まらずに警告を出して続行します。
    for current_dir, _sub_dirs, file_names in os.walk(folder, onerror=warn_walk_error):
        for name in file_names:
            # フォルダ名とファイル名をつなげて、完全なパスを作ります
            path = os.path.join(current_dir, name)

            # シンボリックリンク（ショートカットのようなもの）は、実体と同じファイルを
            # 二重に数えてしまうので対象外にします
            if os.path.islink(path):
                continue

            try:
                size = os.path.getsize(path)
            except OSError as error:
                # 途中でファイルが消えた・権限がない など
                print(f"[警告] サイズを取得できませんでした: {path} ({error})")
                continue

            # 0 バイトの空ファイルは、すべて「同じ内容」になってしまうので対象外にします
            if size == 0:
                continue

            files_by_size[size].append(path)

    return files_by_size


def warn_walk_error(error):
    """os.walk がフォルダを開けなかったときに呼ばれ、警告を表示します。"""
    print(f"[警告] フォルダを読み込めませんでした: {error.filename} ({error.strerror})")


def calculate_hash(path):
    """
    ファイルの中身から SHA-256 というハッシュ値を計算して返します。
    読み込めなかった場合は None を返します。
    """
    hasher = hashlib.sha256()
    try:
        # "rb" は「バイナリ（生のデータ）として読み込む」という意味です。
        # with を使うと、処理が終わったら自動でファイルを閉じてくれます。
        with open(path, "rb") as f:
            # ファイルを CHUNK_SIZE ずつ読み、読むたびにハッシュ計算に追加します。
            # f.read() が空（b""）を返したら、ファイルの最後まで読み終わった合図です。
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
    except OSError as error:
        print(f"[警告] ファイルを読み込めませんでした: {path} ({error})")
        return None

    # hexdigest() でハッシュ値を「英数字の文字列」として取り出します
    return hasher.hexdigest()


def find_duplicates(folder):
    """
    重複ファイルを探して、グループのリストを返します。
    各グループは {"hash": ハッシュ値, "size": サイズ, "paths": [パス, ...]} という辞書です。
    """
    print(f"フォルダを調べています: {folder}")
    files_by_size = collect_files(folder)

    total_files = sum(len(paths) for paths in files_by_size.values())
    print(f"見つかったファイル数（空ファイルを除く）: {total_files}")

    duplicate_groups = []

    # sorted(..., reverse=True) で大きいファイルから順に処理します。
    # （結果も大きい順に並ぶので、容量のムダが大きいものから確認できます）
    for size in sorted(files_by_size, reverse=True):
        paths = files_by_size[size]

        # 同じサイズのファイルが1つしかなければ、重複の可能性はないのでスキップ
        if len(paths) < 2:
            continue

        # 同じサイズのファイルについて、ハッシュ値ごとにグループ分けします
        files_by_hash = defaultdict(list)
        for path in paths:
            file_hash = calculate_hash(path)
            if file_hash is not None:
                files_by_hash[file_hash].append(path)

        # 同じハッシュ値のファイルが2つ以上あれば「重複」です
        for file_hash, same_paths in files_by_hash.items():
            if len(same_paths) >= 2:
                duplicate_groups.append(
                    {
                        "hash": file_hash,
                        "size": size,
                        "paths": sorted(same_paths),  # パスを名前順に並べて見やすくします
                    }
                )

    return duplicate_groups


def print_report(groups):
    """重複ファイルの一覧を画面に表示します。"""
    print()
    print("=" * 70)
    print("重複ファイル レポート")
    print("=" * 70)

    if not groups:
        print("重複しているファイルは見つかりませんでした。")
        return

    wasted_bytes = 0  # 重複によってムダになっている容量の合計

    # enumerate(..., start=1) で、グループに 1, 2, 3... と番号を付けます
    for number, group in enumerate(groups, start=1):
        count = len(group["paths"])
        print()
        print(
            f"[グループ {number}] {count} 個の同じファイル / "
            f"1個あたり {format_size(group['size'])} ({group['size']:,} バイト)"
        )
        for path in group["paths"]:
            print(f"    {path}")

        # 1つを残して、残りのコピー分がムダな容量です
        wasted_bytes += group["size"] * (count - 1)

    duplicate_file_count = sum(len(g["paths"]) for g in groups)
    print()
    print("-" * 70)
    print(f"重複グループ数        : {len(groups)}")
    print(f"重複に含まれるファイル数: {duplicate_file_count}")
    print(f"削減できる可能性のある容量: {format_size(wasted_bytes)} ({wasted_bytes:,} バイト)")
    print("※ このツールはファイルを削除していません。削除する場合はご自身で確認してから行ってください。")


def save_csv(groups, csv_path):
    """重複ファイルの一覧を CSV ファイルに保存します。"""
    # encoding="utf-8-sig" にすると、Excel で開いたときに日本語が文字化けしにくくなります。
    # newline="" は、CSV に余計な空行が入らないようにするためのおまじないです。
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)

        # 1行目は見出し（ヘッダー）です
        writer.writerow(
            ["グループ番号", "ファイルパス", "ファイルサイズ(バイト)", "ファイルサイズ", "SHA-256ハッシュ値"]
        )

        # 1ファイルにつき1行ずつ書き込みます
        for number, group in enumerate(groups, start=1):
            for path in group["paths"]:
                writer.writerow(
                    [number, path, group["size"], format_size(group["size"]), group["hash"]]
                )

    print(f"CSV ファイルに保存しました: {csv_path}")


def main():
    """プログラムの入り口です。ここから処理が始まります。"""
    # コマンドラインから受け取る引数の設定
    parser = argparse.ArgumentParser(
        description="指定フォルダ以下の重複ファイル（中身が同じファイル）を探してレポートします。削除は行いません。"
    )
    parser.add_argument("folder", help="調べたいフォルダのパス")
    parser.add_argument(
        "--csv",
        help="結果を保存する CSV ファイル名（省略すると duplicates_年月日_時分秒.csv）",
    )
    args = parser.parse_args()

    # 「~」（ホームフォルダ）を展開し、絶対パス（フルパス）に変換します
    folder = os.path.abspath(os.path.expanduser(args.folder))

    # フォルダが存在するか確認します
    if not os.path.isdir(folder):
        print(f"[エラー] フォルダが見つかりません: {folder}")
        sys.exit(1)

    # CSV ファイル名が指定されていなければ、日時入りの名前を自動で作ります
    csv_path = args.csv or f"duplicates_{datetime.now():%Y%m%d_%H%M%S}.csv"

    groups = find_duplicates(folder)
    print_report(groups)
    print()
    save_csv(groups, csv_path)


# このファイルを直接実行したときだけ main() を呼び出します。
# （他のプログラムから import したときには自動で動かないようにするための定番の書き方です）
if __name__ == "__main__":
    main()
