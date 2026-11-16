import { AppError } from '@/lib/errors';
import type { DataBackend } from '../backend/types';
import { academicYearSchema, parseOrThrow, profileSchema, type AcademicYearInput } from '../schemas';
import { OFFICIAL_SUBJECTS } from '../seed/officialSubjects';
import type { AcademicYear, Profile, Subject, UUID } from '../types';
import { collectSubjectFilePaths, removeFilesBestEffort } from './storageCleanup';

export async function listAcademicYears(db: DataBackend): Promise<AcademicYear[]> {
  return db.list('academic_years', { orderBy: [{ column: 'created_at', ascending: true }] });
}

/** Ano ativo; se nenhum estiver marcado, o mais recente. */
export function pickActiveYear(years: AcademicYear[]): AcademicYear | null {
  return years.find((y) => y.is_active) ?? years[years.length - 1] ?? null;
}

async function deactivateAll(db: DataBackend, exceptId?: UUID): Promise<void> {
  const active = await db.list('academic_years', { where: { is_active: true } });
  for (const year of active) {
    if (year.id !== exceptId) await db.update('academic_years', year.id, { is_active: false });
  }
}

export interface CreateYearOptions {
  activate?: boolean;
  seedOfficialSubjects?: boolean;
}

export async function createAcademicYear(
  db: DataBackend,
  input: AcademicYearInput,
  options: CreateYearOptions = {},
): Promise<{ year: AcademicYear; seeded: Subject[] }> {
  const values = parseOrThrow(academicYearSchema, input);
  if (options.activate) await deactivateAll(db);
  const year = await db.insert('academic_years', { ...values, is_active: Boolean(options.activate) });
  const seeded = options.seedOfficialSubjects ? await seedOfficialSubjects(db, year.id) : [];
  return { year, seeded };
}

/**
 * Cadastra as 20 disciplinas oficiais no ano letivo. Idempotente: disciplinas
 * que já existem (mesmo nome) são mantidas intactas e não são duplicadas.
 */
export async function seedOfficialSubjects(db: DataBackend, academicYearId: UUID): Promise<Subject[]> {
  const existing = await db.list('subjects', { where: { academic_year_id: academicYearId } });
  const existingNames = new Set(existing.map((s) => s.name.trim().toLocaleLowerCase('pt-BR')));
  let position = existing.reduce((max, s) => Math.max(max, s.position), 0);
  const missing = OFFICIAL_SUBJECTS.filter((s) => !existingNames.has(s.name.toLocaleLowerCase('pt-BR')));
  if (!missing.length) return [];
  return db.insertMany(
    'subjects',
    missing.map((s) => ({
      academic_year_id: academicYearId,
      name: s.name,
      code: s.code,
      category: s.category,
      color: s.color,
      description: null,
      teacher: null,
      position: ++position,
      archived_at: null,
    })),
  );
}

export async function updateAcademicYear(db: DataBackend, id: UUID, input: AcademicYearInput): Promise<AcademicYear> {
  const values = parseOrThrow(academicYearSchema, input);
  return db.update('academic_years', id, values);
}

export async function setActiveAcademicYear(db: DataBackend, id: UUID): Promise<AcademicYear> {
  const target = await db.get('academic_years', id);
  if (!target) throw new AppError('not_found', 'Ano letivo não encontrado.');
  await deactivateAll(db, id);
  if (target.is_active) return target;
  return db.update('academic_years', id, { is_active: true });
}

export async function deleteAcademicYear(db: DataBackend, id: UUID): Promise<void> {
  const subjects = await db.list('subjects', { where: { academic_year_id: id } });
  const paths = await collectSubjectFilePaths(db, subjects.map((s) => s.id));
  await db.remove('academic_years', id);
  await removeFilesBestEffort(db, paths);
}

// ---------------------------------------------------------------------------
// Perfil
// ---------------------------------------------------------------------------
export async function getProfile(db: DataBackend): Promise<Profile | null> {
  const [profile] = await db.list('profiles', { limit: 1 });
  return profile ?? null;
}

export async function saveProfile(db: DataBackend, input: { display_name?: string | null }): Promise<Profile> {
  const values = parseOrThrow(profileSchema, input);
  const current = await getProfile(db);
  if (current) return db.update('profiles', current.id, values);
  return db.insert('profiles', { display_name: values.display_name, preferences: {} });
}
