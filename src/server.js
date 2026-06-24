import 'dotenv/config';
import express from 'express';
import multer  from 'multer';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { config }          from './config.js';
import { loadSheet }       from './sheetsClient.js';
import { extractRowsFromPdf } from './pdfClient.js';
import { runAutoAnalysis } from './agent.js';
import { chat }            from './chatbot.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const app    = express();
const upload = multer({
  dest: join(__dirname, '../uploads/'),
  limits: { fileSize: 20 * 1024 * 1024 },  // 20 MB max
  fileFilter: (_req, file, cb) => {
    cb(null, file.mimetype === 'application/pdf');
  },
});

app.use(express.json());
app.use(express.static(join(__dirname, '../frontend')));

// ── Travel cost chat ──────────────────────────────────────────────────────────
app.post('/api/chat', async (req, res) => {
  const { message, history = [] } = req.body ?? {};
  if (!message) return res.status(400).json({ detail: 'message is required.' });
  try {
    const reply = await chat(message, history);
    return res.json({ reply });
  } catch (err) {
    return res.status(500).json({ detail: err.message });
  }
});

// ── Google Sheet ───────────────────────────────────────────────────────────────
app.post('/api/agent/analyze', async (req, res) => {
  const { sheet_url, sheet_range = 'Sheet1' } = req.body ?? {};
  if (!sheet_url) return res.status(400).json({ detail: 'sheet_url is required.' });

  let rows, sheetName;
  try {
    ({ rows, sheetName } = await loadSheet(sheet_url, config.googleServiceAccountPath, sheet_range));
  } catch (err) {
    const status = err.message.includes('Invalid Google Sheet') ? 400
                 : err.message.includes('not found')           ? 404
                 : 502;
    return res.status(status).json({ detail: err.message });
  }

  try {
    return res.json(await runAutoAnalysis(rows, sheetName));
  } catch (err) {
    return res.status(503).json({ detail: `Analysis error: ${err.message}` });
  }
});

// ── PDF ────────────────────────────────────────────────────────────────────────
app.post('/api/agent/analyze-pdf', upload.single('file'), async (req, res) => {
  if (!req.file) {
    return res.status(400).json({ detail: 'Please upload a PDF file (max 20 MB).' });
  }

  let rows, sheetName;
  try {
    ({ rows, sheetName } = await extractRowsFromPdf(req.file.path));
  } catch (err) {
    return res.status(422).json({ detail: `Could not read PDF: ${err.message}` });
  }

  try {
    return res.json(await runAutoAnalysis(rows, sheetName));
  } catch (err) {
    return res.status(503).json({ detail: `Analysis error: ${err.message}` });
  }
});

// ── Health ─────────────────────────────────────────────────────────────────────
app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok', model: config.agentModel });
});

app.listen(config.port, () => {
  console.log(`\n  Server running at http://localhost:${config.port}\n`);
});
