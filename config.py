"""
config.py

첫사인 알바 안심 체크 (FirstSign x Upstage Document Agent)

프로젝트 환경설정
"""

import os
from pathlib import Path

from dotenv import load_dotenv

##################################################
# Load Environment
##################################################

load_dotenv()

##################################################
# Upstage API
##################################################

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY", "").strip()

UPSTAGE_BASE_URL = "https://api.upstage.ai/v2"

##################################################
# Studio Agents
##################################################

# 계약서 추출 에이전트 (Parse → Extract, contract_info)
CONTRACT_AGENT_ID = os.getenv("CONTRACT_AGENT_ID", "").strip()
CONTRACT_CONFIG_ID = os.getenv("CONTRACT_CONFIG_ID", "").strip()

# 기준서 추출 에이전트 (Parse → Extract, criteria)
CRITERIA_AGENT_ID = os.getenv("CRITERIA_AGENT_ID", "").strip()
CRITERIA_CONFIG_ID = os.getenv("CRITERIA_CONFIG_ID", "").strip()

# 평가 에이전트 (Parse → Classify → 분류별 Extract)
REVIEW_AGENT_ID = os.getenv("REVIEW_AGENT_ID", "").strip()
REVIEW_CONFIG_ID = os.getenv("REVIEW_CONFIG_ID", "").strip()

# 에이전트 Job 하나를 기다리는 최대 시간(초). 넘기기 전에 완료되면 결과를 쓴다.
AGENT_TIMEOUT_SECONDS = int(os.getenv("AGENT_TIMEOUT_SECONDS", "420"))

# Studio 일시 오류(model_request_error 등) 때 Job을 새로 만들어 시도하는 최대 횟수
AGENT_ATTEMPTS = max(1, int(os.getenv("AGENT_ATTEMPTS", "3")))

# 업로드·Job 생성·상태 조회 HTTP 요청 하나의 최대 시간(초)
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "60"))

# 1이면 키가 있어도 데모 모드로 실행한다 (발표 중 요청 제한 대비)
FORCE_DEMO = os.getenv("FORCE_DEMO", "0").strip() == "1"

##################################################
# Project Directory
##################################################

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"

SAMPLE_DIR = DATA_DIR / "samples"

FIXTURE_DIR = BASE_DIR / "fixtures"

OUTPUT_DIR = BASE_DIR / "output"

RESULT_DIR = BASE_DIR / "result"

CACHE_DIR = OUTPUT_DIR / "cache"

RUNS_DIR = OUTPUT_DIR / "runs"

##################################################
# Input Files
##################################################

# 점검 기준서는 서비스가 고정으로 쓴다. 기준을 바꿀 때는 이 PDF만 교체한다.
CRITERIA_FILE = DATA_DIR / "criteria_v2_2026-10.pdf"

# 체험용 가상 근로계약서 4종
SAMPLES = {
    "1": {"file": "sample1.pdf", "label": "샘플 1 · 성실카페 (정상)"},
    "2": {"file": "sample2.pdf", "label": "샘플 2 · 한빛분식 (필수 항목 누락)"},
    "3": {"file": "sample3.pdf", "label": "샘플 3 · 스피드편의점 (위약금·최저임금 미달)"},
    "4": {"file": "sample4.pdf", "label": "샘플 4 · 푸른서점 (주 15시간 미만)"},
}

DEFAULT_CONTRACT_FILE = SAMPLE_DIR / SAMPLES["1"]["file"]

MAX_UPLOAD_MB = 10

##################################################
# Output Files (CLI 기본 경로)
##################################################

CONTRACT_JSON = OUTPUT_DIR / "contract.json"

CRITERIA_JSON = OUTPUT_DIR / "criteria.json"

REVIEW_PDF = OUTPUT_DIR / "Review_Input.pdf"

REVIEW_RESULT = RESULT_DIR / "review_result.json"

##################################################
# Fonts
##################################################

FONT_NAME = "Nanum"

FONT_PATH = BASE_DIR / "fonts" / "NanumGothic-Regular.ttf"


##################################################
# Directory Initialization
##################################################

def create_directories():

    for path in (OUTPUT_DIR, RESULT_DIR, CACHE_DIR, RUNS_DIR):
        path.mkdir(parents=True, exist_ok=True)


##################################################
# Configuration Validation
##################################################

def required_settings() -> dict:

    return {
        "UPSTAGE_API_KEY": UPSTAGE_API_KEY,
        "CONTRACT_AGENT_ID": CONTRACT_AGENT_ID,
        "CONTRACT_CONFIG_ID": CONTRACT_CONFIG_ID,
        "CRITERIA_AGENT_ID": CRITERIA_AGENT_ID,
        "CRITERIA_CONFIG_ID": CRITERIA_CONFIG_ID,
        "REVIEW_AGENT_ID": REVIEW_AGENT_ID,
        "REVIEW_CONFIG_ID": REVIEW_CONFIG_ID,
    }


def missing_settings() -> list[str]:

    return [key for key, value in required_settings().items() if not value]


def is_live_ready() -> bool:
    """
    Studio 에이전트를 실제로 호출할 수 있는지 확인한다.
    """

    return not FORCE_DEMO and not missing_settings()


def validate_config():

    missing = missing_settings()

    if missing:

        raise ValueError(
            "다음 환경변수가 설정되지 않았습니다.\n\n"
            + "\n".join(missing)
        )

    create_directories()


##################################################
# Project Information
##################################################

def print_config():

    print("=" * 60)
    print("Project Configuration")
    print("=" * 60)

    print(f"Project Directory : {BASE_DIR}")
    print(f"Criteria File     : {CRITERIA_FILE.name}")
    print(f"Output Directory  : {OUTPUT_DIR}")
    print(f"Result Directory  : {RESULT_DIR}")

    print()

    print(f"Contract Agent    : {CONTRACT_AGENT_ID} (config {CONTRACT_CONFIG_ID})")
    print(f"Criteria Agent    : {CRITERIA_AGENT_ID} (config {CRITERIA_CONFIG_ID})")
    print(f"Review Agent      : {REVIEW_AGENT_ID} (config {REVIEW_CONFIG_ID})")

    print("=" * 60)
