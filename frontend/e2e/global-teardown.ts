import { closePool } from "./helpers/db";

export default async function globalTeardown(): Promise<void> {
  await closePool().catch(() => undefined);
}
