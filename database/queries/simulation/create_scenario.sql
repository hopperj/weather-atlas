INSERT INTO simulation.scenario (name, description, owner_label)
VALUES (%(name)s, %(description)s, %(owner_label)s)
RETURNING id, name, description, owner_label, created_at, updated_at, archived_at;
