"""
agent_client.py

공통 Agent 실행 모듈

Contract Agent
Criteria Agent
Review Agent

모든 Agent는 이 클래스를 이용하여 실행한다.
"""

import json
import time
from functools import lru_cache

from openai import OpenAI

from config import (
    AGENT_TIMEOUT_SECONDS,
    UPSTAGE_API_KEY,
    UPSTAGE_BASE_URL
)

##################################################
# OpenAI Client
##################################################

@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    """
    Upstage API 클라이언트를 처음 쓸 때 만든다.

    키가 없는 데모 모드에서도 모듈을 import할 수 있도록
    import 시점에 클라이언트를 만들지 않는다.
    """

    if not UPSTAGE_API_KEY:

        raise RuntimeError(
            "UPSTAGE_API_KEY가 설정되지 않았습니다. .env를 확인하세요."
        )

    return OpenAI(
        api_key=UPSTAGE_API_KEY,
        base_url=UPSTAGE_BASE_URL
    )


##################################################
# Agent Error
##################################################

class AgentError(RuntimeError):
    """
    Studio 에이전트 실행 실패
    """


##################################################
# Agent Client
##################################################

class AgentClient:
    """
    Studio Agent 실행 클래스
    """

    def __init__(
        self,
        agent_id: str,
        config_id: str = "1",
        name: str = "Agent"
    ):

        self.agent_id = agent_id
        self.config_id = config_id
        self.name = name

    ##################################################
    # Job 생성
    ##################################################

    def create_job(
        self,
        file_id: str
    ) -> str:

        input_data = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "file_id": file_id
                    }
                ]
            }
        ]

        response = get_client().responses.create(
            model=self.agent_id,
            include=["last"],
            input=input_data,
            extra_body={
                "config_id": self.config_id
            }
        )

        return response.id

    ##################################################
    # Polling
    ##################################################

    def wait_until_complete(
        self,
        job_id: str,
        interval: int = 2
    ):

        deadline = time.monotonic() + AGENT_TIMEOUT_SECONDS

        response = get_client().responses.retrieve(
            job_id,
            include=["last"]
        )

        print(f"[{self.name}] Status : {response.status}")

        while response.status in (
            "queued",
            "in_progress"
        ):

            if time.monotonic() > deadline:

                raise AgentError(
                    f"{self.name} 응답이 {AGENT_TIMEOUT_SECONDS}초 안에 끝나지 않았습니다."
                )

            time.sleep(interval)

            response = get_client().responses.retrieve(
                job_id,
                include=["last"]
            )

            print(f"[{self.name}] Status : {response.status}")

        if response.status == "failed":

            raise AgentError(
                f"{self.name} 실행 실패: {getattr(response, 'error', None) or '원인 미상'}"
            )

        if response.status != "completed":

            raise AgentError(
                f"{self.name} 알 수 없는 상태: {response.status}"
            )

        print(f"[{self.name}] Job Complete")

        return response

    ##################################################
    # Result Parsing
    ##################################################

    def parse_result(
        self,
        response
    ) -> dict:

        text = getattr(response, "output_text", "") or ""

        if not text.strip():

            raise AgentError(
                f"{self.name} 결과에 output_text가 없습니다."
            )

        try:

            result = json.loads(text)

        except json.JSONDecodeError as error:

            raise AgentError(
                f"{self.name} 결과가 JSON 형식이 아닙니다."
            ) from error

        if not isinstance(result, dict):

            raise AgentError(
                f"{self.name} 결과가 JSON 객체가 아닙니다."
            )

        return result

    ##################################################
    # Agent 실행
    ##################################################

    def run(
        self,
        file_id: str
    ) -> tuple[dict, dict]:
        """
        에이전트를 실행하고 (결과 JSON, 응답 원본 dict)를 돌려준다.

        응답 원본은 Classify 결과처럼 output_text 밖에 있는 정보를
        찾을 때 쓴다.
        """

        print("-" * 60)
        print(f"[{self.name}] Create Job")
        print("-" * 60)

        job_id = self.create_job(file_id)

        print(f"[{self.name}] Job ID : {job_id}")

        response = self.wait_until_complete(job_id)

        result = self.parse_result(response)

        try:
            raw = response.model_dump(mode="json")
        except Exception:
            raw = {}

        print(f"[{self.name}] JSON Parsing Complete")

        return result, raw


##################################################
# Classify 결과 찾기
##################################################

def find_classification(
    raw: dict,
    labels: tuple[str, ...]
) -> str | None:
    """
    응답 원본에서 Classify 노드가 고른 분류 이름을 찾는다.

    분류 이름은 응답 구조 안 어딘가에 문자열로 들어 있다.
    키 이름에 class, category, label이 들어간 값을 먼저 보고,
    없으면 값이 분류 이름과 정확히 같은 문자열을 찾는다.
    """

    preferred: list[str] = []
    anywhere: list[str] = []

    def walk(node, key=""):

        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, str(k).lower())

        elif isinstance(node, list):
            for v in node:
                walk(v, key)

        elif isinstance(node, str) and node in labels:
            if any(word in key for word in ("class", "category", "label", "condition")):
                preferred.append(node)
            else:
                anywhere.append(node)

    walk(raw)

    if preferred:
        return preferred[0]

    # output_text 안의 JSON 문자열은 여기서 보지 않는다. 그 안의 값은 결과 스키마가 처리한다.
    return anywhere[0] if len(set(anywhere)) == 1 else None
