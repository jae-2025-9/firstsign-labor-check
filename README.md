# 첫사인 · 알바 안심 체크

근로계약서 PDF를 점검 기준서와 비교하는 ChatGPT Sites 앱입니다. `firstsign-labor-check`의 Python 판정 로직을 TypeScript로 옮겼습니다. 화면은 React, 서버는 Vinext와 Cloudflare Workers를 사용합니다. 앱 실행에는 Python 서버가 필요하지 않습니다.

## 실행

Node.js 22.13 이상이 필요합니다.

```sh
npm ci
npm test
npm run typecheck
npm run lint
npm run dev
```

로컬 빌드는 `npm run build`로 검사합니다. `npm test`와 빌드 전 검사는 기준서 PDF 해시와 저장된 원문 색인의 일치 여부도 확인합니다. PDF 텍스트 재추출 검증과 기준서 코드 색인 갱신에는 Poppler의 `pdftotext`가 필요합니다.

Sites 배포에는 Sites가 제공하는 빌드·소스 동기화·버전 저장 도구를 사용합니다. `vite.config.ts`의 `sites()` 통합과 `build/`의 Worker 소스는 배포 코드이므로 유지하세요. Git 커밋이나 로컬 빌드 완료만으로 사이트가 배포되지는 않습니다.

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

`.env.example`에는 설정 이름만 둡니다. 로컬 값은 Git에서 제외한 `.env*` 또는 `.dev.vars*`에 보관하세요. 서버 비밀값을 `NEXT_PUBLIC_` 변수나 브라우저 코드로 옮기지 마세요. R2 `BUCKET`은 기준서 캐시용 서버 바인딩입니다.

샘플 1~4의 실제 실행 결과를 저장했습니다. 재생 시 최종 등급은 `safe / check_needed / risky / safe`입니다. 샘플 2는 에이전트가 `risky`로 분류했지만, 근거 규칙의 기준서 분류에 따라 `check_needed`로 표시합니다. 샘플 4의 서명·교부와 다음 해 최저임금 지적은 의견 차이로 표시하고 등급에서 제외합니다.

## 처리 과정

1. PDF 시그니처, 최대 10MB, 암호 여부, 열기 가능 여부, 1~20쪽을 검사합니다.
2. Files API로 업로드하고 Contract Agent로 계약 정보를 추출합니다.
3. Criteria Agent로 기준서를 추출합니다. R2 `BUCKET`에 기준서 결과만 캐시합니다.
4. PDF 해시가 같은 원문 표와 대조해 잘린 기준서 칸을 보정합니다.
5. 계약 정보, 기준서, 계산 보조값을 NanumGothic PDF로 조립합니다.
6. Review Agent를 실행하고 규칙 엔진으로 교차 검증합니다.
7. 최종 등급, 카드, 권장 행동, JSON 및 평가 입력 PDF를 반환합니다.

기준서 캐시 키는 PDF 전체 SHA-256, Criteria Agent ID, Config ID를 조합한 SHA-256입니다. R2를 사용하므로 Worker 재시작 및 배포 후에도 재사용합니다. 같은 키의 동시 요청은 메모리 Promise와 R2 조건부 쓰기 잠금으로 묶습니다. 잠금은 25분 후 만료됩니다. 추출이 끝나거나 실패하면 잠금을 해제합니다. 저장된 추출값도 원문 규칙 코드와 다시 대조합니다. 저장소 장애는 오류로 처리합니다. 사용자 업로드와 결과는 R2에 저장하지 않습니다. 실연결 시 Upstage에 전송된 파일의 보관 정책은 별도입니다.

HTTP 요청 제한은 60초입니다. 상태 조회는 작업의 남은 시간을 넘기지 않습니다. 에이전트 폴링 제한은 Job당 420초입니다. HTTP 자체 재시도는 없습니다. Studio가 일시 오류로 Job을 실패 처리한 경우에만 총 3회까지 Job을 생성합니다. 진행 상황은 NDJSON 스트림으로 전달하고 15초마다 heartbeat를 보냅니다. 큰 결과는 64KB 단위로 나누어 전송합니다. 브라우저에 경과 시간을 표시합니다. 오류 진단은 Studio 오류 코드·메시지와 시도 횟수를 표시합니다. 서버 비밀값, Bearer 토큰, URL, UUID는 가립니다. API 응답 원본과 계약서 원문은 오류 로그에 넣지 않습니다.

## 원본과의 관계

이식 기준은 `firstsign-labor-check` 커밋 `81d83d0bb1cdd26c2461ddb32a6d6c8a022bffe4`입니다. 원본 저장소와 별개인 이 사이트 폴더에 구현합니다. 이후 원본 변경은 별도로 비교하며, 원본 저장소는 수정하지 않습니다.

`rules.py`의 값 해석과 최종 판정 정책을 TypeScript로 옮겼습니다. 목록 값의 충돌, 날짜·금액 후보, 갱신 문구, 자정을 넘는 휴게 구간, 교부 문구의 같은 문장 안 부정을 구분합니다. 확정 통과한 규칙에 대한 에이전트 지적은 `disputed`로 분리합니다. 근거 없는 분류는 따르지 않습니다. 판단 보류 규칙과 연결되는 근거가 있을 때만 해당 분류를 반영합니다. 요청 문장은 의견 차이에 해당하는 내용을 빼고, 남은 카드의 권장 행동을 보충합니다.

`fixtures/criteria-source-table.json`은 고정 원본의 `app.criteria_source_table`로 추출한 표입니다. PDF SHA-256과 원본 커밋을 함께 저장합니다. Workers는 글자 좌표를 판독하지 않습니다. 해시가 같은 PDF에서만 `apply_source_table`을 적용합니다. 캐시는 보정 전 추출값을 유지합니다. 결과에는 `criteria_repaired`와 `disputed_rule_codes`를 제공합니다. 기준서 PDF를 바꾸면 코드 색인과 원문 표를 모두 다시 생성해야 합니다.

변경 사항:

- Streamlit을 React 화면과 서버 라우트로 변경했습니다.
- PDF 표를 페이지 분할이 가능한 라벨 문단으로 변경했습니다. 1~3부의 내용은 유지합니다.
- NanumGothic의 마지막 빈 글리프를 읽는 fontkit 호환 문제를 메모리 복사본의 12바이트 패딩으로 해결했습니다. 부분 임베딩에서 생긴 글리프 누락을 막기 위해 전체 폰트를 임베드합니다. 원본 TTF는 유지합니다.
- `fixtures/live` 재생과 `FORCE_DEMO`를 지원합니다. raw 응답에서는 분류 탐색에 필요한 구조와 등급 문자열만 보존합니다. 실행 ID, 에이전트 설정, 파일 URL 등 메타데이터는 저장하지 않습니다.
- 기준서 원문 코드는 빌드 전 `pdftotext`로 읽고 PDF SHA-256과 함께 저장합니다. Worker는 실행 시 해시가 같은 PDF인지 확인합니다. 원본의 실행 중 pypdf 추출과 방식이 다릅니다. PDF를 변경하면 `node scripts/criteria-source.mjs --refresh`로 코드 색인을 갱신하고, 고정 Python 원본으로 표 데이터도 다시 생성하세요. 원문 표 보정은 해시가 다르면 적용하지 않습니다. 코드 색인이 오래됐으면 처리를 중단합니다.
- `AGENT_TIMEOUT_SECONDS`, `AGENT_ATTEMPTS`, `HTTP_TIMEOUT_SECONDS`의 임의 환경값 변경은 제공하지 않습니다. 요청한 420초·총 3회·HTTP 60초를 사용합니다.
- 파일 캐시를 R2 기준서 캐시로 변경했습니다. 사용자 파일과 결과는 서버 디스크에 저장하지 않습니다.
- 최종 결과 JSON 다운로드에는 PDF base64를 제외한 결과 구조를 담습니다.
- 계약서 원문은 React 텍스트 노드로 표시합니다. HTML 삽입이나 Markdown 렌더링을 사용하지 않습니다.

## 확인한 범위

규칙 테스트는 동일 입력에 대한 고정 Python 원본의 전체 JSON 결과와 TypeScript 결과를 비교합니다. 저장된 실제 샘플 4종은 최종 등급·카드·의견 차이·판단 보류·요약·요청·권장 행동·교차 검증을 비교합니다. 최신 테스트 수와 성공 여부는 `npm test` 출력에서 확인하세요.

`tests/`는 규칙, Python 결과 동등성, Upstage 응답·실패·타임아웃, PDF 생성, 업로드 검증, 데모 차단, 저장 결과 재생, 캐시 재사용·동시 요청, 교차 검증 화면, HTML 이스케이프를 검사합니다. 가상 시간 421초 동안 heartbeat 유지도 확인합니다. 실배포 검증 결과와 배포 식별자는 `HANDOFF.md`에 기록합니다.

## GitHub 공개 전 검사

Python 3으로 다음 검사를 실행합니다. 앱 실행과는 별개의 저장소 검사입니다.

```sh
python3 scripts/check-public-readiness.py --self-test
python3 scripts/check-public-readiness.py
```

검사 범위는 모든 로컬 Git 참조에서 도달할 수 있는 커밋과 현재 추적 파일·공개 대상 미추적 파일입니다. 토큰 패턴, 환경 파일, 개인 절대 경로, 로그·생성 파일을 검사합니다. 2,000,000바이트 이상인 파일도 나열합니다. 결과는 Git에서 제외한 `outputs/qa/github-readiness.json`에 저장합니다. 발견된 값은 출력하지 않습니다. 보고서에는 파일·커밋·유형만 기록합니다.

선택 인자 `--reference-env`에 로컬 환경 파일을 지정하면 일곱 서버 설정의 실제 값과도 비교합니다. 해당 값은 프로세스 메모리에서만 사용합니다. 패턴 검사는 모든 종류의 비밀값 부재를 보장하지 않습니다. 이력에서 값이 발견되면 보고서를 검토한 뒤 공개 범위를 결정하세요. 검사 스크립트는 이력이나 원격 저장소를 변경하지 않습니다.

`public/fonts/NanumGothic-Regular.ttf`는 한글 평가 입력 PDF 생성에 필요합니다. `tests/fixtures/rules-python-parity.json`은 Python 결과 동등성 검증에 필요합니다. 두 파일은 크기가 커도 유지합니다. `node_modules`, 빌드 결과, 로컬 환경 파일, 로그, `outputs/`, `HANDOFF.md`는 공개 대상에서 제외합니다.

이 도구는 참고용이며 법률 자문이 아닙니다. 5인 미만 사업장 여부, 만 18세 미만 근로자, 수습 감액은 점검하지 않습니다. 기준서의 법령 기준일은 2026-10-14입니다.
