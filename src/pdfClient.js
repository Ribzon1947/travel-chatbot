import { readFileSync, unlinkSync } from 'fs';
import { GoogleGenerativeAI } from '@google/generative-ai';
import { config } from './config.js';

const EXTRACT_PROMPT = `Extract ALL tabular/structured data from this document.
Return ONLY a valid JSON object in exactly this format:
{
  "rows": [
    { "column1": "value", "column2": "value" },
    { "column1": "value", "column2": "value" }
  ]
}
Rules:
- Include every row — do not truncate or summarize.
- Use the actual column headers from the document as keys.
- If there are multiple tables, merge them or pick the main data table.
- For scanned/image PDFs, read the text from the image carefully.
- Return only the JSON object, no explanation.`;

export async function extractRowsFromPdf(filePath) {
  const pdfBuffer = readFileSync(filePath);
  const base64    = pdfBuffer.toString('base64');

  try {
    const genAI = new GoogleGenerativeAI(config.googleAiKey);
    const model = genAI.getGenerativeModel({ model: config.agentModel });

    const result = await model.generateContent([
      { inlineData: { mimeType: 'application/pdf', data: base64 } },
      EXTRACT_PROMPT,
    ]);

    const text = result.response.text();

    // Pull out the JSON block from the response
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) throw new Error('Gemini could not find structured data in the PDF.');

    const parsed = JSON.parse(jsonMatch[0]);
    const rows   = parsed.rows ?? [];

    if (rows.length === 0) throw new Error('No data rows were extracted from the PDF.');

    return { rows, sheetName: 'PDF Document' };

  } finally {
    // Always clean up the temp file
    try { unlinkSync(filePath); } catch {}
  }
}
