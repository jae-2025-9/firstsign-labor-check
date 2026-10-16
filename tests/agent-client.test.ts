import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AgentClient, AgentError, find_classification, normalize_review, upload_file, sanitize_diagnostic } from "../src/lib/agent-client";

const options = { api_key: "test-key", agent_id: "test-agent", config_id: "1", poll_interval_ms: 1 };
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

beforeEach(()=>vi.spyOn(console,"error").mockImplementation(()=>{}));
afterEach(() => {vi.useRealTimers();vi.restoreAllMocks();});

describe("Upstage client", () => {
  it("uploads a file with the required multipart purpose", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response({ id: "file-test" }));
    expect(await upload_file(new Blob(["pdf"], { type: "application/pdf" }), "review.pdf", { ...options, fetch: fetcher })).toBe("file-test");
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe("https://api.upstage.ai/v2/files");
    expect(init?.headers).toEqual({ Authorization: "Bearer test-key" });
    const body = init?.body as FormData;
    expect(body.get("purpose")).toBe("user_data");
    expect((body.get("file") as File).name).toBe("review.pdf");
  });

  it("creates and polls a job, and reads the raw REST output", async () => {
    const final = { status: "completed", output: [{ type: "message", content: [{ type: "output_text", text: '{"review_level":"safe"}' }] }] };
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(response({ id: "job-test" }))
      .mockResolvedValueOnce(response({ status: "queued" }))
      .mockResolvedValueOnce(response({ status: "in_progress" }))
      .mockResolvedValueOnce(response(final));
    const result = await new AgentClient({ ...options, fetch: fetcher }).run("file-test");
    expect(result).toEqual({ result: { review_level: "safe" }, raw: final });
    expect(JSON.parse(fetcher.mock.calls[0][1]?.body as string)).toEqual({
      model: "test-agent", config_id: "1", include: ["last"],
      input: [{ role: "user", content: [{ type: "input_file", file_id: "file-test" }] }],
    });
    expect(fetcher.mock.calls[1][0]).toBe("https://api.upstage.ai/v2/responses/job-test?include=last");
  });

  it("accepts output_text and rejects missing, invalid, or non-object JSON", () => {
    const client = new AgentClient(options);
    expect(client.parse_result({ output_text: '{"ok":true}' })).toEqual({ ok: true });
    expect(() => client.parse_result({})).toThrow("output_text");
    expect(() => client.parse_result({ output_text: "invalid" })).toThrow("JSON 형식");
    expect(() => client.parse_result({ output_text: "[]" })).toThrow("JSON 객체");
  });

  it.each(["failed", "cancelled", "incomplete"])("rejects the %s terminal state", async (status) => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response({ status, error: "private-document-value" }));
    const client = new AgentClient({ ...options, fetch: fetcher });
    await expect(client.wait_until_complete("job-test")).rejects.toThrow(/에이전트/);
  });

  it("bounds polling by the job deadline", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => response({ status: "in_progress" }));
    const pending = new AgentClient({ ...options, fetch: fetcher, timeout_ms: 100, poll_interval_ms: 20 }).wait_until_complete("job-test");
    const assertion = expect(pending).rejects.toThrow("시간이 초과");
    await vi.advanceTimersByTimeAsync(101);
    await assertion;
    expect(fetcher.mock.calls.length).toBeLessThanOrEqual(6);
  });

  it("allows 420 seconds by default without starting a later poll", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => response({ status: "in_progress" }));
    const pending = new AgentClient({ ...options, fetch: fetcher, poll_interval_ms: 180_000 }).wait_until_complete("job-test");
    const assertion = expect(pending).rejects.toThrow("시간이 초과");
    await vi.advanceTimersByTimeAsync(419_999);
    expect(fetcher).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(1);
    await assertion;
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("limits the last HTTP request to the remaining polling time without retry", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(response({ status: "queued" }))
      .mockImplementation(() => new Promise(() => {}));
    const pending = new AgentClient({ ...options, fetch: fetcher, timeout_ms: 100, poll_interval_ms: 80, http_timeout_ms: 60_000 }).wait_until_complete("job-test");
    const assertion = expect(pending).rejects.toThrow("시간이 초과");
    await vi.advanceTimersByTimeAsync(99);
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls[1][1]?.signal?.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    await assertion;
    expect(fetcher.mock.calls[1][1]?.signal?.aborted).toBe(true);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it.each(["model_request_error", "server_error", "rate_limit_exceeded", "timeout", "internal_error"])("creates another job after the retryable %s failure", async (code) => {
    let jobs = 0;
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (_url, init) => {
      if (init?.method === "POST") return response({ id: `job-${++jobs}` });
      return jobs < 3
        ? response({ status: "failed", error: { code, message: "private-document-value" } })
        : response({ status: "completed", output_text: '{"summary":"완료"}' });
    });
    await expect(new AgentClient({ ...options, fetch: fetcher }).run("file-test")).resolves.toMatchObject({ result: { summary: "완료" } });
    expect(jobs).toBe(3);
    expect(fetcher).toHaveBeenCalledTimes(6);
    for (const [, init] of fetcher.mock.calls.filter(([, init]) => init?.method === "POST")) {
      expect(JSON.parse(init?.body as string).input[0].content[0].file_id).toBe("file-test");
    }
  });

  it("stops retryable failures after three jobs even when a higher limit is requested", async () => {
    let jobs = 0;
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (_url, init) => init?.method === "POST"
      ? response({ id: `job-${++jobs}` })
      : response({ status: "failed", error: { code: "model_request_error", message: "private-document-value" } }));
    const pending = new AgentClient({ ...options, fetch: fetcher, attempts: 10 }).run("file-test");
    await expect(pending).rejects.toMatchObject({ name: "AgentError", retryable: true, message: expect.stringContaining("Job 시도 3/3, 재시도 2회") });
    expect(jobs).toBe(3);
  });

  it("does not retry permanent job failures, invalid JSON, or HTTP failures", async () => {
    for (const terminal of [
      { status: "failed", error: { code: "invalid_input" } },
      { status: "completed", output_text: "bad json" },
    ]) {
      const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(response({ id: "job-test" })).mockResolvedValueOnce(response(terminal));
      await expect(new AgentClient({ ...options, fetch: fetcher }).run("file-test")).rejects.toBeInstanceOf(AgentError);
      expect(fetcher).toHaveBeenCalledTimes(2);
    }
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(response({ id: "job-test" })).mockResolvedValueOnce(response({}, 503));
    await expect(new AgentClient({ ...options, fetch: fetcher }).run("file-test")).rejects.toThrow("HTTP 503");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("aborts HTTP requests and does not wait for a stuck fetch", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn<typeof fetch>().mockImplementation(() => new Promise(() => {}));
    const pending = upload_file(new Blob(["pdf"]), "input.pdf", { ...options, fetch: fetcher, http_timeout_ms: 50 });
    const assertion = expect(pending).rejects.toThrow("시간이 초과");
    await vi.advanceTimersByTimeAsync(51);
    await assertion;
    expect(fetcher.mock.calls[0][1]?.signal?.aborted).toBe(true);
  });

  it("does not expose upstream error bodies", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response({ error: "private-document-value" }, 500));
    await expect(upload_file(new Blob(["pdf"]), "input.pdf", { ...options, fetch: fetcher })).rejects.toThrow("(HTTP 500)");
    const broken = vi.fn<typeof fetch>().mockRejectedValue(new Error("private-document-value"));
    await expect(upload_file(new Blob(["pdf"]), "input.pdf", { ...options, fetch: broken })).rejects.not.toThrow("private-document-value");
  });
});

describe("review classification", () => {
  it("prefers classification keys and rejects ambiguous workflow labels", () => {
    expect(find_classification({ output: [{ classification: "risky" }, { text: "safe" }] })).toBe("risky");
    expect(find_classification({ edges: [{ condition: "safe" }, { condition: "check_needed" }, { condition: "risky" }] })).toBeNull();
    expect(find_classification({ output_text: '{"review_level":"safe"}' })).toBeNull();
  });

  it("selects the more severe grade and reports a conflict", () => {
    const review = normalize_review({ review_level: "안심", summary: ["요약"], matched_rules: "LABOR_BREAK" }, { classification: "risky" });
    expect(review).toMatchObject({ review_level: "risky", schema_level: "safe", classify_level: "risky", level_conflict: true, matched_rules: ["LABOR_BREAK"] });
    expect(normalize_review({ summary: ["요약"] }, {}).review_level).toBeNull();
    expect(normalize_review({ review_level: "risky" }, { classification: "safe" }).review_level).toBe("risky");
  });

  it("prefers executed output over workflow definitions", () => {
    const raw = {
      output: [{ type: "classification", label: "risky" }],
      edges: [{ condition: "safe" }, { condition: "check_needed" }, { condition: "risky" }],
    };
    expect(find_classification(raw)).toBe("risky");
    expect(normalize_review({ review_level: ["safe"], summary: ["..."] }, raw)).toMatchObject({ review_level: "risky", level_conflict: true });
    expect(find_classification({ output: [{ result: "safe" }], label: "risky" })).toBe("safe");
    expect(find_classification({ output: [{ label: "safe" }, { label: "risky" }], label: "safe" })).toBeNull();
  });

  it.each([{}, { summary: [] }, { summary: null }, { review_level: [] }, { summary: " " }, { unknown: "value" }])("rejects an empty review schema %j", (review) => {
    expect(() => normalize_review(review, { output: [{ label: "safe" }] })).toThrow("결과가 비어 있습니다");
  });

  it.each(["review_level", "summary", "matched_rules", "missing_items", "risky_clauses", "confirmed_items", "recommendations"])("rejects an invalid %s type", (field) => {
    for (const value of [{ text: "x" }, 7, true]) {
      expect(() => normalize_review({ summary: "요약", [field]: value }, {})).toThrow(`${field} 형식이 올바르지 않습니다`);
    }
  });

  it("accepts review_level as the only populated field", () => {
    expect(normalize_review({ review_level: ["check_needed"] }, {})).toMatchObject({ review_level: "check_needed", level_conflict: false, summary: "" });
    expect(normalize_review({ review_level: "safe" }, {})).toMatchObject({ review_level: "safe", matched_rules: [] });
  });
});


describe('Studio failure diagnostics',()=>{
 it('reports the final code, message and retry count without runtime secrets or job IDs',async()=>{
  const secrets=['api-private','agent-private','config-private','other-agent-private'];let jobs=0;
  const fetcher=vi.fn<typeof fetch>().mockImplementation(async(_url,init)=>init?.method==='POST'?response({id:`private-job-${++jobs}`}):response({status:'failed',error:{code:'model_request_error',message:`Model failed: ${secrets.join(' ')} https://example.test/?token=private`}}));
  const pending=new AgentClient({api_key:secrets[0],agent_id:secrets[1],config_id:secrets[2],diagnostic_secrets:secrets,name:'REVIEW',fetch:fetcher}).run('file-private');
  let message='';try{await pending;}catch(e){message=(e as Error).message;}
  expect(message).toContain('model_request_error');expect(message).toContain('Model failed:');expect(message).toContain('Job 시도 3/3, 재시도 2회');
  const logs=vi.mocked(console.error).mock.calls.map(args=>JSON.parse(String(args[0])));
  expect(logs.map(x=>[x.attempt,x.retries,x.retry_scheduled])).toEqual([[1,0,true],[2,1,true],[3,2,false]]);
  expect(logs.every(x=>x.role==='REVIEW')).toBe(true);
  const exposed=JSON.stringify(logs)+message;for(const value of [...secrets,'private-job','file-private','token=private'])expect(exposed).not.toContain(value);
 });
 it('bounds diagnostic text and removes credentials and control characters',()=>{
  const clean=sanitize_diagnostic('Bearer abc123 sk-secret abc\n'+ 'x'.repeat(9000),[]);
  expect(clean.length).toBeLessThanOrEqual(500);expect(clean).not.toContain('abc123');expect(clean).not.toContain('sk-secret');expect(clean).not.toContain('\n');
 });
});
