// src/lib/db.ts
import 'server-only'
import postgres from 'postgres'

if (!process.env.ATLAS_DB_URL) {
  throw new Error('ATLAS_DB_URL is not defined. Set it in .env.local.')
}

const isPooler = process.env.ATLAS_DB_URL.includes('pooler.supabase.com')

const sql = postgres(process.env.ATLAS_DB_URL, {
  max: 5,
  idle_timeout: 20,
  connect_timeout: 10,
  // Transaction-mode pooler (Supabase) doesn't support prepared statements
  prepare: !isPooler,
  ssl: process.env.ATLAS_DB_URL.includes('sslmode=require')
    ? { rejectUnauthorized: false }
    : false,
})

export default sql
