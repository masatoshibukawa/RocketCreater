/**
 * Minimal server-sent-events parser for a `fetch` ReadableStream.
 *
 * `EventSource` cannot POST, so the backend stream is read manually. The parser is a pure
 * function: feed it the accumulated text buffer, get back every complete message and the
 * unparsed remainder (which must be prepended to the next chunk).
 *
 * Supported fields: `event`, `data` (multi-line joined with "\n"), `id`. Comment lines (":")
 * and unknown fields are ignored. Blocks without a `data` line are dropped, as the spec says.
 */

export interface SseMessage {
  event: string;
  data: string;
  id?: string;
}

export interface SseParseResult {
  events: SseMessage[];
  rest: string;
}

export function parseSseChunk(buffer: string): SseParseResult {
  // Normalise CRLF line endings. A lone trailing "\r" is kept in `rest`; it is normalised once
  // the following "\n" arrives with the next chunk.
  const normalized = buffer.replace(/\r\n/g, "\n");
  const blocks = normalized.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: SseMessage[] = [];
  for (const block of blocks) {
    const message = parseBlock(block);
    if (message !== null) events.push(message);
  }
  return { events, rest };
}

function parseBlock(block: string): SseMessage | null {
  let event = "message";
  let id: string | undefined;
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line === "" || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
    else if (field === "id") id = value;
  }
  if (data.length === 0) return null;
  const message: SseMessage = { event, data: data.join("\n") };
  if (id !== undefined) message.id = id;
  return message;
}
