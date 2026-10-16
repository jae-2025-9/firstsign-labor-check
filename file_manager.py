"""
file_manager.py

파일 저장 및 로드
"""

import hashlib
import json
from pathlib import Path


##################################################
# Directory
##################################################

def ensure_directory(path: Path):
    """
    폴더가 없으면 생성
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )


##################################################
# JSON
##################################################

def save_json(data, file_path: Path):
    """
    JSON 저장
    """

    ensure_directory(file_path)

    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def load_json(file_path: Path):
    """
    JSON 읽기
    """

    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


##################################################
# Hash
##################################################

def file_sha256(file_path: Path) -> str:
    """
    파일 내용의 SHA-256. 기준서 추출 결과 캐시 키로 쓴다.
    """

    digest = hashlib.sha256()

    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)

    return digest.hexdigest()
