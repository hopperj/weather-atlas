SELECT run.id
FROM simulation.run
WHERE run.run_key = %(run_key)s;
