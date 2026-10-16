import { env } from 'cloudflare:workers';
import { settings, is_live_ready } from '../../../src/lib/settings';
export function GET() { return Response.json({live:is_live_ready(settings(env as unknown as Record<string,unknown>))},{headers:{'Cache-Control':'no-store'}}); }
