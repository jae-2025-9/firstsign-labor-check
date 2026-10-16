"""
contract_agent.py

Contract Agent

근로계약서 PDF에서 임금, 근로시간, 휴일, 서명, 특약 같은 계약 정보를 뽑아 contract.json을 만든다.
"""

from agent_client import AgentClient

from config import (
    CONTRACT_AGENT_ID,
    CONTRACT_CONFIG_ID
)


def analyze_contract(
    file_id: str
) -> tuple[dict, dict]:
    """
    Contract Agent 실행. (결과 JSON, 응답 원본)을 돌려준다.
    """

    agent = AgentClient(
        agent_id=CONTRACT_AGENT_ID,
        config_id=CONTRACT_CONFIG_ID,
        name="Contract Agent"
    )

    return agent.run(file_id)
