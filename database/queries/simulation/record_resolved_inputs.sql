UPDATE simulation.run
SET gfs_cycle_time = %(gfs_cycle_time)s,
    cffeps_build_id = %(cffeps_build_id)s,
    flexpart_build_id = %(flexpart_build_id)s,
    input_manifest_path = %(input_manifest_path)s
WHERE id = %(run_id)s
RETURNING id, gfs_cycle_time, cffeps_build_id, flexpart_build_id, input_manifest_path;
