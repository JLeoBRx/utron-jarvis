import type { FilterCondition, ListQuery, OrderBy, Where } from './types';

/** Avalia uma condição de filtro em memória (usado pelo adaptador local). */
export function matchesCondition(value: unknown, condition: FilterCondition): boolean {
  if (condition === null) return value === null || value === undefined;
  if (typeof condition !== 'object') return value === condition;
  if ('in' in condition) return condition.in.some((c) => c === value);
  if ('neq' in condition) return value !== condition.neq;
  if ('notNull' in condition) return value !== null && value !== undefined;
  if (value === null || value === undefined) return false;
  if ('gte' in condition) return (value as string | number) >= condition.gte;
  if ('lte' in condition) return (value as string | number) <= condition.lte;
  return false;
}

export function matchesWhere(row: Record<string, unknown>, where: Where | undefined): boolean {
  if (!where) return true;
  return Object.entries(where).every(([column, condition]) => matchesCondition(row[column], condition));
}

function compareValues(a: unknown, b: unknown): number {
  // NULLs por último (comportamento padrão do PostgreSQL em ordem crescente).
  const aNull = a === null || a === undefined;
  const bNull = b === null || b === undefined;
  if (aNull && bNull) return 0;
  if (aNull) return 1;
  if (bNull) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  if (typeof a === 'boolean' && typeof b === 'boolean') return Number(a) - Number(b);
  return String(a).localeCompare(String(b), 'pt-BR');
}

export function sortRows<T extends Record<string, unknown>>(rows: T[], orderBy: OrderBy[] | undefined): T[] {
  if (!orderBy?.length) return rows;
  return [...rows].sort((a, b) => {
    for (const { column, ascending = true } of orderBy) {
      const aNull = a[column] === null || a[column] === undefined;
      const bNull = b[column] === null || b[column] === undefined;
      let result: number;
      if (aNull !== bNull) {
        // PostgreSQL: NULLS LAST em ASC e NULLS FIRST em DESC.
        result = aNull ? 1 : -1;
        if (!ascending) result = -result;
      } else {
        result = compareValues(a[column], b[column]);
        if (!ascending) result = -result;
      }
      if (result !== 0) return result;
    }
    return 0;
  });
}

export function applyQuery<T extends Record<string, unknown>>(rows: T[], query: ListQuery | undefined): T[] {
  let result = rows.filter((row) => matchesWhere(row, query?.where));
  result = sortRows(result, query?.orderBy);
  if (query?.limit !== undefined) result = result.slice(0, query.limit);
  return result;
}
