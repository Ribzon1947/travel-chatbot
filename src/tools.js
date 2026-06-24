function toNum(v) {
  const n = Number(v);
  return isNaN(n) ? null : n;
}

function applyFilter(rows, cond) {
  const { column, operator, value } = cond;
  const ops = {
    '==':         r => String(r[column]) === String(value) || Number(r[column]) === Number(value),
    '!=':         r => String(r[column]) !== String(value),
    '>':          r => toNum(r[column]) > Number(value),
    '<':          r => toNum(r[column]) < Number(value),
    '>=':         r => toNum(r[column]) >= Number(value),
    '<=':         r => toNum(r[column]) <= Number(value),
    'contains':   r => String(r[column]).toLowerCase().includes(String(value).toLowerCase()),
    'startswith': r => String(r[column]).toLowerCase().startsWith(String(value).toLowerCase()),
  };
  if (!ops[operator]) throw new Error(`Unknown operator '${operator}'`);
  return rows.filter(ops[operator]);
}

export function runAggregation(rows, column, operation, filter = null) {
  const data = filter ? applyFilter(rows, filter) : rows;
  if (data.length === 0) return { error: 'No rows match those conditions.' };

  const vals = data.map(r => toNum(r[column])).filter(v => v !== null);

  if (vals.length === 0 && ['sum', 'mean', 'median', 'min', 'max'].includes(operation)) {
    return { error: `Column '${column}' has no numeric values.` };
  }

  const ops = {
    sum:     vs => vs.reduce((a, b) => a + b, 0),
    mean:    vs => vs.reduce((a, b) => a + b, 0) / vs.length,
    median:  vs => { const s = [...vs].sort((a, b) => a - b); const m = Math.floor(s.length / 2); return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; },
    min:     vs => Math.min(...vs),
    max:     vs => Math.max(...vs),
    count:   _  => data.map(r => r[column]).filter(v => v !== '' && v != null).length,
    nunique: _  => new Set(data.map(r => r[column])).size,
  };

  if (!ops[operation]) return { error: `Unknown operation '${operation}'` };
  return { result: ops[operation](vals), row_count: data.length };
}

export function groupBy(rows, groupByColumn, aggColumn, operation, sortDescending = true, limit = 10) {
  const groups = {};
  for (const row of rows) {
    const key = row[groupByColumn];
    if (!groups[key]) groups[key] = [];
    const v = toNum(row[aggColumn]);
    if (v !== null) groups[key].push(v);
  }
  const aggFns = {
    sum:   vs => vs.reduce((a, b) => a + b, 0),
    mean:  vs => vs.reduce((a, b) => a + b, 0) / vs.length,
    count: vs => vs.length,
    min:   vs => Math.min(...vs),
    max:   vs => Math.max(...vs),
  };
  const result = Object.entries(groups)
    .map(([key, vs]) => ({ [groupByColumn]: key, [aggColumn]: aggFns[operation]?.(vs) ?? 0 }))
    .sort((a, b) => sortDescending ? b[aggColumn] - a[aggColumn] : a[aggColumn] - b[aggColumn]);
  return { rows: result.slice(0, limit), total_groups: result.length };
}

export function filterRows(rows, conditions, limit = 20, columnsToReturn = null) {
  let data = rows;
  for (const cond of conditions) data = applyFilter(data, cond);
  if (data.length === 0) return { error: 'No rows match those conditions.' };
  const total  = data.length;
  let result   = data.slice(0, limit);
  if (columnsToReturn) result = result.map(r => Object.fromEntries(columnsToReturn.map(c => [c, r[c]])));
  return { rows: result, total_matched: total, truncated: total > limit };
}

export function sortAndLimit(rows, sortColumn, descending = true, limit = 5, columnsToReturn = null) {
  const sorted = [...rows].sort((a, b) => {
    const av = toNum(a[sortColumn]) ?? String(a[sortColumn]);
    const bv = toNum(b[sortColumn]) ?? String(b[sortColumn]);
    return descending ? (bv > av ? 1 : -1) : (av > bv ? 1 : -1);
  });
  let result = sorted.slice(0, limit);
  if (columnsToReturn) result = result.map(r => Object.fromEntries(columnsToReturn.map(c => [c, r[c]])));
  return { rows: result };
}

export function describeColumn(rows, column) {
  const vals    = rows.map(r => r[column]).filter(v => v !== '' && v != null);
  const nullPct = Math.round((1 - vals.length / rows.length) * 100);
  const nums    = vals.map(toNum).filter(v => v !== null);

  if (nums.length === vals.length && nums.length > 0) {
    const sorted = [...nums].sort((a, b) => a - b);
    const mean   = nums.reduce((a, b) => a + b, 0) / nums.length;
    const std    = Math.sqrt(nums.map(v => (v - mean) ** 2).reduce((a, b) => a + b, 0) / nums.length);
    return { type: 'numeric', stats: { count: nums.length, mean, std, min: sorted[0], max: sorted[sorted.length - 1] }, null_pct: nullPct };
  }

  const counts = {};
  for (const v of vals) counts[v] = (counts[v] || 0) + 1;
  const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 10);
  return { type: 'categorical', unique_count: new Set(vals).size, top_values: Object.fromEntries(top), null_pct: nullPct };
}

export function listColumns(rows) {
  if (rows.length === 0) return { columns: [] };
  return {
    columns: Object.keys(rows[0]).map(col => {
      const vals    = rows.map(r => r[col]).filter(v => v !== '' && v != null);
      const nullPct = Math.round((1 - vals.length / rows.length) * 100);
      const isNum   = vals.length > 0 && vals.every(v => !isNaN(Number(v)));
      return { name: col, dtype: isNum ? 'number' : 'string', null_pct: nullPct };
    }),
  };
}

export function calculateCost(rows, { people_column, manual_people_count, cost_per_person_column, cost_per_person_fixed, filter } = {}) {
  const data = filter ? applyFilter(rows, filter) : rows;
  if (data.length === 0) return { error: 'No rows match those conditions.' };

  let totalPeople, peopleVals;

  if (people_column) {
    peopleVals   = data.map(r => toNum(r[people_column])).filter(v => v !== null);
    totalPeople  = Math.round(peopleVals.reduce((a, b) => a + b, 0));
  } else if (manual_people_count != null) {
    totalPeople  = manual_people_count;
    peopleVals   = null;
  } else {
    return { error: "Provide either 'people_column' or 'manual_people_count'." };
  }

  let totalCost, costPerPersonUsed;

  if (cost_per_person_column) {
    const rateVals = data.map(r => toNum(r[cost_per_person_column])).filter(v => v !== null);
    totalCost      = peopleVals
      ? data.reduce((sum, r) => sum + (toNum(r[people_column]) || 0) * (toNum(r[cost_per_person_column]) || 0), 0)
      : rateVals.reduce((a, b) => a + b, 0) * totalPeople;
    costPerPersonUsed = rateVals.reduce((a, b) => a + b, 0) / rateVals.length;
  } else if (cost_per_person_fixed != null) {
    totalCost         = totalPeople * cost_per_person_fixed;
    costPerPersonUsed = cost_per_person_fixed;
  } else {
    return { error: "Provide either 'cost_per_person_column' or 'cost_per_person_fixed'." };
  }

  return {
    total_people:    totalPeople,
    cost_per_person: Math.round(costPerPersonUsed * 100) / 100,
    total_cost:      Math.round(totalCost * 100) / 100,
    rows_used:       data.length,
  };
}

export const TOOL_SCHEMAS = [
  {
    name: 'run_aggregation',
    description: 'Compute an aggregate (sum, mean, median, min, max, count, unique count) on a single column, optionally filtered.',
    parameters: {
      type: 'object',
      properties: {
        column:    { type: 'string', description: 'Column name to aggregate.' },
        operation: { type: 'string', description: 'One of: sum, mean, median, min, max, count, nunique.' },
        filter:    { type: 'object', description: 'Optional filter: {column, operator, value}.' },
      },
      required: ['column', 'operation'],
    },
  },
  {
    name: 'group_by',
    description: 'Group rows by one column and aggregate another.',
    parameters: {
      type: 'object',
      properties: {
        group_by_column: { type: 'string',  description: 'Column to group by.' },
        agg_column:      { type: 'string',  description: 'Column to aggregate.' },
        operation:       { type: 'string',  description: 'One of: sum, mean, count, min, max.' },
        sort_descending: { type: 'boolean', description: 'Sort highest first (default true).' },
        limit:           { type: 'number',  description: 'Max groups to return (default 10).' },
      },
      required: ['group_by_column', 'agg_column', 'operation'],
    },
  },
  {
    name: 'filter_rows',
    description: 'Return rows matching filter conditions.',
    parameters: {
      type: 'object',
      properties: {
        conditions: {
          type: 'array',
          description: 'Array of filter conditions, each with column, operator (==,!=,>,<,>=,<=,contains,startswith), and value.',
          items: { type: 'object' },
        },
        limit:             { type: 'number', description: 'Max rows to return (default 20).' },
        columns_to_return: { type: 'array',  description: 'Columns to include in result.', items: { type: 'string' } },
      },
      required: ['conditions'],
    },
  },
  {
    name: 'sort_and_limit',
    description: 'Sort data by a column and return top/bottom N rows.',
    parameters: {
      type: 'object',
      properties: {
        sort_column:       { type: 'string',  description: 'Column to sort by.' },
        descending:        { type: 'boolean', description: 'Sort descending (default true).' },
        limit:             { type: 'number',  description: 'Number of rows to return (default 5).' },
        columns_to_return: { type: 'array',   description: 'Columns to include.', items: { type: 'string' } },
      },
      required: ['sort_column'],
    },
  },
  {
    name: 'describe_column',
    description: 'Get statistics for a column: numeric gives mean/std/min/max; categorical gives value counts.',
    parameters: {
      type: 'object',
      properties: { column: { type: 'string', description: 'Column name.' } },
      required: ['column'],
    },
  },
  {
    name: 'list_columns',
    description: 'Return all column names and their data types (number or string).',
    parameters: { type: 'object', properties: {} },
  },
  {
    name: 'calculate_cost',
    description: 'Calculate total cost = number of people × per-person rate. Use when the user asks about cost for N people, total cost, attendee pricing, etc.',
    parameters: {
      type: 'object',
      properties: {
        people_column:          { type: 'string', description: 'Column whose values are number of people per row (will be summed).' },
        manual_people_count:    { type: 'number', description: 'Fixed number of people specified by the user (use when no column holds this).' },
        cost_per_person_column: { type: 'string', description: 'Column containing per-person cost/rate.' },
        cost_per_person_fixed:  { type: 'number', description: 'Fixed per-person cost rate given by the user.' },
        filter:                 { type: 'object', description: 'Optional filter condition.' },
      },
    },
  },
];

export function dispatchTool(name, args, rows) {
  switch (name) {
    case 'run_aggregation': return runAggregation(rows, args.column, args.operation, args.filter);
    case 'group_by':        return groupBy(rows, args.group_by_column, args.agg_column, args.operation, args.sort_descending, args.limit);
    case 'filter_rows':     return filterRows(rows, args.conditions, args.limit, args.columns_to_return);
    case 'sort_and_limit':  return sortAndLimit(rows, args.sort_column, args.descending, args.limit, args.columns_to_return);
    case 'describe_column': return describeColumn(rows, args.column);
    case 'list_columns':    return listColumns(rows);
    case 'calculate_cost':  return calculateCost(rows, args);
    default:                return { error: `Unknown tool '${name}'` };
  }
}
