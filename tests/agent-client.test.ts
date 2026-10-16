import { afterEach, describe, expect, it, vi } from "vitest";
import { AgentClient, find_classification, normalize_review, upload_file } from "../src/lib/agent-client";

const options = { api_key: "test-key", agent_id: "test-agent", config_id: "1", poll_interval_ms: 1 };
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

afterEach(() => vi.useRealTimers());

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
    expect(normalize_review({}, {}).review_level).toBeNull();
    expect(normalize_review({ review_level: "risky" }, { classification: "safe" }).review_level).toBe("risky");
  });
});
