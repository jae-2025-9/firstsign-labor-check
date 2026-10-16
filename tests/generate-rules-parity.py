"""최신 Python 회귀 테스트의 입출력을 기록한다. 원본 파일은 변경하지 않는다."""
import copy
from datetime import date
import functools
import hashlib
import importlib
import inspect
import json
import os
import socket
import tempfile
from pathlib import Path
import subprocess
import sys

SITE = Path(__file__).resolve().parents[1]
SOURCE = SITE / "outputs/qa/upstream-81d83d0"
REPOSITORY = SITE.parent / "firstsign-labor-check"
REVISION = subprocess.check_output(["git", "-C", str(REPOSITORY), "rev-parse", "81d83d0"], text=True).strip()
for name in ("rules.py", "tests/test_rules.py"):
    assert (SOURCE / name).read_bytes() == subprocess.check_output(["git", "-C", str(REPOSITORY), "show", f"{REVISION}:{name}"])
# 파일 환경설정과 네트워크를 차단하고 저장된 응답만 재생한다.
os.environ["FORCE_DEMO"] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
for key in ("UPSTAGE_API_KEY", "CONTRACT_AGENT_ID", "CONTRACT_CONFIG_ID", "CRITERIA_AGENT_ID", "CRITERIA_CONFIG_ID", "REVIEW_AGENT_ID", "REVIEW_CONFIG_ID"):
    os.environ[key] = ""
import dotenv
dotenv.load_dotenv = lambda *args, **kwargs: False
dotenv.find_dotenv = lambda *args, **kwargs: ""

def deny_network(*args, **kwargs):
    raise AssertionError("Network is blocked during oracle generation")

socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network
socket.create_connection = deny_network
sys.path.insert(0, str(SOURCE))
rules = importlib.import_module("rules")
pytest = importlib.import_module("pytest")
records = []
depth = 0


def encode(value):
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, set):
        return {"$set": sorted(value)}
    if isinstance(value, dict):
        return {str(k): encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    return value


def capture(name, function):
    signature = inspect.signature(function)

    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        global depth
        outer = depth == 0
        depth += 1
        try:
            result = function(*args, **kwargs)
        finally:
            depth -= 1
        if outer:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            positional = list(bound.arguments.values())
            if name == "more_severe":
                positional = list(positional[0])
            records.append({"function": name, "args": encode(positional), "expected": encode(result)})
        return result

    return wrapped


for name, function in list(vars(rules).items()):
    if inspect.isfunction(function) and function.__module__ == "rules":
        setattr(rules, name, capture(name, function))

exit_code = pytest.main([str(SOURCE / "tests/test_rules.py"), "-q", "-p", "no:cacheprovider"])
assert exit_code == 0, f"Python tests failed: {exit_code}"


def load(folder, name):
    return json.loads((SOURCE / "fixtures" / folder / name).read_text())


criteria = load("expected", "criteria.json")
contract = load("expected", "contract_sample1.json")
codes = set(rules.KNOWN_CONDITIONS)

# 원문 규칙 코드의 누락, 추가, 중복, 빈 행을 각각 기록한다.
for variant in ["missing", "extra", "duplicate", "blank", "column_blank", "match"]:
    changed = copy.deepcopy(criteria)
    rows = changed["check_rules"]
    if variant == "missing":
        changed["check_rules"] = rows[1:]
    elif variant == "extra":
        rows.append({"rule_code": "LABOR_EXTRA", "category": "위험", "check_condition": "추가 규칙"})
    elif variant == "duplicate":
        rows.append(dict(rows[0]))
    elif variant == "blank":
        rows.append({"rule_code": "", "category": "위험"})
    elif variant == "column_blank":
        changed["check_rules"] = {key: [row.get(key, "") for row in rows] for key in ["rule_code", "category", "check_condition", "legal_basis", "recommended_action"]}
        changed["check_rules"]["rule_code"][1] = ""
    engine = rules.evaluate(contract, changed, source_codes=codes)
    review = rules.engine_review(engine)
    check = rules.cross_check(None, [], engine)
    rules.final_view(review, engine, None, check)

# 녹화된 실제 에이전트 결과와 샘플 3 계약을 같은 기준서로 비교한다.
live_criteria = load("live", "criteria.json")
live_contract = load("live", "contract_sample3.json")
live_review = load("live", "review_sample3.json")
live_engine = rules.evaluate(live_contract, live_criteria, source_codes=codes)
live_check = rules.cross_check(live_review["review_level"], live_review["matched_rules"], live_engine)
live_final = rules.final_view(live_review, live_engine, live_review["review_level"], live_check)

# 함수의 보류 경계와 의미 구분을 직접 기록한다.
for value in ["", "없음", "주휴일 없음", "주휴일은 없음.", "미정", "추후 결정", "협의", "매주 일요일 (변경 없음)", "연차유급휴가는 회사 사정에 따라 협의한다."]:
    rules.field_core(value)
    rules.field_state(value)
for clause in ["계약서 교부", "사본", "근로자에게 사본을 제공한다.", "계약서를 근로자에게 교부할 의무는 없다.", "근로자의 요구와 관계없이 근로자에게 교부한다."]:
    rules.copy_clause_status({"copy_delivery_clause": [clause]})
for clause in ["손해가 발생하면 임금에서 공제한다.", "근로자는 위약금을 지급한다.", "회사에서 근로자에게 위약금을 지급한다.", "소득세와 보험료를 임금에서 공제한다.", "세금 및 손해를 임금에서 공제한다.", "임금에서 공제한다.", "근로자는 손해배상을 부담하지 않는다."]:
    rules.classify_penalty_clauses({"special_terms": [clause]})
for start, end, rest in [("", "09:00 ~ 18:00", "1시간"), ("09:00", "09:00", "없음"), ("09:00", "10:00", "1시간"), ("09:00", "13:00", "없음")]:
    changed = {**contract, "work_start_time": [start], "work_end_time": [end], "break_time": [rest]}
    engine = rules.evaluate(changed, criteria)
    review = rules.engine_review(engine)
    check = rules.cross_check(None, [], engine)
    rules.final_view(review, engine, None, check)
for code, (sentence, allow_amounts) in rules.KNOWN_CONDITIONS.items():
    rules.condition_supported({"rule_code": code, "check_condition": sentence}, 2026)
    rules.condition_shape(sentence, 2026, allow_amounts)
    if allow_amounts:
        shifted = sentence.replace("2027년", "2028년").replace("2026년", "2027년").replace("10,320", "10,999")
        rules.condition_supported({"rule_code": code, "check_condition": shifted}, 2027)

# 반복된 호출은 제거한다. 입력과 출력 전체를 보관한다.
unique = {json.dumps(record, ensure_ascii=False, sort_keys=True): record for record in records}
payload = {
    "source_revision": REVISION,
    "source_sha256": hashlib.sha256((SOURCE / "rules.py").read_bytes()).hexdigest(),
    "tests_sha256": hashlib.sha256((SOURCE / "tests/test_rules.py").read_bytes()).hexdigest(),
    "recorded_sample3": {"engine_level": live_engine["level"], "min_level": live_engine["min_level"], "cross_status": live_check["status"], "final_level": live_final["level"], "incomplete": live_final["incomplete"]},
    "cases": list(unique.values()),
}
output = SITE / "tests/fixtures/rules-python-parity.json"
output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
print(f"Captured {len(payload['cases'])} Python cases to {output}")
print(json.dumps(payload["recorded_sample3"], ensure_ascii=False))

# 원본의 회귀 입력 목록도 같은 커밋에서 갱신한다.
regressions = importlib.import_module("test_rules")
(SITE / "tests/fixtures/rules-edge-inputs.json").write_text(json.dumps({"AMBIGUOUS_INPUTS": regressions.AMBIGUOUS_INPUTS, "NORMAL_INPUTS": regressions.NORMAL_INPUTS}, ensure_ascii=False, indent=2) + "\n")

# 서비스 전체 흐름은 임시 폴더에서 재생한다. 원본 출력 폴더는 쓰지 않는다.
service = importlib.import_module("service")
assert not service.is_live_ready()
samples = {}
with tempfile.TemporaryDirectory(prefix="firstsign-service-oracle-") as temporary:
    service.new_run_dir = lambda: Path(tempfile.mkdtemp(dir=temporary))
    for sample_id in ("1", "2", "3", "4"):
        result = service.run_review_service(sample_id=sample_id)
        assert result["mode"] == "demo" and result["source"] == "recorded"
        final = result["final"]
        samples[sample_id] = {
            "final_level": result["final_level"],
            "cards": [{"rule_code": card["rule_code"], "source": card["source"]} for card in final["cards"]],
            **{key: final[key] for key in ("disputed", "pending", "summary", "requests", "requests_missing", "recommendations")},
            "cross_check": result["cross_check"], "criteria_repaired": result["criteria_repaired"],
        }
service_oracle = {"source_commit": REVISION, "criteria_sha256": hashlib.sha256(service.CRITERIA_FILE.read_bytes()).hexdigest(), "samples": samples}
(SITE / "tests/fixtures/service-python-81d83d0.json").write_text(json.dumps(service_oracle, ensure_ascii=False, indent=2) + "\n")
print("Captured 4 Python service sample results with network blocked")
