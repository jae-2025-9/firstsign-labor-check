import { as_list, is_blank, LEVELS, more_severe, normalize_level, text, type ExtractedData, type Level } from "./rules";

const BASE_URL = "https://api.upstage.ai/v2";
const RETRYABLE_ERROR_CODES = ["model_request_error", "server_error", "rate_limit", "timeout", "internal"];
const REVIEW_FIELDS = ["review_level", "summary", "matched_rules", "missing_items", "risky_clauses", "confirmed_items", "recommendations"];

export class AgentError extends Error {
  readonly retryable: boolean;
  readonly diagnostic?: {code:string; message:string};

  constructor(message: string, retryable = false, diagnostic?: {code:string; message:string}) {
    super(message);
    this.name = "AgentError";
    this.retryable = retryable;
    this.diagnostic = diagnostic;
  }
}

export interface UploadOptions {
  api_key: string;
  fetch?: typeof fetch;
  http_timeout_ms?: number;
}

export interface AgentOptions extends UploadOptions {
  agent_id: string;
  config_id: string;
  name?: string;
  timeout_ms?: number;
  poll_interval_ms?: number;
  attempts?: number;
  diagnostic_secrets?: string[];
}

export function sanitize_diagnostic(value: unknown, secrets: string[]): string {
  let result=typeof value==='string'?value:'';
  for(const secret of [...secrets].filter(Boolean).sort((a,b)=>b.length-a.length)) result=result.split(secret).join('[REDACTED]');
  return result.replace(/Bearer\s+[^\s,;"']+/gi,'Bearer [REDACTED]')
    .replace(/(?:sk[-_]|gh[pousr]_)[A-Za-z0-9_-]+/g,'[REDACTED]')
    .replace(/https?:\/\/[^\s"'<>]+/g,'[URL]')
    .replace(/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}/gi,'[ID]')
    .replace(/[\u0000-\u001f\u007f]/g,' ').trim().slice(0,500);
}

function is_record(value: unknown): value is ExtractedData {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

async function request(path: string, init: RequestInit, options: UploadOptions, budget?: number): Promise<ExtractedData> {
  if (!options.api_key.trim()) throw new AgentError("Upstage API 키가 설정되지 않았습니다.");
  const controller = new AbortController();
  const timeout = Math.max(1, Math.min(options.http_timeout_ms ?? 60_000, budget ?? Infinity));
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const operation = async () => {
      const response = await (options.fetch ?? globalThis.fetch)(`${BASE_URL}${path}`, {
        ...init,
        headers: { ...init.headers, Authorization: `Bearer ${options.api_key}` },
        signal: controller.signal,
      });
      if (!response.ok) throw new AgentError(`Upstage 요청에 실패했습니다. (HTTP ${response.status})`);
      const data: unknown = await response.json();
      if (!is_record(data)) throw new AgentError("Upstage 응답 형식이 올바르지 않습니다.");
      return data;
    };
    return await Promise.race([
      operation(),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => {
          controller.abort();
          reject(new AgentError("Upstage 요청 시간이 초과되었습니다."));
        }, timeout);
      }),
    ]);
  } catch (error) {
    if (error instanceof AgentError) throw error;
    // 외부 오류 본문에는 문서 내용이 있을 수 있으므로 반환하지 않습니다.
    throw new AgentError("Upstage 응답을 받지 못했습니다. 잠시 후 다시 시도하세요.");
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

export async function upload_file(file: Blob, filename: string, options: UploadOptions): Promise<string> {
  const form = new FormData();
  form.append("purpose", "user_data");
  form.append("file", file, filename);
  const data = await request("/files", { method: "POST", body: form }, options);
  if (typeof data.id !== "string" || !data.id) throw new AgentError("파일 업로드 결과에 ID가 없습니다.");
  return data.id;
}

export class AgentClient {
  private readonly options: AgentOptions;

  constructor(options: AgentOptions) {
    this.options = options;
  }

  upload_file(file: Blob, filename: string): Promise<string> {
    return upload_file(file, filename, this.options);
  }

  async create_job(file_id: string): Promise<string> {
    if (!this.options.agent_id.trim() || !this.options.config_id.trim()) {
      throw new AgentError("에이전트 설정이 완료되지 않았습니다.");
    }
    const response = await request("/responses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: this.options.agent_id,
        config_id: this.options.config_id,
        include: ["last"],
        input: [{ role: "user", content: [{ type: "input_file", file_id }] }],
      }),
    }, this.options);
    if (typeof response.id !== "string" || !response.id) throw new AgentError("에이전트 응답에 작업 ID가 없습니다.");
    return response.id;
  }

  async wait_until_complete(job_id: string): Promise<ExtractedData> {
    const deadline = performance.now() + (this.options.timeout_ms ?? 420_000);
    while (true) {
      const remaining = deadline - performance.now();
      if (remaining <= 0) throw new AgentError("에이전트 처리 시간이 초과되었습니다.");
      const response = await request(`/responses/${encodeURIComponent(job_id)}?include=last`, { method: "GET" }, this.options, remaining);
      if (response.status === "completed") return response;
      if (response.status === "failed") {
        const code = is_record(response.error) && typeof response.error.code === "string" ? response.error.code : "";
        const secrets=[this.options.api_key,this.options.agent_id,this.options.config_id,...(this.options.diagnostic_secrets??[])];
        const diagnostic={code:sanitize_diagnostic(code,secrets)||'unknown_error',message:sanitize_diagnostic(is_record(response.error)?response.error.message:'',secrets)||'Studio가 상세 오류 메시지를 제공하지 않았습니다.'};
        throw new AgentError("에이전트 실행에 실패했습니다.", RETRYABLE_ERROR_CODES.some((word) => code.includes(word)), diagnostic);
      }
      if (response.status !== "queued" && response.status !== "in_progress") {
        throw new AgentError("에이전트가 결과를 완료하지 못했습니다.");
      }
      const delay = Math.min(this.options.poll_interval_ms ?? 2_000, Math.max(0, deadline - performance.now()));
      await new Promise<void>((resolve) => setTimeout(resolve, delay));
    }
  }

  parse_result(response: ExtractedData): ExtractedData {
    let output = typeof response.output_text === "string" ? response.output_text : "";
    if (!output.trim() && Array.isArray(response.output)) {
      output = response.output.flatMap((item) => {
        if (!is_record(item)) return [];
        if (item.type === "output_text" && typeof item.text === "string") return [item.text];
        if (!Array.isArray(item.content)) return [];
        return item.content.flatMap((part) => is_record(part) && part.type === "output_text" && typeof part.text === "string" ? [part.text] : []);
      }).join("");
    }
    if (!output.trim()) throw new AgentError("에이전트 결과에 output_text가 없습니다.");
    let result: unknown;
    try {
      result = JSON.parse(output);
    } catch {
      throw new AgentError("에이전트 결과가 JSON 형식이 아닙니다.");
    }
    if (!is_record(result)) throw new AgentError("에이전트 결과가 JSON 객체가 아닙니다.");
    return result;
  }

  async run(file_id: string): Promise<{ result: ExtractedData; raw: ExtractedData }> {
    const configured = this.options.attempts ?? 3;
    const attempts = Number.isFinite(configured) ? Math.min(3, Math.max(1, Math.floor(configured))) : 3;
    for (let attempt = 1; attempt <= attempts; attempt++) {
      try {
        const job_id = await this.create_job(file_id);
        const raw = await this.wait_until_complete(job_id);
        return { result: this.parse_result(raw), raw };
      } catch (error) {
        if (!(error instanceof AgentError)) throw error;
        const retry=error.retryable && attempt<attempts;
        const diagnostic=error.diagnostic??{code:'client_error',message:error.message};
        const role=['CONTRACT','CRITERIA','REVIEW'].includes(this.options.name??'')?this.options.name:'AGENT';
        console.error(JSON.stringify({event:'upstage_job_failed',role,code:diagnostic.code,message:diagnostic.message,attempt,max_attempts:attempts,retries:attempt-1,retry_scheduled:retry}));
        if(retry)continue;
        throw new AgentError(`${error.message} [Studio: ${diagnostic.code}] ${diagnostic.message} (Job 시도 ${attempt}/${attempts}, 재시도 ${attempt-1}회)`,error.retryable,diagnostic);
      }
    }
    throw new AgentError("에이전트 실행에 실패했습니다.");
  }
}

export function find_classification(raw: unknown, labels: readonly string[] = LEVELS): string | null {
  const candidates = [new Set<string>(), new Set<string>(), new Set<string>(), new Set<string>()];
  function walk(node: unknown, key = "", in_output = false): void {
    if (Array.isArray(node)) node.forEach((item) => walk(item, key, in_output));
    else if (is_record(node)) Object.entries(node).forEach(([name, value]) => {
      const lower = name.toLowerCase();
      walk(value, lower, in_output || lower === "output");
    });
    else if (typeof node === "string" && labels.includes(node)) {
      const named = /class|category|label|condition/.test(key);
      candidates[(in_output ? 0 : 2) + (named ? 0 : 1)].add(node);
    }
  }
  walk(raw);
  for (const group of candidates) {
    if (group.size) return group.size === 1 ? [...group][0] : null;
  }
  return null;
}

export interface NormalizedReview {
  review_level: Level | null;
  schema_level: Level | null;
  classify_level: Level | null;
  level_conflict: boolean;
  summary: string;
  matched_rules: string[];
  missing_items: string[];
  risky_clauses: string[];
  confirmed_items: string[];
  recommendations: string[];
}

export function normalize_review(review: ExtractedData, raw: ExtractedData): NormalizedReview {
  if (!REVIEW_FIELDS.some((key) => !is_blank(review[key]))) {
    throw new AgentError("평가 에이전트 결과가 비어 있습니다. Review Agent 설정을 확인해 주세요.");
  }
  for (const key of REVIEW_FIELDS) {
    const value = review[key];
    if (value != null && typeof value !== "string" && !Array.isArray(value)) {
      throw new AgentError(`평가 에이전트 결과의 ${key} 형식이 올바르지 않습니다.`);
    }
  }
  const schema_level = normalize_level(review.review_level);
  const classify_level = find_classification(raw) as Level | null;
  return {
    review_level: more_severe(schema_level, classify_level),
    schema_level,
    classify_level,
    level_conflict: Boolean(schema_level && classify_level && schema_level !== classify_level),
    summary: text(review.summary),
    matched_rules: as_list(review.matched_rules).map(String),
    missing_items: as_list(review.missing_items).map(String),
    risky_clauses: as_list(review.risky_clauses).map(String),
    confirmed_items: as_list(review.confirmed_items).map(String),
    recommendations: as_list(review.recommendations).map(String),
  };
}
