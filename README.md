# 첫사인 · 알바 안심 체크

근로계약서 PDF를 점검 기준서와 비교하는 ChatGPT Sites 앱입니다. Vinext와 Cloudflare Workers를 사용합니다.

## 실행

Node.js 22.13 이상이 필요합니다.

```sh
npm ci
npm test
npm run typecheck
npm run dev
```

Sites 배포 빌드는 Sites 플러그인의 `scripts/build-site.mjs`를 사용합니다. `vite.config.ts`의 `sites()` 통합을 유지하세요. 배포에는 Sites 소스 동기화 및 버전 저장 절차가 필요합니다.

## 연결 설정

다음 일곱 값을 Sites 네이티브 도구에서 서버 비밀값으로 설정하세요. 값은 소스나 `.openai/hosting.json`에 넣지 마세요. 설정 후 저장된 버전을 다시 배포해야 새 환경이 적용됩니다.

- `UPSTAGE_API_KEY`
- `CONTRACT_AGENT_ID`
- `CONTRACT_CONFIG_ID`
- `CRITERIA_AGENT_ID`
- `CRITERIA_CONFIG_ID`
- `REVIEW_AGENT_ID`
- `REVIEW_CONFIG_ID`

하나라도 비어 있거나 `FORCE_DEMO=1`이면 데모 모드로 동작합니다. `fixtures/live`에 계약서·기준서·평가 결과가 모두 있는 샘플은 저장된 실행 결과를 재생합니다. 나머지 샘플은 예상 추출값으로 규칙을 계산합니다. 서버는 데모 업로드를 차단합니다. 실연결에서는 샘플도 실제 PDF를 에이전트에 보냅니다.

현재 저장된 샘플 2·3의 에이전트 등급은 모두 `risky`입니다. 예상 추출값만 계산한 샘플 2의 `check_needed`와 다릅니다. 재생 결과는 원본의 실제 평가와 교차 검증 차이를 그대로 표시합니다.

## 처리 과정

1. PDF 시그니처, 최대 10MB, 암호 여부, 열기 가능 여부, 1~20쪽을 검사합니다.
2. Files API로 업로드하고 Contract Agent로 계약 정보를 추출합니다.
3. Criteria Agent로 기준서를 추출합니다. R2 `BUCKET`에 기준서 결과만 캐시합니다.
4. 계약 정보, 기준서, 계산 보조값을 NanumGothic PDF로 조립합니다.
5. Review Agent를 실행하고 규칙 엔진으로 교차 검증합니다.
6. 최종 등급, 카드, 권장 행동, JSON 및 평가 입력 PDF를 반환합니다.

기준서 캐시 키는 PDF 전체 SHA-256, Criteria Agent ID, Config ID를 조합한 SHA-256입니다. R2를 사용하므로 Worker 재시작 및 배포 후에도 재사용합니다. 같은 키의 동시 요청은 메모리 Promise와 R2 조건부 쓰기 잠금으로 묶습니다. 잠금은 25분 후 만료됩니다. 추출이 끝나거나 실패하면 잠금을 해제합니다. 저장된 추출값도 원문 규칙 코드와 다시 대조합니다. 저장소 장애는 오류로 처리합니다. 사용자 업로드와 결과는 R2에 저장하지 않습니다. 실연결 시 Upstage에 전송된 파일의 보관 정책은 별도입니다.

HTTP 요청 제한은 60초입니다. 상태 조회는 작업의 남은 시간을 넘기지 않습니다. 에이전트 폴링 제한은 Job당 420초입니다. HTTP 자체 재시도는 없습니다. Studio가 일시 오류로 Job을 실패 처리한 경우에만 총 3회까지 Job을 생성합니다. 진행 상황은 NDJSON 스트림으로 전달하고 15초마다 heartbeat를 보냅니다. 브라우저에 경과 시간을 표시합니다. 오류 응답에는 API 응답 본문, 비밀값, 계약서 원문을 넣지 않습니다.

## 원본과의 관계

기준: `firstsign-labor-check` 커밋 `9cef9f429b92e1643c8d3c561dd019c74b5911bb`. 이전 기준 `720b1f5` 이후의 변경을 반영했습니다. 원본 저장소는 수정하거나 커밋하지 않았습니다.

`rules.py`의 49개 함수를 TypeScript로 옮겼습니다. 원본 회귀를 포함한 212개 동일 입력의 전체 JSON 결과가 일치했습니다. 정확한 조건 비교, 필드 상태, 부정 문맥과 주체, 휴게 예외, 규칙 코드 검증, 등급 하한, 판정 보류, 교차 검증 4개 상태와 최종 요약 재작성을 포함합니다.

변경 사항:

- Streamlit을 React 화면과 서버 라우트로 변경했습니다.
- PDF 표를 페이지 분할이 가능한 라벨 문단으로 변경했습니다. 1~3부의 내용은 유지합니다.
- NanumGothic의 마지막 빈 글리프를 읽는 fontkit 호환 문제를 메모리 복사본의 12바이트 패딩으로 해결했습니다. 부분 임베딩에서 생긴 글리프 누락을 막기 위해 전체 폰트를 임베드합니다. 원본 TTF는 유지합니다.
- `fixtures/live` 재생과 `FORCE_DEMO`를 지원합니다. raw 응답에서는 분류 탐색에 필요한 구조와 등급 문자열만 보존합니다. 실행 ID, 에이전트 설정, 파일 URL 등 메타데이터는 저장하지 않습니다.
- 기준서 원문 코드는 빌드 전 `pdftotext`로 읽고 PDF SHA-256과 함께 저장합니다. Worker는 실행 시 해시가 같은 PDF인지 확인합니다. 원본의 실행 중 pypdf 추출과 방식이 다릅니다. PDF를 변경하면 `node scripts/criteria-source.mjs --refresh`를 실행하세요. 해시가 다르면 추출 결과를 쓰지 않습니다.
- `AGENT_TIMEOUT_SECONDS`, `AGENT_ATTEMPTS`, `HTTP_TIMEOUT_SECONDS`의 임의 환경값 변경은 제공하지 않습니다. 요청한 420초·총 3회·HTTP 60초를 사용합니다.
- 파일 캐시를 R2 기준서 캐시로 변경했습니다. 사용자 파일과 결과는 서버 디스크에 저장하지 않습니다.
- 최종 결과 JSON 다운로드에는 PDF base64를 제외한 결과 구조를 담습니다.
- 계약서 원문은 React 텍스트 노드로 표시합니다. HTML 삽입이나 Markdown 렌더링을 사용하지 않습니다.

## 확인한 범위

`tests/`는 규칙, Python 결과 동등성, Upstage 응답·실패·타임아웃, PDF 생성, 업로드 검증, 데모 차단, 저장 결과 재생, 캐시 재사용·동시 요청, 교차 검증 화면, HTML 이스케이프를 검사합니다. 가상 시간 421초 동안 heartbeat 유지도 확인합니다. 실배포 검증 결과와 배포 식별자는 `HANDOFF.md`에 기록합니다.

이 도구는 참고용이며 법률 자문이 아닙니다. 5인 미만 사업장 여부, 만 18세 미만 근로자, 수습 감액은 점검하지 않습니다. 기준서의 법령 기준일은 2026-10-14입니다.
