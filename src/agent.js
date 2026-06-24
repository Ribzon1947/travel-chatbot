import { GoogleGenerativeAI } from '@google/generative-ai';
import { config } from './config.js';
import { TOOL_SCHEMAS, dispatchTool } from './tools.js';
import { buildSchemaSummary } from './sheetsClient.js';

// ── Column detection helpers ──────────────────────────────────────────────────

const DEST_PATTERNS   = /destination|location|place|city|venue|site|area|zone|trip|tour/i;
const COST_PATTERNS   = /contract|value|cost|rate|price|fee|amount|charge|fare|tariff|per.person|pp/i;
const PEOPLE_PATTERNS = /people|persons?|pax|guests?|attendees?|headcount|count|members?|nos?\.?|number/i;
const PHONE_PATTERNS  = /phone|mobile|contact|tel(?:ephone)?/i;
const NAME_PATTERNS   = /client.?name|customer.?name|employee.?name|participant.?name|travell?er.?name|^name$|^employee$|^participant$|^travell?er$|^person$/i;
const TOTALS_ROW      = /^(totals?|grand.?total|sub.?total|summary)$/i;

function detectColumns(rows) {
  if (!rows.length) return {};
  const cols = Object.keys(rows[0]);
  return {
    destination: cols.find(c => DEST_PATTERNS.test(c)),
    cost:        cols.find(c => COST_PATTERNS.test(c)),
    // Exclude phone/mobile/contact columns — they hold contact details, not people counts
    people:      cols.find(c => PEOPLE_PATTERNS.test(c) && !PHONE_PATTERNS.test(c)),
    name:        cols.find(c => NAME_PATTERNS.test(c)),
  };
}

// Strip empty rows and totals/summary rows so they don't inflate calculations.
function filterDataRows(rows, nameCol) {
  if (!nameCol) return rows.filter(r => Object.values(r).some(v => String(v).trim() !== ''));
  return rows.filter(r => {
    const name = String(r[nameCol] ?? '').trim();
    return name && !TOTALS_ROW.test(name);
  });
}

// ── Pure-JS calculation (no LLM for arithmetic) ───────────────────────────────

function computeReport(rows, sheetName) {
  const detected = detectColumns(rows);
  const destCol   = detected.destination;
  const costCol   = detected.cost;
  const peopleCol = detected.people;
  const nameCol   = detected.name;

  // Work only on real data rows — exclude empties and TOTALS rows
  const dataRows = filterDataRows(rows, nameCol);

  const lines = [];
  lines.push(`Sheet: ${sheetName}`);
  lines.push(`Total entries: ${dataRows.length}`);
  lines.push('');

  // ── Per-destination breakdown ─────────────────────────────────────────────
  if (destCol) {
    const destMap = {};

    for (const row of dataRows) {
      const dest = String(row[destCol] || 'Unknown').trim();
      if (!destMap[dest]) destMap[dest] = { count: 0, totalCost: 0, totalPeople: 0 };

      destMap[dest].count++;

      if (costCol) {
        const cost = parseFloat(String(row[costCol]).replace(/[^0-9.-]/g, ''));
        if (!isNaN(cost)) destMap[dest].totalCost += cost;
      }

      if (peopleCol) {
        const ppl = parseFloat(String(row[peopleCol]).replace(/[^0-9.-]/g, ''));
        if (!isNaN(ppl)) destMap[dest].totalPeople += ppl;
      }
    }

    const useHeadcountCol = peopleCol && Object.values(destMap).some(d => d.totalPeople > 0);

    lines.push('Destination Breakdown:');
    let grandTotalPeople = 0;
    let grandTotalCost   = 0;

    for (const [dest, data] of Object.entries(destMap)) {
      const headcount = useHeadcountCol ? data.totalPeople : data.count;
      grandTotalPeople += headcount;

      if (costCol && data.totalCost > 0) {
        grandTotalCost += data.totalCost;
        const perPerson = headcount > 0 ? Math.round(data.totalCost / headcount) : 0;
        lines.push(
          `  ${dest}: ${headcount} ${useHeadcountCol ? 'people' : 'entries'} | ` +
          `Total cost: Rs.${data.totalCost.toLocaleString()} | ` +
          `Per person: Rs.${perPerson.toLocaleString()}`
        );
      } else {
        lines.push(`  ${dest}: ${headcount} ${useHeadcountCol ? 'people' : 'entries'}`);
      }
    }

    lines.push('');
    lines.push(`Total people: ${grandTotalPeople}`);

    if (costCol && grandTotalCost > 0) {
      lines.push(`Total cost (all destinations): Rs.${grandTotalCost.toLocaleString()}`);
      if (grandTotalPeople > 0) {
        lines.push(`Average cost per person: Rs.${Math.round(grandTotalCost / grandTotalPeople).toLocaleString()}`);
      }
    } else if (costCol) {
      lines.push('No cost values found in the cost column.');
    } else {
      lines.push('No cost column detected in the sheet.');
    }

  } else {
    // No destination column — just count and cost totals
    lines.push('No destination column detected.');
    lines.push('');

    const totalPeople = peopleCol
      ? dataRows.reduce((s, r) => {
          const v = parseFloat(String(r[peopleCol]).replace(/[^0-9.-]/g, ''));
          return s + (isNaN(v) ? 0 : v);
        }, 0)
      : dataRows.length;

    lines.push(`Total people: ${totalPeople}`);

    if (costCol) {
      const totalCost = dataRows.reduce((s, r) => {
        const v = parseFloat(String(r[costCol]).replace(/[^0-9.-]/g, ''));
        return s + (isNaN(v) ? 0 : v);
      }, 0);
      lines.push(`Total cost: Rs.${totalCost.toLocaleString()}`);
      if (totalPeople > 0) {
        lines.push(`Average cost per person: Rs.${Math.round(totalCost / totalPeople).toLocaleString()}`);
      }
    } else {
      lines.push('No cost column detected in the sheet.');
    }
  }

  // ── Columns found ─────────────────────────────────────────────────────────
  lines.push('');
  lines.push(
    `Columns used: ${[
      destCol   && `destination="${destCol}"`,
      costCol   && `cost="${costCol}"`,
      peopleCol && `people="${peopleCol}"`,
      nameCol   && `name="${nameCol}"`,
    ].filter(Boolean).join(', ') || 'none matched'}`
  );

  return lines.join('\n');
}

// ── LLM enrichment (summary sentence on top, optional) ───────────────────────

const SYSTEM_INSTRUCTION = (sheetName, schema, sample) =>
`You are a data analysis assistant. The sheet has already been analyzed — the numbers below are exact.
Your job is to write ONE concise plain-English summary paragraph (3-5 sentences) describing what the data shows.
Do not recalculate anything. Do not use markdown. No asterisks, no bullet points.

Sheet: ${sheetName}
Columns:
${schema}

Sample rows (first 5):
${sample}`;

// ── Main export ───────────────────────────────────────────────────────────────

export async function runAutoAnalysis(rows, sheetName) {
  const start = Date.now();

  // Step 1: compute the full report in pure JS — no LLM needed for numbers
  const calculatedReport = computeReport(rows, sheetName);

  // Step 2: ask LLM only for a plain-English summary on top
  let summary = '';
  try {
    const schema  = buildSchemaSummary(rows);
    const sample  = rows.slice(0, 5).map(r => JSON.stringify(r)).join('\n');
    const genAI   = new GoogleGenerativeAI(config.googleAiKey);
    const model   = genAI.getGenerativeModel({
      model: config.agentModel,
      systemInstruction: SYSTEM_INSTRUCTION(sheetName, schema, sample),
    });
    const result  = await model.generateContent(
      `Here is the computed analysis:\n\n${calculatedReport}\n\nWrite a short plain-English summary.`
    );
    summary = result.response.text().trim();
  } catch (_) {
    // LLM summary is optional — computed report is always returned
  }

  const report = summary
    ? `${summary}\n\n${'─'.repeat(40)}\n\n${calculatedReport}`
    : calculatedReport;

  return { report, tool_calls: [], duration_ms: Date.now() - start };
}
