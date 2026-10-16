# 첫사인 · 알바 안심 체크

**사인하기 전 30초, 알바 근로계약서의 빠진 항목과 불리한 조항을 기준서대로 짚어 주는 Document Agent**

고려대학교 세종캠퍼스 Document Agent 해커톤 · 2조 NPOS

> 참고용 점검 도구이며 법률 자문이 아닙니다. 중요한 계약은 노무사나 고용노동부 상담(국번 없이 1350)으로 확인하세요.
> 저장소의 계약서는 모두 가상 문서입니다.

---

## 무엇을 하나

첫 알바를 시작하는 대학생이 근로계약서 PDF를 올리면

1. **Contract Agent**가 임금, 근로시간, 휴일, 서명, 특약 같은 항목 20개를 JSON으로 뽑고
2. **Criteria Agent**가 점검 기준서(규칙 7개, 최저임금, 필수 기재사항)를 JSON으로 뽑고
3. 코드가 두 JSON과 **계산 보조값**(1일·1주 근로시간, 시급 환산, 적용 최저임금)을 PDF 한 장으로 합치면
4. **Review Agent**가 안심 / 확인 필요 / 위험 중 하나로 분류하고, 해당 규칙·법령 근거·사장님께 보낼 요청 문구를 만듭니다.
5. 마지막으로 코드가 같은 규칙으로 **교차 검증**해, 에이전트와 계산이 다르면 화면에 알리고 더 엄격한 등급을 보여 줍니다.

| 등급 | 기준 (점검 기준서 v2) |
|---|---|
| 위험 | 기준서에서 분류가 "위험"인 규칙(최저임금 미달, 위약금·임금 공제 조항) 중 하나라도 해당 |
| 확인 필요 | 위험 규칙은 통과, "확인 필요" 규칙(필수 기재사항, 휴게, 주휴일, 서명·교부, 다음 해 최저임금) 중 하나 이상 해당 |
| 안심 | 규칙 7개 모두 통과 |
| 판정 보류 | 시급·근로시간을 읽지 못했거나 기준서 조건이 바뀌어 판단할 수 없는 규칙이 있어 안심이라고 단정하지 않음 |

## 워크플로우

```text
근로계약서.pdf → [Contract Agent] → contract.json ─┐
                                                   ├→ [review_builder.py] → Review_Input.pdf → [Review Agent] → review_result.json
점검기준서.pdf → [Criteria Agent] → criteria.json ──┘   1부 계약 정보                                   │
                                                         2부 점검 기준                                    ▼
                                                         3부 계산 보조값 (rules.py)          [rules.py 교차 검증] → 화면
```

플레이북의 HR 예시(이력서 → 채용공고 → 매칭)와 같은 "문서 A, 문서 B, 평가 에이전트" 패턴입니다.

| 에이전트 | 입력 | 노드 | 출력 | Studio 템플릿 |
|---|---|---|---|---|
| Contract Agent | 근로계약서 PDF | Parse → Extract (20개 항목) | `contract.json` | 문서 정보 추출 |
| Criteria Agent | 점검 기준서 PDF (고정) | Parse → Extract (규칙 표 포함) | `criteria.json` | 문서 정보 추출 |
| Review Agent | 두 JSON + 계산값을 합친 PDF | Parse → Classify (3분류) → 분류별 Extract | `review_result.json` | 문서 분류 후 정보 추출 |

설정 파일은 [`agent_configs/`](agent_configs)에 있습니다.

## 기준서만 바꾸면 된다

중간 점검 때 남은 문제는 평가 에이전트의 분류 설명에 규칙과 금액(10,320원 등)이 직접 적혀 있어, 기준서를 바꿔도 에이전트 설명을 따로 고쳐야 한다는 점이었습니다. 이렇게 풀었습니다.

- **평가 에이전트 설명을 기준서 참조형으로**: [`agent_configs/Review Agent.json`](agent_configs/Review%20Agent.json)은 분류 설명과 결과 스키마 설명에서 금액·규칙 코드를 모두 빼고 "2부에서 분류가 '위험'인 규칙", "3부의 적용 최저임금"처럼 입력 문서를 가리키게 바꾼 수정본입니다. 원본은 [`Review Agent (v13 원본).json`](agent_configs)으로 남겨 두었습니다.
- **숫자는 코드가 계산**: [`rules.py`](rules.py)가 기준서의 최저임금과 규칙별 분류를 읽어 근로시간·시급·적용 최저임금을 계산하고 입력 PDF 3부에 적습니다. LLM이 "주 3일 × 5시간 = 15시간" 같은 계산을 틀릴 여지를 줄입니다.
- **교차 검증**: 같은 기준서 규칙을 코드로도 판정해 에이전트 결과와 비교합니다. 둘이 다르면 더 엄격한 등급과 두 쪽의 지적을 모두 보여 주고, 요약·권장 행동도 그에 맞춰 고칩니다.
- **코드가 옛 기준으로 덮어쓰지 않게**: 코드가 구현한 점검 조건 문장을 `rules.KNOWN_CONDITIONS`에 적어 두고, 기준서에서 읽은 조건과 공백·줄바꿈·문장부호만 빼고 **정확히 같은지** 비교합니다. "이상→초과", "낮다→높다", "1월 1일→7월 1일"처럼 한두 글자로 뜻이 바뀌면 그 규칙은 "판단 보류"로 두고 평가 에이전트의 판단을 따릅니다. 최저임금 규칙만 금액과 기준 연도가 바뀌는 것을 허용합니다(값은 기준서의 최저임금 항목에서 읽습니다).
- **기준서 추출 결과 검증**: 기준서 PDF 원문에서 규칙 코드를 직접 읽어 추출 결과와 대조합니다. 규칙이 빠졌거나 중복되면 기준서 문제로 보고 등급을 내지 않습니다.
- **확정된 지적보다 낮은 등급은 없음**: 최종 등급은 에이전트 등급, 규칙 계산 등급, 지적 카드의 기준서 분류 중 가장 엄격한 것입니다. 판단 보류가 남았는데 에이전트 분류도 없으면 "최소 ○○"로 표시합니다.

`tests/test_rules.py`에 "기준서의 최저임금·규칙 분류를 바꾸면 결과가 바뀐다", "임계값을 바꾸면 코드는 판단을 보류한다"는 테스트가 있습니다.

### Studio에 반영할 것

수정본 JSON의 내용을 Studio의 Review Agent에 옮겨야 실제 서비스에 반영됩니다.

1. Classify-1 노드의 세 분류(safe, check_needed, risky) 설명을 수정본의 `documentClassifyConfiguration` 값으로 바꿉니다.
2. 세 Extract 노드(`review_result_safe`, `review_result_check_needed`, `review_result_risky`) 모두에 **`review_level`(String)** 항목을 맨 앞에 추가하고, 설명을 "항상 safe라고 쓴다"처럼 노드마다 자기 분류 값으로 적습니다(플레이북 HR 예시의 `match_level`과 같은 방식). 코드는 이 값으로 Classify 결과를 읽습니다.
3. 나머지 6개 항목 설명을 수정본 값으로 바꿉니다. 세 노드의 항목 이름·유형·목록 설정은 똑같아야 합니다.
4. Contract Agent의 `work_days` 설명에 "요일 없이 '주 5일 (요일은 협의)'처럼 일수만 적혀 있으면 그 문구를 그대로 한 항목으로 쓴다"를 추가합니다([`Contract Agent.json`](agent_configs/Contract%20Agent.json) 수정본). 그래야 1주 근로시간을 계산할 수 있습니다.
5. 실행해 본 뒤 "워크플로우 설정 내보내기"로 JSON을 다시 받아 `agent_configs/`의 파일을 교체합니다. 이때 "API로 이용하기" 화면의 Config ID를 `.env`의 `*_CONFIG_ID`에 그대로 넣습니다(1로 두지 않습니다).

## FirstSign에서 가져온 것

[FirstSign](https://github.com/FIo-g/FirstSign)(React + Express + Gemini)의 아이디어를 해커톤 구조로 옮겼습니다.

| FirstSign | 이 프로젝트 |
|---|---|
| Gemini 프롬프트 하나로 분석 | Upstage Studio 에이전트 3개 + 코드 계산 |
| 위험 / 주의 / 안전 신호등 | 위험 / 확인 필요 / 안심 신호등 (같은 색) |
| 조항 카드 (원문, 법령 근거, 권장 행동, 규칙 코드) | 같은 구성의 규칙 카드 + 계약서 값 vs 기준값 |
| "AI는 주관적으로 판단하지 않는다" | 기준서 규칙 + 코드 교차 검증, 모든 지적에 법령 근거 |
| 사진 업로드, Vercel | PDF 업로드, Streamlit + Railway |

## 실행

Python 3.12를 씁니다(`.python-version`, Railway도 같은 버전). 의존성 버전은 `requirements.txt`에 고정했습니다.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # UPSTAGE_API_KEY와 Agent ID 3개를 채운다
```

```bash
python app.py --sample 3           # 콘솔에서 샘플 3 점검 (에이전트 3개 실제 호출)
streamlit run streamlit_app.py     # 화면 (http://localhost:8501)
```

`.env`가 비어 있으면 **데모 모드**로 열립니다. 업로드는 받지 않고 샘플 4종만 점검하며, 화면에 "데모: 규칙 계산 결과"라고 표시합니다.

### 발표용으로 실제 결과 저장하기

Upstage API 요청 제한에 걸려도 시연할 수 있게, 실제 에이전트 결과를 저장해 두고 재생할 수 있습니다.

```bash
for i in 1 2 3 4; do python app.py --sample $i --save-fixture; done   # fixtures/live/에 저장
```

이후 `FORCE_DEMO=1`이면 샘플은 저장된 실제 결과("저장된 실행 결과 재생"으로 표시)를 보여 줍니다.

### 테스트

```bash
pip install -r requirements-dev.txt
pytest
```

## 배포 (Railway)

플레이북 6장과 같습니다.

1. 이 폴더를 GitHub 저장소로 올립니다. `.env`는 `.gitignore`에 있어 올라가지 않습니다.
2. Railway → New → GitHub Repository → 저장소 선택.
3. Variables에 `.env`의 7개(`UPSTAGE_API_KEY`, `CONTRACT_AGENT_ID`, `CONTRACT_CONFIG_ID`, `CRITERIA_AGENT_ID`, `CRITERIA_CONFIG_ID`, `REVIEW_AGENT_ID`, `REVIEW_CONFIG_ID`)를 등록합니다. 발표 중 요청 제한이 걱정되면 `FORCE_DEMO=1`도 둡니다.
4. Start Command는 [`railway.json`](railway.json)에 들어 있습니다: `streamlit run streamlit_app.py --server.port=$PORT --server.address=0.0.0.0`
5. Settings → Networking → Generate Domain으로 공개 URL을 만듭니다.

## 제출 전 확인

- [ ] Studio에 수정본(Review Agent 분류·스키마, Contract Agent `work_days`)을 반영하고 샘플 4종으로 실행해 등급이 정상·누락·위험·안심으로 나온다
- [ ] 최종 설정을 다시 내보내 `agent_configs/`를 교체했다 (최종 제출물: Studio Agent JSON)
- [ ] `.env`의 Agent ID·Config ID가 "API로 이용하기" 화면 값과 같다
- [ ] `python app.py --sample N --save-fixture`로 샘플 4종의 실제 결과를 저장했다 (발표 중 요청 제한 대비)
- [ ] Railway 공개 URL에서 팀원이 아닌 사람이 샘플과 업로드로 결과까지 확인했다
- [ ] `git ls-files | grep -i env`에 `.env.example`만 나온다

## 검수

Codex(gpt-6-astra, reasoning xhigh) 읽기 전용 검수를 돌리고, 지적을 하나씩 확인해 맞는 것만 고쳤습니다. 테스트는 Python 3.12(배포)와 3.14에서 모두 통과합니다(`pytest`, 화면 자동 테스트 포함).

2차에서 고친 것: 유사도 대신 정확 일치로 조건 비교, 기준서 원문 규칙 코드 대조, 확정 지적보다 낮은 등급과 모순된 요약 제거, '없음'·'미정'·'협의' 표기 처리, 4시간 휴게 예외, 배상 주체·부정 교부 문구, 불가능한 휴게시간·여러 근무 시각, 특약은 항상 표 밖 문단, 다음 해 최저임금 연도 표시, 빈 평가 결과 거부, Classify 실행 결과 우선, 폴링 남은 시간 제한, 기준서 추출 잠금.

1차에서 고친 것: 판단 보류가 안심으로 처리되던 경로, 시급 반올림으로 최저임금 미달이 통과하던 문제, 표의 빈 셀로 규칙이 어긋나던 문제, 부정 문맥("교부하지 않는다", "위약금을 금지한다") 오판, 등급만 올리고 요약·권장 행동이 그대로이던 문제, 긴 특약에서 PDF 생성 실패, HTTP 타임아웃, 캐시 키·원자적 저장, 손상·암호 PDF 검사, 의존성 버전 고정.

## 폴더 구조

| 계층 | 파일 | 역할 |
|---|---|---|
| Presentation | `streamlit_app.py` | 업로드·샘플 선택, 신호등 결과, 규칙 카드, 요청 문구, 다운로드 |
| Service | `service.py` | 업로드 검증, 실연결/데모 모드, 교차 검증, 임시 폴더 정리 |
| Application | `app.py` | 에이전트 실행 순서, 기준서 캐시, CLI |
| Agent | `contract_agent.py`, `criteria_agent.py`, `review_agent.py`, `agent_client.py` | Studio 에이전트 호출 |
| Domain | `rules.py` | 계산 보조값, 규칙 판정, 교차 검증 |
| Infrastructure | `config.py`, `upload.py`, `review_builder.py`, `file_manager.py` | 설정, Files API, 입력 PDF 조립, 파일 입출력 |

| 폴더 | 내용 |
|---|---|
| `data/` | 점검 기준서 v2, 가상 근로계약서 샘플 4종 |
| `agent_configs/` | Studio 에이전트 설정 JSON |
| `fixtures/expected/` | 팀이 만든 예상 추출값 (샘플 정답 라벨, 데모 모드) |
| `fixtures/live/` | `--save-fixture`로 저장한 실제 에이전트 결과 |
| `tests/` | 규칙 계산, 데모 서비스, 입력 PDF 테스트 |

## 한계

- 5인 미만 사업장, 만 18세 미만 근로자, 수습 감액은 계약서만으로 판단할 수 없어 점검하지 않습니다.
- 기준서는 법령 기준일 2026-10-14 기준입니다. 2026-12-10 시행 근로기준법 제54조 개정(4시간 근무 휴게 예외)은 안내 문구로만 반영했습니다.
- Criteria Agent 스키마에 다음 해 최저임금 항목 이름이 `min_wage_hourly_2027`로 고정되어 있습니다. 연도가 바뀌면 스키마와 `rules.NEXT_MIN_WAGE_FIELD`를 함께 바꿔야 합니다.
- 근무일을 읽지 못해 1주 근로시간을 계산할 수 없으면, 주휴일·'해당 없음' 표기처럼 15시간 기준이 걸린 판정은 보류합니다.
- 위약금·교부 문구는 뜻과 부담 주체가 문장 구조로 분명한 경우("근로자가 … 위약금을 지급", "임금에서 공제", "근로자에게 … 교부한다")만 코드가 확정하고, 나머지 자연어는 평가 에이전트의 판단을 따릅니다.
- 2026-12-10 시행 휴게 예외(정확히 4시간 + 근로자의 명시적 요청)는 계약 시작일과 휴게시간 문구로 판단합니다.

## 팀 NPOS

| 이름 | 역할 |
|---|---|
| 백선우 | 조장, 기획, Studio 에이전트, 발표자료 |
| 김태형 | 코드·데모 |
| 이제원 | 코드·데모 |
| 권세현 | 데모 영상 |
| 김영진 | 발표 |
