#!/bin/bash
set -e

TABLE_COUNT=$(psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'" 2>/dev/null || echo "0")

if [ "$TABLE_COUNT" = "0" ] || [ "$TABLE_COUNT" = "" ]; then
    echo "Database is empty. Restoring from seed dump..."
    if [ -f /docker-entrypoint-initdb.d/wlv_kb_dump.sql ]; then
        psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/wlv_kb_dump.sql
        echo "Database restored successfully."
    else
        echo "No seed dump found. App will create tables on first run."
    fi
else
    echo "Database already has data. Skipping restore."
fi

# Seed quiz questions (safe to re-run — TRUNCATE at top of file)
if [ -f /docker-entrypoint-initdb.d/quiz_questions.sql ]; then
    echo "Seeding quiz questions..."
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/quiz_questions.sql
    echo "Quiz questions seeded."
fi
