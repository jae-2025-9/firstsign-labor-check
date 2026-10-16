"""
review_agent.py

Review Agent

계약 정보와 점검 기준을 합친 PDF를 안심, 확인 필요, 위험 중 하나로 분류하고 결과 JSON을 만든다.
"""

from agent_client import AgentClient

from config import (
    REVIEW_AGENT_ID,
    REVIEW_CONFIG_ID
)


def analyze_review(
    file_id: str
) -> tuple[dict, dict]:
    """
    Review Agent 실행. (결과 JSON, 응답 원본)을 돌려준다.
    """

    agent = AgentClient(
        agent_id=REVIEW_AGENT_ID,
        config_id=REVIEW_CONFIG_ID,
        name="Review Agent"
    )

    return agent.run(file_id)
