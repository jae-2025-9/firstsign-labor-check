"""
file_manager.py

파일 저장 및 로드
"""

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None


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
    JSON 저장. 임시 파일에 다 쓴 뒤 바꿔치기해서, 다른 요청이 쓰다 만 파일을 읽지 않게 한다.
    """

    file_path = Path(file_path)
    ensure_directory(file_path)

    descriptor, temp_path = tempfile.mkstemp(dir=file_path.parent, prefix=f".{file_path.name}.", suffix=".tmp")

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
        os.replace(temp_path, file_path)
    except BaseException:
        Path(temp_path).unlink(missing_ok=True)
        raise


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


##################################################
# Lock
##################################################

@contextmanager
def file_lock(path: Path):
    """
    같은 파일을 여러 요청이 동시에 만들지 않게 잠근다 (Linux·macOS).
    Windows에서는 잠금 없이 진행한다. 로컬 실행은 한 사람만 쓰므로 충분하다.
    """

    ensure_directory(path)

    with open(path, "w") as handle:
        if fcntl is not None:
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)
