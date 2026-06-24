import { google } from 'googleapis';
import { readFileSync, existsSync } from 'fs';

const SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly'];

const API_DISABLED_PHRASES = [
  'has not been used',
  'is disabled',
  'accessNotConfigured',
  'SERVICE_DISABLED',
];

function buildService(serviceAccountPath) {
  // When deployed to Cloud Run, SERVICE_ACCOUNT_JSON env var takes priority
  const raw = process.env.SERVICE_ACCOUNT_JSON;
  const credentials = raw ? JSON.parse(raw) : JSON.parse(readFileSync(serviceAccountPath, 'utf8'));
  const auth = new google.auth.GoogleAuth({ credentials, scopes: SCOPES });
  return google.sheets({ version: 'v4', auth });
}

export function extractSheetId(url) {
  const match = url.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  if (!match) throw new Error('Invalid Google Sheet URL — could not find spreadsheet ID.');
  return match[1];
}

export async function readSheetValues(sheetId, rangeName, serviceAccountPath) {
  const service = buildService(serviceAccountPath);
  const res = await service.spreadsheets.values.get({
    spreadsheetId: sheetId,
    range: rangeName,
  });
  return res.data.values || [];
}

async function loadViaCsv(sheetId, sheetRange) {
  const url = `https://docs.google.com/spreadsheets/d/${sheetId}/export?format=csv&sheet=${encodeURIComponent(sheetRange)}`;
  const res = await fetch(url);
  if (res.status === 401 || res.status === 403) {
    throw new Error(
      'The Google Sheets API is not enabled and the sheet is not publicly shared.\n' +
      'Fix either one:\n' +
      '  1. Set sheet sharing to "Anyone with the link can view"\n' +
      '  2. Enable the Sheets API at https://console.developers.google.com/apis/api/sheets.googleapis.com/overview?project=17600891104'
    );
  }
  if (!res.ok) throw new Error(`CSV export failed: ${res.status} ${res.statusText}`);

  const text = await res.text();
  const lines = text.trim().split('\n');
  if (lines.length === 0) throw new Error('The sheet is empty.');

  // Parse CSV respecting quoted fields
  const parseRow = line => {
    const cells = [];
    let cur = '', inQuote = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') { inQuote = !inQuote; }
      else if (ch === ',' && !inQuote) { cells.push(cur); cur = ''; }
      else { cur += ch; }
    }
    cells.push(cur);
    return cells;
  };

  const headers = parseRow(lines[0]);
  const rows = lines.slice(1).map(line => {
    const cells = parseRow(line);
    const obj = {};
    headers.forEach((h, i) => { obj[h] = cells[i] ?? ''; });
    return obj;
  });

  if (rows.length === 0) throw new Error('The sheet has headers but no data rows.');
  return rows;
}

export function valuesToRows(values) {
  if (!values || values.length === 0) throw new Error('The sheet is empty.');
  const headers = values[0];
  const rawRows = values.slice(1);
  if (rawRows.length === 0) throw new Error('The sheet has headers but no data rows.');
  return rawRows.map(row => {
    const obj = {};
    headers.forEach((h, i) => { obj[h] = row[i] ?? ''; });
    return obj;
  });
}

export async function loadSheet(sheetUrl, serviceAccountPath, sheetRange = 'Sheet1') {
  const sheetId = extractSheetId(sheetUrl);

  // Try service account API first
  if (existsSync(serviceAccountPath)) {
    try {
      const values = await readSheetValues(sheetId, sheetRange, serviceAccountPath);
      let rows = valuesToRows(values);
      if (rows.length > 10000) rows = rows.slice(0, 10000);
      return { rows, sheetName: sheetRange };
    } catch (err) {
      const msg = err.message || '';
      if (!API_DISABLED_PHRASES.some(p => msg.includes(p))) throw err;
      // API not enabled — fall through to CSV export
    }
  }

  // Fallback: public CSV export (sheet must be "Anyone with the link can view")
  let rows = await loadViaCsv(sheetId, sheetRange);
  if (rows.length > 10000) rows = rows.slice(0, 10000);
  return { rows, sheetName: sheetRange };
}

export function buildSchemaSummary(rows) {
  if (rows.length === 0) return '(empty)';
  return Object.keys(rows[0]).map(col => {
    const vals    = rows.map(r => r[col]).filter(v => v !== '' && v != null);
    const nullPct = Math.round((1 - vals.length / rows.length) * 100);
    const isNum   = vals.length > 0 && vals.every(v => !isNaN(Number(v)));
    const nullNote = nullPct > 0 ? ` [${nullPct}% empty]` : '';
    return `  - ${col} (${isNum ? 'number' : 'text'})${nullNote}`;
  }).join('\n');
}
