const http = require("http");
const fs = require("fs");
const path = require("path");

const taskId = "a04e64fb-b64f-427e-8e8c-2c2fb15ab5cb";
const base = path.join(process.cwd(), "backend", "exports", taskId);

function getJson(url) {
  return new Promise((resolve) => {
    http
      .get(url, (res) => {
        let data = "";
        res.on("data", (chunk) => {
          data += chunk;
        });
        res.on("end", () => {
          try {
            resolve(JSON.parse(data));
          } catch (error) {
            resolve({ error: String(error), raw: data.slice(0, 200) });
          }
        });
      })
      .on("error", (error) => resolve({ error: String(error) }));
  });
}

function stat(rel) {
  const filePath = path.join(base, rel);
  try {
    const s = fs.statSync(filePath);
    return `${rel}:${s.size}:${new Date(s.mtimeMs).toTimeString().slice(0, 8)}`;
  } catch {
    return null;
  }
}

(async () => {
  while (true) {
    const data = await getJson(`http://localhost:8000/api/v1/workflows/${taskId}`);
    const status = data.current_state || data.status || data.current_phase || data.state;
    const files = [
      "requirement/latest.json",
      "retrieval/latest.json",
      "draft/latest.json",
      "review/latest.json",
    ]
      .map(stat)
      .filter(Boolean)
      .join(" | ");
    console.log(
      new Date().toTimeString().slice(0, 8),
      "state=",
      status,
      "updated=",
      data.updated_at || "",
      "files=",
      files,
    );
    if (["completed", "failed", "cancelled"].includes(String(status))) break;
    await new Promise((resolve) => setTimeout(resolve, 30000));
  }
})();
