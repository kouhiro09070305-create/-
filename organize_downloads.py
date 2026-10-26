# -*- coding: utf-8 -*-
"""
ダウンロードフォルダ整理ツール (Windows 用)

ダウンロードフォルダ直下のファイルを拡張子ごとに分類し、
以下のサブフォルダへ移動します。

    PDF   (.pdf)                         -> Documents
    画像  (.jpg .jpeg .png .gif など)    -> Images
    ZIP   (.zip)                         -> Archives

・移動先フォルダが存在しない場合は自動で作成します。
・移動先に同名ファイルがある場合は上書きせず、
  「ファイル名 (1).pdf」「ファイル名 (2).pdf」のように連番を付けて保存します。

使い方 (コマンドプロンプト / PowerShell):
    python organize_downloads.py              # ダウンロードフォルダを整理
    python organize_downloads.py --dry-run    # 実際には移動せず、結果だけ表示
    python organize_downloads.py --path "D:\\Downloads"   # 対象フォルダを指定

Python 3.8 以降の標準ライブラリのみで動作します (追加インストール不要)。
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 設定: 拡張子 → 移動先フォルダ名
# 拡張子は小文字・ドット付きで記述します。分類を増やしたい場合はここに追記してください。
# ---------------------------------------------------------------------------
CATEGORY_MAP = {
    # PDF → Documents
    ".pdf": "Documents",
    # 画像 → Images
    ".jpg": "Images",
    ".jpeg": "Images",
    ".png": "Images",
    ".gif": "Images",
    ".bmp": "Images",
    ".webp": "Images",
    ".tif": "Images",
    ".tiff": "Images",
    ".heic": "Images",
    ".svg": "Images",
    ".ico": "Images",
    # ZIP → Archives
    ".zip": "Archives",
}


def get_downloads_folder() -> Path:
    """Windows のダウンロードフォルダのパスを取得する。

    ダウンロードフォルダは場所を変更されている場合があるため、
    Windows API (SHGetKnownFolderPath) で実際の場所を問い合わせます。
    取得できない場合は「ユーザーフォルダ\\Downloads」を使います。
    """
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            import uuid

            # ダウンロードフォルダを表す KNOWNFOLDERID
            folder_id = uuid.UUID("{374DE290-123F-4565-9164-39C4925E467B}")

            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", wintypes.DWORD),
                    ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD),
                    ("Data4", wintypes.BYTE * 8),
                ]

            guid = GUID.from_buffer_copy(folder_id.bytes_le)
            path_ptr = ctypes.c_wchar_p()
            # 戻り値 0 (S_OK) なら成功
            result = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(guid), 0, None, ctypes.byref(path_ptr)
            )
            if result == 0:
                path = Path(path_ptr.value)
                # API が確保したメモリを解放する
                ctypes.windll.ole32.CoTaskMemFree(path_ptr)
                return path
        except Exception:
            # 何らかの理由で API 呼び出しに失敗した場合は下の既定値へ
            pass

    # 既定値: C:\Users\<ユーザー名>\Downloads
    return Path.home() / "Downloads"


def get_unique_path(dest_path: Path) -> Path:
    """移動先に同名ファイルがある場合、連番付きの空いているパスを返す。

    例: report.pdf が既にある → report (1).pdf、それもある → report (2).pdf ...
    """
    if not dest_path.exists():
        return dest_path

    stem = dest_path.stem      # 拡張子を除いたファイル名 (例: report)
    suffix = dest_path.suffix  # 拡張子 (例: .pdf)
    counter = 1
    while True:
        candidate = dest_path.with_name(f"{stem} ({counter}){suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def organize(target_dir: Path, dry_run: bool = False) -> None:
    """指定フォルダ直下のファイルを分類して移動する。"""
    if not target_dir.is_dir():
        print(f"[エラー] フォルダが見つかりません: {target_dir}")
        sys.exit(1)

    print(f"対象フォルダ: {target_dir}")
    if dry_run:
        print("※ ドライランモード: 実際にはファイルを移動しません")
    print("-" * 60)

    moved = 0    # 移動したファイル数
    skipped = 0  # 対象外としてスキップしたファイル数
    errors = 0   # 移動に失敗したファイル数

    # フォルダ直下の項目を名前順に処理 (サブフォルダの中までは見ない)
    for item in sorted(target_dir.iterdir(), key=lambda p: p.name.lower()):
        # フォルダはスキップ (Documents / Images / Archives 自体もここで除外される)
        if not item.is_file():
            continue

        # 拡張子を小文字にして判定 (.PDF や .Jpg にも対応)
        category = CATEGORY_MAP.get(item.suffix.lower())
        if category is None:
            skipped += 1
            continue

        dest_dir = target_dir / category

        try:
            # 移動先フォルダが無ければ作成 (既にあれば何もしない)
            if not dry_run:
                dest_dir.mkdir(parents=True, exist_ok=True)

            # 同名ファイルがあれば連番付きの名前にする (上書き防止)
            dest_path = get_unique_path(dest_dir / item.name)

            if not dry_run:
                shutil.move(str(item), str(dest_path))

            renamed = "" if dest_path.name == item.name else f"  (名前変更: {dest_path.name})"
            print(f"[移動] {item.name} -> {category}\\{dest_path.name}{renamed}")
            moved += 1
        except PermissionError:
            # 他のアプリで開いている、またはダウンロード中のファイルなど
            print(f"[スキップ] 使用中のため移動できません: {item.name}")
            errors += 1
        except OSError as e:
            print(f"[エラー] {item.name} の移動に失敗しました: {e}")
            errors += 1

    print("-" * 60)
    print(f"完了: 移動 {moved} 件 / 対象外 {skipped} 件 / 失敗 {errors} 件")


def main() -> None:
    # コマンドライン引数の定義
    parser = argparse.ArgumentParser(
        description="ダウンロードフォルダのファイルを拡張子ごとに自動分類します。"
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="整理するフォルダ (省略時は Windows のダウンロードフォルダ)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際には移動せず、どう分類されるかだけを表示する",
    )
    args = parser.parse_args()

    target_dir = args.path if args.path else get_downloads_folder()
    organize(target_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
