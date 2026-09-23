INSERT INTO simulation.scenario (name, description, owner_label)
VALUES (%(name)s, %(description)s, 'system')
ON CONFLICT (name) WHERE owner_label = 'system' AND archived_at IS NULL
DO UPDATE SET
    description = EXCLUDED.description,
    updated_at = clock_timestamp()
RETURNING id, name, description, owner_label, created_at, updated_at, archived_at;
