"""
criteria_agent.py

Criteria Agent

점검 기준서 PDF에서 최저임금, 필수 기재사항, 점검 규칙을 뽑아 criteria.json을 만든다.
"""

from agent_client import AgentClient

from config import (
    CRITERIA_AGENT_ID,
    CRITERIA_CONFIG_ID
)


def analyze_criteria(
    file_id: str
) -> tuple[dict, dict]:
    """
    Criteria Agent 실행. (결과 JSON, 응답 원본)을 돌려준다.
    """

    agent = AgentClient(
        agent_id=CRITERIA_AGENT_ID,
        config_id=CRITERIA_CONFIG_ID,
        name="Criteria Agent"
    )

    return agent.run(file_id)
