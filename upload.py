"""
upload.py

Upstage Files API
"""

from pathlib import Path

from agent_client import get_client


##################################################
# Upload File
##################################################

def upload_file(
    file_path: str | Path
) -> str:
    """
    Files API를 이용하여 문서를 업로드한다.

    Returns
    -------
    str
        업로드된 File ID
    """

    file_path = Path(file_path)

    if not file_path.exists():

        raise FileNotFoundError(
            f"{file_path} 파일이 존재하지 않습니다."
        )

    print(f"Uploading... {file_path.name}")

    with open(file_path, "rb") as f:

        uploaded_file = get_client().files.create(
            file=f,
            purpose="user_data"
        )

    print(f"Upload Complete : {uploaded_file.id}")

    return uploaded_file.id
