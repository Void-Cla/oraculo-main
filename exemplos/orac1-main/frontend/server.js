const express = require("express");
const path = require("path");
const fetch = require("node-fetch");

const app = express();
const PORT = process.env.PORT || 3000;
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

app.use(express.json({ limit: "1mb" }));
app.use(express.static(path.join(__dirname, "public")));

app.all("/v1/*", async (req, res) => {
  const target = `${BACKEND_URL}${req.originalUrl}`;
  const headers = {};
  if (req.headers["content-type"]) {
    headers["content-type"] = req.headers["content-type"];
  }
  if (req.headers.cookie) {
    headers.cookie = req.headers.cookie;
  }

  const options = {
    method: req.method,
    headers,
  };

  if (!["GET", "HEAD"].includes(req.method.toUpperCase())) {
    options.body = JSON.stringify(req.body || {});
  }

  try {
    const response = await fetch(target, options);
    const contentType = response.headers.get("content-type") || "application/json";
    const setCookies = response.headers.raw()["set-cookie"];
    res.status(response.status);
    res.set("content-type", contentType);
    if (setCookies && setCookies.length) {
      res.setHeader("set-cookie", setCookies);
    }

    if (contentType.includes("application/json")) {
      res.send(await response.text());
      return;
    }

    const buffer = await response.buffer();
    res.send(buffer);
  } catch (error) {
    res.status(502).json({ erro: "falha_no_proxy", detalhe: error.message, backend: BACKEND_URL });
  }
});

app.listen(PORT, () => {
  console.log(`Servidor frontend rodando em http://localhost:${PORT}`);
});
