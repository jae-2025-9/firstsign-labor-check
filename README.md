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

하나라도 비어 있으면 데모 모드로 동작합니다. 데모에서는 샘플 4종의 예상 추출값을 규칙 엔진으로 계산합니다. 서버는 사용자 업로드를 차단합니다. 실연결에서는 샘플도 실제 PDF를 에이전트에 보냅니다.

## 처리 과정

1. PDF 시그니처, 최대 10MB, 암호 여부, 열기 가능 여부, 1~20쪽을 검사합니다.
2. Files API로 업로드하고 Contract Agent로 계약 정보를 추출합니다.
3. Criteria Agent로 기준서를 추출합니다. R2 `BUCKET`에 기준서 결과만 캐시합니다.
4. 계약 정보, 기준서, 계산 보조값을 NanumGothic PDF로 조립합니다.
5. Review Agent를 실행하고 규칙 엔진으로 교차 검증합니다.
6. 최종 등급, 카드, 권장 행동, JSON 및 평가 입력 PDF를 반환합니다.

기준서 캐시 키는 PDF 전체 SHA-256, Criteria Agent ID, Config ID를 조합한 SHA-256입니다. R2를 사용하므로 Worker 재시작 및 배포 후에도 재사용합니다. 캐시 읽기·쓰기 실패 시 검증된 추출 결과로 계속 진행합니다. 사용자 업로드와 결과는 R2에 저장하지 않습니다. 실연결 시 Upstage에 전송된 파일의 보관 정책은 별도입니다.

HTTP 요청 제한은 60초입니다. 에이전트 폴링 제한은 작업당 180초입니다. 진행 상황은 NDJSON 스트림으로 전달합니다. 오류 응답에는 API 응답 본문, 비밀값, 계약서 원문을 넣지 않습니다.

## 원본과의 관계

기준: `firstsign-labor-check` 커밋 `720b1f5f59145683a2669acc9bf7567e468c24c6`. 이식 중 원본 작업 트리에 별도 수정이 발생했습니다. 진행 중인 변경은 이번 기준에 포함하지 않았습니다. 원본 저장소는 수정하거나 커밋하지 않았습니다.

`rules.py`의 45개 함수를 TypeScript로 옮겼습니다. 7개 규칙, 판정 보류, 조건 비교, 반올림 전 비교, 교차 검증, `final_view`를 유지했습니다. 정상 원본 38개 사례와 최종 JSON이 일치했습니다.

변경 사항:

- Streamlit을 React 화면과 서버 라우트로 변경했습니다.
- PDF 표를 페이지 분할이 가능한 라벨 문단으로 변경했습니다. 1~3부의 내용은 유지합니다.
- NanumGothic의 마지막 빈 글리프를 읽는 fontkit 호환 문제를 메모리 복사본의 12바이트 패딩으로 해결했습니다. 원본 TTF는 유지합니다.
- 데모는 `fixtures/expected`만 사용합니다. `fixtures/live` 재생과 `FORCE_DEMO` 옵션은 이식하지 않았습니다.
- 파일 캐시를 R2 기준서 캐시로 변경했습니다. 사용자 파일과 결과는 서버 디스크에 저장하지 않습니다.
- 최종 결과 JSON 다운로드에는 PDF base64를 제외한 결과 구조를 담습니다.
- 계약서 원문은 React 텍스트 노드로 표시합니다. HTML 삽입이나 Markdown 렌더링을 사용하지 않습니다.

## 확인한 범위

`tests/`는 규칙, Upstage 응답·타임아웃, PDF 생성, 업로드 검증, 데모 차단, 샘플 등급, 캐시 키를 검사합니다. 실제 Upstage 연결은 비밀값이 없어 확인하지 않았습니다.

이 도구는 참고용이며 법률 자문이 아닙니다. 5인 미만 사업장 여부, 만 18세 미만 근로자, 수습 감액은 점검하지 않습니다. 기준서의 법령 기준일은 2026-10-14입니다.
